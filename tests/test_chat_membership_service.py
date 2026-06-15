"""Tests for group membership and cross-channel contexts."""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock

from database import BotChat, UserChatMembership, User, get_session, init_db
from services.calendar_service import CalendarService
from services.chat_membership_service import ChatMembershipService
from telegram import ChatMember


class TestChatMembershipService(unittest.TestCase):
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

    def setUp(self):
        with get_session() as session:
            session.query(UserChatMembership).delete()
            session.query(BotChat).delete()

    def test_record_bot_joined_creates_group(self):
        self.service.record_bot_joined(-1001, "Familie")

        with get_session() as session:
            row = session.get(BotChat, -1001)
            self.assertIsNotNone(row)
            self.assertEqual(row.title, "Familie")

    def test_record_bot_joined_ignores_private_chat(self):
        self.service.record_bot_joined(12345, "Privat")

        with get_session() as session:
            row = session.get(BotChat, 12345)

        self.assertIsNone(row)

    def test_record_user_seen_creates_membership(self):
        self.service.record_bot_joined(-2002, "Team")
        self.service.record_user_seen(111, -2002)

        with get_session() as session:
            row = session.scalar(
                __import__("sqlalchemy")
                .select(UserChatMembership)
                .where(UserChatMembership.platform_user_id == "111")
                .where(UserChatMembership.context_chat_id == -2002)
            )

        self.assertIsNotNone(row)

    def test_get_visible_context_ids_includes_private_and_groups(self):
        self.service.record_user_seen(222, -3003)

        visible = self.service.get_visible_context_ids(222)

        self.assertEqual(visible, frozenset({222, -3003}))

    def test_sync_memberships_adds_active_member(self):
        self.service.record_bot_joined(-4004, "Verein")
        bot = MagicMock()
        member = MagicMock()
        member.status = ChatMember.MEMBER
        bot.get_chat_member = AsyncMock(return_value=member)
        bot.get_chat = AsyncMock(return_value=MagicMock(title="Verein"))

        import asyncio

        visible = asyncio.run(self.service.sync_memberships(bot, 333))

        self.assertIn(-4004, visible)
        self.assertIn(333, visible)
        self.assertIn(-4004, self.service.list_member_group_ids(333))

    def test_bootstrap_bot_chats_from_events(self):
        with get_session() as session:
            user = User(name="Owner")
            session.add(user)
            session.flush()
            owner_id = user.id
        CalendarService().create_event(
            owner_id=owner_id,
            context_chat_id=-7777,
            title="Gruppen-Termin",
            starts_at=__import__("datetime").datetime(2026, 6, 5, 10, 0),
        )

        self.service.bootstrap_bot_chats_from_events()

        with get_session() as session:
            row = session.get(BotChat, -7777)
        self.assertIsNotNone(row)

    def test_sync_memberships_refreshes_missing_title(self):
        self.service.record_bot_joined(-6006)
        bot = MagicMock()
        member = MagicMock()
        member.status = ChatMember.MEMBER
        bot.get_chat_member = AsyncMock(return_value=member)
        chat = MagicMock()
        chat.title = "Nachgeladen"
        bot.get_chat = AsyncMock(return_value=chat)

        import asyncio

        asyncio.run(self.service.sync_memberships(bot, 555))

        self.assertEqual(self.service.get_chat_display_name(-6006), "Nachgeladen")

    def test_sync_memberships_removes_inactive_member(self):
        self.service.record_bot_joined(-5005, "Alt")
        self.service.record_user_seen(444, -5005)
        bot = MagicMock()
        member = MagicMock()
        member.status = ChatMember.LEFT
        bot.get_chat_member = AsyncMock(return_value=member)
        bot.get_chat = AsyncMock(return_value=MagicMock(title="Alt"))

        import asyncio

        visible = asyncio.run(self.service.sync_memberships(bot, 444))

        self.assertNotIn(-5005, visible)
        self.assertEqual(self.service.list_member_group_ids(444), [])


if __name__ == "__main__":
    unittest.main()
