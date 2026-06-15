"""Tests for interactive event UI and callback data."""
import unittest
import uuid
from datetime import datetime, timedelta

from services.calendar_service import EventDTO
from services.event_filter import (
    EventFilterPreset,
    ParsedFilter,
    parsed_filter_from_dict,
    parsed_filter_to_dict,
    ui_filter_empty_label,
)
from views.message_factory import MessageFactory


class TestInteractiveUI(unittest.TestCase):
    def test_callback_data_under_64_chars(self):
        event_id = str(uuid.uuid4())
        occ = datetime(2026, 5, 29, 16, 0)
        from services.occurrence_util import build_occ_callback, build_view_evt_callback

        self.assertLessEqual(len(build_view_evt_callback(event_id)), 64)
        self.assertLessEqual(len(build_view_evt_callback(event_id, occ)), 64)
        self.assertLessEqual(len(build_occ_callback("del_one_", event_id, occ)), 64)
        self.assertLessEqual(len(f"edit_ttl_{event_id}"), 64)
        self.assertLessEqual(len(f"del_cfm_{event_id}"), 64)
        self.assertLessEqual(len("filter_all"), 64)
        self.assertLessEqual(len("noop"), 64)

    def test_create_events_view_structure(self):
        event_id = str(uuid.uuid4())
        event = EventDTO(
            id=event_id,
            owner_id="user-1",
            context_chat_id=-1,
            title="Testtermin",
            starts_at=datetime(2026, 6, 1, 7, 0),
            ends_at=datetime(2026, 6, 1, 8, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=False,
            rrule=None,
        )
        text, keyboard = MessageFactory.create_events_view(
            [event], active_filter="future"
        )
        self.assertIn("antippen", text)
        rows = keyboard.inline_keyboard
        self.assertEqual(len(rows), 5)
        self.assertEqual(len(rows[0]), 3)
        self.assertEqual(rows[1][0].callback_data, "termfilter:today")
        self.assertEqual(rows[2][0].callback_data, "termfilter:pick:month")
        self.assertEqual(rows[3][0].callback_data, "noop")
        self.assertEqual(rows[4][0].callback_data, f"view_evt_{event_id}")

    def test_event_list_button_label_formats(self):
        normal = EventDTO(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            owner_id="user-1",
            context_chat_id=1,
            title="Taschengeld",
            starts_at=datetime(2026, 6, 1, 7, 0),
            ends_at=datetime(2026, 6, 1, 8, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=False,
            rrule=None,
        )
        label = MessageFactory._event_list_button_label(normal)
        self.assertTrue(label.startswith("📅"))
        self.assertIn("01.06.", label)
        self.assertIn("07:00", label)
        self.assertIn("Taschengeld", label)
        self.assertNotIn("#", label)

        series = EventDTO(
            id="b2c3d4e5-f6a7-8901-bcde-f12345678901",
            owner_id="user-1",
            context_chat_id=1,
            title="Wöchentlich",
            starts_at=datetime(2026, 6, 1, 7, 0),
            ends_at=datetime(2026, 6, 1, 8, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=True,
            rrule="FREQ=WEEKLY",
        )
        series_label = MessageFactory._event_list_button_label(series)
        self.assertTrue(series_label.startswith("🔄"))

    def test_event_list_button_label_moved_occurrence(self):
        moved = EventDTO(
            id="d4e5f6a7-b8c9-0123-def4-567890abcdef",
            owner_id="user-1",
            context_chat_id=1,
            title="Verschoben",
            starts_at=datetime(2026, 5, 18, 18, 0),
            ends_at=datetime(2026, 5, 18, 19, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=True,
            rrule="FREQ=WEEKLY",
            display_starts_at=datetime(2026, 5, 26, 10, 0),
            occurrence_ends_at=datetime(2026, 5, 26, 11, 0),
            occurrence_original_start=datetime(2026, 5, 25, 18, 0),
            occurrence_is_moved=True,
        )
        label = MessageFactory._event_list_button_label(moved)
        self.assertTrue(label.startswith("↪️"))
        self.assertIn("26.05.", label)

    def test_event_list_button_label_shows_date_for_multi_hour_same_day(self):
        event = EventDTO(
            id="c3d4e5f6-a7b8-9012-cdef-123456789012",
            owner_id="user-1",
            context_chat_id=1,
            title="GEV",
            starts_at=datetime(2026, 6, 25, 18, 0),
            ends_at=datetime(2026, 6, 25, 20, 0),
            is_all_day=False,
            reminder_offset=1440,
            is_recurring=False,
            rrule=None,
        )
        label = MessageFactory._event_list_button_label(event)
        self.assertIn("25.06.", label)
        self.assertIn("18:00", label)
        self.assertIn("20:00", label)
        self.assertIn("GEV", label)

    def test_event_list_button_label_with_source(self):
        event = EventDTO(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            owner_id="user-1",
            context_chat_id=-5001,
            title="Ein test",
            starts_at=datetime(2026, 6, 5, 15, 0),
            ends_at=datetime(2026, 6, 5, 17, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=False,
            rrule=None,
        )
        label = MessageFactory._event_list_button_label(
            event, source_label="Familie"
        )
        self.assertTrue(label.endswith("👥 (Familie)"))
        self.assertIn("Ein test", label)
        self.assertLessEqual(len(label), 64)

    def test_event_list_button_label_truncates_long_group_name(self):
        event = EventDTO(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            owner_id="user-1",
            context_chat_id=-5001,
            title="Änderung",
            starts_at=datetime(2026, 6, 5, 15, 7),
            ends_at=datetime(2026, 6, 5, 16, 7),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=False,
            rrule=None,
        )
        label = MessageFactory._event_list_button_label(
            event, source_label="Merken-Gruppe"
        )
        self.assertTrue(label.endswith("👥 (Merken-G)"))

    def test_event_detail_text_shows_group_source(self):
        event = EventDTO(
            id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            owner_id="user-1",
            context_chat_id=-5001,
            title="Ein test",
            starts_at=datetime(2026, 6, 5, 15, 0),
            ends_at=datetime(2026, 6, 5, 17, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=False,
            rrule=None,
        )
        text = MessageFactory.event_detail_text(event, source_label="Familie")
        self.assertIn("👥 Gruppe: Familie", text)

    def test_filter_buttons_active_mark(self):
        _, keyboard = MessageFactory.create_events_view(
            [], active_filter="all", active_period="today"
        )
        scope_labels = [btn.text for btn in keyboard.inline_keyboard[0]]
        period_labels = [btn.text for row in keyboard.inline_keyboard[1:3] for btn in row]
        self.assertTrue(any("·" in lbl and "Alle" in lbl for lbl in scope_labels))
        self.assertTrue(any("·" in lbl and "Heute" in lbl for lbl in period_labels))
        self.assertTrue(
            any("Monat & Jahr" in btn.text for btn in keyboard.inline_keyboard[2])
        )

    def test_detail_keyboard_has_required_buttons(self):
        event_id = str(uuid.uuid4())
        keyboard = MessageFactory.create_event_detail_keyboard(
            event_id, is_recurring=False
        )
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        self.assertIn(f"edit_ttl_{event_id}", all_data)
        self.assertIn(f"edit_tme_{event_id}", all_data)
        self.assertIn(f"edit_rrc_{event_id}", all_data)
        self.assertIn(f"edit_rem_{event_id}", all_data)
        self.assertIn(f"del_cfm_{event_id}", all_data)
        self.assertIn("list_all_events", all_data)

    def test_detail_keyboard_recurring_occurrence_uses_scope_callbacks(self):
        event_id = str(uuid.uuid4())
        occ = datetime(2026, 5, 25, 18, 0)
        from services.occurrence_util import build_occ_callback

        keyboard = MessageFactory.create_event_detail_keyboard(
            event_id,
            occurrence_original_start=occ,
            is_recurring=True,
        )
        all_data = [
            btn.callback_data
            for row in keyboard.inline_keyboard
            for btn in row
        ]
        self.assertIn(build_occ_callback("del_ask_", event_id, occ), all_data)
        self.assertIn(build_occ_callback("tme_ask_", event_id, occ), all_data)

    def test_parsed_filter_roundtrip(self):
        original = ParsedFilter(
            EventFilterPreset.CALENDAR_MONTH, year=2026, month=6
        )
        restored = parsed_filter_from_dict(parsed_filter_to_dict(original))
        self.assertEqual(restored.preset, original.preset)
        self.assertEqual(restored.year, 2026)
        self.assertEqual(restored.month, 6)

    def test_ui_filter_empty_label(self):
        self.assertEqual(ui_filter_empty_label("all"), "Alle (12 Mon.)")
        self.assertEqual(ui_filter_empty_label("recurring"), "Serien")


if __name__ == "__main__":
    unittest.main()
