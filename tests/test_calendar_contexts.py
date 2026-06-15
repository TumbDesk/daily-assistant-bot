"""Tests for list_events_for_contexts."""
import os
import unittest
from datetime import datetime

from database import User, get_session, init_db
from services.calendar_service import CalendarService


class TestCalendarContexts(unittest.TestCase):
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

    @classmethod
    def _create_user(cls, name: str = "Test User") -> str:
        with get_session() as session:
            user = User(name=name)
            session.add(user)
            session.flush()
            return user.id

    def test_list_events_for_contexts_aggregates_multiple_chats(self):
        owner = self._create_user()
        self.calendar.create_event(
            owner_id=owner,
            context_chat_id=111,
            title="Privat",
            starts_at=datetime(2026, 5, 25, 10, 0),
        )
        self.calendar.create_event(
            owner_id=owner,
            context_chat_id=-999,
            title="Gruppe",
            starts_at=datetime(2026, 5, 26, 10, 0),
        )
        other = self._create_user("Other")
        self.calendar.create_event(
            owner_id=other,
            context_chat_id=-888,
            title="Andere Gruppe",
            starts_at=datetime(2026, 5, 27, 10, 0),
        )

        events = self.calendar.list_events_for_contexts([111, -999])

        titles = {event.title for event in events}
        self.assertEqual(titles, {"Privat", "Gruppe"})

    def test_list_events_for_contexts_empty_input(self):
        self.assertEqual(self.calendar.list_events_for_contexts([]), [])


if __name__ == "__main__":
    unittest.main()
