"""Tests for UserSettingsService."""
import os
import unittest
from datetime import date

from database import User, UserIdentity, get_session, init_db
from services.user_settings import (
    DEFAULT_REPORT_TIME,
    UserSettingsService,
    get_user_settings_service,
)
from services.user_service import PLATFORM_TELEGRAM


class TestUserSettingsService(unittest.TestCase):
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
        cls.service = UserSettingsService()

    @classmethod
    def _create_user(cls, platform_user_id: int = 1001) -> str:
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

    def test_defaults_for_new_user(self):
        user_id = self._create_user()
        settings = self.service.get_settings(user_id)
        self.assertTrue(settings.report_enabled)
        self.assertEqual(settings.report_time, DEFAULT_REPORT_TIME)
        self.assertTrue(settings.include_events)
        self.assertTrue(settings.include_birthdays)
        self.assertTrue(settings.include_weather)
        self.assertIsNone(settings.locale)

    def test_set_locale(self):
        user_id = self._create_user(1006)
        self.service.set_locale(user_id, "en")
        self.assertEqual(self.service.get_settings(user_id).locale, "en")

    def test_set_locale_normalizes_code(self):
        user_id = self._create_user(1007)
        self.service.set_locale(user_id, "de-DE")
        self.assertEqual(self.service.get_settings(user_id).locale, "de")

    def test_set_locale_invalid_raises(self):
        user_id = self._create_user(1008)
        with self.assertRaises(ValueError):
            self.service.set_locale(user_id, "fr")

    def test_toggle_setting(self):
        user_id = self._create_user(1002)
        self.service.toggle_setting(user_id, "include_weather")
        settings = self.service.get_settings(user_id)
        self.assertFalse(settings.include_weather)

    def test_set_report_time(self):
        user_id = self._create_user(1003)
        self.service.set_report_time(user_id, "08:30")
        self.assertEqual(self.service.get_settings(user_id).report_time, "08:30")

    def test_cycle_report_time(self):
        user_id = self._create_user(1004)
        self.service.set_report_time(user_id, "07:00")
        self.service.cycle_report_time(user_id, 1)
        self.assertEqual(self.service.get_settings(user_id).report_time, "07:30")
        self.service.cycle_report_time(user_id, -1)
        self.assertEqual(self.service.get_settings(user_id).report_time, "07:00")

    def test_list_users_due_for_report(self):
        user_id = self._create_user(1005)
        today = date(2026, 5, 25)
        due = self.service.list_users_due_for_report("07:00", today)
        due_ids = {entry[0] for entry in due}
        self.assertIn(user_id, due_ids)

        self.service.mark_report_sent(user_id, today)
        due_after = self.service.list_users_due_for_report("07:00", today)
        due_after_ids = {entry[0] for entry in due_after}
        self.assertNotIn(user_id, due_after_ids)

    def test_singleton(self):
        self.assertIs(get_user_settings_service(), get_user_settings_service())

    def test_list_users_for_weather_alerts_includes_defaults(self):
        user_id = self._create_user(1010)
        alert_ids = {entry[0] for entry in self.service.list_users_for_weather_alerts()}
        self.assertIn(user_id, alert_ids)

    def test_list_users_for_weather_alerts_excludes_disabled_report(self):
        user_id = self._create_user(1011)
        self.service.update_settings(user_id, report_enabled=False)
        alert_ids = {entry[0] for entry in self.service.list_users_for_weather_alerts()}
        self.assertNotIn(user_id, alert_ids)

    def test_list_users_for_weather_alerts_excludes_disabled_weather(self):
        user_id = self._create_user(1012)
        self.service.update_settings(user_id, include_weather=False)
        alert_ids = {entry[0] for entry in self.service.list_users_for_weather_alerts()}
        self.assertNotIn(user_id, alert_ids)

    def test_list_users_for_weather_alerts_includes_both_enabled(self):
        user_id = self._create_user(1013)
        self.service.update_settings(user_id, report_enabled=True, include_weather=True)
        alert_ids = {entry[0] for entry in self.service.list_users_for_weather_alerts()}
        self.assertIn(user_id, alert_ids)


if __name__ == "__main__":
    unittest.main()
