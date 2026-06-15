"""Tests for event permissions and UNTIL in RRULE."""
import os
import unittest
from datetime import date, datetime

from database import User, UserIdentity, get_session, init_db
from services.calendar_service import (
    CalendarService,
    EventDTO,
    can_access_event,
    can_modify_event,
)
from services.rrule_util import apply_until, parse_until_from_rrule, recurrence_label
from services.user_service import PLATFORM_TELEGRAM

ADMIN_ID = 9001
USER_A = 1001
USER_B = 1002
GROUP_CHAT = -5001


class TestEventPermissions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy.orm import sessionmaker

        import database.connection as db_conn
        from database.models import Base

        os.environ["ADMIN_ID"] = str(ADMIN_ID)
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
        cls.owner_a = cls._ensure_owner(USER_A, "User A")
        cls.owner_b = cls._ensure_owner(USER_B, "User B")
        cls.owner_admin = cls._ensure_owner(ADMIN_ID, "Admin", is_admin=True)

    @staticmethod
    def _ensure_owner(platform_user_id: int, name: str, *, is_admin: bool = False) -> str:
        with get_session() as session:
            stmt = __import__("sqlalchemy").select(UserIdentity).where(
                UserIdentity.platform == PLATFORM_TELEGRAM,
                UserIdentity.platform_user_id == str(platform_user_id),
            )
            identity = session.scalars(stmt).first()
            if identity:
                return identity.user_id
            user = User(name=name, is_admin=is_admin)
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

    def _create(
        self,
        *,
        context_chat_id: int,
        owner_id: str,
        title: str = "Test",
    ) -> EventDTO:
        svc = CalendarService()
        return svc.create_event(
            owner_id=owner_id,
            context_chat_id=context_chat_id,
            title=title,
            starts_at=datetime(2026, 6, 15, 10, 0),
        )

    def test_admin_can_delete_foreign_group_event(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_a)
        svc = CalendarService()
        self.assertTrue(
            svc.delete_event(
                GROUP_CHAT,
                event.id,
                self.owner_admin,
                ADMIN_ID,
                is_admin=True,
            )
        )

    def test_user_cannot_delete_foreign_group_event(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_a)
        svc = CalendarService()
        self.assertFalse(
            svc.delete_event(
                GROUP_CHAT,
                event.id,
                self.owner_b,
                USER_B,
                is_admin=False,
            )
        )

    def test_event_id_is_uuid_string(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_a)
        self.assertEqual(len(event.id), 36)
        self.assertTrue(CalendarService.is_valid_event_id(event.id))

    def test_creator_can_delete_own_group_event(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_a)
        svc = CalendarService()
        self.assertTrue(
            svc.delete_event(
                GROUP_CHAT,
                event.id,
                self.owner_a,
                USER_A,
                is_admin=False,
            )
        )

    def test_can_modify_admin_in_group(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_a)
        dto = EventDTO(
            id=event.id,
            owner_id=event.owner_id,
            context_chat_id=event.context_chat_id,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            is_all_day=event.is_all_day,
            reminder_offset=event.reminder_offset,
            is_recurring=event.is_recurring,
            rrule=event.rrule,
        )
        self.assertTrue(
            can_modify_event(dto, GROUP_CHAT, ADMIN_ID, self.owner_admin, True)
        )
        self.assertFalse(
            can_modify_event(dto, GROUP_CHAT, USER_B, self.owner_b, False)
        )

    def test_private_event_not_visible_in_group(self):
        event = self._create(context_chat_id=USER_A, owner_id=self.owner_a)
        dto = EventDTO(
            id=event.id,
            owner_id=event.owner_id,
            context_chat_id=event.context_chat_id,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            is_all_day=event.is_all_day,
            reminder_offset=event.reminder_offset,
            is_recurring=event.is_recurring,
            rrule=event.rrule,
        )
        self.assertFalse(can_access_event(dto, GROUP_CHAT, USER_A))

    def test_group_event_visible_in_dm_with_visible_context_ids(self):
        event = self._create(context_chat_id=GROUP_CHAT, owner_id=self.owner_b)
        dto = EventDTO(
            id=event.id,
            owner_id=event.owner_id,
            context_chat_id=event.context_chat_id,
            title=event.title,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            is_all_day=event.is_all_day,
            reminder_offset=event.reminder_offset,
            is_recurring=event.is_recurring,
            rrule=event.rrule,
        )
        visible = frozenset({USER_A, GROUP_CHAT})

        self.assertTrue(
            can_access_event(
                dto, USER_A, USER_A, visible_context_ids=visible
            )
        )
        self.assertFalse(
            can_modify_event(
                dto, USER_A, USER_A, self.owner_a, False, visible_context_ids=visible
            )
        )
        self.assertTrue(
            can_modify_event(
                dto, USER_A, USER_A, self.owner_b, False, visible_context_ids=visible
            )
        )


class TestUntilRrule(unittest.TestCase):
    def test_build_rrule_with_until(self):
        is_recurring, rrule = CalendarService.build_rrule(
            "weekly", until_date=date(2026, 12, 31)
        )
        self.assertTrue(is_recurring)
        self.assertIn("UNTIL=20261231T225959", rrule)
        self.assertEqual(parse_until_from_rrule(rrule), date(2026, 12, 31))

    def test_recurrence_label_with_until(self):
        rrule = apply_until("FREQ=WEEKLY", date(2026, 6, 30))
        self.assertEqual(recurrence_label(rrule), "wöch., bis 30.06.2026")

    def test_finalize_rrule_rejects_until_before_start(self):
        with self.assertRaises(ValueError):
            CalendarService.finalize_rrule(
                True,
                "FREQ=DAILY",
                date(2026, 1, 1),
                datetime(2026, 6, 1, 10, 0),
            )


if __name__ == "__main__":
    unittest.main()
