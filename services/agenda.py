"""Local agenda system: birthdays and daily events."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import extract, select
from sqlalchemy.exc import IntegrityError

from database import Birthday, get_session
from services.calendar_service import CalendarService
from services.event_exceptions import get_exception_service
from services.event_filter import resolve_occurrences_in_range
from services.i18n_util import LocalizedError
from services.timezone_util import now
from views.message_factory import MessageFactory


@dataclass(frozen=True)
class BirthdayToday:
    name: str
    age: int


@dataclass(frozen=True)
class AgendaEventToday:
    event_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    is_all_day: bool
    context_chat_id: int
    is_recurring: bool = False
    is_moved: bool = False


@dataclass(frozen=True)
class TodayAgenda:
    birthdays: tuple[BirthdayToday, ...]
    events: tuple[AgendaEventToday, ...]


def _birthday_occurrence_on(year: int, birth_date: date) -> date:
    month, day = birth_date.month, birth_date.day
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, day - 1)


def days_until_next_birthday(today: date, birth_date: date) -> int:
    """Days until the next birthday (0 = today)."""
    this_year = _birthday_occurrence_on(today.year, birth_date)
    if this_year >= today:
        return (this_year - today).days
    next_occurrence = _birthday_occurrence_on(today.year + 1, birth_date)
    return (next_occurrence - today).days


class AgendaService:
    @staticmethod
    def _detach_birthday(session, birthday: Birthday) -> Birthday:
        session.refresh(birthday)
        session.expunge(birthday)
        return birthday

    def add_birthday(self, user_id: str, name: str, birth_date: date) -> Birthday:
        clean_name = name.strip()
        if not clean_name:
            raise LocalizedError("err_name_empty")

        with get_session() as session:
            birthday = Birthday(
                user_id=user_id,
                name=clean_name,
                birth_date=birth_date,
            )
            session.add(birthday)
            session.flush()
            return self._detach_birthday(session, birthday)

    def list_birthdays(self, user_id: str) -> list[Birthday]:
        today = now().date()
        with get_session() as session:
            rows = list(
                session.scalars(
                    select(Birthday).where(Birthday.user_id == user_id)
                ).all()
            )
            for row in rows:
                session.expunge(row)
        rows.sort(
            key=lambda b: (
                days_until_next_birthday(today, b.birth_date),
                b.name.lower(),
            )
        )
        return rows

    def get_birthday(self, user_id: str, birthday_id: int) -> Birthday | None:
        with get_session() as session:
            birthday = session.scalar(
                select(Birthday)
                .where(Birthday.id == birthday_id)
                .where(Birthday.user_id == user_id)
            )
            if birthday is None:
                return None
            return self._detach_birthday(session, birthday)

    def update_birthday(
        self,
        user_id: str,
        birthday_id: int,
        *,
        name: str | None = None,
        birth_date: date | None = None,
    ) -> Birthday:
        with get_session() as session:
            birthday = session.scalar(
                select(Birthday)
                .where(Birthday.id == birthday_id)
                .where(Birthday.user_id == user_id)
            )
            if birthday is None:
                raise LocalizedError("err_birthday_not_found")

            if name is not None:
                clean_name = name.strip()
                if not clean_name:
                    raise LocalizedError("err_name_empty")
                birthday.name = clean_name
            if birth_date is not None:
                birthday.birth_date = birth_date

            try:
                session.flush()
            except IntegrityError as exc:
                raise LocalizedError("birthday_duplicate")
            return self._detach_birthday(session, birthday)

    def delete_birthday(self, user_id: str, birthday_id: int) -> bool:
        with get_session() as session:
            birthday = session.scalar(
                select(Birthday)
                .where(Birthday.id == birthday_id)
                .where(Birthday.user_id == user_id)
            )
            if birthday is None:
                return False
            session.delete(birthday)
            return True

    def get_agenda_for_today(
        self,
        user_id: str,
        *,
        on_date: date | None = None,
        context_chat_ids: frozenset[int] | None = None,
    ) -> TodayAgenda:
        today = on_date or now().date()
        day_start = datetime(today.year, today.month, today.day)
        day_end = day_start + timedelta(days=1)

        with get_session() as session:
            birthday_rows = session.scalars(
                select(Birthday)
                .where(Birthday.user_id == user_id)
                .where(extract("month", Birthday.birth_date) == today.month)
                .where(extract("day", Birthday.birth_date) == today.day)
                .order_by(Birthday.name.asc())
            ).all()

            birthdays = tuple(
                BirthdayToday(name=row.name, age=today.year - row.birth_date.year)
                for row in birthday_rows
            )

        if context_chat_ids is None:
            raise LocalizedError("err_context_chat_ids_required")
        calendar_events = CalendarService().list_events_for_contexts(
            context_chat_ids
        )
        recurring_ids = [event.id for event in calendar_events if event.is_recurring]
        exceptions_by_event = get_exception_service().get_exceptions_for_events(
            recurring_ids
        )
        agenda_events: list[AgendaEventToday] = []
        for event in calendar_events:
            excs = exceptions_by_event.get(event.id, [])
            for inst in resolve_occurrences_in_range(
                event, day_start, day_end, excs
            ):
                agenda_events.append(
                    AgendaEventToday(
                        event_id=event.id,
                        title=event.title,
                        starts_at=inst.starts_at,
                        ends_at=inst.ends_at,
                        is_all_day=event.is_all_day,
                        context_chat_id=event.context_chat_id,
                        is_recurring=event.is_recurring,
                        is_moved=inst.is_moved,
                    )
                )

        agenda_events.sort(key=lambda entry: (entry.starts_at, entry.title.lower()))
        return TodayAgenda(birthdays=birthdays, events=tuple(agenda_events))


def format_daily_agenda(
    agenda: TodayAgenda,
    *,
    include_birthdays: bool = True,
    include_events: bool = True,
    view_context_chat_id: int | None = None,
    locale: str = "de",
) -> str:
    if not include_birthdays and not include_events:
        return ""

    sections: list[str] = []

    if include_birthdays and agenda.birthdays:
        lines = [
            MessageFactory._t(
                "agenda_birthday_line",
                locale,
                name=entry.name,
                age=entry.age,
            )
            for entry in agenda.birthdays
        ]
        sections.append(
            MessageFactory._t("agenda_birthdays_today_header", locale) + "\n" + "\n".join(lines)
        )

    if include_events and agenda.events:
        lines = [
            _format_event_line(
                event, view_context_chat_id=view_context_chat_id, locale=locale
            )
            for event in agenda.events
        ]
        sections.append(
            MessageFactory._t("agenda_events_today_header", locale) + "\n" + "\n".join(lines)
        )

    if not sections:
        return ""
    return "\n\n".join(sections)


def _resolve_weather_location(
    user_id: str, on_date: date | None = None
) -> tuple[float, float, str, bool] | None:
    from services.travel import get_travel_service
    from services.user_service import get_user_service

    trip = get_travel_service().get_active_trip(user_id, on_date)
    if trip is not None:
        return trip.latitude, trip.longitude, trip.destination, True

    home = get_user_service().get_home_location(user_id)
    if home is None:
        return None

    latitude, longitude, name = home
    return latitude, longitude, name, False


async def build_daily_report(
    user_id: str,
    settings,
    *,
    on_date: date | None = None,
    context_chat_ids: frozenset[int] | None = None,
    view_context_chat_id: int | None = None,
) -> str:
    from services.locale_service import resolve_user_locale
    from services.weather import WeatherServiceError, get_weather_service, parse_todays_weather

    locale = resolve_user_locale(settings.locale, None)

    sections: list[str] = []
    agenda_service = get_agenda_service()
    agenda = agenda_service.get_agenda_for_today(
        user_id, on_date=on_date, context_chat_ids=context_chat_ids
    )

    if settings.include_weather:
        location = _resolve_weather_location(user_id, on_date)
        if location is None:
            sections.append(
                MessageFactory._t("agenda_weather_home_missing", locale)
            )
        else:
            latitude, longitude, name, is_travel = location
            try:
                data = await get_weather_service().get_forecast(latitude, longitude)
                weather = parse_todays_weather(data)
                if is_travel:
                    header = MessageFactory._t(
                        "agenda_weather_travel_header", locale, location_name=name
                    )
                    sections.append(
                        f"{header}\n"
                        + MessageFactory._t(
                            "agenda_weather_temp_line",
                            locale,
                            temperature=f"{weather.temperature:.1f}",
                            apparent_temperature=f"{weather.apparent_temperature:.1f}",
                        )
                        + "\n"
                        + MessageFactory._t(
                            "agenda_weather_range_line",
                            locale,
                            min_temperature=f"{weather.temperature_min:.0f}",
                            max_temperature=f"{weather.temperature_max:.0f}",
                        )
                    )
                else:
                    sections.append(
                        MessageFactory._t("agenda_weather_today_header", locale)
                        + "\n"
                        + MessageFactory._t(
                            "agenda_weather_location_line",
                            locale,
                            location_name=name,
                        )
                        + "\n"
                        + MessageFactory._t(
                            "agenda_weather_temp_line",
                            locale,
                            temperature=f"{weather.temperature:.1f}",
                            apparent_temperature=f"{weather.apparent_temperature:.1f}",
                        )
                        + "\n"
                        + MessageFactory._t(
                            "agenda_weather_range_line",
                            locale,
                            min_temperature=f"{weather.temperature_min:.0f}",
                            max_temperature=f"{weather.temperature_max:.0f}",
                        )
                    )
            except WeatherServiceError:
                sections.append(MessageFactory._t("agenda_weather_unavailable", locale))

    agenda_text = format_daily_agenda(
        agenda,
        include_birthdays=settings.include_birthdays,
        include_events=settings.include_events,
        view_context_chat_id=view_context_chat_id,
        locale=locale,
    )
    if agenda_text:
        sections.append(agenda_text)

    if not sections:
        return MessageFactory._t("agenda_empty_today", locale)
    return "\n\n".join(sections)


def _format_event_line(
    event: AgendaEventToday,
    *,
    view_context_chat_id: int | None = None,
    locale: str = "de",
) -> str:
    from services.user_service import event_source_label

    if event.is_moved:
        prefix = "↪️ "
    elif event.is_recurring:
        prefix = "🔁 "
    else:
        prefix = ""
    source_suffix = ""
    if view_context_chat_id is not None:
        source_label = event_source_label(
            event.context_chat_id, view_context_chat_id
        )
        if source_label:
            source_suffix = MessageFactory.format_source_suffix(
                source_label, locale=locale
            )
    title = f"*{event.title}*"
    if event.is_all_day:
        return MessageFactory._t(
            "agenda_event_all_day_line",
            locale,
            prefix=prefix,
            title=title,
            source_suffix=source_suffix,
        )
    when = MessageFactory.format_event_when(
        event.starts_at, event.ends_at, event.is_all_day, short=True, locale=locale
    )
    return MessageFactory._t(
        "agenda_event_time_line",
        locale,
        prefix=prefix,
        when=when,
        title=title,
        source_suffix=source_suffix,
    )


_agenda_service: Optional[AgendaService] = None


def get_agenda_service() -> AgendaService:
    global _agenda_service
    if _agenda_service is None:
        _agenda_service = AgendaService()
    return _agenda_service
