from __future__ import annotations
import calendar as cal_mod
import re
from datetime import datetime, date, time, timedelta
from typing import Optional, Sequence

from dateparser.search import search_dates
from services.rrule_util import apply_until
from services.timezone_util import get_timezone, to_naive_local
from services.parser.base import BaseEventParser, TerminParseError


class EnglishEventParser(BaseEventParser):
    def __init__(self):
        super().__init__()
        
        # --- English Language Dictionaries ---
        self._MONTH_NAME_TO_NUM = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
            "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
            "november": 11, "december": 12,
        }
        self._MONTH_PATTERN = "|".join(self._MONTH_NAME_TO_NUM.keys())

        self._WEEKDAY_NAME_TO_NUM = {
            "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6,
        }
        self._WEEKDAY_NUM_TO_RRULE = {
            0: "MO", 1: "TU", 2: "WE", 3: "TH", 4: "FR", 5: "SA", 6: "SU",
        }
        self._WEEKDAY_PATTERN = "|".join(self._WEEKDAY_NAME_TO_NUM.keys())

        self._REMINDER_AMOUNT_WORDS = {
            "one": 1, "a": 1, "an": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7,
        }

        self._SIMPLE_RRULE = {
            "daily": "FREQ=DAILY",
            "weekly": "FREQ=WEEKLY",
            "monthly": "FREQ=MONTHLY",
        }

        self._UNIT_TO_FREQ = {
            "day": ("DAILY", "days"), "days": ("DAILY", "days"),
            "week": ("WEEKLY", "weeks"), "weeks": ("WEEKLY", "weeks"),
            "month": ("MONTHLY", "months"), "months": ("MONTHLY", "months"),
        }

        # --- English Regular Expressions ---
        self._UNTIL_PATTERN = re.compile(r"\buntil\s+(\d{1,2})[\./](\d{1,2})[\./](\d{4})\b", re.IGNORECASE)
        self._UNTIL_MONTH_END_PATTERN = re.compile(
            rf"\buntil\s+(?:end\s+of\s+)?({self._MONTH_PATTERN})(?:\s+(\d{{4}}))?\b",
            re.IGNORECASE | re.UNICODE,
        )
        self._INTERVAL_PATTERN = re.compile(r"\bevery\s+(\d+)\s*(days?|weeks?|months?)\b", re.IGNORECASE)
        self._BIWEEKLY_PATTERN = re.compile(r"\b(?:biweekly|every\s+(?:2|two)\s*weeks?)\b", re.IGNORECASE)
        self._SIMPLE_RECUR_PATTERN = re.compile(r"\b(daily|weekly|monthly)\b", re.IGNORECASE)

        self._WEEKLY_EACH_WEEKDAY_PATTERN = re.compile(
            rf"\bevery\s+(?P<day>{self._WEEKDAY_PATTERN})\b", re.IGNORECASE | re.UNICODE,
        )
        self._WEEKLY_BYDAY_PATTERN = re.compile(
            rf"\bon\s+(?P<day>{self._WEEKDAY_PATTERN})s?\b", re.IGNORECASE | re.UNICODE,
        )
        self._JEDE_WOCHE_PATTERN = re.compile(
            rf"\bevery\s+week\b(?!\s+(?:{self._WEEKDAY_PATTERN})\b)", re.IGNORECASE | re.UNICODE,
        )

        self._RELATIVE_WEEKDAY_PATTERN = re.compile(
            rf"\b(?P<rel>next|coming|following)\s+"
            rf"(?P<day>{self._WEEKDAY_PATTERN})"
            rf"(?:\s+at\s+(?P<hour>\d{{1,2}})(?::(?P<minute>\d{{2}}))?\s*(?P<ampm>am|pm)?)\b",
            re.IGNORECASE | re.UNICODE,
        )

        self._TIME_PATTERN = re.compile(r"\bat\s+(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?\b", re.IGNORECASE)
        self._BARE_TIME_PATTERN = re.compile(r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)\b", re.IGNORECASE)

        self._ENGLISH_NUMERIC_DATE_PATTERN = re.compile(
            r"\b(?:on\s+)?(?P<month>\d{1,2})[\./](?P<day>\d{1,2})[\./](?P<year>\d{2,4})"
            r"(?:\s+at\s+(?P<hour>\d{{1,2}})(?::(?P<minute>\d{{2}}))?\s*(?P<ampm>am|pm)?)?\b", re.IGNORECASE,
        )
        self._ENGLISH_ABSOLUTE_DATE_PATTERN = re.compile(
            rf"\b(?:on\s+)?(?P<month>{self._MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?"
            rf"(?:\s+at\s+(?P<hour>\d{{1,2}})(?::(?P<minute>\d{{2}}))?\s*(?P<ampm>am|pm)?)?\b",
            re.IGNORECASE | re.UNICODE,
        )

        self._REMINDER_NONE_PATTERN = re.compile(r"\b(?:without|no)\s+reminder\b", re.IGNORECASE)
        self._REMINDER_VORTAG_PATTERN = re.compile(r"\b(?:on\s+the\s+)?day\s+before\b", re.IGNORECASE)
        self._REMINDER_GENERAL_PATTERN = re.compile(
            r"\b(?:reminder\s+)?"
            r"(?:(?P<amount>\d+|one|a|an|two|three|four|five|six|seven)\s*)?"
            r"(?P<unit>days?|hours?|hrs?|h|minutes?|mins?|m)"
            r"\s*before\b", re.IGNORECASE,
        )

        self._DATE_RANGE_BIS = re.compile(
            r"\b(?P<s_month>\d{1,2})[\./](?P<s_day>\d{1,2})(?:[\./](?P<s_year>\d{2,4}))?\s+"
            r"until\s*"
            r"(?P<e_month>\d{1,2})[\./](?P<e_day>\d{1,2})(?:[\./](?P<e_year>\d{2,4}))?\b",
            re.IGNORECASE,
        )
        self._VON_BIS_NAMED_RANGE = re.compile(
            rf"\bfrom\s+"
            rf"(?P<s_month>{self._MONTH_PATTERN})\s+(?P<s_day>\d{{1,2}})(?:st|nd|rd|th)?\s*"
            rf"(?:(?P<s_year>\d{{4}})\s*)?"
            rf"until\s*"
            rf"(?P<e_month>{self._MONTH_PATTERN})\s+(?P<e_day>\d{{1,2}})(?:st|nd|rd|th)?\s*"
            rf"(?P<e_year>\d{{4}})?\b", re.IGNORECASE | re.UNICODE,
        )
        self._NAMED_DATE_RANGE_BIS = re.compile(
            rf"\b(?P<s_month>{self._MONTH_PATTERN})\s+(?P<s_day>\d{{1,2}})(?:st|nd|rd|th)?\s*"
            rf"(?:(?P<s_year>\d{{4}})\s*)?"
            rf"until\s*"
            rf"(?P<e_month>{self._MONTH_PATTERN})\s+(?P<e_day>\d{{1,2}})(?:st|nd|rd|th)?\s*"
            rf"(?P<e_year>\d{{4}})?\b", re.IGNORECASE | re.UNICODE,
        )
        self._VON_BIS_RANGE = re.compile(
            r"\bfrom\s+"
            r"(?:(?P<s_month>\d{1,2})[\./](?P<s_day>\d{1,2})[\./](?:(?P<s_year>\d{2,4}))?\s*)?"
            r"(?:at\s+(?P<s_hour>\d{1,2})(?::(?P<s_min>\d{2}))?\s*(?P<s_ampm>am|pm)?\s*)?"
            r"until\s*"
            r"(?:(?P<e_month>\d{1,2})[\./](?P<e_day>\d{1,2})[\./](?:(?P<e_year>\d{2,4}))?\s*)?"
            r"(?:at\s+(?P<e_hour>\d{1,2})(?::(?P<e_min>\d{2}))?\s*(?P<e_ampm>am|pm)?)?", re.IGNORECASE,
        )
        self._INLINE_TIME_RANGE = re.compile(
            r"\b(?:from\s+)?(?P<s_hour>\d{1,2})(?::(?P<s_min>\d{2}))?\s*(?P<s_ampm>am|pm)?\s*"
            r"(?:-|–|—|until|to)\s*"
            r"(?P<e_hour>\d{1,2})(?::(?P<e_min>\d{2}))?\s*(?P<e_ampm>am|pm)?\b", re.IGNORECASE,
        )
        self._DURATION_PATTERN = re.compile(
            r"\bfor\s+(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>hours?|hrs?|h|minutes?|mins?|m)\b", re.IGNORECASE,
        )
        self._ALL_DAY_HINT_PATTERN = re.compile(r"\ball\s*day\b", re.IGNORECASE | re.UNICODE)
        
        # --- Clean-up Leftovers ---
        self._LEFTOVER_TIME_FRAGMENT = re.compile(
            r"[,.\s]*(?:from\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:-|–|—|until|to)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?", re.IGNORECASE,
        )
        self._LEFTOVER_NAMED_RANGE_FRAGMENT = re.compile(
            rf"(?:[,.\s]*\bfrom\b)?[,.\s]*(?:{self._MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?\s*(?:\d{{4}})?\s*(?:until\s*)?(?:{self._MONTH_PATTERN})\s+\d{{1,2}}(?:st|nd|rd|th)?\s*(?:\d{{4}})?",
            re.IGNORECASE | re.UNICODE,
        )

    # --- Abstract Method Implementations ---

    def extract_recurrence(
        self, text: str, reference: date
    ) -> tuple[str, bool, Optional[str], Optional[date]]:
        cleaned = text
        base_rrule: Optional[str] = None
        reference_date = reference

        # 1. Bi-weekly parsing
        biweekly = list(self._BIWEEKLY_PATTERN.finditer(cleaned))
        if biweekly:
            base_rrule = "FREQ=WEEKLY;INTERVAL=2"
            for match in reversed(biweekly):
                cleaned = self._remove_span(cleaned, match.start(), match.end())

        # 2. Multi-unit interval matching
        interval_matches = list(self._INTERVAL_PATTERN.finditer(cleaned))
        if interval_matches and base_rrule is None:
            match = interval_matches[-1]
            count = int(match.group(1))
            unit = match.group(2).lower()
            freq, _ = self._UNIT_TO_FREQ[unit]
            if count < 1:
                raise TerminParseError("err_parse_interval_min")
            base_rrule = f"FREQ={freq};INTERVAL={count}"
            cleaned = self._remove_span(cleaned, match.start(), match.end())
            for other in reversed(interval_matches[:-1]):
                cleaned = self._remove_span(cleaned, other.start(), other.end())

        # 3. Dedicated weekday recurrence loops
        if base_rrule is None:
            each_weekday_matches = list(self._WEEKLY_EACH_WEEKDAY_PATTERN.finditer(cleaned))
            if each_weekday_matches:
                match = each_weekday_matches[-1]
                base_rrule = self._weekly_rrule_for_day(match.group("day"))
                cleaned = self._remove_span(cleaned, match.start(), match.end())
                for other in reversed(each_weekday_matches[:-1]):
                    cleaned = self._remove_span(cleaned, other.start(), other.end())

        if base_rrule is None:
            byday_matches = list(self._WEEKLY_BYDAY_PATTERN.finditer(cleaned))
            if byday_matches:
                match = byday_matches[-1]
                base_rrule = self._weekly_rrule_for_day(match.group("day"))
                cleaned = self._remove_span(cleaned, match.start(), match.end())
                for other in reversed(byday_matches[:-1]):
                    cleaned = self._remove_span(cleaned, other.start(), other.end())

        if base_rrule is None:
            jede_woche_matches = list(self._JEDE_WOCHE_PATTERN.finditer(cleaned))
            if jede_woche_matches:
                base_rrule = "FREQ=WEEKLY"
                for match in reversed(jede_woche_matches):
                    cleaned = self._remove_span(cleaned, match.start(), match.end())

        # 4. Fallback macro expressions (daily, etc.)
        simple_matches = list(self._SIMPLE_RECUR_PATTERN.finditer(cleaned))
        if simple_matches and base_rrule is None:
            match = simple_matches[-1]
            keyword = match.group(1).lower()
            base_rrule = self._SIMPLE_RRULE[keyword]
            cleaned = self._remove_span(cleaned, match.start(), match.end())

        is_recurring = base_rrule is not None
        
        # 5. Extract 'until' boundary constraint mapping if recurring
        until_date: Optional[date] = None
        if is_recurring:
            cleaned, until_date = self._extract_until_date(cleaned, reference_date)

        rrule = apply_until(base_rrule, until_date) if (is_recurring and base_rrule) else None
        return cleaned, is_recurring, rrule, until_date

    def extract_reminder(self, text: str) -> tuple[str, int]:
        candidates: list[tuple[int, int, int]] = []

        for match in self._REMINDER_NONE_PATTERN.finditer(text):
            candidates.append((match.start(), match.end(), 0))

        for match in self._REMINDER_VORTAG_PATTERN.finditer(text):
            candidates.append((match.start(), match.end(), 24 * 60))

        for match in self._REMINDER_GENERAL_PATTERN.finditer(text):
            candidates.append((match.start(), match.end(), self._reminder_match_to_minutes(match)))

        if not candidates:
            return text, 0

        start, end, offset = max(candidates, key=lambda item: item[0])
        offset = self._validate_reminder_offset(offset)
        cleaned = self._remove_span(text, start, end)
        return cleaned, offset

    def extract_datetime_or_range(self, text: str, reference: datetime) -> tuple[str, datetime, Optional[datetime], bool, Optional[timedelta]]:
        cleaned, duration = self._extract_duration(text)
        cleaned, all_day_hint = self._extract_all_day_hint(cleaned)

        # 1. Attempt scanning structured range tokens (from...until)
        range_result = self._extract_date_range(cleaned, reference)
        if range_result is not None:
            cleaned, starts_at, ends_at, is_all_day = range_result
            return cleaned, starts_at, ends_at, is_all_day, duration

        # 2. Extract explicit standalone times or standalone text deadlines
        cleaned, inline_range = self._extract_inline_time_range(cleaned)
        cleaned, starts_at = self._extract_single_datetime(cleaned, reference)
        
        ends_at = None
        is_all_day = False

        if inline_range is not None:
            start_t, end_t = inline_range
            starts_at = datetime.combine(starts_at.date(), start_t)
            ends_at = datetime.combine(starts_at.date(), end_t)
            is_all_day = False
        elif all_day_hint:
            ends_at = datetime.combine(starts_at.date(), time(23, 59, 59))
            is_all_day = True

        return cleaned, starts_at, ends_at, is_all_day, duration

    def extract_title(self, text: str) -> str:
        title = re.sub(r"\s+", " ", text).strip()
        title = self._ALL_DAY_HINT_PATTERN.sub("", title)
        title = self._LEFTOVER_TIME_FRAGMENT.sub("", title)
        title = self._LEFTOVER_NAMED_RANGE_FRAGMENT.sub("", title)
        title = re.sub(r"\s*,\s*,\s*", ", ", title)
        title = re.sub(r"^[,.\s;:–—\-]+|[,.\s;:–—\-]+$", "", title)
        title = re.sub(r"\s+", " ", title).strip()
        return title if title else "Event"

    # --- Internal Language Helpers ---

    def _weekly_rrule_for_day(self, day_name: str) -> str:
        weekday_num = self._WEEKDAY_NAME_TO_NUM[day_name.lower()]
        byday = self._WEEKDAY_NUM_TO_RRULE[weekday_num]
        return f"FREQ=WEEKLY;BYDAY={byday}"

    def _extract_until_date(self, text: str, reference: date) -> tuple[str, Optional[date]]:
        until_date: Optional[date] = None
        cleaned = text

        for match in reversed(list(self._UNTIL_MONTH_END_PATTERN.finditer(cleaned))):
            month = self._MONTH_NAME_TO_NUM[match.group(1).lower()]
            explicit_year = int(match.group(2)) if match.group(2) else None
            
            year = explicit_year or reference.year
            if explicit_year is None and month < reference.month:
                year += 1
                
            _, last_day = cal_mod.monthrange(year, month)
            until_date = date(year, month, last_day)
            cleaned = self._remove_span(cleaned, match.start(), match.end())

        for match in reversed(list(self._UNTIL_PATTERN.finditer(cleaned))):
            month, day, year = map(int, match.groups())
            if year < 100: year += 2000
            until_date = date(year, month, day)
            cleaned = self._remove_span(cleaned, match.start(), match.end())

        return cleaned, until_date

    def _reminder_match_to_minutes(self, match: re.Match) -> int:
        raw_amount = match.group("amount")
        unit = match.group("unit").lower()
        
        if raw_amount is None or not raw_amount.strip():
            amount = 1 if unit.startswith("day") else 0
            if amount == 0: raise TerminParseError("err_reminder_no_amount")
        else:
            token = raw_amount.strip().lower()
            if token.isdigit(): amount = int(token)
            elif token in self._REMINDER_AMOUNT_WORDS: amount = self._REMINDER_AMOUNT_WORDS[token]
            else: raise TerminParseError("err_reminder_unknown", raw=raw_amount)

        if unit.startswith("day"): return amount * 24 * 60
        if unit.startswith("h"): return amount * 60
        return amount

    def _validate_reminder_offset(self, minutes: int) -> int:
        if minutes == 0: return 0
        if minutes < 1: raise TerminParseError("err_reminder_min_minutes")
        if minutes > 10080: raise TerminParseError("err_reminder_max_days", max_days=7)
        return minutes

    def _extract_duration(self, text: str) -> tuple[str, Optional[timedelta]]:
        match = self._DURATION_PATTERN.search(text)
        if not match: return text, None
        value = float(match.group("value").replace(",", "."))
        unit = match.group("unit").lower()
        delta = timedelta(hours=value) if unit.startswith("h") else timedelta(minutes=value)
        if delta.total_seconds() <= 0: raise TerminParseError("err_duration_positive")
        return self._remove_span(text, match.start(), match.end()), delta

    def _extract_all_day_hint(self, text: str) -> tuple[str, bool]:
        if not self._ALL_DAY_HINT_PATTERN.search(text): return text, False
        cleaned = re.sub(r"\s+", " ", self._ALL_DAY_HINT_PATTERN.sub(" ", text)).strip()
        return cleaned, True

    def _parse_clock(self, hour: str, minute: Optional[str], ampm: Optional[str]) -> time:
        h = int(hour)
        m = int(minute) if minute else 0
        if ampm:
            ampm_lower = ampm.lower()
            if ampm_lower == "pm" and h < 12: h += 12
            elif ampm_lower == "am" and h == 12: h = 0
        if h > 23 or m > 59: raise TerminParseError("err_invalid_time")
        return time(h, m)

    def _extract_inline_time_range(self, text: str) -> tuple[str, Optional[tuple[time, time]]]:
        match = self._INLINE_TIME_RANGE.search(text)
        if not match: return text, None
        start = self._parse_clock(match.group("s_hour"), match.group("s_min"), match.group("s_ampm"))
        end = self._parse_clock(match.group("e_hour"), match.group("e_min"), match.group("e_ampm"))
        return self._remove_span(text, match.start(), match.end()), (start, end)

    def _extract_date_range(
        self, text: str, reference: datetime
    ) -> Optional[tuple[str, datetime, datetime, bool]]:
        ref_date = reference.date()

        for pattern in (self._VON_BIS_NAMED_RANGE, self._NAMED_DATE_RANGE_BIS):
            match = pattern.search(text)
            if match:
                return self._all_day_range_from_match(text, match, ref_date)

        match = self._VON_BIS_RANGE.search(text)
        if match:
            s_day = match.group("s_day")
            e_day = match.group("e_day")
            if s_day and e_day:
                start_date = self._resolve_date(
                    int(s_day),
                    int(match.group("s_month")),
                    int(match.group("s_year")) if match.group("s_year") else None,
                    ref_date,
                )
                end_date = self._resolve_date(
                    int(e_day),
                    int(match.group("e_month")),
                    int(match.group("e_year")) if match.group("e_year") else None,
                    ref_date,
                )
                s_hour, e_hour = match.group("s_hour"), match.group("e_hour")
                if s_hour and e_hour:
                    starts_at = datetime.combine(
                        start_date,
                        self._parse_clock(
                            s_hour, match.group("s_min"), match.group("s_ampm")
                        ),
                    )
                    ends_at = datetime.combine(
                        end_date,
                        self._parse_clock(
                            e_hour, match.group("e_min"), match.group("e_ampm")
                        ),
                    )
                    if end_date == start_date and ends_at <= starts_at:
                        raise TerminParseError("err_end_time_after_start")
                    cleaned = self._remove_span(text, match.start(), match.end())
                    return cleaned, starts_at, ends_at, False
                if end_date < start_date:
                    raise TerminParseError("err_end_before_start")
                cleaned = self._remove_span(text, match.start(), match.end())
                return (
                    cleaned,
                    datetime.combine(start_date, time(0, 0)),
                    self._end_of_day(end_date),
                    True,
                )

        match = self._DATE_RANGE_BIS.search(text)
        if match:
            start_date = self._resolve_date(
                int(match.group("s_day")),
                int(match.group("s_month")),
                int(match.group("s_year")) if match.group("s_year") else None,
                ref_date,
            )
            end_date = self._resolve_date(
                int(match.group("e_day")),
                int(match.group("e_month")),
                int(match.group("e_year")) if match.group("e_year") else None,
                ref_date,
            )
            if end_date < start_date:
                raise TerminParseError("err_end_before_start")
            cleaned = self._remove_span(text, match.start(), match.end())
            return (
                cleaned,
                datetime.combine(start_date, time(0, 0)),
                self._end_of_day(end_date),
                True,
            )

        return None

    def _extract_single_datetime(self, text: str, reference: datetime) -> tuple[str, datetime]:
        cleaned = text
        time_hint = None
        for pattern in (self._TIME_PATTERN, self._BARE_TIME_PATTERN):
            m = pattern.search(cleaned)
            if m:
                time_hint = self._parse_clock(m.group("hour"), m.group("minute"), m.group("ampm"))
                cleaned = self._remove_span(cleaned, m.start(), m.end())

        # Relative weekdays (next monday)
        match = self._RELATIVE_WEEKDAY_PATTERN.search(cleaned)
        if match:
            weekday = self._WEEKDAY_NAME_TO_NUM[match.group("day").lower()]
            delta = (weekday - reference.weekday()) % 7
            if delta == 0: delta = 7
            ev_date = reference.date() + timedelta(days=delta)
            ev_time = self._parse_clock(match.group("hour"), match.group("minute"), match.group("ampm")) if match.group("hour") else (time_hint or time(0,0))
            return self._remove_span(cleaned, match.start(), match.end()), datetime.combine(ev_date, ev_time)

        # Numeric English strings (MM/DD/YYYY)
        match = self._ENGLISH_NUMERIC_DATE_PATTERN.search(cleaned)
        if match:
            year = int(match.group("year"))
            if year < 100: year += 2000
            ev_date = date(year, int(match.group("month")), int(match.group("day")))
            ev_time = self._parse_clock(match.group("hour"), match.group("minute"), match.group("ampm")) if match.group("hour") else (time_hint or time(0,0))
            return self._remove_span(cleaned, match.start(), match.end()), datetime.combine(ev_date, ev_time)

        # Absolute English words (May 20th)
        match = self._ENGLISH_ABSOLUTE_DATE_PATTERN.search(cleaned)
        if match:
            month = self._MONTH_NAME_TO_NUM[match.group("month").lower()]
            year = int(match.group("year")) if match.group("year") else reference.year
            ev_date = date(year, month, int(match.group("day")))
            ev_time = self._parse_clock(match.group("hour"), match.group("minute"), match.group("ampm")) if match.group("hour") else (time_hint or time(0,0))
            return self._remove_span(cleaned, match.start(), match.end()), datetime.combine(ev_date, ev_time)

        # Dateparser fallback engine
        settings = {"PREFER_DATES_FROM": "future", "RELATIVE_BASE": reference, "TIMEZONE": str(get_timezone()), "RETURN_AS_TIMEZONE_AWARE": False}
        found = search_dates(cleaned, languages=["en"], settings=settings)
        if not found: raise TerminParseError("err_no_date_time_found")
        
        for frag, dt in found: cleaned = cleaned.replace(frag, " ", 1)
        ev_time = time_hint if time_hint else found[0][1].time()
        return cleaned.strip(), datetime.combine(found[0][1].date(), ev_time)