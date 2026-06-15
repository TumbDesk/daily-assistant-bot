"""Tests for weather views and inline keyboard callbacks."""
import unittest
from datetime import date

from services.weather import (
    TodaysWeather,
    TrendDay,
    format_trend_line,
    get_five_day_trend,
    get_tomorrow_weather,
    parse_todays_weather,
)
from views.message_factory import (
    WEATHER_VIEW_TODAY,
    WEATHER_VIEW_TOMORROW,
    WEATHER_VIEW_TREND,
    MessageFactory,
)


def _build_daily_mock() -> dict:
    days = [
        "2026-05-25",
        "2026-05-26",
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
        "2026-05-30",
        "2026-05-31",
    ]
    return {
        "timezone": "Europe/Berlin",
        "daily": {
            "time": days,
            "weather_code": [0, 3, 61, 80, 95, 1, 2],
            "temperature_2m_min": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0],
            "temperature_2m_max": [20.0, 21.0, 22.0, 23.0, 24.0, 25.0, 26.0],
            "precipitation_probability_max": [10, 20, 30, 40, 50, 60, 70],
            "precipitation_sum": [0.0, 0.5, 1.2, 2.3, 3.4, 4.5, 5.6],
        },
        "hourly": {
            "time": [f"2026-05-26T{hour:02d}:00" for hour in range(24)],
            "precipitation_probability": [0] * 10 + [80, 80] + [0] * 12,
        },
    }


def _build_today_mock() -> dict:
    data = _build_daily_mock()
    data["current"] = {
        "time": "2026-05-25T14:00",
        "temperature_2m": 16.3,
        "apparent_temperature": 15.1,
        "relative_humidity_2m": 55,
        "weather_code": 2,
        "wind_speed_10m": 12.5,
    }
    data["hourly"] = {
        "time": [f"2026-05-25T{hour:02d}:00" for hour in range(24)],
        "precipitation_probability": [10] * 24,
    }
    return data


class TestWeatherViews(unittest.TestCase):
    def test_parse_todays_weather_uses_daily_index_zero_for_min_max(self):
        data = _build_today_mock()
        weather = parse_todays_weather(data)

        self.assertEqual(weather.temperature_min, 10.0)
        self.assertEqual(weather.temperature_max, 20.0)
        self.assertEqual(weather.temperature, 16.3)

    def test_weather_forecast_shows_min_max_in_temperature_line(self):
        weather = TodaysWeather(
            observed_at="2026-05-25T14:00",
            temperature=16.3,
            apparent_temperature=15.1,
            temperature_min=10.0,
            temperature_max=20.0,
            humidity=55,
            wind_speed=12.5,
            weather_code=2,
            precipitation_probability=10,
            precipitation_sum=0.0,
        )
        text = MessageFactory.weather_forecast("Hamburg", weather)
        self.assertIn(
            "• Temperatur: 16.3 °C (Gefühlt wie: 15.1 °C)",
            text,
        )
        self.assertIn("• Temperaturspanne: 10°C bis 20°C", text)
        self.assertNotIn("Min:", text)
        self.assertNotIn("Max:", text)

    def test_weather_forecast_has_no_home_location_suffix(self):
        weather = TodaysWeather(
            observed_at="2026-05-25T14:00",
            temperature=16.3,
            apparent_temperature=15.1,
            temperature_min=10.0,
            temperature_max=20.0,
            humidity=55,
            wind_speed=12.5,
            weather_code=2,
            precipitation_probability=10,
            precipitation_sum=0.0,
        )
        text = MessageFactory.weather_forecast(
            "Zwiesel, Bayern, Deutschland", weather
        )
        self.assertIn("📍 <b>Wetter für Zwiesel, Bayern, Deutschland</b>", text)
        self.assertNotIn("(Heimatort)", text)

    def test_get_tomorrow_weather_uses_daily_index_one(self):
        data = _build_daily_mock()
        weather = get_tomorrow_weather(data, "Hamburg")

        self.assertEqual(weather.weather_code, 3)
        self.assertEqual(weather.temperature_min, 11.0)
        self.assertEqual(weather.temperature_max, 21.0)
        self.assertEqual(weather.precipitation_probability, 20)
        self.assertEqual(weather.precipitation_sum, 0.5)
        self.assertEqual(len(weather.rain_blocks), 1)
        self.assertEqual(weather.rain_blocks[0].start_time, "10:00")

    def test_get_five_day_trend_returns_five_days(self):
        data = _build_daily_mock()
        days = get_five_day_trend(data, "Hamburg")

        self.assertEqual(len(days), 5)
        self.assertEqual(days[0].day, date(2026, 5, 25))
        self.assertEqual(days[4].day, date(2026, 5, 29))
        self.assertEqual(days[2].weather_code, 61)
        self.assertEqual(days[2].precip_prob, 30)

    def test_format_trend_line(self):
        day = TrendDay(
            day=date(2026, 5, 26),
            weather_code=3,
            temp_min=11.0,
            temp_max=21.0,
            precip_prob=20,
            precip_sum=0.5,
        )
        line = format_trend_line(day)
        self.assertEqual(
            line,
            "*Dienstag, 26.05.:* ☁️ 11°C - 21°C | 💧 20% | 🪣 0.5 mm",
        )


class TestWeatherKeyboard(unittest.TestCase):
    def test_callback_data_under_64_chars(self):
        long_name = "Sehr langer Ortsname mit vielen Details, Region, Land"
        for view in (WEATHER_VIEW_TODAY, WEATHER_VIEW_TOMORROW, WEATHER_VIEW_TREND):
            keyboard = MessageFactory.weather_view_keyboard(
                view, long_name, 53.5511, 9.9937
            )
            for row in keyboard.inline_keyboard:
                for btn in row:
                    self.assertLessEqual(len(btn.callback_data.encode("utf-8")), 64)

    def test_parse_weather_callback_roundtrip(self):
        encoded = MessageFactory.encode_weather_callback(
            WEATHER_VIEW_MORROW := WEATHER_VIEW_TOMORROW,
            51.5074,
            -0.1278,
            "London",
        )
        parsed = MessageFactory.parse_weather_callback(encoded)
        self.assertIsNotNone(parsed)
        view, lat, lon, name = parsed
        self.assertEqual(view, WEATHER_VIEW_MORROW)
        self.assertAlmostEqual(lat, 51.5074, places=4)
        self.assertAlmostEqual(lon, -0.1278, places=4)
        self.assertEqual(name, "London")

    def test_today_keyboard_shows_morgen_and_trend(self):
        keyboard = MessageFactory.weather_view_keyboard(
            WEATHER_VIEW_TODAY, "Berlin", 52.52, 13.405
        )
        labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
        self.assertEqual(labels, ["🔮 Morgen", "📅 5-Tage-Trend"])

    def test_tomorrow_keyboard_shows_heute_and_trend(self):
        keyboard = MessageFactory.weather_view_keyboard(
            WEATHER_VIEW_TOMORROW, "Berlin", 52.52, 13.405
        )
        labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
        self.assertEqual(labels, ["☀️ Heute", "📅 5-Tage-Trend"])

    def test_trend_keyboard_shows_heute_and_morgen(self):
        keyboard = MessageFactory.weather_view_keyboard(
            WEATHER_VIEW_TREND, "Berlin", 52.52, 13.405
        )
        labels = [btn.text for row in keyboard.inline_keyboard for btn in row]
        self.assertEqual(labels, ["☀️ Heute", "🔮 Morgen"])


if __name__ == "__main__":
    unittest.main()
