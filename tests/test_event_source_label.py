"""Tests for event source labels."""
import os
import unittest

from database import get_session, init_db
from services.chat_membership_service import ChatMembershipService
from services.user_service import event_source_label


class TestEventSourceLabel(unittest.TestCase):
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
        cls.service = ChatMembershipService()

    def test_same_context_returns_none(self):
        self.assertIsNone(event_source_label(12345, 12345))

    def test_group_context_returns_group_name(self):
        self.service.record_bot_joined(-9001, "Verein")
        self.assertEqual(event_source_label(-9001, 12345), "Verein")

    def test_group_without_title_returns_fallback(self):
        self.service.record_bot_joined(-9002)
        self.assertEqual(event_source_label(-9002, 12345), "Gruppe")

    def test_private_context_from_group_view(self):
        self.assertEqual(event_source_label(12345, -9001), "Privat")


if __name__ == "__main__":
    unittest.main()
