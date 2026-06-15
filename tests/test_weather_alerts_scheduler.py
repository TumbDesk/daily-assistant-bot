"""Tests for rain alert privacy filter in the scheduler."""
import asyncio
import os
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from database import User, UserIdentity, get_session, init_db
from database.models import TravelTrip
from sqlalchemy import delete
from services.scheduler_service import check_weather_alerts
from services.user_settings import UserSettingsService
from services.user_service import PLATFORM_TELEGRAM
from services.weather import RainBlock


class TestCheckWeatherAlertsPrivacy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy.orm import sessionmaker

        import database.connection as db_conn
        from database.models import Base

        os.environ.setdefault("ADMIN_ID", "9001")
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        db_conn.engine.dispose()
        db_conn.engine = __import__("sqlalchemy").create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        db_conn.SessionLocal = sessionmaker(
            bind=db_conn.engine, autoflush=False, autocommit=False
        )
        Base.metadata.drop_all(bind=db_conn.engine)
        init_db()
        cls.settings_service = UserSettingsService()

    def setUp(self):
        with get_session() as session:
            session.execute(delete(TravelTrip))
            session.execute(delete(UserIdentity))
            session.execute(delete(User))

    @classmethod
    def _create_user(cls, platform_user_id: int) -> str:
        with get_session() as session:
            user = User(name="Test")
            session.add(user)
            session.flush()
            session.add(
                UserIdentity(
                    user_id=user.id,
                    platform=PLATFORM_TELEGRAM,
                    platform_user_id=str(platform_user_id),
                )
            )
            return user.id

    def test_skips_api_for_user_with_weather_disabled(self):
        user_id = self._create_user(2001)
        self.settings_service.update_settings(user_id, include_weather=False)

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        with patch("services.weather.get_weather_service") as mock_weather:
            mock_weather.return_value.get_forecast = AsyncMock()
            asyncio.run(check_weather_alerts(context))

        mock_weather.return_value.get_forecast.assert_not_called()
        context.bot.send_message.assert_not_called()

    def test_calls_api_for_subscribed_user_with_location(self):
        user_id = self._create_user(2002)
        tz = ZoneInfo("Europe/Berlin")
        current = datetime(2026, 5, 25, 11, 0, tzinfo=tz)
        rain_block = RainBlock(
            max_probability=80,
            avg_probability=70,
            start=datetime(2026, 5, 25, 11, 30, tzinfo=tz),
            end=datetime(2026, 5, 25, 13, 0, tzinfo=tz),
        )
        forecast_data = {
            "current": {
                "time": "2026-05-25T11:00",
                "temperature_2m": 18.0,
                "apparent_temperature": 17.0,
                "relative_humidity_2m": 60,
                "wind_speed_10m": 5.0,
                "weather_code": 2,
            },
            "daily": {
                "temperature_2m_min": [12.0],
                "temperature_2m_max": [20.0],
                "precipitation_probability_max": [80],
                "precipitation_sum": [2.0],
            },
            "hourly": {"time": [], "precipitation_probability": []},
            "timezone": "Europe/Berlin",
        }

        context = MagicMock()
        context.bot.send_message = AsyncMock()

        with patch("services.scheduler_service.now", return_value=current), patch(
            "services.agenda._resolve_weather_location",
            return_value=(48.13, 11.58, "München", False),
        ), patch("services.weather.parse_todays_weather") as mock_parse, patch(
            "services.weather.get_weather_service"
        ) as mock_weather:
            mock_parse.return_value = MagicMock(rain_blocks=(rain_block,))
            mock_weather.return_value.get_forecast = AsyncMock(return_value=forecast_data)
            asyncio.run(check_weather_alerts(context))

        mock_weather.return_value.get_forecast.assert_called_once()
        context.bot.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
