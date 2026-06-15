import unittest
from datetime import date, datetime
from unittest.mock import patch

from services.rrule_util import recurrence_label
from services.parser import TerminParseError, parse_termin_text

_BASE = datetime(2026, 5, 21, 10, 0)


class TestTerminParser(unittest.TestCase):
    @patch("services.parser.now")
    def test_example_sentence_full(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Müllentleerung Garten in 3 Tagen um 07:00 alle 14 Tage bis 30.10.2026",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Müllentleerung Garten")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 24, 7, 0))
        self.assertTrue(parsed.is_recurring)
        self.assertIn("FREQ=DAILY", parsed.rrule)
        self.assertIn("INTERVAL=14", parsed.rrule)
        self.assertIn("UNTIL=", parsed.rrule)
        self.assertEqual(parsed.until_date, date(2026, 10, 30))

    @patch("services.parser.now")
    def test_single_appointment_no_recurrence(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Team-Meeting morgen um 14:30",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Team-Meeting")
        self.assertFalse(parsed.is_recurring)
        self.assertIsNone(parsed.rrule)
        self.assertEqual(parsed.starts_at.date(), date(2026, 5, 22))
        self.assertEqual(parsed.starts_at.hour, 14)
        self.assertEqual(parsed.starts_at.minute, 30)

    def test_empty_text_raises(self):
        with self.assertRaises(TerminParseError):
            parse_termin_text("   ", base=_BASE, locale="de")

    @patch("services.parser.now")
    def test_no_datetime_raises(self, mock_now):
        mock_now.return_value = _BASE
        with self.assertRaises(TerminParseError):
            parse_termin_text("Nur ein Titel ohne Zeit", base=_BASE, locale="de")

    @patch("services.parser.now")
    def test_until_before_start_raises(self, mock_now):
        mock_now.return_value = _BASE
        with self.assertRaises(TerminParseError):
            parse_termin_text(
                "Test in 5 Tagen um 10:00 täglich bis 01.05.2026",
                base=_BASE,
            locale="de",
            )

    @patch("services.parser.now")
    def test_weekly_interval(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Sport jeden zweiten Tag in 1 Woche um 18:00 alle 2 Wochen",
            base=_BASE,
            locale="de",
        )
        self.assertTrue(parsed.is_recurring)
        self.assertIn("FREQ=WEEKLY", parsed.rrule)
        self.assertIn("INTERVAL=2", parsed.rrule)

    def test_recurrence_label_interval_14_days(self):
        label = recurrence_label("FREQ=DAILY;INTERVAL=14;UNTIL=20261030T225959")
        self.assertIn("alle 14 Tage", label)
        self.assertIn("30.10.2026", label)

    @patch("services.parser.now")
    def test_aufbau_festzelt_naechsten_samstag_um_9(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Aufbau Festzelt nächsten Samstag um 9 Uhr",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Aufbau Festzelt")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 23, 9, 0))
        self.assertFalse(parsed.is_recurring)

    @patch("services.parser.now")
    def test_gev_pkg_numeric_date_short_year(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "GEV PKG, am 04.06.26 um 18:00 Uhr, erinnerung 1 tag vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "GEV PKG")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 4, 18, 0))
        self.assertEqual(parsed.reminder_offset, 1440)

    @patch("services.parser.now")
    def test_muellentleerung_am_20_mai_mit_serie_und_erinnerung(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Müllentleerung Garten, am 20. Mai 2026 um 7 Uhr, "
            "alle 14 Tage, Erinnerung 13h vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Müllentleerung Garten")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 20, 7, 0))
        self.assertTrue(parsed.is_recurring)
        self.assertIn("INTERVAL=14", parsed.rrule)
        self.assertEqual(parsed.reminder_offset, 780)

    @patch("services.parser.now")
    def test_reminder_3h_vorher(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting morgen um 10:00, 3h vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.reminder_offset, 180)

    @patch("services.parser.now")
    def test_reminder_35m_vorher(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Arzttermin übermorgen um 14:00, 35m vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.reminder_offset, 35)

    @patch("services.parser.now")
    def test_reminder_vortag(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Lieferung in 2 Tagen um 08:00, am Vortag",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.reminder_offset, 1440)

    @patch("services.parser.now")
    def test_reminder_1_tag_vorher_with_event(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Aufbau Festzelt nächsten Samstag um 9 Uhr, Erinnerung 1 Tag vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Aufbau Festzelt")
        self.assertEqual(parsed.starts_at, datetime(2026, 5, 23, 9, 0))
        self.assertEqual(parsed.reminder_offset, 1440)

    @patch("services.parser.now")
    def test_reminder_2_tage_vorher(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting morgen um 10:00, Erinnerung 2 Tage vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Meeting")
        self.assertEqual(parsed.reminder_offset, 2 * 24 * 60)

    @patch("services.parser.now")
    def test_reminder_3_stunden_vorher_with_erinnerung_prefix(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting morgen um 10:00, Erinnerung 3 Stunden vorher",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Meeting")
        self.assertEqual(parsed.reminder_offset, 180)

    @patch("services.parser.now")
    def test_reminder_too_large_raises(self, mock_now):
        mock_now.return_value = _BASE
        with self.assertRaises(TerminParseError):
            parse_termin_text(
                "Test morgen um 10:00, 5000 Stunden vorher",
                base=_BASE,
            locale="de",
            )

    @patch("services.parser.now")
    def test_muellabholung_morgen_bis_ende_juli(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Müllabholung morgen alle 14 Tage bis ende Juli",
            base=_BASE,
            locale="de",
        )
        self.assertEqual(parsed.title, "Müllabholung")
        self.assertEqual(parsed.starts_at.date(), date(2026, 5, 22))
        self.assertTrue(parsed.is_recurring)
        self.assertIn("INTERVAL=14", parsed.rrule)
        self.assertEqual(parsed.until_date, date(2026, 7, 31))
        self.assertIn("UNTIL=", parsed.rrule)

    @patch("services.parser.now")
    def test_weekly_jeden_montag_with_time_range(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 2, 10, 0)
        parsed = parse_termin_text(
            "serientermin 01.06.2026 09:00-11:00 Uhr. Jeden Montag",
            base=datetime(2026, 6, 2, 10, 0),
            locale="de",
        )
        self.assertEqual(parsed.title, "serientermin")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 1, 9, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 1, 11, 0))
        self.assertTrue(parsed.is_recurring)
        self.assertEqual(parsed.rrule, "FREQ=WEEKLY;BYDAY=MO")

    @patch("services.parser.now")
    def test_weekly_jede_woche_montag_with_time_range(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 2, 10, 0)
        parsed = parse_termin_text(
            "serientermin 01.06.2026 09:00-11:00 Uhr. jede Woche Montag",
            base=datetime(2026, 6, 2, 10, 0),
            locale="de",
        )
        self.assertEqual(parsed.title, "serientermin")
        self.assertEqual(parsed.starts_at, datetime(2026, 6, 1, 9, 0))
        self.assertEqual(parsed.ends_at, datetime(2026, 6, 1, 11, 0))
        self.assertTrue(parsed.is_recurring)
        self.assertEqual(parsed.rrule, "FREQ=WEEKLY;BYDAY=MO")

    @patch("services.parser.now")
    def test_jeden_ersten_montag_is_not_weekly(self, mock_now):
        mock_now.return_value = _BASE
        parsed = parse_termin_text(
            "Meeting jeden 1. Montag um 10:00",
            base=_BASE,
            locale="de",
        )
        self.assertFalse(parsed.is_recurring)
        self.assertIsNone(parsed.rrule)

    @patch("services.parser.now")
    def test_weekly_keyword_regression_without_byday(self, mock_now):
        mock_now.return_value = datetime(2026, 6, 2, 10, 0)
        parsed = parse_termin_text(
            "Training 01.06.2026 09:00 wöchentlich",
            base=datetime(2026, 6, 2, 10, 0),
            locale="de",
        )
        self.assertTrue(parsed.is_recurring)
        self.assertEqual(parsed.rrule, "FREQ=WEEKLY")
        self.assertNotIn("BYDAY", parsed.rrule or "")


if __name__ == "__main__":
    unittest.main()
