"""Tests for travel UI (list and detail keyboards)."""
import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from views.message_factory import MessageFactory


class TestTravelUi(unittest.TestCase):
    def _trip(
        self,
        trip_id: int,
        destination: str,
        start_date: date,
        end_date: date,
    ):
        return SimpleNamespace(
            id=trip_id,
            destination=destination,
            start_date=start_date,
            end_date=end_date,
        )

    def test_list_button_labels(self):
        trips = [
            self._trip(1, "Berlin", date(2026, 6, 1), date(2026, 6, 8)),
            self._trip(2, "Hamburg", date(2026, 7, 10), date(2026, 7, 20)),
        ]
        labels = [MessageFactory.trip_list_button_label(t) for t in trips]
        self.assertEqual(
            labels,
            ["01.06.–08.06. Berlin", "10.07.–20.07. Hamburg"],
        )

    def test_create_trips_view_has_callbacks(self):
        trips = [self._trip(42, "Berlin", date(2026, 6, 1), date(2026, 6, 8))]
        text, keyboard = MessageFactory.create_trips_view(trips)

        self.assertIn("Reisen", text)
        all_data = [
            btn.callback_data for row in keyboard.inline_keyboard for btn in row
        ]
        self.assertEqual(all_data, ["view_trip_42"])

    def test_empty_trips_view(self):
        text, keyboard = MessageFactory.create_trips_view([])

        self.assertIn("Noch keine Reisen", text)
        self.assertEqual(len(keyboard.inline_keyboard), 0)

    def test_detail_keyboard_has_required_buttons(self):
        keyboard = MessageFactory.create_trip_detail_keyboard(7)
        all_data = [
            btn.callback_data for row in keyboard.inline_keyboard for btn in row
        ]
        self.assertIn("edit_trip_dest_7", all_data)
        self.assertIn("edit_trip_dates_7", all_data)
        self.assertIn("del_trip_7", all_data)
        self.assertIn("list_trips", all_data)

    @patch("services.timezone_util.now")
    def test_trip_detail_text_active(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 4, 12, 0)
        trip = self._trip(1, "Berlin", date(2026, 6, 1), date(2026, 6, 8))
        text = MessageFactory.trip_detail_text(trip)

        self.assertIn("Berlin", text)
        self.assertIn("01.06.2026", text)
        self.assertIn("08.06.2026", text)
        self.assertIn("aktiv", text)

    @patch("services.timezone_util.now")
    def test_trip_detail_text_inactive(self, mock_now):
        mock_now.return_value = datetime(2026, 5, 1, 12, 0)
        trip = self._trip(1, "Berlin", date(2026, 6, 1), date(2026, 6, 8))
        text = MessageFactory.trip_detail_text(trip)

        self.assertIn("Berlin", text)
        self.assertNotIn("aktiv", text)
