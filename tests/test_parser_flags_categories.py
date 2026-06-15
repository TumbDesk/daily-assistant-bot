"""Parser tests for hashtags and category prefix."""
import unittest
from datetime import datetime
from unittest.mock import patch

from services.types import CategoryDTO
from services.parser import (
    TerminParseError,
    parse_event_text,
    parse_termin_text,
)

_BASE = datetime(2026, 5, 20, 12, 0)


class TestParserFlagsCategories(unittest.TestCase):
    @patch("services.parser.now")
    def test_extracts_flags_from_title(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting #wichtig #Team nächsten Montag um 10 Uhr",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.flag_names, ["wichtig", "team"])
        self.assertNotIn("#", parsed.title)
        self.assertIn("Meeting", parsed.title)

    @patch("services.parser.now")
    def test_category_prefix_when_known(self, mock_now):
        mock_now.return_value = _BASE
        categories = [
            CategoryDTO(1, "Arbeit", is_global=True),
            CategoryDTO(2, "Einkauf", is_global=True),
        ]
        parsed = parse_event_text(
            "Arbeit: Review nächsten Dienstag um 14 Uhr",
            user_categories=categories,
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.category_id, 1)
        self.assertIn("Review", parsed.title)
        self.assertNotIn("Arbeit:", parsed.title)

    @patch("services.parser.now")
    def test_unknown_prefix_stays_in_title(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_event_text(
            "Privat: Spaziergang morgen um 8 Uhr",
            user_categories=[CategoryDTO(1, "Arbeit", is_global=True)],
            base=_BASE,
            locale="de",
        )
        self.assertIsNone(parsed.category_id)
        self.assertIn("Privat:", parsed.title)

    @patch("services.parser.now")
    def test_fallback_without_meta(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text("Kaffee morgen um 9 Uhr", base=_BASE, locale="de")
        self.assertIsNone(parsed.category_id)
        self.assertEqual(parsed.flag_names, [])

    @patch("services.parser.now")
    def test_ein_tag_vorher_reminder_with_category_and_flags(self, mock_now):
        mock_now.return_value = _BASE
        categories = [CategoryDTO(1, "Schule", is_global=True)]
        parsed = parse_event_text(
            "Schule: GEV 25.06.2026 von 18 bis 20 Uhr, Erinnerung ein Tag vorher #PKG",
            user_categories=categories,
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "GEV")
        self.assertEqual(parsed.reminder_offset, 24 * 60)
        self.assertEqual(parsed.category_id, 1)
        self.assertEqual(parsed.flag_names, ["pkg"])
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 25, 18, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 25, 20, 0))

    @patch("services.parser.now")
    def test_zwei_tag_vorher_reminder_with_category_and_flags(self, mock_now):
        mock_now.return_value = _BASE
        categories = [CategoryDTO(1, "Schule", is_global=True)]
        parsed = parse_event_text(
            "Schule: GEV 25.06.2026 von 18 bis 20 Uhr, Erinnerung zwei Tag vorher #PKG",
            user_categories=categories,
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "GEV")
        self.assertEqual(parsed.reminder_offset, 2 * 24 * 60)
        self.assertEqual(parsed.category_id, 1)
        self.assertEqual(parsed.flag_names, ["pkg"])

    def test_empty_text_raises(self):
        with self.assertRaises(TerminParseError):
            parse_termin_text("   ", base=_BASE, locale="de")


if __name__ == "__main__":
    unittest.main()
