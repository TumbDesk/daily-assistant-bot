"""Tests for AgendaService (birthdays and daily events)."""
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from database import User, get_session, init_db
from services.agenda import (
    AgendaEventToday,
    AgendaService,
    TodayAgenda,
    days_until_next_birthday,
    format_daily_agenda,
)
from services.calendar_service import CalendarService


class TestAgendaService(unittest.TestCase):
    _context_seq = 100000

    @classmethod
    def _next_context(cls) -> int:
        cls._context_seq += 1
        return cls._context_seq
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
        cls.service = AgendaService()
        cls.calendar = CalendarService()

    @classmethod
    def _create_user(cls, name: str = "Test User") -> str:
        with get_session() as session:
            user = User(name=name)
            session.add(user)
            session.flush()
            return user.id

    def _create_calendar_event(
        self,
        user_id: str,
        title: str,
        starts_at: datetime,
        *,
        ends_at: datetime | None = None,
        context_chat_id: int | None = None,
        is_all_day: bool = False,
        is_recurring: bool = False,
        rrule: str | None = None,
    ):
        if context_chat_id is None:
            context_chat_id = self._next_context()
        return self.calendar.create_event(
            owner_id=user_id,
            context_chat_id=context_chat_id,
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            is_all_day=is_all_day,
            is_recurring=is_recurring,
            rrule=rrule,
        )

    def test_add_birthday_and_age_on_birthday(self):
        user_id = self._create_user()
        self.service.add_birthday(user_id, "Anna Müller", date(1996, 5, 25))

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({self._next_context()}),
        )

        self.assertEqual(len(agenda.birthdays), 1)
        self.assertEqual(agenda.birthdays[0].name, "Anna Müller")
        self.assertEqual(agenda.birthdays[0].age, 30)

    def test_birthday_not_on_other_day(self):
        user_id = self._create_user()
        self.service.add_birthday(user_id, "Anna Müller", date(1996, 5, 25))

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 26),
            context_chat_ids=frozenset({self._next_context()}),
        )

        self.assertEqual(agenda.birthdays, ())

    def test_calendar_event_with_time_range(self):
        user_id = self._create_user()
        event = self._create_calendar_event(
            user_id,
            "Team-Meeting",
            datetime(2026, 5, 25, 9, 0),
            ends_at=datetime(2026, 5, 25, 10, 30),
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({event.context_chat_id}),
        )

        self.assertEqual(len(agenda.events), 1)
        self.assertEqual(agenda.events[0].title, "Team-Meeting")
        self.assertEqual(agenda.events[0].starts_at, datetime(2026, 5, 25, 9, 0))
        self.assertEqual(agenda.events[0].ends_at, datetime(2026, 5, 25, 10, 30))

    def test_calendar_event_all_day(self):
        user_id = self._create_user()
        event = self._create_calendar_event(
            user_id,
            "Urlaub",
            datetime(2026, 5, 25, 0, 0),
            ends_at=datetime(2026, 5, 25, 23, 59),
            is_all_day=True,
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({event.context_chat_id}),
        )

        self.assertTrue(agenda.events[0].is_all_day)

    def test_recurring_event_appears_on_matching_day(self):
        user_id = self._create_user()
        event = self._create_calendar_event(
            user_id,
            "Training",
            datetime(2026, 5, 18, 18, 0),
            ends_at=datetime(2026, 5, 18, 20, 0),
            is_recurring=True,
            rrule="FREQ=WEEKLY",
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({event.context_chat_id}),
        )

        self.assertEqual(len(agenda.events), 1)
        self.assertEqual(agenda.events[0].title, "Training")
        self.assertTrue(agenda.events[0].is_recurring)
        self.assertEqual(agenda.events[0].starts_at, datetime(2026, 5, 25, 18, 0))
        self.assertEqual(agenda.events[0].ends_at, datetime(2026, 5, 25, 20, 0))

    def test_private_chat_event_appears_in_agenda(self):
        user_id = self._create_user()
        private_chat_id = 987654321
        self._create_calendar_event(
            user_id,
            "GEV",
            datetime(2026, 5, 25, 14, 0),
            ends_at=datetime(2026, 5, 25, 15, 0),
            context_chat_id=private_chat_id,
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({private_chat_id}),
        )

        self.assertEqual(len(agenda.events), 1)
        self.assertEqual(agenda.events[0].title, "GEV")

    def test_agenda_includes_foreign_group_events(self):
        viewer_id = self._create_user("Viewer")
        other_id = self._create_user("Other")
        group_id = -5001
        self._create_calendar_event(
            other_id,
            "Gruppen-Termin",
            datetime(2026, 5, 25, 11, 0),
            context_chat_id=group_id,
        )

        agenda = self.service.get_agenda_for_today(
            viewer_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({987654321, group_id}),
        )

        self.assertEqual(len(agenda.events), 1)
        self.assertEqual(agenda.events[0].title, "Gruppen-Termin")

    def test_list_events_for_owner_includes_all_contexts(self):
        user_id = self._create_user()
        self._create_calendar_event(
            user_id,
            "Privat",
            datetime(2026, 5, 25, 10, 0),
            context_chat_id=111,
        )
        self._create_calendar_event(
            user_id,
            "Gruppe",
            datetime(2026, 5, 26, 10, 0),
            context_chat_id=-999,
        )

        events = self.calendar.list_events_for_owner(user_id)

        self.assertEqual(len(events), 2)
        titles = {event.title for event in events}
        self.assertEqual(titles, {"Privat", "Gruppe"})

    def test_add_birthday_empty_name_raises(self):
        user_id = self._create_user()
        with self.assertRaises(ValueError):
            self.service.add_birthday(user_id, "   ", date(1990, 1, 1))

    def test_days_until_next_birthday(self):
        today = date(2026, 6, 1)
        self.assertEqual(days_until_next_birthday(today, date(1990, 6, 1)), 0)
        self.assertEqual(days_until_next_birthday(today, date(1990, 6, 15)), 14)
        self.assertEqual(days_until_next_birthday(today, date(1990, 5, 31)), 364)
        self.assertEqual(days_until_next_birthday(today, date(2000, 3, 15)), 287)

    @patch("services.agenda.now")
    def test_list_birthdays_sorted_from_today(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 1, 12, 0)
        user_id = self._create_user()
        self.service.add_birthday(user_id, "Mai", date(1990, 5, 25))
        self.service.add_birthday(user_id, "Anna", date(1985, 6, 1))
        self.service.add_birthday(user_id, "März", date(2000, 3, 15))
        self.service.add_birthday(user_id, "Zoe", date(1992, 6, 1))

        birthdays = self.service.list_birthdays(user_id)

        self.assertEqual(
            [(b.name, b.birth_date.month, b.birth_date.day) for b in birthdays],
            [
                ("Anna", 6, 1),
                ("Zoe", 6, 1),
                ("März", 3, 15),
                ("Mai", 5, 25),
            ],
        )

    def test_get_birthday_wrong_user_returns_none(self):
        owner = self._create_user("Owner")
        other = self._create_user("Other")
        added = self.service.add_birthday(owner, "Anna", date(1990, 5, 25))

        self.assertIsNone(self.service.get_birthday(other, added.id))

    def test_update_birthday_name_and_date(self):
        user_id = self._create_user()
        added = self.service.add_birthday(user_id, "Anna", date(1990, 5, 25))

        updated = self.service.update_birthday(
            user_id, added.id, name="Anna Müller", birth_date=date(1991, 6, 10)
        )

        self.assertEqual(updated.name, "Anna Müller")
        self.assertEqual(updated.birth_date, date(1991, 6, 10))

    def test_update_birthday_duplicate_raises(self):
        user_id = self._create_user()
        self.service.add_birthday(user_id, "Anna", date(1990, 5, 25))
        bob = self.service.add_birthday(user_id, "Bob", date(1988, 3, 1))

        with self.assertRaises(ValueError):
            self.service.update_birthday(
                user_id, bob.id, name="Anna", birth_date=date(1990, 5, 25)
            )

    def test_delete_birthday(self):
        user_id = self._create_user()
        added = self.service.add_birthday(user_id, "Anna", date(1990, 5, 25))

        self.assertTrue(self.service.delete_birthday(user_id, added.id))
        self.assertIsNone(self.service.get_birthday(user_id, added.id))
        self.assertFalse(self.service.delete_birthday(user_id, added.id))

    def test_format_daily_agenda_with_birthday_and_event(self):
        user_id = self._create_user()
        self.service.add_birthday(user_id, "Anna Müller", date(1996, 5, 25))
        event = self._create_calendar_event(
            user_id,
            "Team-Meeting",
            datetime(2026, 5, 25, 9, 0),
            ends_at=datetime(2026, 5, 25, 10, 30),
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({event.context_chat_id}),
        )
        text = format_daily_agenda(agenda)

        self.assertIn("🎉 **Geburtstage heute:**", text)
        self.assertIn("• *Anna Müller* wird heute *30* Jahre alt! 🎂", text)
        self.assertIn("💼 **Termine heute:**", text)
        self.assertIn("• 09:00–10:30: *Team-Meeting*", text)

    def test_format_daily_agenda_empty(self):
        text = format_daily_agenda(
            TodayAgenda(birthdays=(), events=()),
            include_birthdays=True,
            include_events=True,
        )
        self.assertEqual(text, "")

    def test_format_daily_agenda_all_day_event(self):
        agenda = TodayAgenda(
            birthdays=(),
            events=(
                AgendaEventToday(
                    event_id="evt-1",
                    title="Urlaub",
                    starts_at=datetime(2026, 5, 25, 0, 0),
                    ends_at=datetime(2026, 5, 25, 23, 59),
                    is_all_day=True,
                    context_chat_id=12345,
                ),
            ),
        )
        text = format_daily_agenda(agenda)
        self.assertIn("• Ganztägig: *Urlaub*", text)

    def test_format_daily_agenda_recurring_prefix(self):
        agenda = TodayAgenda(
            birthdays=(),
            events=(
                AgendaEventToday(
                    event_id="evt-2",
                    title="Training",
                    starts_at=datetime(2026, 5, 25, 18, 0),
                    ends_at=datetime(2026, 5, 25, 20, 0),
                    is_all_day=False,
                    context_chat_id=12345,
                    is_recurring=True,
                ),
            ),
        )
        text = format_daily_agenda(agenda)
        self.assertIn("• 🔁 18:00–20:00: *Training*", text)

    def test_format_daily_agenda_shows_group_source(self):
        from services.chat_membership_service import get_chat_membership_service

        group_id = -5001
        get_chat_membership_service().record_bot_joined(group_id, "Familie")
        agenda = TodayAgenda(
            birthdays=(),
            events=(
                AgendaEventToday(
                    event_id="evt-4",
                    title="Gruppen-Termin",
                    starts_at=datetime(2026, 5, 25, 15, 0),
                    ends_at=datetime(2026, 5, 25, 17, 0),
                    is_all_day=False,
                    context_chat_id=group_id,
                ),
            ),
        )
        text = format_daily_agenda(
            agenda, view_context_chat_id=987654321
        )
        self.assertIn("*Gruppen-Termin* 👥 (Familie)", text)

    def test_format_daily_agenda_moved_prefix(self):
        agenda = TodayAgenda(
            birthdays=(),
            events=(
                AgendaEventToday(
                    event_id="evt-3",
                    title="Training",
                    starts_at=datetime(2026, 5, 26, 10, 0),
                    ends_at=datetime(2026, 5, 26, 11, 0),
                    is_all_day=False,
                    context_chat_id=12345,
                    is_recurring=True,
                    is_moved=True,
                ),
            ),
        )
        text = format_daily_agenda(agenda)
        self.assertIn("• ↪️ 10:00–11:00: *Training*", text)

    def test_moved_occurrence_in_agenda(self):
        user_id = self._create_user()
        start = datetime(2026, 5, 18, 18, 0)
        event = self.calendar.create_event(
            owner_id=user_id,
            context_chat_id=12345,
            title="Training",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            is_recurring=True,
            rrule="FREQ=WEEKLY",
        )
        from services.event_exceptions import get_exception_service

        get_exception_service().move_occurrence(
            event.id,
            datetime(2026, 5, 25, 18, 0),
            datetime(2026, 5, 25, 10, 0),
            12345,
            12345,
            user_id,
            new_end=datetime(2026, 5, 25, 11, 0),
        )

        agenda = self.service.get_agenda_for_today(
            user_id,
            on_date=date(2026, 5, 25),
            context_chat_ids=frozenset({12345}),
        )
        self.assertEqual(len(agenda.events), 1)
        self.assertTrue(agenda.events[0].is_moved)
        text = format_daily_agenda(agenda)
        self.assertIn("↪️", text)

    def test_build_daily_report_respects_include_flags(self):
        import asyncio
        from unittest.mock import patch

        from services.user_settings import UserSettings

        user_id = self._create_user()
        self.service.add_birthday(user_id, "Anna Müller", date(1996, 5, 25))
        settings = UserSettings(
            report_enabled=True,
            report_time="07:00",
            include_events=False,
            include_birthdays=True,
            include_weather=False,
        )

        with patch(
            "services.user_service.get_user_service"
        ) as mock_user_service:
            mock_user_service.return_value.get_home_location.return_value = None
            from services.agenda import build_daily_report

            text = asyncio.run(
                build_daily_report(
                    user_id,
                    settings,
                    on_date=date(2026, 5, 25),
                    context_chat_ids=frozenset({self._next_context()}),
                )
            )

        self.assertIn("Geburtstage heute", text)
        self.assertNotIn("Termine heute", text)
        self.assertNotIn("Wetter", text)

    def test_build_daily_report_uses_travel_weather(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from services.travel import get_travel_service
        from services.user_settings import UserSettings

        user_id = self._create_user()
        get_travel_service().add_trip(
            user_id,
            "Berlin, Berlin, Deutschland",
            52.52,
            13.405,
            date(2026, 6, 1),
            date(2026, 6, 8),
        )
        settings = UserSettings(
            report_enabled=True,
            report_time="07:00",
            include_events=False,
            include_birthdays=False,
            include_weather=True,
        )
        forecast_data = {
            "current": {
                "time": "2026-06-05T12:00",
                "temperature_2m": 22.0,
                "apparent_temperature": 21.0,
                "relative_humidity_2m": 50,
                "wind_speed_10m": 10.0,
                "weather_code": 1,
            },
            "daily": {
                "temperature_2m_min": [18.0],
                "temperature_2m_max": [25.0],
                "precipitation_probability_max": [10],
                "precipitation_sum": [0.0],
            },
            "hourly": {"time": [], "precipitation_probability": []},
            "timezone": "Europe/Berlin",
        }

        with patch("services.weather.get_weather_service") as mock_weather:
            mock_weather.return_value.get_forecast = AsyncMock(
                return_value=forecast_data
            )
            from services.agenda import build_daily_report

            text = asyncio.run(
                build_daily_report(
                    user_id,
                    settings,
                    on_date=date(2026, 6, 5),
                    context_chat_ids=frozenset({self._next_context()}),
                )
            )

        self.assertIn("Urlaubs-Wetter", text)
        self.assertIn("Berlin, Berlin, Deutschland", text)
        self.assertNotIn("Heimatort nicht gesetzt", text)

    def test_build_daily_report_falls_back_to_home_without_travel(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from services.user_settings import UserSettings

        user_id = self._create_user()
        settings = UserSettings(
            report_enabled=True,
            report_time="07:00",
            include_events=False,
            include_birthdays=False,
            include_weather=True,
        )
        forecast_data = {
            "current": {
                "time": "2026-05-25T12:00",
                "temperature_2m": 18.0,
                "apparent_temperature": 17.0,
                "relative_humidity_2m": 60,
                "wind_speed_10m": 5.0,
                "weather_code": 2,
            },
            "daily": {
                "temperature_2m_min": [12.0],
                "temperature_2m_max": [20.0],
                "precipitation_probability_max": [20],
                "precipitation_sum": [0.5],
            },
            "hourly": {"time": [], "precipitation_probability": []},
            "timezone": "Europe/Berlin",
        }

        with patch("services.user_service.get_user_service") as mock_user_service, patch(
            "services.weather.get_weather_service"
        ) as mock_weather:
            mock_user_service.return_value.get_home_location.return_value = (
                48.13,
                11.58,
                "München",
            )
            mock_weather.return_value.get_forecast = AsyncMock(
                return_value=forecast_data
            )
            from services.agenda import build_daily_report

            text = asyncio.run(
                build_daily_report(
                    user_id,
                    settings,
                    on_date=date(2026, 5, 25),
                    context_chat_ids=frozenset({self._next_context()}),
                )
            )

        self.assertIn("Wetter heute", text)
        self.assertIn("München", text)
        self.assertNotIn("Urlaubs-Wetter", text)


if __name__ == "__main__":
    unittest.main()
