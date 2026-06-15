from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
import uuid
from typing import Collection, Optional, Tuple

from dateutil.rrule import rrulestr
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from database import Category, Event, Flag, User, get_session
from services.i18n_util import LocalizedError
from services.rrule_util import (
    apply_until,
    parse_until_from_rrule,
    parse_rrule_to_freq_key,
    recurrence_label,
    strip_until,
)
from services.types import CategoryDTO
from services.timezone_util import to_naive_local
from services.user_service import visible_context_chat_id

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")

WEEKDAY_LABELS = {
    "MO": "Montag",
    "TU": "Dienstag",
    "WE": "Mittwoch",
    "TH": "Donnerstag",
    "FR": "Freitag",
    "SA": "Samstag",
    "SU": "Sonntag",
}

POSITION_LABELS = {
    1: "1.",
    2: "2.",
    3: "3.",
    4: "4.",
    -1: "letzten",
}

RRULE_MAP = {
    "none": (False, None),
    "daily": (True, "FREQ=DAILY"),
    "weekly": (True, "FREQ=WEEKLY"),
    "biweekly": (True, "FREQ=WEEKLY;INTERVAL=2"),
    "monthly": (True, "FREQ=MONTHLY"),
}

MAX_CATEGORY_NAME_LEN = 64


def normalize_category_names(raw: list[str]) -> list[str]:
    """Normalize names and deduplicate (case-sensitive)."""
    seen: set[str] = set()
    result: list[str] = []
    for part in raw:
        for segment in part.split(","):
            name = segment.strip()
            if not name or len(name) > MAX_CATEGORY_NAME_LEN:
                continue
            if name in seen:
                continue
            seen.add(name)
            result.append(name)
    return result


@dataclass
class GlobalCategoryResult:
    created_count: int
    names: list[str]
    total_global: int


def category_visible_to_user(category: Category, owner_id: str) -> bool:
    return category.user_id is None or category.user_id == owner_id


def visible_chat_id(chat_id: int, user_id: int) -> int:
    return visible_context_chat_id(chat_id, user_id)


def can_access_event(
    event: "EventDTO",
    chat_id: int,
    platform_user_id: int,
    *,
    visible_context_ids: frozenset[int] | None = None,
) -> bool:
    if visible_context_ids is not None:
        return event.context_chat_id in visible_context_ids
    return event.context_chat_id == visible_chat_id(chat_id, platform_user_id)


def visible_context_ids_from_user_data(user_data: dict) -> frozenset[int] | None:
    raw = user_data.get("visible_context_ids")
    if raw is None:
        return None
    return frozenset(raw)


def can_modify_event(
    event: "EventDTO",
    chat_id: int,
    platform_user_id: int,
    global_user_id: str,
    is_admin: bool,
    *,
    visible_context_ids: frozenset[int] | None = None,
) -> bool:
    if not can_access_event(
        event,
        chat_id,
        platform_user_id,
        visible_context_ids=visible_context_ids,
    ):
        return False
    return event.owner_id == global_user_id or is_admin


def build_monthly_by_weekday(weekday: str, position: int) -> str:
    if weekday not in WEEKDAY_LABELS:
        raise LocalizedError("err_invalid_weekday")
    if position not in POSITION_LABELS:
        raise LocalizedError("err_invalid_position")
    return f"FREQ=MONTHLY;BYDAY={weekday};BYSETPOS={position}"


def default_end_datetime(start: datetime) -> datetime:
    return start + timedelta(hours=1)


def validate_event_datetimes(start: datetime, end: datetime) -> None:
    if end <= start:
        raise LocalizedError("err_end_time_after_start")


@dataclass
class EventDTO:
    id: str
    owner_id: str
    context_chat_id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    is_all_day: bool
    reminder_offset: int
    is_recurring: bool
    rrule: Optional[str]
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    flag_names: Optional[list[str]] = None
    display_starts_at: Optional[datetime] = None
    occurrence_original_start: Optional[datetime] = None
    occurrence_ends_at: Optional[datetime] = None
    occurrence_is_moved: bool = False

    @property
    def list_starts_at(self) -> datetime:
        return self.display_starts_at or self.starts_at


class CalendarService:
    DATE_PATTERN = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
    TIME_PATTERN = re.compile(r"^(\d{2}):(\d{2})$")

    @staticmethod
    def is_valid_event_id(event_id: str) -> bool:
        try:
            uuid.UUID(event_id)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    @staticmethod
    def parse_date(text: str) -> date:
        match = CalendarService.DATE_PATTERN.match(text.strip())
        if not match:
            raise LocalizedError("err_invalid_date")
        day, month, year = map(int, match.groups())
        return date(year, month, day)

    @staticmethod
    def parse_time(text: str) -> time:
        match = CalendarService.TIME_PATTERN.match(text.strip())
        if not match:
            raise LocalizedError("err_invalid_time")
        hour, minute = map(int, match.groups())
        if hour > 23 or minute > 59:
            raise LocalizedError("err_invalid_time")
        return time(hour, minute)

    @staticmethod
    def build_datetime(event_date: date, event_time: time) -> datetime:
        return datetime.combine(event_date, event_time)

    @staticmethod
    def build_rrule(
        freq_key: str,
        *,
        weekday: Optional[str] = None,
        position: Optional[int] = None,
        until_date: Optional[date] = None,
    ) -> tuple[bool, Optional[str]]:
        if freq_key == "monthly_byweekday":
            if weekday is None or position is None:
                raise LocalizedError("err_weekday_position_required")
            base = build_monthly_by_weekday(weekday, position)
            return True, apply_until(base, until_date)

        if freq_key not in RRULE_MAP:
            raise LocalizedError("err_invalid_series_option")
        is_recurring, base = RRULE_MAP[freq_key]
        return is_recurring, apply_until(base, until_date)

    @staticmethod
    def finalize_rrule(
        is_recurring: bool,
        rrule: Optional[str],
        until_date: Optional[date],
        starts_at: datetime,
    ) -> tuple[bool, Optional[str]]:
        if not is_recurring:
            return False, None
        if until_date is not None and until_date < starts_at.date():
            raise LocalizedError("err_end_before_start")
        return True, apply_until(rrule, until_date)

    @staticmethod
    def next_occurrence(
        starts_at: datetime, rrule_str: str, after: datetime
    ) -> Optional[datetime]:
        dtstart = to_naive_local(starts_at)
        after_naive = to_naive_local(after)
        rule = rrulestr(rrule_str, dtstart=dtstart)
        return rule.after(after_naive, inc=True)

    @staticmethod
    def first_occurrence_on_or_after(
        starts_at: datetime, rrule_str: Optional[str], is_recurring: bool, after: datetime
    ) -> datetime:
        if not is_recurring or not rrule_str:
            return starts_at
        next_dt = CalendarService.next_occurrence(starts_at, rrule_str, after)
        return next_dt if next_dt is not None else starts_at

    def effective_display_datetime(self, event: EventDTO) -> datetime:
        """Next relevant date for display/sorting (for series)."""
        from services.timezone_util import now

        current = now().replace(tzinfo=None)
        if not event.is_recurring or not event.rrule:
            return event.starts_at
        if event.starts_at >= current:
            return event.starts_at
        next_dt = self.next_occurrence(event.starts_at, event.rrule, current)
        return next_dt if next_dt is not None else event.starts_at

    def _sort_events_for_display(self, events: list[EventDTO]) -> list[EventDTO]:
        for event in events:
            event.display_starts_at = self.effective_display_datetime(event)
        return sorted(events, key=lambda e: e.list_starts_at)

    @staticmethod
    def _to_dto(event: Event) -> EventDTO:
        category_name = event.category.name if event.category else None
        flag_names = sorted(flag.name for flag in event.flags) if event.flags else []
        return EventDTO(
            id=event.id,
            owner_id=event.owner_id,
            context_chat_id=event.context_chat_id or 0,
            title=event.title,
            starts_at=event.start_datetime,
            ends_at=event.end_datetime,
            is_all_day=event.is_all_day,
            reminder_offset=event.reminder_offset,
            is_recurring=event.is_recurring,
            rrule=event.rrule,
            category_id=event.category_id,
            category_name=category_name,
            flag_names=flag_names,
        )

    def _load_event(self, session, event_id: str) -> Optional[Event]:
        stmt = (
            select(Event)
            .options(
                selectinload(Event.flags),
                selectinload(Event.category),
            )
            .where(Event.id == event_id)
        )
        return session.scalars(stmt).first()

    def _get_or_create_flag(self, session, user_id: str, name: str) -> Flag:
        normalized = name.lower().strip()
        stmt = select(Flag).where(Flag.user_id == user_id, Flag.name == normalized)
        flag = session.scalars(stmt).first()
        if flag is None:
            flag = Flag(user_id=user_id, name=normalized)
            session.add(flag)
            session.flush()
        return flag

    @staticmethod
    def _to_category_dto(category: Category) -> CategoryDTO:
        return CategoryDTO(
            id=category.id,
            name=category.name,
            is_global=category.user_id is None,
        )

    def _visible_categories_filter(self, owner_id: str):
        return or_(Category.user_id.is_(None), Category.user_id == owner_id)

    def list_categories_dto(self, owner_id: str) -> list[CategoryDTO]:
        with get_session() as session:
            stmt = (
                select(Category)
                .where(self._visible_categories_filter(owner_id))
                .order_by(
                    case((Category.user_id.is_(None), 0), else_=1),
                    Category.name.asc(),
                )
            )
            return [
                self._to_category_dto(category)
                for category in session.scalars(stmt).all()
            ]

    def list_categories_for_suggestions(
        self, owner_id: str, *, limit: int = 6
    ) -> list[CategoryDTO]:
        visible = self._visible_categories_filter(owner_id)
        with get_session() as session:
            stmt = (
                select(
                    Category.id,
                    Category.name,
                    Category.user_id,
                    func.count(Event.id).label("usage"),
                )
                .outerjoin(
                    Event,
                    (Event.category_id == Category.id)
                    & (Event.owner_id == owner_id),
                )
                .where(visible)
                .group_by(Category.id, Category.name, Category.user_id)
                .order_by(func.count(Event.id).desc(), Category.name.asc())
                .limit(limit)
            )
            rows = session.execute(stmt).all()
            if rows:
                return [
                    CategoryDTO(
                        row.id,
                        row.name,
                        is_global=row.user_id is None,
                    )
                    for row in rows
                ]
            return self.list_categories_dto(owner_id)[:limit]

    def list_global_category_names(self) -> list[str]:
        with get_session() as session:
            return list(
                session.scalars(
                    select(Category.name)
                    .where(Category.user_id.is_(None))
                    .order_by(Category.name.asc())
                ).all()
            )

    def create_global_categories(self, names: list[str]) -> GlobalCategoryResult:
        normalized = normalize_category_names(names)
        created = 0
        with get_session() as session:
            existing = set(
                session.scalars(
                    select(Category.name).where(Category.user_id.is_(None))
                ).all()
            )
            for name in normalized:
                if name in existing:
                    continue
                session.add(Category(user_id=None, name=name))
                existing.add(name)
                created += 1
            session.flush()
            total = len(existing)
        return GlobalCategoryResult(
            created_count=created,
            names=normalized,
            total_global=total,
        )

    def create_personal_category(
        self, owner_id: str, name: str
    ) -> tuple[str, Optional[CategoryDTO]]:
        """Returns (status, dto) with status created|duplicate|global_collision|invalid."""
        cleaned = name.strip()
        if not cleaned or len(cleaned) > MAX_CATEGORY_NAME_LEN:
            return "invalid", None

        with get_session() as session:
            globals_list = session.scalars(
                select(Category).where(Category.user_id.is_(None))
            ).all()
            for global_cat in globals_list:
                if global_cat.name.lower() == cleaned.lower():
                    return "global_collision", None

            existing = session.scalars(
                select(Category).where(
                    Category.user_id == owner_id,
                    Category.name == cleaned,
                )
            ).first()
            if existing is not None:
                return "duplicate", self._to_category_dto(existing)

            category = Category(user_id=owner_id, name=cleaned)
            session.add(category)
            session.flush()
            session.refresh(category)
            return "created", self._to_category_dto(category)

    def create_from_parsed(
        self,
        owner_id: str,
        context_chat_id: int,
        parsed,
    ) -> EventDTO:
        return self.create_event(
            owner_id=owner_id,
            context_chat_id=context_chat_id,
            title=parsed.title,
            starts_at=parsed.starts_at,
            ends_at=parsed.ends_at,
            is_all_day=parsed.is_all_day,
            reminder_offset=parsed.reminder_offset,
            is_recurring=parsed.is_recurring,
            rrule=parsed.rrule,
            category_id=parsed.category_id,
            flag_names=parsed.flag_names,
        )

    def create_event(
        self,
        owner_id: str,
        context_chat_id: int,
        title: str,
        starts_at: datetime,
        reminder_offset: int = 0,
        is_recurring: bool = False,
        rrule: Optional[str] = None,
        *,
        ends_at: Optional[datetime] = None,
        is_all_day: bool = False,
        category_id: Optional[int] = None,
        flag_names: Optional[list[str]] = None,
    ) -> EventDTO:
        end_dt = ends_at if ends_at is not None else default_end_datetime(starts_at)
        validate_event_datetimes(starts_at, end_dt)
        with get_session() as session:
            if category_id is not None:
                category = session.get(Category, category_id)
                if category is None or not category_visible_to_user(
                    category, owner_id
                ):
                    category_id = None

            event = Event(
                owner_id=owner_id,
                context_chat_id=context_chat_id,
                title=title,
                start_datetime=starts_at,
                end_datetime=end_dt,
                is_all_day=is_all_day,
                reminder_offset=reminder_offset,
                is_recurring=is_recurring,
                rrule=rrule,
                category_id=category_id,
            )
            session.add(event)
            session.flush()

            for flag_name in flag_names or []:
                flag = self._get_or_create_flag(session, owner_id, flag_name)
                event.flags.append(flag)

            session.flush()
            loaded = self._load_event(session, event.id)
            return self._to_dto(loaded or event)

    def assign_category(
        self,
        event_id: str,
        category_id: Optional[int],
        owner_id: str,
        *,
        is_admin: bool = False,
    ) -> Optional[EventDTO]:
        with get_session() as session:
            event = self._load_event(session, event_id)
            if event is None:
                return None
            if event.owner_id != owner_id and not is_admin:
                return None
            if category_id is not None:
                category = session.get(Category, category_id)
                if category is None or not category_visible_to_user(
                    category, owner_id
                ):
                    return None
                event.category_id = category_id
            else:
                event.category_id = None
            session.flush()
            loaded = self._load_event(session, event_id)
            return self._to_dto(loaded) if loaded else None

    def get_event_by_id(self, event_id: str) -> Optional[EventDTO]:
        with get_session() as session:
            event = self._load_event(session, event_id)
            if event is None:
                return None
            return self._to_dto(event)

    def list_events_for_chat_filtered(
        self,
        chat_id: int,
        user_id: int,
        preset,
        *,
        year: Optional[int] = None,
        month: Optional[int] = None,
        month_offset: Optional[int] = None,
    ) -> list[EventDTO]:
        from services.event_filter import apply_filter

        events = self.list_events_for_chat(chat_id, user_id)
        return apply_filter(
            events,
            preset,
            year=year,
            month=month,
            month_offset=month_offset,
        )

    def list_events_for_chat(
        self, chat_id: int, platform_user_id: int
    ) -> list[EventDTO]:
        filter_chat_id = visible_chat_id(chat_id, platform_user_id)
        return self.list_events_for_contexts([filter_chat_id])

    def list_events_for_contexts(
        self, context_chat_ids: Collection[int]
    ) -> list[EventDTO]:
        ids = list(context_chat_ids)
        if not ids:
            return []

        with get_session() as session:
            stmt = (
                select(Event)
                .options(
                    selectinload(Event.flags),
                    selectinload(Event.category),
                )
                .where(Event.context_chat_id.in_(ids))
                .order_by(Event.start_datetime.asc())
            )
            events = session.scalars(stmt).all()
            return self._sort_events_for_display(
                [self._to_dto(event) for event in events]
            )

    def list_events_for_owner(self, owner_id: str) -> list[EventDTO]:
        with get_session() as session:
            stmt = (
                select(Event)
                .options(
                    selectinload(Event.flags),
                    selectinload(Event.category),
                )
                .where(Event.owner_id == owner_id)
                .order_by(Event.start_datetime.asc())
            )
            events = session.scalars(stmt).all()
            return self._sort_events_for_display(
                [self._to_dto(event) for event in events]
            )

    def list_events(self, context_chat_id: int) -> list[EventDTO]:
        """Legacy helper; prefer list_events_for_chat."""
        with get_session() as session:
            stmt = (
                select(Event)
                .options(
                    selectinload(Event.flags),
                    selectinload(Event.category),
                )
                .where(Event.context_chat_id == context_chat_id)
                .order_by(Event.start_datetime.asc())
            )
            events = session.scalars(stmt).all()
            return self._sort_events_for_display(
                [self._to_dto(event) for event in events]
            )

    def list_events_with_reminders(self) -> list[EventDTO]:
        with get_session() as session:
            stmt = (
                select(Event)
                .options(
                    selectinload(Event.flags),
                    selectinload(Event.category),
                )
                .where(Event.reminder_offset > 0)
            )
            events = session.scalars(stmt).all()
            return [self._to_dto(event) for event in events]

    def delete_event(
        self,
        chat_id: int,
        event_id: str,
        global_user_id: str,
        platform_user_id: int,
        *,
        is_admin: bool = False,
        visible_context_ids: frozenset[int] | None = None,
    ) -> bool:
        with get_session() as session:
            event = self._load_event(session, event_id)
            if event is None:
                return False
            dto = self._to_dto(event)
            if not can_modify_event(
                dto,
                chat_id,
                platform_user_id,
                global_user_id,
                is_admin,
                visible_context_ids=visible_context_ids,
            ):
                return False
            session.delete(event)
            return True

    def update_event(
        self,
        chat_id: int,
        event_id: str,
        global_user_id: str,
        platform_user_id: int,
        *,
        is_admin: bool = False,
        visible_context_ids: frozenset[int] | None = None,
        title: str,
        starts_at: datetime,
        reminder_offset: int,
        is_recurring: bool,
        rrule: Optional[str],
        ends_at: Optional[datetime] = None,
        is_all_day: Optional[bool] = None,
    ) -> Optional[EventDTO]:
        with get_session() as session:
            event = self._load_event(session, event_id)
            if event is None:
                return None
            dto = self._to_dto(event)
            if not can_modify_event(
                dto,
                chat_id,
                platform_user_id,
                global_user_id,
                is_admin,
                visible_context_ids=visible_context_ids,
            ):
                return None
            end_dt = ends_at
            if end_dt is None:
                duration = dto.ends_at - dto.starts_at
                end_dt = starts_at + duration
            all_day = dto.is_all_day if is_all_day is None else is_all_day
            validate_event_datetimes(starts_at, end_dt)
            event.title = title
            event.start_datetime = starts_at
            event.end_datetime = end_dt
            event.is_all_day = all_day
            event.reminder_offset = reminder_offset
            event.is_recurring = is_recurring
            event.rrule = rrule
            session.flush()
            loaded = self._load_event(session, event_id)
            return self._to_dto(loaded) if loaded else None
