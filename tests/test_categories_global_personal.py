"""Tests for global and personal categories."""
import os
import unittest

from database import Category, User, UserIdentity, get_session, init_db
from services.calendar_service import CalendarService
from services.user_service import PLATFORM_TELEGRAM, UserService

ADMIN_ID = 9001
USER_A = 1001
USER_B = 1002


class TestCategoriesGlobalPersonal(unittest.TestCase):
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

    @classmethod
    def _ensure_user(cls, platform_user_id: int, name: str, *, is_admin: bool = False) -> str:
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

    def setUp(self):
        self.admin_id = self._ensure_user(ADMIN_ID, "Admin", is_admin=True)
        self.user_a_id = self._ensure_user(USER_A, "User A")
        self.user_b_id = self._ensure_user(USER_B, "User B")
        self.svc = CalendarService()
        with get_session() as session:
            session.execute(__import__("sqlalchemy").delete(Category))

    def _count_global_categories(self) -> int:
        with get_session() as session:
            stmt = __import__("sqlalchemy").select(Category).where(
                Category.user_id.is_(None)
            )
            return len(session.scalars(stmt).all())

    def test_create_global_categories_single_row_per_name(self):
        result = self.svc.create_global_categories(["Arbeit", "Einkauf"])
        self.assertEqual(result.created_count, 2)
        self.assertEqual(result.total_global, 2)
        self.assertEqual(self._count_global_categories(), 2)

    def test_create_global_categories_idempotent(self):
        self.svc.create_global_categories(["Arbeit", "Einkauf"])
        result = self.svc.create_global_categories(["Arbeit", "Einkauf"])
        self.assertEqual(result.created_count, 0)
        self.assertEqual(result.total_global, 2)
        self.assertEqual(self._count_global_categories(), 2)

    def test_both_users_see_same_global_id(self):
        self.svc.create_global_categories(["Arbeit"])
        list_a = self.svc.list_categories_dto(self.user_a_id)
        list_b = self.svc.list_categories_dto(self.user_b_id)
        global_a = [c for c in list_a if c.is_global]
        global_b = [c for c in list_b if c.is_global]
        self.assertEqual(len(global_a), 1)
        self.assertEqual(len(global_b), 1)
        self.assertEqual(global_a[0].id, global_b[0].id)
        self.assertEqual(global_a[0].name, "Arbeit")

    def test_personal_category_only_for_owner(self):
        status, dto = self.svc.create_personal_category(self.user_a_id, "Privat")
        self.assertEqual(status, "created")
        self.assertFalse(dto.is_global)

        list_a = self.svc.list_categories_dto(self.user_a_id)
        list_b = self.svc.list_categories_dto(self.user_b_id)
        personal_a = [c for c in list_a if not c.is_global]
        personal_b = [c for c in list_b if not c.is_global]
        self.assertEqual(len(personal_a), 1)
        self.assertEqual(personal_a[0].name, "Privat")
        self.assertEqual(len(personal_b), 0)

    def test_personal_duplicate(self):
        self.svc.create_personal_category(self.user_a_id, "Privat")
        status, _ = self.svc.create_personal_category(self.user_a_id, "Privat")
        self.assertEqual(status, "duplicate")

    def test_personal_global_collision(self):
        self.svc.create_global_categories(["Arbeit"])
        status, dto = self.svc.create_personal_category(self.user_a_id, "Arbeit")
        self.assertEqual(status, "global_collision")
        self.assertIsNone(dto)

    def test_assign_global_category_to_user_event(self):
        self.svc.create_global_categories(["Arbeit"])
        global_cats = [
            c for c in self.svc.list_categories_dto(self.user_a_id) if c.is_global
        ]
        from datetime import datetime

        event = self.svc.create_event(
            owner_id=self.user_a_id,
            context_chat_id=USER_A,
            title="Test",
            starts_at=datetime(2026, 6, 1, 10, 0),
            category_id=global_cats[0].id,
        )
        self.assertEqual(event.category_name, "Arbeit")

    def test_add_allowed_user_sees_globals_without_seed(self):
        self.svc.create_global_categories(["Arbeit", "Einkauf"])
        user_svc = UserService()
        success, _ = user_svc.add_allowed_user(str(ADMIN_ID), "9999", "Neu")
        self.assertTrue(success)
        with get_session() as session:
            stmt = __import__("sqlalchemy").select(UserIdentity).where(
                UserIdentity.platform_user_id == "9999"
            )
            identity = session.scalars(stmt).first()
            cats = self.svc.list_categories_dto(identity.user_id)
            global_names = [c.name for c in cats if c.is_global]
        self.assertEqual(global_names, ["Arbeit", "Einkauf"])


if __name__ == "__main__":
    unittest.main()
