from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr

from services.calendar_service import EventDTO
from services.event_exceptions import EXCEPTION_CANCELLED, EXCEPTION_MOVED, EventExceptionDTO
from services.timezone_util import as_local, now


@dataclass(frozen=True)
class OccurrenceInstance:
    starts_at: datetime
    ends_at: datetime
    original_start: datetime
    is_moved: bool = False

class EventFilterPreset(str, Enum):
    FUTURE = "future"
    TODAY = "today"
    THIS_WEEK = "this_week"
    NEXT_WEEK = "next_week"
    THIS_MONTH = "this_month"
    MONTH_OFFSET = "month_offset"
    CALENDAR_MONTH = "calendar_month"
    CALENDAR_YEAR = "calendar_year"
    PICK_MONTH = "pick_month"
    PICK_YEAR = "pick_year"
    ALL_VISIBLE = "all_visible"


@dataclass
class ParsedFilter:
    preset: EventFilterPreset
    year: Optional[int] = None
    month: Optional[int] = None
    month_offset: Optional[int] = None
    picker_year: Optional[int] = None


def parsed_filter_to_dict(parsed: ParsedFilter) -> dict:
    return {
        "preset": parsed.preset.value,
        "year": parsed.year,
        "month": parsed.month,
        "month_offset": parsed.month_offset,
        "picker_year": parsed.picker_year,
    }


def parsed_filter_from_dict(data: dict) -> ParsedFilter:
    return ParsedFilter(
        preset=EventFilterPreset(data["preset"]),
        year=data.get("year"),
        month=data.get("month"),
        month_offset=data.get("month_offset"),
        picker_year=data.get("picker_year"),
    )


_ARG_ALIASES: dict[str, EventFilterPreset] = {
    "heute": EventFilterPreset.TODAY,
    "today": EventFilterPreset.TODAY,
    "woche": EventFilterPreset.THIS_WEEK,
    "week": EventFilterPreset.THIS_WEEK,
    "naechste": EventFilterPreset.NEXT_WEEK,
    "naechste_woche": EventFilterPreset.NEXT_WEEK,
    "+1w": EventFilterPreset.NEXT_WEEK,
    "monat": EventFilterPreset.MONTH_OFFSET,
    "month": EventFilterPreset.MONTH_OFFSET,
    "jahr": EventFilterPreset.CALENDAR_YEAR,
    "zukunft": EventFilterPreset.FUTURE,
    "future": EventFilterPreset.FUTURE,
}


def current_year() -> int:
    return now().year


def month_name(month: int, locale: str = "de") -> str:
    from services.i18n_util import t_list

    names = t_list("month_short", locale)
    if len(names) < 12:
        names = t_list("month_short", "de")
    return names[month - 1]


def _month_year_from_offset(offset: int) -> tuple[int, int]:
    base = _start_of_day(now()).replace(day=1)
    target = base + relativedelta(months=offset)
    return target.year, target.month


def parse_filter_arg(args: list[str]) -> ParsedFilter:
    if not args:
        return ParsedFilter(EventFilterPreset.FUTURE)

    key = args[0].lower()

    if key.isdigit() and len(key) == 4:
        return ParsedFilter(EventFilterPreset.CALENDAR_YEAR, year=int(key))

    if key == "monat" and len(args) >= 2:
        if args[1] in ("+1", "naechster", "naechste"):
            return ParsedFilter(EventFilterPreset.MONTH_OFFSET, month_offset=1)
        if args[1] in ("+2", "uebernaechster", "uebernaechste"):
            return ParsedFilter(EventFilterPreset.MONTH_OFFSET, month_offset=2)
        if len(args) >= 3 and args[1].isdigit() and args[2].isdigit():
            month = int(args[1])
            year = int(args[2])
            if 1 <= month <= 12:
                return ParsedFilter(
                    EventFilterPreset.CALENDAR_MONTH, year=year, month=month
                )
        if args[1].isdigit() and 1 <= int(args[1]) <= 12:
            month = int(args[1])
            year = int(args[2]) if len(args) >= 3 and args[2].isdigit() else current_year()
            return ParsedFilter(
                EventFilterPreset.CALENDAR_MONTH, year=year, month=month
            )

    if key == "jahr" and len(args) >= 2 and args[1].isdigit():
        return ParsedFilter(EventFilterPreset.CALENDAR_YEAR, year=int(args[1]))

    preset = _ARG_ALIASES.get(key)
    if preset is None:
        return ParsedFilter(EventFilterPreset.FUTURE)

    if preset == EventFilterPreset.MONTH_OFFSET:
        return ParsedFilter(EventFilterPreset.MONTH_OFFSET, month_offset=0)
    if preset == EventFilterPreset.CALENDAR_YEAR:
        return ParsedFilter(EventFilterPreset.CALENDAR_YEAR, year=current_year())

    return ParsedFilter(preset)


def parse_callback_data(data: str) -> ParsedFilter:
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "termfilter":
        return ParsedFilter(EventFilterPreset.FUTURE)

    key = parts[1]

    if key == "pick" and len(parts) >= 3:
        if parts[2] == "month":
            return ParsedFilter(
                EventFilterPreset.PICK_MONTH, picker_year=current_year()
            )
        if parts[2] == "year":
            return ParsedFilter(EventFilterPreset.PICK_YEAR, picker_year=current_year())

    if key == "my" and len(parts) >= 3:
        return ParsedFilter(EventFilterPreset.PICK_MONTH, picker_year=int(parts[2]))

    if key == "mo" and len(parts) >= 3:
        return ParsedFilter(EventFilterPreset.MONTH_OFFSET, month_offset=int(parts[2]))

    if key == "m" and len(parts) >= 4:
        return ParsedFilter(
            EventFilterPreset.CALENDAR_MONTH,
            year=int(parts[2]),
            month=int(parts[3]),
        )

    if key == "y" and len(parts) >= 3:
        return ParsedFilter(EventFilterPreset.CALENDAR_YEAR, year=int(parts[2]))

    if key == "year" and len(parts) >= 3:
        return ParsedFilter(EventFilterPreset.CALENDAR_YEAR, year=int(parts[2]))

    try:
        preset = EventFilterPreset(key)
    except ValueError:
        return ParsedFilter(EventFilterPreset.FUTURE)

    if preset == EventFilterPreset.THIS_MONTH:
        return ParsedFilter(EventFilterPreset.MONTH_OFFSET, month_offset=0)

    return ParsedFilter(preset)


def _start_of_day(dt: datetime) -> datetime:
    local = as_local(dt)
    return local.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def _monday_of_week(day: datetime) -> datetime:
    sod = _start_of_day(day)
    return sod - timedelta(days=sod.weekday())


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    return start, end


def get_range(
    preset: EventFilterPreset,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    month_offset: Optional[int] = None,
) -> tuple[datetime, Optional[datetime]]:
    current = now()
    today = _start_of_day(current)

    if preset == EventFilterPreset.FUTURE:
        return current.replace(tzinfo=None), None

    if preset == EventFilterPreset.ALL_VISIBLE:
        start = _start_of_day(current) - relativedelta(months=12)
        return start, None

    if preset == EventFilterPreset.TODAY:
        return today, today + timedelta(days=1)

    if preset == EventFilterPreset.THIS_WEEK:
        week_start = _monday_of_week(current)
        return week_start, week_start + timedelta(days=7)

    if preset == EventFilterPreset.NEXT_WEEK:
        week_start = _monday_of_week(current) + timedelta(days=7)
        return week_start, week_start + timedelta(days=7)

    if preset in (EventFilterPreset.THIS_MONTH, EventFilterPreset.MONTH_OFFSET):
        offset = month_offset if month_offset is not None else 0
        start, end = _month_range(*_month_year_from_offset(offset))
        return start, end

    if preset == EventFilterPreset.CALENDAR_MONTH:
        y = year if year is not None else current_year()
        m = month if month is not None else today.month
        start, end = _month_range(y, m)
        return start, end

    if preset == EventFilterPreset.CALENDAR_YEAR:
        y = year if year is not None else current_year()
        return datetime(y, 1, 1), datetime(y + 1, 1, 1)

    return current.replace(tzinfo=None), None


def filter_label(
    preset: EventFilterPreset,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    month_offset: Optional[int] = None,
    locale: str = "de",
) -> str:
    from views.message_factory import MessageFactory

    if preset == EventFilterPreset.FUTURE:
        return MessageFactory._t("filter_future", locale)
    if preset == EventFilterPreset.ALL_VISIBLE:
        return MessageFactory._t("filter_all_visible", locale)
    if preset == EventFilterPreset.TODAY:
        return MessageFactory._t("filter_today", locale)
    if preset == EventFilterPreset.THIS_WEEK:
        return MessageFactory._t("filter_this_week", locale)
    if preset == EventFilterPreset.NEXT_WEEK:
        return MessageFactory._t("filter_next_week", locale)
    if preset in (EventFilterPreset.THIS_MONTH, EventFilterPreset.MONTH_OFFSET):
        offset = month_offset if month_offset is not None else 0
        y, m = _month_year_from_offset(offset)
        if offset == 0:
            return MessageFactory._t("filter_this_month", locale)
        if offset == 1:
            return MessageFactory._t("filter_next_month", locale)
        if offset == 2:
            return MessageFactory._t("filter_month_after_next", locale)
        return f"{month_name(m, locale)} {y}"
    if preset == EventFilterPreset.CALENDAR_MONTH and year and month:
        return f"{month_name(month, locale)} {year}"
    if preset == EventFilterPreset.CALENDAR_YEAR and year:
        return str(year)
    return MessageFactory._t("filter_future", locale)


def _to_naive_local(dt: datetime) -> datetime:
    return as_local(dt).replace(tzinfo=None)


def _in_range(when: datetime, start: datetime, end: Optional[datetime]) -> bool:
    when_naive = _to_naive_local(when)
    start_naive = _to_naive_local(start)
    if end is None:
        return when_naive >= start_naive
    end_naive = _to_naive_local(end)
    return start_naive <= when_naive < end_naive


def _overlaps_range(
    event_start: datetime,
    event_end: datetime,
    range_start: datetime,
    range_end: Optional[datetime],
) -> bool:
    start_naive = _to_naive_local(event_start)
    end_naive = _to_naive_local(event_end)
    range_start_naive = _to_naive_local(range_start)
    if range_end is None:
        return end_naive >= range_start_naive
    range_end_naive = _to_naive_local(range_end)
    return start_naive < range_end_naive and end_naive >= range_start_naive


def _occurrences_in_range(
    event: EventDTO, start: datetime, end: datetime
) -> list[datetime]:
    """All occurrences in the time range (series are expanded)."""
    if not event.is_recurring or not event.rrule:
        if _overlaps_range(event.starts_at, event.ends_at, start, end):
            return [event.starts_at]
        return []

    rule = rrulestr(event.rrule, dtstart=_to_naive_local(event.starts_at))
    return list(
        rule.between(
            _to_naive_local(start),
            _to_naive_local(end) - timedelta(microseconds=1),
            inc=True,
        )
    )


def _first_occurrence_in_range(
    event: EventDTO, start: datetime, end: datetime
) -> Optional[datetime]:
    """First occurrence in the time range."""
    occurrences = _occurrences_in_range(event, start, end)
    return occurrences[0] if occurrences else None


def resolve_occurrences_in_range(
    event: EventDTO,
    start: datetime,
    end: datetime,
    exceptions: list[EventExceptionDTO] | None = None,
) -> list[OccurrenceInstance]:
    exceptions = exceptions or []
    cancelled = {
        _occurrence_key(e.original_start)
        for e in exceptions
        if e.exception_type == EXCEPTION_CANCELLED
    }
    moved_by_key = {
        _occurrence_key(e.original_start): e
        for e in exceptions
        if e.exception_type == EXCEPTION_MOVED
    }
    duration = event.ends_at - event.starts_at
    result: list[OccurrenceInstance] = []
    seen_moved_new: set[datetime] = set()

    for occ_start in _occurrences_in_range(event, start, end):
        key = _occurrence_key(occ_start)
        if key in cancelled:
            continue
        if key in moved_by_key:
            exc = moved_by_key[key]
            new_start = exc.new_start
            if new_start is None:
                continue
            new_end = exc.new_end or (new_start + duration)
            if _overlaps_range(new_start, new_end, start, end):
                new_key = _occurrence_key(new_start)
                if new_key not in seen_moved_new:
                    result.append(
                        OccurrenceInstance(
                            starts_at=new_start,
                            ends_at=new_end,
                            original_start=occ_start,
                            is_moved=True,
                        )
                    )
                    seen_moved_new.add(new_key)
            continue
        result.append(
            OccurrenceInstance(
                starts_at=occ_start,
                ends_at=occ_start + duration,
                original_start=occ_start,
                is_moved=False,
            )
        )

    for exc in moved_by_key.values():
        if _occurrence_key(exc.original_start) in cancelled:
            continue
        new_start = exc.new_start
        if new_start is None:
            continue
        new_end = exc.new_end or (new_start + duration)
        new_key = _occurrence_key(new_start)
        if new_key in seen_moved_new:
            continue
        if _overlaps_range(new_start, new_end, start, end):
            result.append(
                OccurrenceInstance(
                    starts_at=new_start,
                    ends_at=new_end,
                    original_start=exc.original_start,
                    is_moved=True,
                )
            )
            seen_moved_new.add(new_key)

    return sorted(result, key=lambda item: item.starts_at)


def _occurrence_key(dt: datetime) -> datetime:
    return _to_naive_local(dt).replace(second=0, microsecond=0)


def _first_future_occurrence(
    event: EventDTO,
    after: datetime,
    exceptions: list[EventExceptionDTO] | None = None,
    *,
    horizon_days: int = 730,
) -> OccurrenceInstance | None:
    after_naive = _to_naive_local(after)
    horizon_end = after_naive + timedelta(days=horizon_days)
    for inst in resolve_occurrences_in_range(
        event, after_naive, horizon_end, exceptions
    ):
        if _to_naive_local(inst.starts_at) >= after_naive:
            return inst
    return None


def apply_filter(
    events: list[EventDTO],
    preset: EventFilterPreset,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    month_offset: Optional[int] = None,
    exceptions_by_event: dict[str, list[EventExceptionDTO]] | None = None,
) -> list[EventDTO]:
    start, end = get_range(
        preset, year=year, month=month, month_offset=month_offset
    )

    if end is not None:
        if exceptions_by_event is None:
            recurring_ids = [event.id for event in events if event.is_recurring]
            if recurring_ids:
                from services.event_exceptions import get_exception_service

                exceptions_by_event = get_exception_service().get_exceptions_for_events(
                    recurring_ids
                )
            else:
                exceptions_by_event = {}

        filtered = []
        for event in events:
            excs = exceptions_by_event.get(event.id, [])
            for inst in resolve_occurrences_in_range(event, start, end, excs):
                filtered.append(
                    replace(
                        event,
                        display_starts_at=inst.starts_at,
                        occurrence_ends_at=inst.ends_at,
                        occurrence_original_start=inst.original_start,
                        occurrence_is_moved=inst.is_moved,
                    )
                )
    else:
        if exceptions_by_event is None:
            recurring_ids = [event.id for event in events if event.is_recurring]
            if recurring_ids:
                from services.event_exceptions import get_exception_service

                exceptions_by_event = get_exception_service().get_exceptions_for_events(
                    recurring_ids
                )
            else:
                exceptions_by_event = {}

        filtered = []
        for event in events:
            if event.is_recurring and event.rrule:
                inst = _first_future_occurrence(
                    event, start, exceptions_by_event.get(event.id, [])
                )
                if inst is not None:
                    filtered.append(
                        replace(
                            event,
                            display_starts_at=inst.starts_at,
                            occurrence_ends_at=inst.ends_at,
                            occurrence_original_start=inst.original_start,
                            occurrence_is_moved=inst.is_moved,
                        )
                    )
            elif _overlaps_range(event.starts_at, event.ends_at, start, end):
                filtered.append(event)

    return sorted(filtered, key=lambda e: e.list_starts_at)


def filter_events_for_ui(events: list[EventDTO], ui_filter: str) -> list[EventDTO]:
    if ui_filter == "all":
        return apply_filter(events, EventFilterPreset.ALL_VISIBLE)
    if ui_filter == "recurring":
        recurring = [e for e in events if e.is_recurring]
        return sorted(recurring, key=lambda e: e.list_starts_at)
    return apply_filter(events, EventFilterPreset.FUTURE)


def ui_filter_empty_label(ui_filter: str, locale: str = "de") -> str:
    from views.message_factory import MessageFactory

    if ui_filter == "all":
        return MessageFactory._t("filter_all_visible", locale)
    if ui_filter == "recurring":
        return MessageFactory._t("filter_recurring_short", locale)
    return MessageFactory._t("filter_future", locale)
