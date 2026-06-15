"""Shared parser types, base class and date-range helpers."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional, Sequence

from services.i18n_util import LocalizedError
from services.timezone_util import now, to_naive_local
from services.types import CategoryDTO


class TerminParseError(LocalizedError):
    """Free text could not be converted into an event."""


@dataclass
class ParsedEvent:
    title: str
    starts_at: datetime
    ends_at: datetime
    is_all_day: bool
    is_recurring: bool
    rrule: Optional[str]
    until_date: Optional[date] = None
    reminder_offset: int = 0
    category_id: Optional[int] = None
    flag_names: list[str] = field(default_factory=list)


ParsedTermin = ParsedEvent


class BaseEventParser(ABC):
    def __init__(self):
        self._FLAG_PATTERN = re.compile(
            r"\B#([a-zA-Z0-9_äöüÄÖÜß\-]{2,32})\b",
            re.UNICODE,
        )
        self._CATEGORY_PREFIX_PATTERN = re.compile(r"^([^:]+):\s*", re.UNICODE)

    @abstractmethod
    def extract_recurrence(
        self, text: str, reference: date
    ) -> tuple[str, bool, Optional[str], Optional[date]]:
        """Extracts recurrence rules and 'until' limits from the text."""
        pass

    @abstractmethod
    def extract_reminder(self, text: str) -> tuple[str, int]:
        """Extracts and validates the reminder offset configuration."""
        pass

    @abstractmethod
    def extract_datetime_or_range(
        self, text: str, reference: datetime
    ) -> tuple[str, datetime, Optional[datetime], bool, Optional[timedelta]]:
        """Extracts start/end datetimes, durations, or all-day range markers."""
        pass

    @abstractmethod
    def extract_title(self, text: str) -> str:
        """Cleans up leftover language-specific fragments to extract the final clean title."""
        pass

    def _remove_span(self, text: str, start: int, end: int) -> str:
        return (text[:start] + " " + text[end:]).strip()

    def _normalize_year(self, year: int) -> int:
        if year < 100:
            return 2000 + year
        return year

    def _year_from_group(self, raw: Optional[str]) -> Optional[int]:
        if raw is None:
            return None
        return self._normalize_year(int(raw))

    def _month_from_token(self, token: str) -> int:
        if token.isdigit():
            return int(token)
        return self._MONTH_NAME_TO_NUM[token.lower()]  # type: ignore[attr-defined]

    def _resolve_date(
        self, day: int, month: int, year: Optional[int], reference: date
    ) -> date:
        resolved_year = (
            self._normalize_year(year) if year is not None else reference.year
        )
        try:
            return date(resolved_year, month, day)
        except ValueError as exc:
            raise TerminParseError("err_invalid_date_in_text") from exc

    def _end_of_day(self, event_date: date) -> datetime:
        return datetime.combine(event_date, time(23, 59, 59))

    def _resolve_range_dates(
        self,
        *,
        s_day: int,
        s_month: int,
        s_year: Optional[int],
        e_day: int,
        e_month: int,
        e_year: Optional[int],
        reference: date,
    ) -> tuple[date, date]:
        end_year = s_year
        start_year = s_year

        if e_year is not None and s_year is None:
            start_year = e_year
            if s_month > e_month:
                start_year = e_year - 1
        elif s_year is not None and e_year is None:
            end_year = s_year
            if e_month < s_month:
                end_year = s_year + 1
        elif s_year is None and e_year is None:
            start_year = reference.year
            if s_month < reference.month or (
                s_month == reference.month and s_day < reference.day
            ):
                start_year += 1
            end_year = start_year
            if e_month < s_month or (e_month == s_month and e_day < s_day):
                end_year = start_year + 1
        else:
            start_year = s_year
            end_year = e_year

        try:
            start_date = date(start_year, s_month, s_day)
            end_date = date(end_year, e_month, e_day)
        except ValueError as exc:
            raise TerminParseError("err_invalid_date_in_text") from exc

        if end_date < start_date:
            raise TerminParseError("err_end_before_start")
        return start_date, end_date

    def _all_day_range_from_match(
        self, text: str, match: re.Match, reference: date
    ) -> tuple[str, datetime, datetime, bool]:
        start_date, end_date = self._resolve_range_dates(
            s_day=int(match.group("s_day")),
            s_month=self._month_from_token(match.group("s_month")),
            s_year=self._year_from_group(match.group("s_year")),
            e_day=int(match.group("e_day")),
            e_month=self._month_from_token(match.group("e_month")),
            e_year=self._year_from_group(match.group("e_year")),
            reference=reference,
        )
        cleaned = self._remove_span(text, match.start(), match.end())
        return (
            cleaned,
            datetime.combine(start_date, time(0, 0)),
            self._end_of_day(end_date),
            True,
        )

    def _extract_flags(self, text: str) -> tuple[str, list[str]]:
        names: list[str] = []
        seen: set[str] = set()

        def replacer(match: re.Match) -> str:
            name = match.group(1).lower()
            if name not in seen:
                seen.add(name)
                names.append(name)
            return " "

        cleaned = self._FLAG_PATTERN.sub(replacer, text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned, names

    def _extract_category_prefix(
        self, text: str, user_categories: Sequence[CategoryDTO]
    ) -> tuple[str, Optional[int]]:
        if not user_categories:
            return text, None
        match = self._CATEGORY_PREFIX_PATTERN.match(text)
        if not match:
            return text, None

        prefix_lower = match.group(1).strip().lower()
        global_match: Optional[CategoryDTO] = None
        personal_match: Optional[CategoryDTO] = None

        for category in user_categories:
            if category.name.lower() != prefix_lower:
                continue
            if category.is_global:
                global_match = category
            elif personal_match is None:
                personal_match = category

        chosen = global_match or personal_match
        if chosen is not None:
            remainder = text[match.end() :].strip()
            return remainder, chosen.id
        return text, None

    def _finalize_end(
        self,
        starts_at: datetime,
        ends_at: Optional[datetime],
        duration: Optional[timedelta],
    ) -> tuple[datetime, bool]:
        if duration is not None:
            ends_at = starts_at + duration
        if ends_at is None:
            ends_at = starts_at + timedelta(hours=1)
        if ends_at <= starts_at:
            raise TerminParseError("err_end_time_after_start")
        return ends_at, False

    def parse(
        self,
        text: str,
        user_categories: Sequence[CategoryDTO] = (),
        base: Optional[datetime] = None,
    ) -> ParsedEvent:
        raw = text.strip()
        if not raw:
            raise TerminParseError("err_termin_text_required")

        reference = to_naive_local(base) if base is not None else to_naive_local(now())

        working, is_recurring, rrule, until_date = self.extract_recurrence(
            raw, reference.date()
        )
        working, reminder_offset = self.extract_reminder(working)
        working, flag_names = self._extract_flags(working)
        working, category_id = self._extract_category_prefix(working, user_categories)
        working, starts_at, ends_at, is_all_day, duration = self.extract_datetime_or_range(
            working, reference
        )

        if not is_all_day:
            ends_at, is_all_day = self._finalize_end(starts_at, ends_at, duration)

        title = self.extract_title(working)

        if is_recurring and rrule and until_date and until_date < starts_at.date():
            raise TerminParseError("err_series_end_before_first")

        return ParsedEvent(
            title=title,
            starts_at=starts_at,
            ends_at=ends_at,
            is_all_day=is_all_day,
            is_recurring=is_recurring,
            rrule=rrule,
            until_date=until_date,
            reminder_offset=reminder_offset,
            category_id=category_id,
            flag_names=flag_names,
        )
