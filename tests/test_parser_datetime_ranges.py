"""Tests for start/end time, duration, and all-day ranges in the parser."""
import os
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from database import get_session, init_db
from services.calendar_service import CalendarService
from services.event_filter import EventFilterPreset, apply_filter
from services.parser import TerminParseError, parse_termin_text

_BASE = datetime(2026, 5, 21, 10, 0)


class TestParserDatetimeRanges(unittest.TestCase):
    @patch("services.parser.now")
    def test_morgen_um_15_uhr_default_end_plus_one_hour(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text("Morgen um 15 Uhr", base=_BASE, locale="de")
        self.assertEqual(parsed.title, "Termin")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 15, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 16, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_inline_time_range_same_day(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting morgen von 10 bis 12 Uhr",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 10, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 12, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_duration_for_two_hours(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Workshop für 2 Stunden morgen 14 Uhr",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 14, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 16, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_multi_day_all_day_trip(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Urlaub 05.06. bis 12.06.2026",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Urlaub")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 5, 0, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 12, 23, 59, 59))
        self.assertTrue(parsed.is_all_day)

    @patch("services.parser.now")
    def test_named_month_date_range_with_vom(self, mock_now):
        mock_now.return_value = _BASE
        from services.parser import parse_event_text
        from services.types import CategoryDTO

        parsed = parse_event_text(
            "Arbeit: Sommerurlaub vom 27. Juli 2026 bis 14. August 2026, ganztägig",
            user_categories=[CategoryDTO(id=1, name="Arbeit", is_global=True)],
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Sommerurlaub")
        self.assertEqual(parsed.starts_at, datetime(2026, 7, 27, 0, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 8, 14, 23, 59, 59))
        self.assertTrue(parsed.is_all_day)
        self.assertEqual(parsed.category_id, 1)

    @patch("services.parser.now")
    def test_named_month_date_range_without_ganztaegig_keyword(self, mock_now):
        mock_now.return_value = _BASE
        from services.parser import parse_event_text
        from services.types import CategoryDTO

        parsed = parse_event_text(
            "Arbeit: Sommerurlaub vom 27. Juli 2026 bis 14. August 2026",
            user_categories=[CategoryDTO(id=1, name="Arbeit", is_global=True)],
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Sommerurlaub")
        self.assertTrue(parsed.is_all_day)
        self.assertEqual(parsed.ends_at, datetime(2026, 8, 14, 23, 59, 59))

    @patch("services.parser.now")
    def test_inline_time_range_without_space_after_bis(self, mock_now):
        mock_now.return_value = _BASE
        from services.parser import parse_event_text
        from services.types import CategoryDTO

        parsed = parse_event_text(
            "Arbeit: Umzug, am 23.06.2026, von 9 Uhr bis13 Uhr, Erinnerung 7h vorher",
            user_categories=[CategoryDTO(id=1, name="Arbeit", is_global=True)],
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Umzug")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 23, 9, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 23, 13, 0))
        self.assertEqual(parsed.reminder_offset, 420)
        self.assertEqual(parsed.category_id, 1)

    @patch("services.parser.now")
    def test_recurrence_until_not_confused_with_date_range(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Müllabholung morgen alle 14 Tage bis ende Juli",
            base=_BASE,
            locale="de",
        )
        self.assertTrue(parsed.is_recurring)
        self.assertEqual(parsed.until_date, date(2026, 7, 31))
        self.assertIn("UNTIL=", parsed.rrule)


class TestCalendarServiceDatetimeRanges(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy.orm import sessionmaker

        import database.connection as db_conn
        from database.models import Base

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

    def test_create_event_persists_end_datetime(self):
        svc = CalendarService()
        start = datetime(2026, 6, 1, 9, 0)
        end = datetime(2026, 6, 1, 11, 0)
        event = svc.create_event(
            owner_id="owner-1",
            context_chat_id=1,
            title="Besprechung",
            starts_at=start,
            ends_at=end,
        )
        self.assertEqual(event.ends_at, end)

        with get_session() as session:
            from database.models import Event

            stored = session.get(Event, event.id)
            self.assertEqual(stored.end_datetime, end)
            self.assertFalse(stored.is_all_day)

    def test_create_event_default_end_plus_one_hour(self):
        svc = CalendarService()
        start = datetime(2026, 6, 1, 9, 0)
        event = svc.create_event(
            owner_id="owner-1",
            context_chat_id=1,
            title="Kurz",
            starts_at=start,
        )
        self.assertEqual(event.ends_at, start + timedelta(hours=1))

    @patch("services.event_filter.now")
    def test_filter_overlaps_multi_day_event(self, mock_now):
        mock_now.return_value = _BASE.replace(tzinfo=__import__(
            "services.timezone_util", fromlist=["get_timezone"]
        ).get_timezone())
        svc = CalendarService()
        trip = svc.create_event(
            owner_id="owner-1",
            context_chat_id=1,
            title="Reise",
            starts_at=datetime(2026, 6, 5, 0, 0),
            ends_at=datetime(2026, 6, 12, 23, 59, 59),
            is_all_day=True,
        )
        filtered = apply_filter(
            [trip],
            EventFilterPreset.CALENDAR_MONTH,
            year=2026,
            month=6,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].id, trip.id)


if __name__ == "__main__":
    unittest.main()
