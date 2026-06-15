"""Tests for recurring event RRULEs (RFC 5545) and display labels."""
import unittest
import uuid
from datetime import datetime, timedelta

from dateutil.rrule import rrulestr

from services.calendar_service import (
    CalendarService,
    EventDTO,
    build_monthly_by_weekday,
)
from services.rrule_util import recurrence_label
from services.event_filter import (
    EventFilterPreset,
    _first_occurrence_in_range,
    apply_filter,
)


class TestBuildRrule(unittest.TestCase):
    def test_biweekly(self):
        is_recurring, rrule = CalendarService.build_rrule("biweekly")
        self.assertTrue(is_recurring)
        self.assertEqual(rrule, "FREQ=WEEKLY;INTERVAL=2")

    def test_monthly_by_weekday_first_monday(self):
        rrule = build_monthly_by_weekday("MO", 1)
        self.assertEqual(rrule, "FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1")
        is_recurring, built = CalendarService.build_rrule(
            "monthly_byweekday", weekday="MO", position=1
        )
        self.assertTrue(is_recurring)
        self.assertEqual(built, rrule)

    def test_monthly_by_weekday_third_thursday(self):
        is_recurring, rrule = CalendarService.build_rrule(
            "monthly_byweekday", weekday="TH", position=3
        )
        self.assertEqual(rrule, "FREQ=MONTHLY;BYDAY=TH;BYSETPOS=3")

    def test_monthly_by_weekday_last_sunday(self):
        is_recurring, rrule = CalendarService.build_rrule(
            "monthly_byweekday", weekday="SU", position=-1
        )
        self.assertEqual(rrule, "FREQ=MONTHLY;BYDAY=SU;BYSETPOS=-1")


class TestRecurrenceLabel(unittest.TestCase):
    def test_biweekly_label(self):
        self.assertEqual(recurrence_label("FREQ=WEEKLY;INTERVAL=2"), "alle 2 Wo.")

    def test_weekly_byday_label(self):
        self.assertEqual(
            recurrence_label("FREQ=WEEKLY;BYDAY=MO"),
            "jeden Montag",
        )

    def test_biweekly_byday_label(self):
        self.assertEqual(
            recurrence_label("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO"),
            "alle 2 Wo., jeden Montag",
        )

    def test_first_monday_label(self):
        self.assertEqual(
            recurrence_label("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1"),
            "jeden 1. Montag",
        )

    def test_last_sunday_label(self):
        self.assertEqual(
            recurrence_label("FREQ=MONTHLY;BYDAY=SU;BYSETPOS=-1"),
            "jeden letzten Sonntag",
        )

    def test_third_thursday_label(self):
        self.assertEqual(
            recurrence_label("FREQ=MONTHLY;BYDAY=TH;BYSETPOS=3"),
            "jeden 3. Donnerstag",
        )


class TestBiweeklyOccurrences(unittest.TestCase):
    def test_interval_is_fourteen_days(self):
        start = datetime(2026, 5, 20, 10, 0)
        rule = rrulestr("FREQ=WEEKLY;INTERVAL=2", dtstart=start)
        second = rule.after(start, inc=False)
        third = rule.after(second, inc=False)
        self.assertEqual((second - start).days, 14)
        self.assertEqual((third - second).days, 14)


class TestYearFilterByWeekday(unittest.TestCase):
    def test_first_monday_in_calendar_year(self):
        event = EventDTO(
            id=str(uuid.uuid4()),
            owner_id="user-1",
            context_chat_id=1,
            title="Serie",
            starts_at=datetime(2026, 1, 1, 9, 0),
            ends_at=datetime(2026, 1, 1, 10, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=True,
            rrule="FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1",
        )
        occ = _first_occurrence_in_range(
            event, datetime(2026, 1, 1), datetime(2027, 1, 1)
        )
        self.assertIsNotNone(occ)
        self.assertEqual(occ, datetime(2026, 1, 5, 9, 0))

        filtered = apply_filter(
            [event], EventFilterPreset.CALENDAR_YEAR, year=2026
        )
        self.assertEqual(len(filtered), 12)
        self.assertEqual(filtered[0].display_starts_at, datetime(2026, 1, 5, 9, 0))

    def test_weekly_series_expands_all_occurrences_in_month(self):
        event = EventDTO(
            id=str(uuid.uuid4()),
            owner_id="user-1",
            context_chat_id=1,
            title="Wöchentlich",
            starts_at=datetime(2026, 5, 6, 10, 0),
            ends_at=datetime(2026, 5, 6, 11, 0),
            is_all_day=False,
            reminder_offset=0,
            is_recurring=True,
            rrule="FREQ=WEEKLY",
        )
        filtered = apply_filter(
            [event], EventFilterPreset.CALENDAR_MONTH, year=2026, month=5
        )
        self.assertEqual(len(filtered), 4)
        self.assertEqual(
            [e.display_starts_at for e in filtered],
            [
                datetime(2026, 5, 6, 10, 0),
                datetime(2026, 5, 13, 10, 0),
                datetime(2026, 5, 20, 10, 0),
                datetime(2026, 5, 27, 10, 0),
            ],
        )
        self.assertTrue(all(e.id == event.id for e in filtered))

    def test_rrule_between_covers_full_year(self):
        start = datetime(2026, 1, 1, 9, 0)
        rule = rrulestr("FREQ=MONTHLY;BYDAY=MO;BYSETPOS=1", dtstart=start)
        occurrences = rule.between(
            datetime(2026, 1, 1),
            datetime(2026, 12, 31, 23, 59, 59),
            inc=True,
        )
        self.assertEqual(len(occurrences), 12)


if __name__ == "__main__":
    unittest.main()
