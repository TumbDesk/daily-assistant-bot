"""Tests for TravelService."""
import os
import unittest
from datetime import date

from database import User, get_session, init_db
from services.travel import TravelService, TravelTripDTO, get_travel_service


class TestTravelService(unittest.TestCase):
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
        cls.service = TravelService()

    @classmethod
    def _create_user(cls) -> str:
        with get_session() as session:
            user = User(name="Test")
            session.add(user)
            session.flush()
            return user.id

    def test_add_trip_stores_coordinates(self):
        user_id = self._create_user()
        self.service.add_trip(
            user_id,
            "Berlin, Berlin, Deutschland",
            52.52,
            13.405,
            date(2026, 6, 1),
            date(2026, 6, 8),
        )
        active = self.service.get_active_trip(user_id, on_date=date(2026, 6, 4))
        self.assertEqual(active.destination, "Berlin, Berlin, Deutschland")
        self.assertAlmostEqual(active.latitude, 52.52)
        self.assertAlmostEqual(active.longitude, 13.405)

    def test_get_active_trip_inclusive_boundaries(self):
        user_id = self._create_user()
        self.service.add_trip(
            user_id,
            "Berlin",
            52.52,
            13.405,
            date(2026, 6, 1),
            date(2026, 6, 8),
        )

        start = self.service.get_active_trip(user_id, on_date=date(2026, 6, 1))
        end = self.service.get_active_trip(user_id, on_date=date(2026, 6, 8))
        middle = self.service.get_active_trip(user_id, on_date=date(2026, 6, 4))

        self.assertIsInstance(start, TravelTripDTO)
        self.assertIsInstance(end, TravelTripDTO)
        self.assertIsInstance(middle, TravelTripDTO)

    def test_get_active_trip_outside_range(self):
        user_id = self._create_user()
        self.service.add_trip(
            user_id,
            "Berlin",
            52.52,
            13.405,
            date(2026, 6, 1),
            date(2026, 6, 8),
        )

        self.assertIsNone(
            self.service.get_active_trip(user_id, on_date=date(2026, 5, 31))
        )
        self.assertIsNone(
            self.service.get_active_trip(user_id, on_date=date(2026, 6, 9))
        )

    def test_add_trip_invalid_date_range_raises(self):
        user_id = self._create_user()
        with self.assertRaises(ValueError):
            self.service.add_trip(
                user_id,
                "Berlin",
                52.52,
                13.405,
                date(2026, 6, 8),
                date(2026, 6, 1),
            )

    def test_overlapping_trips_prefers_latest_start(self):
        user_id = self._create_user()
        self.service.add_trip(
            user_id,
            "Hamburg",
            53.55,
            9.99,
            date(2026, 6, 1),
            date(2026, 6, 15),
        )
        self.service.add_trip(
            user_id,
            "Berlin",
            52.52,
            13.405,
            date(2026, 6, 5),
            date(2026, 6, 10),
        )

        active = self.service.get_active_trip(user_id, on_date=date(2026, 6, 7))
        self.assertEqual(active.destination, "Berlin")

    def test_singleton(self):
        self.assertIs(get_travel_service(), get_travel_service())

    def test_list_trips_sorted_by_start_date(self):
        user_id = self._create_user()
        self.service.add_trip(
            user_id, "Hamburg", 53.55, 9.99, date(2026, 7, 1), date(2026, 7, 10)
        )
        self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        trips = self.service.list_trips(user_id)
        self.assertEqual(len(trips), 2)
        self.assertEqual(trips[0].destination, "Berlin")
        self.assertEqual(trips[1].destination, "Hamburg")

    def test_get_trip_returns_detached_object(self):
        user_id = self._create_user()
        added = self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        trip = self.service.get_trip(user_id, added.id)
        self.assertIsNotNone(trip)
        self.assertEqual(trip.destination, "Berlin")

    def test_get_trip_wrong_user_returns_none(self):
        user_a = self._create_user()
        user_b = self._create_user()
        added = self.service.add_trip(
            user_a, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        self.assertIsNone(self.service.get_trip(user_b, added.id))

    def test_delete_trip(self):
        user_id = self._create_user()
        added = self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        self.assertTrue(self.service.delete_trip(user_id, added.id))
        self.assertIsNone(self.service.get_trip(user_id, added.id))

    def test_delete_trip_wrong_user_returns_false(self):
        user_a = self._create_user()
        user_b = self._create_user()
        added = self.service.add_trip(
            user_a, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        self.assertFalse(self.service.delete_trip(user_b, added.id))
        self.assertIsNotNone(self.service.get_trip(user_a, added.id))

    def test_update_trip_destination(self):
        user_id = self._create_user()
        added = self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        updated = self.service.update_trip(
            user_id,
            added.id,
            destination="Hamburg",
            latitude=53.55,
            longitude=9.99,
        )
        self.assertEqual(updated.destination, "Hamburg")
        self.assertAlmostEqual(updated.latitude, 53.55)

    def test_update_trip_dates(self):
        user_id = self._create_user()
        added = self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        updated = self.service.update_trip(
            user_id,
            added.id,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 15),
        )
        self.assertEqual(updated.start_date, date(2026, 7, 1))
        self.assertEqual(updated.end_date, date(2026, 7, 15))

    def test_update_trip_invalid_date_range_raises(self):
        user_id = self._create_user()
        added = self.service.add_trip(
            user_id, "Berlin", 52.52, 13.405, date(2026, 6, 1), date(2026, 6, 8)
        )

        with self.assertRaises(ValueError):
            self.service.update_trip(
                user_id,
                added.id,
                start_date=date(2026, 6, 10),
                end_date=date(2026, 6, 1),
            )

    def test_update_trip_not_found_raises(self):
        user_id = self._create_user()
        with self.assertRaises(ValueError):
            self.service.update_trip(user_id, 9999, destination="Berlin")


class TestReiseParser(unittest.TestCase):
    def test_parse_reise_args(self):
        from handlers.travel_handler import _parse_reise_args

        destination, start, end = _parse_reise_args(
            ["Berlin", "01.06.2026", "-", "08.06.2026"]
        )
        self.assertEqual(destination, "Berlin")
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 8))

    def test_parse_reise_args_multi_word_destination(self):
        from handlers.travel_handler import _parse_reise_args

        destination, start, end = _parse_reise_args(
            ["New", "York", "01.06.2026", "-", "08.06.2026"]
        )
        self.assertEqual(destination, "New York")
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 8))

    def test_parse_date_range(self):
        from handlers.travel_handler import parse_date_range

        start, end = parse_date_range("01.06.2026 - 08.06.2026")
        self.assertEqual(start, date(2026, 6, 1))
        self.assertEqual(end, date(2026, 6, 8))

    def test_parse_date_range_invalid(self):
        from handlers.travel_handler import parse_date_range

        with self.assertRaises(ValueError):
            parse_date_range("ungültig")


if __name__ == "__main__":
    unittest.main()
