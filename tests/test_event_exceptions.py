"""Tests for series exceptions."""
import os
import unittest
from datetime import datetime, timedelta

from database import User, get_session, init_db
from services.calendar_service import CalendarService
from services.event_exceptions import (
    EXCEPTION_MOVED,
    EventExceptionService,
)
from services.event_filter import EventFilterPreset, apply_filter, resolve_occurrences_in_range
from views.message_factory import MessageFactory


class TestEventExceptions(unittest.TestCase):
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
        cls.calendar = CalendarService()
        cls.exceptions = EventExceptionService()

    @classmethod
    def _create_user(cls) -> str:
        with get_session() as session:
            user = User(name="Test User")
            session.add(user)
            session.flush()
            return user.id

    def _create_weekly(self, user_id: str, start: datetime):
        return self.calendar.create_event(
            owner_id=user_id,
            context_chat_id=12345,
            title="Training",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            is_recurring=True,
            rrule="FREQ=WEEKLY",
        )

    def test_cancel_occurrence_hides_from_range(self):
        user_id = self._create_user()
        start = datetime(2026, 5, 18, 18, 0)
        event = self._create_weekly(user_id, start)
        occ = datetime(2026, 5, 25, 18, 0)

        self.exceptions.cancel_occurrence(
            event.id, occ, 12345, 12345, user_id
        )
        excs = self.exceptions.get_exceptions_for_event(event.id)
        day_start = datetime(2026, 5, 25)
        day_end = day_start + timedelta(days=1)
        instances = resolve_occurrences_in_range(event, day_start, day_end, excs)
        self.assertEqual(instances, [])

    def test_move_occurrence_shows_at_new_time(self):
        user_id = self._create_user()
        start = datetime(2026, 5, 18, 18, 0)
        event = self._create_weekly(user_id, start)
        original = datetime(2026, 5, 25, 18, 0)
        new_start = datetime(2026, 5, 26, 10, 0)

        self.exceptions.move_occurrence(
            event.id,
            original,
            new_start,
            12345,
            12345,
            user_id,
            new_end=new_start + timedelta(hours=1),
        )
        excs = self.exceptions.get_exceptions_for_event(event.id)
        self.assertEqual(excs[0].exception_type, EXCEPTION_MOVED)

        range_start = datetime(2026, 5, 26)
        range_end = range_start + timedelta(days=1)
        instances = resolve_occurrences_in_range(
            event, range_start, range_end, excs
        )
        self.assertEqual(len(instances), 1)
        self.assertTrue(instances[0].is_moved)
        self.assertEqual(instances[0].starts_at, new_start)

    def test_apply_filter_respects_cancelled(self):
        user_id = self._create_user()
        start = datetime(2026, 5, 18, 18, 0)
        event = self._create_weekly(user_id, start)
        occ = datetime(2026, 5, 25, 18, 0)
        self.exceptions.cancel_occurrence(
            event.id, occ, 12345, 12345, user_id
        )

        filtered = apply_filter([event], EventFilterPreset.TODAY)
        # Manually set today range via calendar month containing occ
        filtered = apply_filter(
            [event],
            EventFilterPreset.CALENDAR_MONTH,
            year=2026,
            month=5,
        )
        titles = [e.title for e in filtered if e.display_starts_at == occ]
        self.assertEqual(titles, [])

    def test_apply_filter_future_shows_moved_occurrence(self):
        user_id = self._create_user()
        start = datetime(2026, 5, 18, 18, 0)
        event = self._create_weekly(user_id, start)
        original = datetime(2026, 5, 25, 18, 0)
        new_start = datetime(2026, 5, 27, 18, 0)
        self.exceptions.move_occurrence(
            event.id,
            original,
            new_start,
            12345,
            12345,
            user_id,
            new_end=new_start + timedelta(hours=1),
        )

        from unittest.mock import patch

        from services.timezone_util import get_timezone

        with patch("services.event_filter.now") as mock_now:
            mock_now.return_value = datetime(2026, 5, 24, 12, 0).replace(
                tzinfo=get_timezone()
            )
            filtered = apply_filter([event], EventFilterPreset.FUTURE)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].list_starts_at, new_start)
        self.assertTrue(filtered[0].occurrence_is_moved)
        label = MessageFactory._event_list_button_label(filtered[0])
        self.assertIn("27.05.", label)
        self.assertTrue(label.startswith("↪️"))

    def test_cancel_non_recurring_raises(self):
        user_id = self._create_user()
        event = self.calendar.create_event(
            owner_id=user_id,
            context_chat_id=12345,
            title="Einzeln",
            starts_at=datetime(2026, 5, 25, 10, 0),
        )
        with self.assertRaises(ValueError):
            self.exceptions.cancel_occurrence(
                event.id,
                datetime(2026, 5, 25, 10, 0),
                12345,
                12345,
                user_id,
            )


if __name__ == "__main__":
    unittest.main()
