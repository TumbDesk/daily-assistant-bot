"""Open-Meteo geocoding and weather forecast."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from services.i18n_util import LocalizedError, t, t_list
from services.timezone_util import get_timezone, now

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT = 10.0
RAIN_PROBABILITY_THRESHOLD = 30
INTENSITY_TIER_HIGH = 70
INTENSITY_TIER_MID = 50
FORECAST_DAYS = 7
TREND_DAY_COUNT = 5

WMO_EMOJI: dict[int, str] = {
    0: "☀️",
    1: "🌤️",
    2: "⛅",
    3: "☁️",
    45: "🌫️",
    48: "🌫️",
    51: "🌦️",
    53: "🌦️",
    55: "🌧️",
    61: "🌧️",
    63: "🌧️",
    65: "🌧️",
    71: "🌨️",
    73: "❄️",
    75: "❄️",
    80: "🌦️",
    81: "🌦️",
    82: "🌧️",
    95: "⛈️",
    96: "⛈️",
    99: "⛈️",
}


@dataclass(frozen=True)
class GeoLocation:
    latitude: float
    longitude: float
    name: str


@dataclass(frozen=True)
class RainBlock:
    max_probability: int
    avg_probability: int
    start: datetime
    end: datetime
    hour_count: int = 1

    @property
    def start_time(self) -> str:
        return self.start.strftime("%H:%M")

    @property
    def end_time(self) -> str:
        return self.end.strftime("%H:%M")


@dataclass(frozen=True)
class TodaysWeather:
    observed_at: str
    temperature: float
    apparent_temperature: float
    temperature_min: float
    temperature_max: float
    humidity: int
    wind_speed: float
    weather_code: int
    precipitation_probability: int
    precipitation_sum: float
    rain_blocks: tuple[RainBlock, ...] = ()


@dataclass(frozen=True)
class TomorrowWeather:
    weather_code: int
    temperature_min: float
    temperature_max: float
    precipitation_probability: int
    precipitation_sum: float
    rain_blocks: tuple[RainBlock, ...] = ()


@dataclass(frozen=True)
class TrendDay:
    day: date
    weather_code: int
    temp_min: float
    temp_max: float
    precip_prob: int
    precip_sum: float


class WeatherServiceError(LocalizedError):
    pass


class LocationNotFoundError(WeatherServiceError):
    def __init__(self, query: str) -> None:
        super().__init__("weather_location_not_found", query=query)


def weather_code_label(code: int, locale: str = "de") -> str:
    from services.i18n_util import DEFAULT_LOCALE, t

    key = f"weather_wmo_{code}"
    text = t(key, locale)
    if text == key:
        return t("weather_code_unknown", locale, code=code)
    return text


def weather_code_emoji(code: int) -> str:
    return WMO_EMOJI.get(code, "🌡️")


def format_observed_at(iso_time: str, locale: str = "de") -> str:
    from services.i18n_util import DEFAULT_LOCALE

    observed = datetime.fromisoformat(iso_time)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=get_timezone())
    else:
        observed = observed.astimezone(get_timezone())

    time_part = observed.strftime("%H:%M")
    if observed.date() == now().date():
        return t("weather_observed_today", locale, time=time_part)
    date_part = observed.strftime("%d.%m.")
    return t("weather_observed_date", locale, date=date_part, time=time_part)


def wind_speed_label(speed_kmh: float, locale: str = "de") -> str:
    if speed_kmh < 6:
        return t("weather_wind_calm", locale)
    if speed_kmh <= 19:
        return t("weather_wind_light", locale)
    if speed_kmh <= 38:
        return t("weather_wind_moderate", locale)
    if speed_kmh <= 61:
        return t("weather_wind_strong", locale)
    return t("weather_wind_storm", locale)


def parse_hourly_for_date(
    hourly: dict,
    target_date: date,
    tz: Optional[ZoneInfo] = None,
    *,
    from_hour: Optional[datetime] = None,
) -> list[tuple[datetime, int]]:
    times = hourly.get("time") or []
    probs = hourly.get("precipitation_probability") or []
    if not times or len(times) != len(probs):
        return []

    local_tz = tz or get_timezone()
    result: list[tuple[datetime, int]] = []
    for time_str, prob in zip(times, probs):
        dt = datetime.fromisoformat(str(time_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=local_tz)
        else:
            dt = dt.astimezone(local_tz)
        if dt.date() != target_date:
            continue
        if from_hour is not None and dt < from_hour:
            continue
        result.append((dt, int(prob)))
    return result


def parse_hourly_for_today(
    hourly: dict, tz: Optional[ZoneInfo] = None
) -> list[tuple[datetime, int]]:
    local_tz = tz or get_timezone()
    local_now = datetime.now(local_tz)
    current_hour = local_now.replace(minute=0, second=0, microsecond=0)
    return parse_hourly_for_date(
        hourly,
        local_now.date(),
        tz=local_tz,
        from_hour=current_hour,
    )


def _rain_intensity_tier(prob: int) -> int:
    if prob >= INTENSITY_TIER_HIGH:
        return 3
    if prob >= INTENSITY_TIER_MID:
        return 2
    return 1


def _split_entries_by_intensity(
    entries: list[tuple[datetime, int]],
) -> list[RainBlock]:
    if not entries:
        return []

    segments: list[list[tuple[datetime, int]]] = []
    current = [entries[0]]
    tier = _rain_intensity_tier(entries[0][1])
    for item in entries[1:]:
        if _rain_intensity_tier(item[1]) != tier:
            segments.append(current)
            current = [item]
            tier = _rain_intensity_tier(item[1])
        else:
            current.append(item)
    segments.append(current)
    return [_finalize_rain_block(segment) for segment in segments]


def _merge_short_segments(periods: list[RainBlock]) -> list[RainBlock]:
    if len(periods) <= 1:
        return periods

    merged: list[RainBlock] = []
    index = 0
    while index < len(periods):
        current = periods[index]
        if (
            current.hour_count == 1
            and index + 1 < len(periods)
            and current.avg_probability < periods[index + 1].avg_probability
        ):
            nxt = periods[index + 1]
            merged.append(
                RainBlock(
                    max_probability=max(current.max_probability, nxt.max_probability),
                    avg_probability=round(
                        (
                            current.avg_probability * current.hour_count
                            + nxt.avg_probability * nxt.hour_count
                        )
                        / (current.hour_count + nxt.hour_count)
                    ),
                    start=current.start,
                    end=nxt.end,
                    hour_count=current.hour_count + nxt.hour_count,
                )
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    return merged


def summarize_rain_periods(hours: list[tuple[datetime, int]]) -> list[RainBlock]:
    periods: list[RainBlock] = []
    current: list[tuple[datetime, int]] = []

    for dt, prob in hours:
        if prob >= RAIN_PROBABILITY_THRESHOLD:
            current.append((dt, prob))
            continue
        if current:
            periods.extend(_split_entries_by_intensity(current))
            current = []

    if current:
        periods.extend(_split_entries_by_intensity(current))

    return _merge_short_segments(periods)


def find_rain_blocks(
    hours: list[tuple[datetime, int]],
    threshold: int = RAIN_PROBABILITY_THRESHOLD,
) -> list[RainBlock]:
    blocks: list[RainBlock] = []
    current: list[tuple[datetime, int]] = []

    for dt, prob in hours:
        if prob >= threshold:
            current.append((dt, prob))
            continue
        if current:
            blocks.append(_finalize_rain_block(current))
            current = []

    if current:
        blocks.append(_finalize_rain_block(current))
    return blocks


def _finalize_rain_block(entries: list[tuple[datetime, int]]) -> RainBlock:
    start_dt = entries[0][0]
    end_dt = entries[-1][0] + timedelta(hours=1)
    probs = [prob for _, prob in entries]
    return RainBlock(
        max_probability=max(probs),
        avg_probability=round(sum(probs) / len(probs)),
        start=start_dt,
        end=end_dt,
        hour_count=len(entries),
    )


WOCHENTAGE = tuple(t_list("weekday_names", "de"))


def format_rain_risk_lines(
    max_prob: int,
    blocks: tuple[RainBlock, ...],
    locale: str = "de",
) -> list[str]:
    if max_prob < RAIN_PROBABILITY_THRESHOLD or not blocks:
        return [t("weather_rain_risk_simple", locale, prob=max_prob)]

    lines: list[str] = []
    for block in blocks:
        time_range = t(
            "weather_time_range",
            locale,
            start=block.start_time,
            end=block.end_time,
        )
        if block.max_probability > block.avg_probability + 4:
            lines.append(
                t(
                    "weather_rain_risk_range_avg_max",
                    locale,
                    time_range=time_range,
                    avg=block.avg_probability,
                    max=block.max_probability,
                )
            )
        else:
            lines.append(
                t(
                    "weather_rain_risk_range_avg",
                    locale,
                    time_range=time_range,
                    avg=block.avg_probability,
                )
            )
    return lines


def _api_timezone(data: dict) -> ZoneInfo:
    return ZoneInfo(data.get("timezone", str(get_timezone())))


def _daily_date(data: dict, index: int) -> date:
    daily = data.get("daily") or {}
    times = daily.get("time") or []
    if index >= len(times):
        raise WeatherServiceError("err_weather_no_daily_forecast")
    return date.fromisoformat(str(times[index]))


def parse_todays_weather(data: dict) -> TodaysWeather:
    current = data.get("current")
    daily = data.get("daily")
    if not current or not daily:
        raise WeatherServiceError("err_weather_no_current_data")

    api_tz = _api_timezone(data)
    hours = parse_hourly_for_today(data.get("hourly") or {}, tz=api_tz)
    rain_blocks = tuple(summarize_rain_periods(hours))

    return TodaysWeather(
        observed_at=str(current["time"]),
        temperature=float(current["temperature_2m"]),
        apparent_temperature=float(current["apparent_temperature"]),
        temperature_min=float(daily["temperature_2m_min"][0]),
        temperature_max=float(daily["temperature_2m_max"][0]),
        humidity=int(current["relative_humidity_2m"]),
        wind_speed=float(current["wind_speed_10m"]),
        weather_code=int(current["weather_code"]),
        precipitation_probability=int(daily["precipitation_probability_max"][0]),
        precipitation_sum=float(daily["precipitation_sum"][0]),
        rain_blocks=rain_blocks,
    )


def get_tomorrow_weather(data: dict, location_name: str) -> TomorrowWeather:
    del location_name
    daily = data.get("daily")
    if not daily:
        raise WeatherServiceError("err_weather_no_daily_forecast")

    api_tz = _api_timezone(data)
    tomorrow = _daily_date(data, 1)
    hours = parse_hourly_for_date(data.get("hourly") or {}, tomorrow, tz=api_tz)
    rain_blocks = tuple(summarize_rain_periods(hours))

    return TomorrowWeather(
        weather_code=int(daily["weather_code"][1]),
        temperature_min=float(daily["temperature_2m_min"][1]),
        temperature_max=float(daily["temperature_2m_max"][1]),
        precipitation_probability=int(daily["precipitation_probability_max"][1]),
        precipitation_sum=float(daily["precipitation_sum"][1]),
        rain_blocks=rain_blocks,
    )


def get_five_day_trend(data: dict, location_name: str) -> tuple[TrendDay, ...]:
    del location_name
    daily = data.get("daily")
    if not daily:
        raise WeatherServiceError("err_weather_no_daily_forecast")

    days: list[TrendDay] = []
    for index in range(TREND_DAY_COUNT):
        days.append(
            TrendDay(
                day=_daily_date(data, index),
                weather_code=int(daily["weather_code"][index]),
                temp_min=float(daily["temperature_2m_min"][index]),
                temp_max=float(daily["temperature_2m_max"][index]),
                precip_prob=int(daily["precipitation_probability_max"][index]),
                precip_sum=float(daily["precipitation_sum"][index]),
            )
        )
    return tuple(days)


def format_trend_line(day: TrendDay, locale: str = "de") -> str:
    weekday_names = t_list("weekday_names", locale)
    if len(weekday_names) < 7:
        weekday_names = t_list("weekday_names", "de")
    weekday = weekday_names[day.day.weekday()]
    date_part = day.day.strftime("%d.%m.")
    emoji = weather_code_emoji(day.weather_code)
    return t(
        "weather_trend_line",
        locale,
        weekday=weekday,
        date=date_part,
        emoji=emoji,
        temp_min=f"{day.temp_min:.0f}",
        temp_max=f"{day.temp_max:.0f}",
        precip_prob=day.precip_prob,
        precip_sum=f"{day.precip_sum:.1f}",
    )


class WeatherService:
    async def get_forecast(self, latitude: float, longitude: float) -> dict:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "weather_code,wind_speed_10m"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,precipitation_sum"
            ),
            "hourly": "precipitation_probability",
            "timezone": "auto",
            "forecast_days": FORECAST_DAYS,
        }
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(FORECAST_URL, params=params)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise WeatherServiceError("err_weather_request_failed") from exc

    async def get_todays_weather(
        self, latitude: float, longitude: float
    ) -> TodaysWeather:
        data = await self.get_forecast(latitude, longitude)
        return parse_todays_weather(data)


_weather_service: Optional[WeatherService] = None


def get_weather_service() -> WeatherService:
    global _weather_service
    if _weather_service is None:
        _weather_service = WeatherService()
    return _weather_service


async def geocode_location(query: str) -> GeoLocation:
    params = {"name": query.strip(), "count": 1, "language": "de"}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(GEOCODING_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        raise WeatherServiceError("err_weather_geocoding_failed") from exc

    results = data.get("results") or []
    if not results:
        raise LocationNotFoundError(query)

    first = results[0]
    name = first.get("name", query)
    admin1 = first.get("admin1")
    country = first.get("country")
    parts = [name]
    if admin1:
        parts.append(admin1)
    if country:
        parts.append(country)
    display_name = ", ".join(parts)

    return GeoLocation(
        latitude=float(first["latitude"]),
        longitude=float(first["longitude"]),
        name=display_name,
    )


async def resolve_location(query: str) -> GeoLocation:
    if not query.strip():
        raise LocationNotFoundError(query)
    return await geocode_location(query)
