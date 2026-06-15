"""English parser tests for locale-aware event parsing."""
import unittest
from datetime import date, datetime
from unittest.mock import patch

from services.parser import TerminParseError, parse_event_text, parse_termin_text
from services.types import CategoryDTO

_BASE = datetime(2026, 5, 21, 10, 0)


class TestParserEnglish(unittest.TestCase):
    @patch("services.parser.now")
    def test_tomorrow_at_3pm_default_end_plus_one_hour(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text("Meeting tomorrow at 3pm", base=_BASE, locale="en")
        self.assertEqual(parsed.title, "Meeting")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 15, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 16, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_inline_time_range_same_day(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting tomorrow from 10am to 12pm",
            base=_BASE,
            locale="en",
        )
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 10, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 12, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_duration_for_two_hours(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Workshop for 2 hours tomorrow at 2pm",
            base=_BASE,
            locale="en",
        )
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 22, 14, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 5, 22, 16, 0))
        self.assertFalse(parsed.is_all_day)

    @patch("services.parser.now")
    def test_multi_day_all_day_trip(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Vacation 06/05 until 06/12/2026",
            base=_BASE,
            locale="en",
        )
        self.assertEqual(parsed.title, "Vacation")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 5, 0, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 12, 23, 59, 59))
        self.assertTrue(parsed.is_all_day)

    @patch("services.parser.now")
    def test_weekly_every_monday(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Trash pickup tomorrow every 2 weeks until end of July",
            base=_BASE,
            locale="en",
        )
        self.assertTrue(parsed.is_recurring)
        self.assertIn("INTERVAL=2", parsed.rrule)
        self.assertEqual(parsed.until_date, date(2026, 7, 31))

    @patch("services.parser.now")
    def test_reminder_one_day_before(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting tomorrow at 10am, reminder 1 day before",
            base=_BASE,
            locale="en",
        )
        self.assertEqual(parsed.reminder_offset, 24 * 60)

    @patch("services.parser.now")
    def test_category_prefix_and_flags(self, mock_now):
        mock_now.return_value = _BASE
        categories = [CategoryDTO(1, "Work", is_global=True)]
        parsed = parse_event_text(
            "Work: Review next Tuesday at 2pm #important",
            user_categories=categories,
            base=_BASE,
            locale="en",
        )
        self.assertEqual(parsed.category_id, 1)
        self.assertEqual(parsed.flag_names, ["important"])
        self.assertIn("Review", parsed.title)

    @patch("services.parser.now")
    def test_no_datetime_raises(self, mock_now):
        mock_now.return_value = _BASE
        with self.assertRaises(TerminParseError):
            parse_termin_text("Title only without time", base=_BASE, locale="en")


if __name__ == "__main__":
    unittest.main()
