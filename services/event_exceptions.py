"""Exceptions for individual series occurrences (cancel / reschedule)."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from database import EventException, get_session
from services.i18n_util import LocalizedError
from services.calendar_service import (
    CalendarService,
    EventDTO,
    can_modify_event,
    default_end_datetime,
    validate_event_datetimes,
)
from services.occurrence_util import normalize_occurrence

EXCEPTION_CANCELLED = "cancelled"
EXCEPTION_MOVED = "moved"


@dataclass(frozen=True)
class EventExceptionDTO:
    id: int
    event_id: str
    original_start: datetime
    exception_type: str
    new_start: datetime | None
    new_end: datetime | None


class EventExceptionService:
    def __init__(self) -> None:
        self._calendar = CalendarService()

    @staticmethod
    def _to_dto(row: EventException) -> EventExceptionDTO:
        return EventExceptionDTO(
            id=row.id,
            event_id=row.event_id,
            original_start=row.original_start,
            exception_type=row.exception_type,
            new_start=row.new_start,
            new_end=row.new_end,
        )

    def get_exceptions_for_event(self, event_id: str) -> list[EventExceptionDTO]:
        with get_session() as session:
            rows = session.scalars(
                select(EventException)
                .where(EventException.event_id == event_id)
                .order_by(EventException.original_start.asc())
            ).all()
            return [self._to_dto(row) for row in rows]

    def get_exceptions_for_events(
        self, event_ids: list[str]
    ) -> dict[str, list[EventExceptionDTO]]:
        if not event_ids:
            return {}
        with get_session() as session:
            rows = session.scalars(
                select(EventException)
                .where(EventException.event_id.in_(event_ids))
                .order_by(EventException.original_start.asc())
            ).all()
            dtos = [self._to_dto(row) for row in rows]
        result: dict[str, list[EventExceptionDTO]] = {eid: [] for eid in event_ids}
        for dto in dtos:
            result[dto.event_id].append(dto)
        return result

    def _assert_can_modify(
        self,
        event: EventDTO,
        chat_id: int,
        platform_user_id: int,
        global_user_id: str,
        *,
        is_admin: bool = False,
        visible_context_ids: frozenset[int] | None = None,
    ) -> None:
        if not can_modify_event(
            event,
            chat_id,
            platform_user_id,
            global_user_id,
            is_admin,
            visible_context_ids=visible_context_ids,
        ):
            raise PermissionError("Keine Berechtigung.")

    def cancel_occurrence(
        self,
        event_id: str,
        original_start: datetime,
        chat_id: int,
        platform_user_id: int,
        global_user_id: str,
        *,
        is_admin: bool = False,
        visible_context_ids: frozenset[int] | None = None,
    ) -> EventExceptionDTO:
        event = self._calendar.get_event_by_id(event_id)
        if event is None:
            raise LocalizedError("err_event_not_found")
        if not event.is_recurring:
            raise LocalizedError("err_occurrence_only_cancel")
        self._assert_can_modify(
            event,
            chat_id,
            platform_user_id,
            global_user_id,
            is_admin=is_admin,
            visible_context_ids=visible_context_ids,
        )

        original = normalize_occurrence(original_start)
        with get_session() as session:
            existing = session.scalars(
                select(EventException).where(
                    EventException.event_id == event_id,
                    EventException.original_start == original,
                )
            ).first()
            if existing is not None:
                existing.exception_type = EXCEPTION_CANCELLED
                existing.new_start = None
                existing.new_end = None
                session.flush()
                session.refresh(existing)
                return self._to_dto(existing)

            row = EventException(
                event_id=event_id,
                original_start=original,
                exception_type=EXCEPTION_CANCELLED,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return self._to_dto(row)

    def move_occurrence(
        self,
        event_id: str,
        original_start: datetime,
        new_start: datetime,
        chat_id: int,
        platform_user_id: int,
        global_user_id: str,
        *,
        new_end: datetime | None = None,
        is_admin: bool = False,
        visible_context_ids: frozenset[int] | None = None,
    ) -> EventExceptionDTO:
        event = self._calendar.get_event_by_id(event_id)
        if event is None:
            raise LocalizedError("err_event_not_found")
        if not event.is_recurring:
            raise LocalizedError("err_occurrence_only_move")
        self._assert_can_modify(
            event,
            chat_id,
            platform_user_id,
            global_user_id,
            is_admin=is_admin,
            visible_context_ids=visible_context_ids,
        )

        original = normalize_occurrence(original_start)
        end_dt = new_end if new_end is not None else default_end_datetime(new_start)
        validate_event_datetimes(new_start, end_dt)

        with get_session() as session:
            existing = session.scalars(
                select(EventException).where(
                    EventException.event_id == event_id,
                    EventException.original_start == original,
                )
            ).first()
            if existing is not None:
                existing.exception_type = EXCEPTION_MOVED
                existing.new_start = new_start
                existing.new_end = end_dt
                session.flush()
                session.refresh(existing)
                return self._to_dto(existing)

            row = EventException(
                event_id=event_id,
                original_start=original,
                exception_type=EXCEPTION_MOVED,
                new_start=new_start,
                new_end=end_dt,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return self._to_dto(row)


_service: Optional[EventExceptionService] = None


def get_exception_service() -> EventExceptionService:
    global _service
    if _service is None:
        _service = EventExceptionService()
    return _service


def resolve_occurrence_times(
    event: EventDTO,
    original_start: datetime,
    exceptions: list[EventExceptionDTO] | None = None,
) -> tuple[datetime, datetime, bool, datetime]:
    """(starts_at, ends_at, is_moved, original_start_for_hint)."""
    if exceptions is None:
        exceptions = get_exception_service().get_exceptions_for_event(event.id)
    duration = event.ends_at - event.starts_at
    key = normalize_occurrence(original_start)
    for exc in exceptions:
        if normalize_occurrence(exc.original_start) != key:
            continue
        if exc.exception_type == EXCEPTION_MOVED and exc.new_start is not None:
            end = exc.new_end or (exc.new_start + duration)
            return exc.new_start, end, True, exc.original_start
    return original_start, original_start + duration, False, original_start
