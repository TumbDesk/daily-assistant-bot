import json
import logging
import os
from datetime import datetime, timedelta
from html import escape
from typing import Any, Dict, Optional, Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from services.event_filter import (
    EventFilterPreset,
    filter_label as build_filter_label,
    month_name,
)
from services.occurrence_util import build_occ_callback, build_view_evt_callback
from services.weather import (
    TodaysWeather,
    TomorrowWeather,
    TrendDay,
    format_observed_at,
    format_rain_risk_lines,
    format_trend_line,
    weather_code_emoji,
    weather_code_label,
    wind_speed_label,
)

logger = logging.getLogger(__name__)

WEATHER_VIEW_TODAY = "today"
WEATHER_VIEW_TOMORROW = "tomorrow"
WEATHER_VIEW_TREND = "trend"

_WEATHER_CALLBACK_PREFIX = {
    WEATHER_VIEW_TODAY: "wetter_heute",
    WEATHER_VIEW_TOMORROW: "wetter_morgen",
    WEATHER_VIEW_TREND: "wetter_trend",
}

_WEATHER_CALLBACK_TO_VIEW = {v: k for k, v in _WEATHER_CALLBACK_PREFIX.items()}


class MessageFactory:
    _TRANSLATIONS: Dict[str, Dict[str, str]] = {}
    DEFAULT_LOCALE = "de"
    LOCALES_DIR = "locales"

    @classmethod
    def load_locales(cls):
        """Load all JSON files from the locales folder into memory."""
        from services import i18n_util

        i18n_util.load_locales()
        cls._TRANSLATIONS = i18n_util._TRANSLATIONS

    @staticmethod
    def _text_value(value: Any) -> str:
        if isinstance(value, list):
            return "\n".join(str(line) for line in value)
        if value is None:
            return ""
        return str(value)

    @classmethod
    def _t_list(cls, key: str, locale: str = "de") -> list[str]:
        from services.i18n_util import t_list

        return t_list(key, locale)

    @classmethod
    def _t(cls, key: str, locale: str = "de", **kwargs: Any) -> str:
        from services.i18n_util import t

        return t(key, locale, **kwargs)

    _PREDEFINED_REMINDER_KEYS = {
        15: "reminder_15_min",
        60: "reminder_1_hour",
        1440: "reminder_1_day",
    }

    RECURRING_LABELS = {
        False: "",
        True: "Serie",
    }

    @classmethod
    def welcome(cls, locale: str = "de") -> str:
        return cls._t("welcome", locale)

    @classmethod
    def help_text(cls, locale: str = "de") -> str:
        return cls._t("help_text", locale)

    @staticmethod
    def _bool_icon(value: bool) -> str:
        return "✅" if value else "❌"

    @classmethod
    def settings_overview(cls, settings, locale: str = "de") -> str:
        from services.locale_service import locale_label

        language_name = locale_label(locale)
        return (
            f"{cls._t('settings_header', locale)}\n\n"
            f"{cls._bool_icon(settings.report_enabled)} {cls._t('settings_report', locale)}\n"
            f"🕐 {cls._t('settings_time', locale)}: {settings.report_time}\n"
            f"{cls._bool_icon(settings.include_events)} {cls._t('settings_events', locale)}\n"
            f"{cls._bool_icon(settings.include_birthdays)} {cls._t('settings_birthdays', locale)}\n"
            f"{cls._bool_icon(settings.include_weather)} {cls._t('settings_weather', locale)}\n"
            f"🌐 {cls._t('settings_language', locale)}: {language_name}"
        )

    @classmethod
    def settings_keyboard(cls, settings, locale: str = "de") -> InlineKeyboardMarkup:
        from services.locale_service import list_supported_locales, locale_label

        language_buttons = [
            InlineKeyboardButton(
                f"{'✅ ' if code == locale else ''}{locale_label(code)}",
                callback_data=f"settings:lang:{code}",
            )
            for code in list_supported_locales()
        ]
        rows = [
            [
                InlineKeyboardButton(
                    cls._t("btn_report_toggle", locale),
                    callback_data="settings:toggle:report_enabled",
                ),
            ],
            [
                InlineKeyboardButton("◀", callback_data="settings:time:prev"),
                InlineKeyboardButton(cls._t("btn_time", locale), callback_data="settings:noop"),
                InlineKeyboardButton("▶", callback_data="settings:time:next"),
            ],
            [
                InlineKeyboardButton(
                    cls._t("btn_events", locale),
                    callback_data="settings:toggle:include_events",
                ),
                InlineKeyboardButton(
                    cls._t("btn_birthdays", locale),
                    callback_data="settings:toggle:include_birthdays",
                ),
            ],
            [
                InlineKeyboardButton(
                    cls._t("btn_weather", locale),
                    callback_data="settings:toggle:include_weather",
                ),
            ],
        ]
        for index in range(0, len(language_buttons), 2):
            rows.append(language_buttons[index : index + 2])
        return InlineKeyboardMarkup(rows)

    @classmethod
    def geburtstag_success(cls, name: str, birth_date, locale: str = "de") -> str:
        return cls._t(
            "birthday_success",
            locale,
            name=name,
            date=birth_date.strftime("%d.%m.%Y"),
        )

    @classmethod
    def agenda_usage_geburtstag(cls, locale: str = "de") -> str:
        return cls._t("agenda_usage_geburtstag", locale)

    @classmethod
    def birthdays_list_header(cls, locale: str = "de") -> str:
        return cls._t("birthdays_list_header", locale)

    @classmethod
    def birthdays_empty(cls, locale: str = "de") -> str:
        return cls._t("birthdays_empty", locale)

    @staticmethod
    def birthday_turning_age(birth_date, *, on_date=None) -> int:
        """Age the person will reach on their next birthday."""
        from services.timezone_util import now

        today = on_date or now().date()
        age = today.year - birth_date.year
        if (today.month, today.day) > (birth_date.month, birth_date.day):
            age += 1
        return age

    @classmethod
    def birthday_list_button_label(cls, birthday, locale: str = "de") -> str:
        age = cls.birthday_turning_age(birthday.birth_date)
        return cls._t(
            "birthday_list_button",
            locale,
            day_month=birthday.birth_date.strftime("%d.%m."),
            name=birthday.name,
            age=age,
        )

    @classmethod
    def create_birthdays_view(
        cls, birthdays: Sequence, locale: str = "de"
    ) -> tuple[str, InlineKeyboardMarkup]:
        if not birthdays:
            text = cls.birthdays_empty(locale)
        else:
            text = cls.birthdays_list_header(locale)
        rows: list[list[InlineKeyboardButton]] = []
        for birthday in birthdays:
            rows.append(
                [
                    InlineKeyboardButton(
                        cls.birthday_list_button_label(birthday, locale),
                        callback_data=f"view_bday_{birthday.id}",
                    )
                ]
            )
        return text, InlineKeyboardMarkup(rows)

    @classmethod
    def birthday_detail_text(cls, birthday, locale: str = "de") -> str:
        from services.timezone_util import now

        today = now().date()
        age = today.year - birthday.birth_date.year
        if (today.month, today.day) < (
            birthday.birth_date.month,
            birthday.birth_date.day,
        ):
            age -= 1
        return cls._t(
            "birthday_detail_text",
            locale,
            name=birthday.name,
            birth_date=birthday.birth_date.strftime("%d.%m.%Y"),
            age=age,
        )

    @classmethod
    def create_birthday_detail_keyboard(
        cls, birthday_id: int, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_name", locale),
                        callback_data=f"edit_bday_name_{birthday_id}",
                    ),
                    InlineKeyboardButton(
                        cls._t("btn_edit_date", locale),
                        callback_data=f"edit_bday_date_{birthday_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_delete", locale),
                        callback_data=f"del_bday_{birthday_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back_to_list", locale),
                        callback_data="list_birthdays",
                    ),
                ],
            ]
        )

    @classmethod
    def birthday_not_found(cls, locale: str = "de") -> str:
        return cls._t("birthday_not_found", locale)

    @classmethod
    def birthday_updated(cls, locale: str = "de") -> str:
        return cls._t("birthday_updated", locale)

    @classmethod
    def birthday_deleted(cls, locale: str = "de") -> str:
        return cls._t("birthday_deleted", locale)

    @classmethod
    def birthday_duplicate(cls, locale: str = "de") -> str:
        return cls._t("birthday_duplicate", locale)

    @classmethod
    def conversation_edit_birthday_name(cls, locale: str = "de") -> str:
        return cls._t("conversation_edit_birthday_name", locale)

    @classmethod
    def conversation_edit_birthday_date(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_birthday_date", locale, current=current)

    @classmethod
    def trips_list_header(cls, locale: str = "de") -> str:
        return cls._t("trips_list_header", locale)

    @classmethod
    def trips_empty(cls, locale: str = "de") -> str:
        return cls._t("trips_empty", locale)

    @classmethod
    def trip_list_button_label(cls, trip, locale: str = "de") -> str:
        start = trip.start_date.strftime("%d.%m.")
        end = trip.end_date.strftime("%d.%m.")
        return cls._t(
            "trip_list_button",
            locale,
            start=start,
            end=end,
            destination=trip.destination,
        )

    @classmethod
    def create_trips_view(
        cls, trips: Sequence, locale: str = "de"
    ) -> tuple[str, InlineKeyboardMarkup]:
        if not trips:
            text = cls.trips_empty(locale)
        else:
            text = cls.trips_list_header(locale)
        rows: list[list[InlineKeyboardButton]] = []
        for trip in trips:
            rows.append(
                [
                    InlineKeyboardButton(
                        cls.trip_list_button_label(trip, locale),
                        callback_data=f"view_trip_{trip.id}",
                    )
                ]
            )
        return text, InlineKeyboardMarkup(rows)

    @classmethod
    def trip_detail_text(cls, trip, locale: str = "de") -> str:
        from services.timezone_util import now

        today = now().date()
        active = trip.start_date <= today <= trip.end_date
        lines = [
            cls._t("trip_detail_header", locale, destination=trip.destination),
            cls._t(
                "trip_detail_period",
                locale,
                start_date=trip.start_date.strftime("%d.%m.%Y"),
                end_date=trip.end_date.strftime("%d.%m.%Y"),
            ),
        ]
        if active:
            lines.append(cls._t("trip_detail_status_active", locale))
        return "\n".join(lines)

    @classmethod
    def create_trip_detail_keyboard(
        cls, trip_id: int, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_location", locale),
                        callback_data=f"edit_trip_dest_{trip_id}",
                    ),
                    InlineKeyboardButton(
                        cls._t("btn_edit_period", locale),
                        callback_data=f"edit_trip_dates_{trip_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_delete", locale),
                        callback_data=f"del_trip_{trip_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back_to_list", locale),
                        callback_data="list_trips",
                    ),
                ],
            ]
        )

    @classmethod
    def trip_not_found(cls, locale: str = "de") -> str:
        return cls._t("trip_not_found", locale)

    @classmethod
    def conversation_edit_trip_destination(cls, locale: str = "de") -> str:
        return cls._t("conversation_edit_trip_destination", locale)

    @classmethod
    def conversation_edit_trip_dates(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_trip_dates", locale, current=current)

    @classmethod
    def reise_usage(cls, locale: str = "de") -> str:
        return cls._t("reise_usage", locale)

    @classmethod
    def reise_success(
        cls, destination: str, start_date, end_date, locale: str = "de"
    ) -> str:
        return cls._t(
            "reise_success",
            locale,
            destination=destination,
            start_date=start_date.strftime("%d.%m.%Y"),
            end_date=end_date.strftime("%d.%m.%Y"),
        )

    @classmethod
    def agenda_parse_error(cls, message_or_exc, locale: str = "de") -> str:
        from services.i18n_util import LocalizedError, localized_message

        if isinstance(message_or_exc, LocalizedError):
            message = localized_message(message_or_exc, locale)
        elif isinstance(message_or_exc, BaseException):
            message = str(message_or_exc)
        else:
            message = message_or_exc
        return cls._t("agenda_parse_error", locale, message=message)

    @classmethod
    def localized_exception_message(cls, exc: BaseException, locale: str = "de") -> str:
        from services.i18n_util import localized_message

        return localized_message(exc, locale)

    @classmethod
    def weather_forecast(
        cls,
        location_name: str,
        weather: TodaysWeather,
        locale: str = "de",
    ) -> str:
        safe_name = escape(location_name)
        condition = escape(weather_code_label(weather.weather_code, locale=locale))
        wind_desc = escape(wind_speed_label(weather.wind_speed, locale=locale))
        stand = escape(format_observed_at(weather.observed_at, locale=locale))
        rain_lines = format_rain_risk_lines(
            weather.precipitation_probability,
            weather.rain_blocks,
            locale=locale,
        )
        rain_section = "\n".join(f"• {escape(line)}" for line in rain_lines)
        temp_span = cls._t(
            "weather_temp_span",
            locale,
            min_temperature=f"{weather.temperature_min:.0f}",
            max_temperature=f"{weather.temperature_max:.0f}",
        )

        lines = [
            cls._t("weather_header", locale, location_name=safe_name),
            f"<i>{stand}</i>",
            "",
            f"{weather_code_emoji(weather.weather_code)} {condition}",
            cls._t("weather_details_header", locale),
            cls._t(
                "weather_temperature_line",
                locale,
                temperature=f"{weather.temperature:.1f}",
                apparent_temperature=f"{weather.apparent_temperature:.1f}",
            ),
            cls._t("weather_humidity_line", locale, humidity=weather.humidity),
            cls._t(
                "weather_wind_line",
                locale,
                wind_speed=f"{weather.wind_speed:.1f}",
                wind_desc=wind_desc,
            ),
            "",
            cls._t("weather_outlook_today_header", locale),
            temp_span,
            rain_section,
            cls._t(
                "weather_precipitation_sum_line",
                locale,
                precipitation_sum=f"{weather.precipitation_sum:.1f}",
            ),
        ]
        return "\n".join(lines)

    @classmethod
    def weather_tomorrow(
        cls,
        location_name: str,
        weather: TomorrowWeather,
        locale: str = "de",
    ) -> str:
        safe_name = escape(location_name)
        condition = escape(weather_code_label(weather.weather_code, locale=locale))
        rain_lines = format_rain_risk_lines(
            weather.precipitation_probability,
            weather.rain_blocks,
            locale=locale,
        )
        rain_section = "\n".join(f"• {escape(line)}" for line in rain_lines)

        lines = [
            cls._t("weather_header", locale, location_name=safe_name),
            cls._t("weather_tomorrow_label", locale),
            "",
            f"{weather_code_emoji(weather.weather_code)} {condition}",
            cls._t("weather_details_header", locale),
            cls._t(
                "weather_tomorrow_temperature_line",
                locale,
                min_temperature=f"{weather.temperature_min:.1f}",
                max_temperature=f"{weather.temperature_max:.1f}",
            ),
            "",
            cls._t("weather_outlook_tomorrow_header", locale),
            rain_section,
            cls._t(
                "weather_precipitation_sum_line",
                locale,
                precipitation_sum=f"{weather.precipitation_sum:.1f}",
            ),
        ]
        return "\n".join(lines)

    @classmethod
    def weather_five_day_trend(
        cls,
        location_name: str,
        days: Sequence[TrendDay],
        locale: str = "de",
    ) -> str:
        safe_name = escape(location_name)
        trend_lines: list[str] = []
        for day in days:
            trend_lines.append(format_trend_line(day, locale=locale))

        return "\n".join(
            [
                cls._t("weather_header", locale, location_name=safe_name),
                cls._t("weather_five_day_trend_label", locale),
                "",
                "\n".join(trend_lines),
            ]
        )

    @staticmethod
    def encode_weather_callback(
        view: str,
        latitude: float,
        longitude: float,
        location_name: str,
    ) -> str:
        prefix = _WEATHER_CALLBACK_PREFIX[view]
        base = f"{prefix}:{latitude:.4f},{longitude:.4f}:"
        max_name_bytes = 64 - len(base.encode("utf-8"))
        if max_name_bytes <= 0:
            return base.rstrip(":")

        encoded_name = location_name.encode("utf-8")[:max_name_bytes].decode(
            "utf-8", errors="ignore"
        )
        return f"{base}{encoded_name}"

    @staticmethod
    def parse_weather_callback(
        data: str,
    ) -> Optional[tuple[str, float, float, str]]:
        if ":" not in data:
            return None

        prefix, rest = data.split(":", 1)
        view = _WEATHER_CALLBACK_TO_VIEW.get(prefix)
        if view is None or ":" not in rest:
            return None

        coords_part, location_name = rest.split(":", 1)
        if "," not in coords_part:
            return None

        lat_str, lon_str = coords_part.split(",", 1)
        try:
            latitude = float(lat_str)
            longitude = float(lon_str)
        except ValueError:
            return None

        return view, latitude, longitude, location_name

    @classmethod
    def weather_view_keyboard(
        cls,
        view: str,
        location_name: str,
        latitude: float,
        longitude: float,
        locale: str = "de",
    ) -> InlineKeyboardMarkup:
        encode = cls.encode_weather_callback

        if view == WEATHER_VIEW_TODAY:
            buttons = [
                InlineKeyboardButton(
                    cls._t("weather_btn_tomorrow", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TOMORROW, latitude, longitude, location_name
                    ),
                ),
                InlineKeyboardButton(
                    cls._t("weather_btn_trend", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TREND, latitude, longitude, location_name
                    ),
                ),
            ]
        elif view == WEATHER_VIEW_TOMORROW:
            buttons = [
                InlineKeyboardButton(
                    cls._t("weather_btn_today", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TODAY, latitude, longitude, location_name
                    ),
                ),
                InlineKeyboardButton(
                    cls._t("weather_btn_trend", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TREND, latitude, longitude, location_name
                    ),
                ),
            ]
        else:
            buttons = [
                InlineKeyboardButton(
                    cls._t("weather_btn_today", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TODAY, latitude, longitude, location_name
                    ),
                ),
                InlineKeyboardButton(
                    cls._t("weather_btn_tomorrow", locale),
                    callback_data=encode(
                        WEATHER_VIEW_TOMORROW, latitude, longitude, location_name
                    ),
                ),
            ]

        return InlineKeyboardMarkup([buttons])

    @classmethod
    def weather_ask_home(cls, locale: str = "de") -> str:
        return cls._t("weather_ask_home", locale)

    @classmethod
    def weather_location_not_found(cls, query: str, locale: str = "de") -> str:
        return cls._t("weather_location_not_found", locale, query=query)

    @classmethod
    def weather_api_error(cls, locale: str = "de") -> str:
        return cls._t("weather_api_error", locale)

    @classmethod
    def weather_rain_alert(
        cls, location_name: str, rain_lines: list[str], locale: str = "de"
    ) -> str:
        lines = "\n".join(f"• {line}" for line in rain_lines)
        return cls._t("weather_rain_alert", locale, location_name=location_name, lines=lines)

    @classmethod
    def set_home_usage(cls, locale: str = "de") -> str:
        return cls._t("set_home_usage", locale)

    @classmethod
    def set_home_success(cls, location_name: str, locale: str = "de") -> str:
        return cls._t("set_home_success", locale, location_name=location_name)

    @classmethod
    def access_denied(cls, locale: str = "de") -> str:
        return cls._t("access_denied", locale)

    @classmethod
    def my_id(cls, user_id: int, locale: str = "de") -> str:
        return cls._t("my_id", locale, user_id=user_id)

    @classmethod
    def conversation_ask_title(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_title", locale)

    @classmethod
    def conversation_ask_date(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_date", locale)

    @classmethod
    def conversation_ask_time(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_time", locale)

    @classmethod
    def conversation_ask_recurring(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_recurring", locale)

    @classmethod
    def conversation_ask_weekday(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_weekday", locale)

    @classmethod
    def conversation_ask_position(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_position", locale)

    @classmethod
    def conversation_ask_recur_until(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_recur_until", locale)

    @classmethod
    def conversation_ask_until_date(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_until_date", locale)

    @classmethod
    def conversation_ask_reminder(cls, locale: str = "de") -> str:
        return cls._t("conversation_ask_reminder", locale)

    @classmethod
    def conversation_edit_title(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_title", locale, current=current)

    @classmethod
    def conversation_edit_date(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_date", locale, current=current)

    @classmethod
    def conversation_edit_time(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_time", locale, current=current)

    @classmethod
    def conversation_cancelled(cls, locale: str = "de") -> str:
        return cls._t("conversation_cancelled", locale)
    
    @classmethod
    def conversation_title_empty(cls, locale: str = "de") -> str:
        return cls._t("conversation_title_empty", locale)

    @classmethod
    def parse_error(cls, field: str, locale: str = "de") -> str:
        return cls._t("parse_error", locale, field=field)

    @classmethod
    def termin_parse_error(cls, message_or_exc, locale: str = "de") -> str:
        from services.i18n_util import LocalizedError, localized_message

        if isinstance(message_or_exc, LocalizedError):
            message = localized_message(message_or_exc, locale)
        elif isinstance(message_or_exc, BaseException):
            message = str(message_or_exc)
        else:
            message = message_or_exc
        return cls._t("termin_parse_error", locale, message=message)

    @classmethod
    def format_event_when(
        cls,
        start: datetime,
        end: datetime,
        is_all_day: bool,
        *,
        short: bool = False,
        locale: str = "de",
    ) -> str:
        if is_all_day:
            if start.date() == end.date():
                label = start.strftime("%d.%m.%Y")
                if short:
                    return label
                return cls._t("event_when_all_day_single", locale, date=label)
            if short:
                return f"{start.strftime('%d.%m.')}–{end.strftime('%d.%m.')}"
            return cls._t(
                "event_when_all_day_range",
                locale,
                start_date=start.strftime("%d.%m.%Y"),
                end_date=end.strftime("%d.%m.%Y"),
            )
        if start.date() == end.date():
            if short:
                return f"{start.strftime('%H:%M')}–{end.strftime('%H:%M')}"
            return cls._t(
                "event_when_same_day",
                locale,
                date=start.strftime("%d.%m.%Y"),
                start_time=start.strftime("%H:%M"),
                end_time=end.strftime("%H:%M"),
            )
        if short:
            return (
                f"{start.strftime('%d.%m. %H:%M')}–{end.strftime('%d.%m. %H:%M')}"
            )
        return cls._t(
            "event_when_multi_day",
            locale,
            start=start.strftime("%d.%m.%Y %H:%M"),
            end=end.strftime("%d.%m.%Y %H:%M"),
        )

    @classmethod
    def format_reminder_offset(cls, reminder_offset: int, locale: str = "de") -> str:
        if reminder_offset <= 0:
            return ""
        key = cls._PREDEFINED_REMINDER_KEYS.get(reminder_offset)
        if key:
            return cls._t(key, locale)
        if reminder_offset % (24 * 60) == 0:
            days = reminder_offset // (24 * 60)
            if days == 1:
                return cls._t("reminder_1_day", locale)
            return cls._t("reminder_days_before", locale, days=days)
        if reminder_offset % 60 == 0:
            hours = reminder_offset // 60
            if hours == 1:
                return cls._t("reminder_1_hour", locale)
            return cls._t("reminder_hours_before", locale, hours=hours)
        return cls._t("reminder_minutes_before", locale, minutes=reminder_offset)

    @classmethod
    def termin_parsed_success(
        cls,
        title: str,
        starts_at: datetime,
        is_recurring: bool = False,
        rrule: Optional[str] = None,
        reminder_offset: int = 0,
        *,
        ends_at: Optional[datetime] = None,
        is_all_day: bool = False,
        category_name: Optional[str] = None,
        flag_names: Optional[Sequence[str]] = None,
        locale: str = "de",
    ) -> str:
        from services.calendar_service import recurrence_label

        end = ends_at if ends_at is not None else starts_at + timedelta(hours=1)
        when = cls.format_event_when(starts_at, end, is_all_day, locale=locale)
        lines = [
            cls._t("event_parsed_success_header", locale),
            cls._t("event_label_title", locale, title=title),
            cls._t("event_label_when", locale, when=when),
        ]
        if category_name:
            lines.append(
                cls._t("event_label_category", locale, category_name=category_name)
            )
        if flag_names:
            lines.append(
                cls._t("event_label_flags", locale, flag_names=", ".join(flag_names))
            )
        if is_recurring and rrule:
            label = recurrence_label(rrule, locale=locale)
            lines.append(cls._t("event_label_series", locale, series_label=label))
        reminder_label = cls.format_reminder_offset(reminder_offset, locale=locale)
        if reminder_label:
            lines.append(
                cls._t("event_label_reminder", locale, reminder_label=reminder_label)
            )
        return "\n".join(lines)

    @classmethod
    def category_pick_prompt(cls, locale: str = "de") -> str:
        return cls._t("category_pick_prompt", locale)

    @classmethod
    def category_assigned(
        cls, title: str, category_name: str, locale: str = "de"
    ) -> str:
        return cls._t(
            "category_assigned",
            locale,
            title=title,
            category_name=category_name,
        )

    @classmethod
    def category_skipped(cls, title: str, locale: str = "de") -> str:
        return cls._t("category_skipped", locale, title=title)

    @classmethod
    def _recurring_suffix(
        cls, is_recurring: bool, rrule: Optional[str], locale: str = "de"
    ) -> str:
        from services.calendar_service import recurrence_label

        if not is_recurring or not rrule:
            return ""
        label = recurrence_label(rrule, locale=locale)
        return cls._t("event_detail_series_suffix", locale, series_label=label) if label else ""

    @classmethod
    def _reminder_suffix(cls, reminder_offset: int, locale: str = "de") -> str:
        label = cls.format_reminder_offset(reminder_offset, locale=locale)
        if not label:
            return ""
        return cls._t("reminder_suffix", locale, label=label)

    @classmethod
    def event_created(
        cls,
        title: str,
        starts_at: datetime,
        is_recurring: bool = False,
        rrule: Optional[str] = None,
        reminder_offset: int = 0,
        *,
        ends_at: Optional[datetime] = None,
        is_all_day: bool = False,
        locale: str = "de",
    ) -> str:
        end = ends_at if ends_at is not None else starts_at + timedelta(hours=1)
        formatted = cls.format_event_when(
            starts_at, end, is_all_day, locale=locale
        )
        suffix = cls._recurring_suffix(is_recurring, rrule, locale=locale)
        reminder = cls._reminder_suffix(reminder_offset, locale=locale)
        return cls._t(
            "event_created",
            locale,
            title=title,
            when=formatted,
            suffix=suffix,
            reminder=reminder,
        )

    @classmethod
    def reminder_notification(
        cls, title: str, occurrence_at: datetime, locale: str = "de"
    ) -> str:
        date_part = occurrence_at.strftime("%d.%m.%Y")
        time_part = occurrence_at.strftime("%H:%M")
        return cls._t(
            "reminder_notification",
            locale,
            title=title,
            date=date_part,
            time=time_part,
        )

    @classmethod
    def events_empty(cls, locale: str = "de") -> str:
        return cls._t("events_empty", locale)

    @classmethod
    def filter_label(
        cls,
        preset: EventFilterPreset,
        year: Optional[int] = None,
        month: Optional[int] = None,
        month_offset: Optional[int] = None,
        locale: str = "de",
    ) -> str:
        return build_filter_label(
            preset, year=year, month=month, month_offset=month_offset, locale=locale
        )

    @classmethod
    def events_empty_filtered(cls, filter_label: str, locale: str = "de") -> str:
        return cls._t("events_empty_filtered", locale, filter_label=filter_label)

    @classmethod
    def termine_usage(cls, locale: str = "de") -> str:
        return cls._t("termine_usage", locale)

    @classmethod
    def termine_filter_keyboard(
        cls,
        active: EventFilterPreset,
        *,
        active_year: Optional[int] = None,
        active_month: Optional[int] = None,
        active_offset: Optional[int] = None,
        locale: str = "de",
    ) -> InlineKeyboardMarkup:
        def mark(text: str, is_active: bool) -> str:
            return f"· {text}" if is_active else text

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        mark(cls._t("filter_today", locale), active == EventFilterPreset.TODAY),
                        callback_data="termfilter:today",
                    ),
                    InlineKeyboardButton(
                        mark(
                            cls._t("filter_this_week", locale),
                            active == EventFilterPreset.THIS_WEEK,
                        ),
                        callback_data="termfilter:this_week",
                    ),
                    InlineKeyboardButton(
                        mark(
                            cls._t("filter_next_week", locale),
                            active == EventFilterPreset.NEXT_WEEK,
                        ),
                        callback_data="termfilter:next_week",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        mark(cls._t("filter_future", locale), active == EventFilterPreset.FUTURE),
                        callback_data="termfilter:future",
                    ),
                    InlineKeyboardButton(
                        cls._t("filter_pick_month", locale),
                        callback_data="termfilter:pick:month",
                    ),
                    InlineKeyboardButton(
                        cls._t("filter_pick_year", locale),
                        callback_data="termfilter:pick:year",
                    ),
                ],
            ]
        )

    @classmethod
    def month_picker_keyboard(
        cls, picker_year: int, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        def off_btn(label: str, offset: int) -> InlineKeyboardButton:
            return InlineKeyboardButton(
                label, callback_data=f"termfilter:mo:{offset}"
            )

        month_rows = []
        for row_start in (1, 5, 9):
            row = []
            for m in range(row_start, row_start + 4):
                row.append(
                    InlineKeyboardButton(
                        month_name(m),
                        callback_data=f"termfilter:m:{picker_year}:{m}",
                    )
                )
            month_rows.append(row)

        return InlineKeyboardMarkup(
            [
                [
                    off_btn(cls._t("btn_this_month", locale), 0),
                    off_btn(cls._t("btn_next_month", locale), 1),
                    off_btn(cls._t("btn_month_after_next", locale), 2),
                ],
                [
                    InlineKeyboardButton("‹", callback_data=f"termfilter:my:{picker_year - 1}"),
                    InlineKeyboardButton(str(picker_year), callback_data=f"termfilter:my:{picker_year}"),
                    InlineKeyboardButton("›", callback_data=f"termfilter:my:{picker_year + 1}"),
                ],
                *month_rows,
                [
                    InlineKeyboardButton(
                        cls._t("btn_back", locale), callback_data="termfilter:future"
                    ),
                ],
            ]
        )

    @classmethod
    def year_picker_keyboard(
        cls, center_year: int, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        years = [center_year - 1, center_year, center_year + 1]
        year_buttons = [
            InlineKeyboardButton(str(y), callback_data=f"termfilter:y:{y}")
            for y in years
        ]

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "‹", callback_data=f"termfilter:yy:{center_year - 3}"
                    ),
                    *year_buttons,
                    InlineKeyboardButton(
                        "›", callback_data=f"termfilter:yy:{center_year + 3}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back", locale), callback_data="termfilter:future"
                    ),
                ],
            ]
        )

    @classmethod
    def month_picker_text(cls, picker_year: int, locale: str = "de") -> str:
        return cls._t("month_picker_text", locale, year=picker_year)

    @classmethod
    def year_picker_text(cls, center_year: int, locale: str = "de") -> str:
        return cls._t("year_picker_text", locale, year=center_year)

    @classmethod
    def events_list_header(
        cls, filter_label: Optional[str] = None, locale: str = "de"
    ) -> str:
        if filter_label:
            return cls._t(
                "events_list_header_filtered",
                locale,
                filter_label=filter_label,
            )
        return cls._t("events_list_header", locale)

    @staticmethod
    def _truncate_source_label(source_label: str, max_len: int) -> str:
        if len(source_label) <= max_len:
            return source_label
        if max_len < 2:
            return source_label[:max_len]
        return source_label[: max_len - 1] + "…"

    @staticmethod
    def format_source_suffix(source_label: str, locale: str = "de") -> str:
        from services.source_label import display_source_label

        display = display_source_label(source_label, locale)
        return f" 👥 ({display[:8]})"

    @classmethod
    def _event_list_button_label(
        cls, event, *, source_label: str | None = None, locale: str = "de"
    ) -> str:
        when = event.list_starts_at
        end_dt = event.occurrence_ends_at or event.ends_at
        if getattr(event, "occurrence_is_moved", False):
            emoji = "↪️"
        elif event.is_recurring:
            emoji = "🔄"
        else:
            emoji = "📅"
        if getattr(event, "is_all_day", False):
            when_label = cls.format_event_when(
                when, end_dt, True, short=True, locale=locale
            )
        elif when.date() == end_dt.date():
            when_label = (
                f"{when.strftime('%d.%m.')} "
                f"{when.strftime('%H:%M')}–{end_dt.strftime('%H:%M')}"
            )
        else:
            when_label = cls.format_event_when(
                when, end_dt, False, short=True, locale=locale
            )
        source_suffix = (
            cls.format_source_suffix(source_label, locale=locale)
            if source_label
            else ""
        )
        prefix = f"{emoji} {when_label} – "
        max_title_len = 64 - len(prefix) - len(source_suffix)
        title = event.title
        if max_title_len < 1:
            return (prefix + title + source_suffix)[:64]
        if len(title) > max_title_len:
            title = title[: max_title_len - 1] + "…"
        return f"{prefix}{title}{source_suffix}"

    @classmethod
    def _mark_active(cls, text: str, key: str, active: Optional[str]) -> str:
        return f"· {text}" if active == key else text

    @classmethod
    def _filter_scope_row(
        cls, active_filter: str, locale: str = "de"
    ) -> list[InlineKeyboardButton]:
        return [
            InlineKeyboardButton(
                cls._mark_active(cls._t("filter_all", locale), "all", active_filter),
                callback_data="filter_all",
            ),
            InlineKeyboardButton(
                cls._mark_active(
                    cls._t("filter_future", locale), "future", active_filter
                ),
                callback_data="filter_future",
            ),
            InlineKeyboardButton(
                cls._mark_active(
                    cls._t("filter_recurring", locale), "recurring", active_filter
                ),
                callback_data="filter_recurring",
            ),
        ]

    @classmethod
    def _filter_period_rows(
        cls, active_period: Optional[str], locale: str = "de"
    ) -> list[list[InlineKeyboardButton]]:
        return [
            [
                InlineKeyboardButton(
                    cls._mark_active(cls._t("filter_today", locale), "today", active_period),
                    callback_data="termfilter:today",
                ),
                InlineKeyboardButton(
                    cls._mark_active(
                        cls._t("filter_this_week", locale), "this_week", active_period
                    ),
                    callback_data="termfilter:this_week",
                ),
                InlineKeyboardButton(
                    cls._mark_active(
                        cls._t("filter_next_week", locale), "next_week", active_period
                    ),
                    callback_data="termfilter:next_week",
                ),
            ],
            [
                InlineKeyboardButton(
                    cls._mark_active(
                        cls._t("filter_pick_month_year", locale),
                        "month_year",
                        active_period,
                    ),
                    callback_data="termfilter:pick:month",
                ),
            ],
        ]

    @classmethod
    def create_events_view(
        cls,
        events: Sequence,
        *,
        active_filter: str,
        active_period: Optional[str] = None,
        view_context_chat_id: int | None = None,
        locale: str = "de",
    ) -> tuple[str, InlineKeyboardMarkup]:
        from services.user_service import event_source_label
        rows: list[list[InlineKeyboardButton]] = [
            cls._filter_scope_row(active_filter, locale),
            *cls._filter_period_rows(active_period, locale),
            [
                InlineKeyboardButton(
                    "[ ────────✨✨✨──────── ]", callback_data="noop"
                )
            ],
        ]
        for event in events:
            occ_start = event.occurrence_original_start
            if event.is_recurring and occ_start is not None:
                callback = build_view_evt_callback(event.id, occ_start)
            elif event.is_recurring and event.display_starts_at is not None:
                callback = build_view_evt_callback(event.id, event.display_starts_at)
            else:
                callback = build_view_evt_callback(event.id)
            source_label = None
            if view_context_chat_id is not None:
                source_label = event_source_label(
                    event.context_chat_id, view_context_chat_id
                )
            rows.append(
                [
                    InlineKeyboardButton(
                        cls._event_list_button_label(
                            event, source_label=source_label, locale=locale
                        ),
                        callback_data=callback,
                    )
                ]
            )
        text = cls.events_list_header(locale=locale)
        return text, InlineKeyboardMarkup(rows)

    @classmethod
    def create_events_view_empty(
        cls,
        *,
        active_filter: str,
        filter_label: str,
        active_period: Optional[str] = None,
        locale: str = "de",
    ) -> tuple[str, InlineKeyboardMarkup]:
        text = cls.events_empty_filtered(filter_label, locale)
        _, keyboard = cls.create_events_view(
            [], active_filter=active_filter, active_period=active_period, locale=locale
        )
        return text, keyboard

    @classmethod
    def _event_button_label(cls, event, *, locale: str = "de") -> str:
        return cls._event_list_button_label(event, locale=locale)

    @classmethod
    def events_list_keyboard(
        cls,
        events: Sequence,
        filter_keyboard: InlineKeyboardMarkup,
        *,
        locale: str = "de",
    ) -> InlineKeyboardMarkup:
        """Legacy: month/year picker with event rows."""
        rows = list(filter_keyboard.inline_keyboard)
        for event in events:
            occ_start = event.occurrence_original_start
            if event.is_recurring and occ_start is not None:
                callback = build_view_evt_callback(event.id, occ_start)
            elif event.is_recurring and event.display_starts_at is not None:
                callback = build_view_evt_callback(event.id, event.display_starts_at)
            else:
                callback = build_view_evt_callback(event.id)
            rows.append(
                [
                    InlineKeyboardButton(
                        cls._event_list_button_label(event, locale=locale),
                        callback_data=callback,
                    )
                ]
            )
        return InlineKeyboardMarkup(rows)

    @classmethod
    def events_empty_list_keyboard(
        cls,
        filter_keyboard: InlineKeyboardMarkup,
    ) -> InlineKeyboardMarkup:
        return filter_keyboard

    @classmethod
    def event_detail_text(
        cls,
        event,
        *,
        occurrence_start=None,
        occurrence_end=None,
        occurrence_is_moved: bool = False,
        occurrence_original_start=None,
        source_label: str | None = None,
        locale: str = "de",
    ) -> str:
        start = occurrence_start or event.starts_at
        end = occurrence_end or event.ends_at
        when = cls.format_event_when(
            start, end, event.is_all_day, locale=locale
        )
        suffix = cls._recurring_suffix(event.is_recurring, event.rrule, locale=locale)
        reminder = cls._reminder_suffix(event.reminder_offset, locale=locale)
        lines = [
            f"📅 {event.title}",
            cls._t("event_detail_when", locale, when=f"{when}{suffix}{reminder}"),
        ]
        if source_label:
            from services.source_label import display_source_label, is_private_source

            display = display_source_label(source_label, locale)
            if is_private_source(source_label):
                lines.append(f"📍 {display}")
            else:
                lines.append(
                    cls._t("event_detail_group", locale, source_label=display)
                )
        if occurrence_is_moved and occurrence_original_start is not None:
            planned_end = occurrence_original_start + (event.ends_at - event.starts_at)
            planned = cls.format_event_when(
                occurrence_original_start,
                planned_end,
                event.is_all_day,
                locale=locale,
            )
            lines.append(cls._t("event_detail_moved", locale))
            lines.append(cls._t("event_detail_original", locale, when=planned))
        if getattr(event, "category_name", None):
            lines.append(
                cls._t("event_label_category", locale, category_name=event.category_name)
            )
        flag_names = getattr(event, "flag_names", None) or []
        if flag_names:
            lines.append(
                cls._t("event_label_flags", locale, flag_names=", ".join(flag_names))
            )
        return "\n".join(lines)

    @classmethod
    def create_event_detail_keyboard(
        cls,
        event_id: str,
        *,
        occurrence_original_start=None,
        is_recurring: bool = False,
        locale: str = "de",
    ) -> InlineKeyboardMarkup:
        has_occurrence = is_recurring and occurrence_original_start is not None
        if has_occurrence:
            delete_cb = build_occ_callback(
                "del_ask_", event_id, occurrence_original_start
            )
            time_cb = build_occ_callback(
                "tme_ask_", event_id, occurrence_original_start
            )
        else:
            delete_cb = f"del_cfm_{event_id}"
            time_cb = f"edit_tme_{event_id}"

        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_title", locale), callback_data=f"edit_ttl_{event_id}"
                    ),
                    InlineKeyboardButton(cls._t("btn_edit_time", locale), callback_data=time_cb),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_series", locale), callback_data=f"edit_rrc_{event_id}"
                    ),
                    InlineKeyboardButton(
                        cls._t("btn_edit_reminder", locale), callback_data=f"edit_rem_{event_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_delete_event", locale), callback_data=delete_cb
                    ),
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back_to_list", locale), callback_data="list_all_events"
                    ),
                ],
            ]
        )

    @classmethod
    def delete_scope_keyboard(
        cls, event_id: str, original_start, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        cls._t("btn_cancel_occurrence", locale),
                        callback_data=build_occ_callback(
                            "del_one_", event_id, original_start
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_delete_series", locale),
                        callback_data=f"del_all_{event_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back", locale),
                        callback_data=build_view_evt_callback(event_id, original_start),
                    )
                ],
            ]
        )

    @classmethod
    def time_edit_scope_keyboard(
        cls, event_id: str, original_start, locale: str = "de"
    ) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_occurrence_only", locale),
                        callback_data=build_occ_callback(
                            "tme_one_", event_id, original_start
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_edit_series_only", locale),
                        callback_data=f"edit_tme_{event_id}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        cls._t("btn_back", locale),
                        callback_data=build_view_evt_callback(event_id, original_start),
                    )
                ],
            ]
        )

    @classmethod
    def occurrence_cancelled(cls, locale: str = "de") -> str:
        return cls._t("occurrence_cancelled", locale)

    @classmethod
    def occurrence_moved(
        cls, original_start: datetime, new_start: datetime, locale: str = "de"
    ) -> str:
        original = original_start.strftime("%d.%m.%Y %H:%M")
        new_label = new_start.strftime("%d.%m.%Y %H:%M")
        return cls._t(
            "occurrence_moved",
            locale,
            new_start=new_label,
            original_start=original,
        )

    @classmethod
    def event_deleted_short(cls, locale: str = "de") -> str:
        return cls._t("event_deleted", locale)

    @classmethod
    def event_deleted(cls, event_id: str, locale: str = "de") -> str:
        return cls._t("event_deleted", locale, event_id=event_id)

    @classmethod
    def conversation_edit_field_title(cls, locale: str = "de") -> str:
        return cls._t("conversation_edit_field_title", locale)

    @classmethod
    def conversation_edit_field_date(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_field_date", locale, current=current)

    @classmethod
    def conversation_edit_field_time(cls, current: str, locale: str = "de") -> str:
        return cls._t("conversation_edit_field_time", locale, current=current)

    @classmethod
    def event_not_found(cls, locale: str = "de") -> str:
        return cls._t("event_not_found", locale)

    @classmethod
    def termin_loeschen_usage(cls, locale: str = "de") -> str:
        return cls._t("termin_loeschen_usage", locale)

    @classmethod
    def termin_bearbeiten_usage(cls, locale: str = "de") -> str:
        return cls._t("termin_bearbeiten_usage", locale)

    @classmethod
    def event_updated(
        cls,
        title: str,
        starts_at: datetime,
        is_recurring: bool = False,
        rrule: Optional[str] = None,
        reminder_offset: int = 0,
        *,
        ends_at: Optional[datetime] = None,
        is_all_day: bool = False,
        locale: str = "de",
    ) -> str:
        end = ends_at if ends_at is not None else starts_at + timedelta(hours=1)
        formatted = cls.format_event_when(
            starts_at, end, is_all_day, locale=locale
        )
        suffix = cls._recurring_suffix(is_recurring, rrule, locale=locale)
        reminder = cls._reminder_suffix(reminder_offset, locale=locale)
        return cls._t(
            "event_updated",
            locale,
            title=title,
            when=formatted,
            suffix=suffix,
            reminder=reminder,
        )

    @classmethod
    def event_permission_denied(cls, locale: str = "de") -> str:
        return cls._t("event_permission_denied", locale)

    @classmethod
    def kategorie_set_usage(cls, locale: str = "de") -> str:
        return cls._t("kategorie_set_usage", locale)

    @classmethod
    def kategorie_set_empty_names(cls, locale: str = "de") -> str:
        return cls._t("kategorie_set_empty_names", locale)

    @classmethod
    def kategorie_set_success(
        cls, created_count: int, total_global: int, names: list[str], locale: str = "de"
    ) -> str:
        name_list = ", ".join(names)
        if created_count == 0:
            return cls._t(
                "kategorie_set_success_existing",
                locale,
                names=name_list,
                total=total_global,
            )
        return cls._t(
            "kategorie_set_success_created",
            locale,
            names=name_list,
            created=created_count,
            total=total_global,
        )

    @classmethod
    def kategorie_add_usage(cls, locale: str = "de") -> str:
        return cls._t("kategorie_add_usage", locale)

    @classmethod
    def kategorie_add_empty_name(cls, locale: str = "de") -> str:
        return cls._t("kategorie_add_empty_name", locale)

    @classmethod
    def kategorie_add_success(cls, name: str, locale: str = "de") -> str:
        return cls._t("kategorie_add_success", locale, name=name)

    @classmethod
    def kategorie_add_duplicate(cls, name: str, locale: str = "de") -> str:
        return cls._t("kategorie_add_duplicate", locale, name=name)

    @classmethod
    def kategorie_add_global_collision(cls, name: str, locale: str = "de") -> str:
        return cls._t("kategorie_add_global_collision", locale, name=name)

    @classmethod
    def allow_usage(cls, locale: str = "de") -> str:
        return cls._t("allow_usage", locale)

    @staticmethod
    def version_text(version: str) -> str:
        return version

    @classmethod
    def allow_success(cls, user_id: int, name: str, locale: str = "de") -> str:
        return cls._t("allow_success", locale, name=name, user_id=user_id)

    @classmethod
    def allow_denied(cls, locale: str = "de") -> str:
        return cls._t("allow_denied", locale)

    @classmethod
    def allow_invalid_id(cls, locale: str = "de") -> str:
        return cls._t("allow_invalid_id", locale)

    @classmethod
    def group_intruder_warning(cls, locale: str = "de") -> str:
        return cls._t("group_intruder_warning", locale)

    @classmethod
    def admin_group_intrusion_alert(
        cls,
        group_title: str, group_id: int, adder_name: str, adder_id: int
        , locale: str = "de"
    ) -> str:
        return cls._t(
            "admin_group_intrusion_alert",
            locale,
            group_title=group_title,
            group_id=group_id,
            adder_name=adder_name,
            adder_id=adder_id,
        )

    @classmethod
    def admin_group_success_alert(
        cls,
        group_title: str, group_id: int, adder_name: str, adder_id: int
        , locale: str = "de"
    ) -> str:
        return cls._t(
            "admin_group_success_alert",
            locale,
            group_title=group_title,
            group_id=group_id,
            adder_name=adder_name,
            adder_id=adder_id,
        )

    @classmethod
    def generic_error(cls, locale: str = "de") -> str:
        return cls._t("generic_error", locale)

MessageFactory.load_locales()