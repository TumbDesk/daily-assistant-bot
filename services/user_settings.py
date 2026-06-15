"""Agenda report settings per user."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import or_, select

from database import User, UserIdentity, get_session
from services.calendar_service import CalendarService
from services.locale_service import normalize_locale
from services.user_service import PLATFORM_TELEGRAM
from views.message_factory import MessageFactory

DEFAULT_REPORT_TIME = "07:00"
TOGGLE_FIELDS = frozenset(
    {
        "report_enabled",
        "include_events",
        "include_birthdays",
        "include_weather",
    }
)


@dataclass(frozen=True)
class UserSettings:
    report_enabled: bool
    report_time: str
    include_events: bool
    include_birthdays: bool
    include_weather: bool
    locale: Optional[str] = None


def _settings_from_user(user: User) -> UserSettings:
    return UserSettings(
        report_enabled=user.report_enabled
        if user.report_enabled is not None
        else True,
        report_time=user.report_time or DEFAULT_REPORT_TIME,
        include_events=user.include_events if user.include_events is not None else True,
        include_birthdays=user.include_birthdays
        if user.include_birthdays is not None
        else True,
        include_weather=user.include_weather if user.include_weather is not None else True,
        locale=user.locale,
    )


class UserSettingsService:
    def get_settings(self, user_id: str) -> UserSettings:
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("User nicht gefunden.")
            return _settings_from_user(user)

    def update_settings(self, user_id: str, **kwargs) -> UserSettings:
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                raise ValueError("User nicht gefunden.")
            for key, value in kwargs.items():
                if not hasattr(user, key):
                    raise ValueError(f"Unbekanntes Feld: {key}")
                setattr(user, key, value)
            session.flush()
            return _settings_from_user(user)

    def toggle_setting(self, user_id: str, field: str) -> UserSettings:
        if field not in TOGGLE_FIELDS:
            raise ValueError(f"Unbekanntes Toggle-Feld: {field}")
        current = self.get_settings(user_id)
        new_value = not getattr(current, field)
        return self.update_settings(user_id, **{field: new_value})

    def set_locale(self, user_id: str, locale: str) -> UserSettings:
        normalized = normalize_locale(locale.strip())
        if not normalized or normalized not in MessageFactory._TRANSLATIONS:
            supported = ", ".join(sorted(MessageFactory._TRANSLATIONS.keys()))
            raise ValueError(f"Unbekannte Sprache. Verfügbar: {supported}")
        return self.update_settings(user_id, locale=normalized)

    def set_report_time(self, user_id: str, time_str: str) -> UserSettings:
        parsed = CalendarService.parse_time(time_str.strip())
        formatted = parsed.strftime("%H:%M")
        return self.update_settings(user_id, report_time=formatted)

    def cycle_report_time(self, user_id: str, direction: int) -> UserSettings:
        current = self.get_settings(user_id)
        parsed = CalendarService.parse_time(current.report_time)
        base = datetime.combine(date.today(), parsed)
        shifted = base + timedelta(minutes=30 * direction)
        formatted = shifted.time().strftime("%H:%M")
        return self.update_settings(user_id, report_time=formatted)

    def list_users_due_for_report(
        self, now_hhmm: str, today: date
    ) -> list[tuple[str, str]]:
        with get_session() as session:
            time_match = [User.report_time == now_hhmm]
            if now_hhmm == DEFAULT_REPORT_TIME:
                time_match.append(User.report_time.is_(None))
            stmt = (
                select(User.id, UserIdentity.platform_user_id)
                .join(UserIdentity, UserIdentity.user_id == User.id)
                .where(UserIdentity.platform == PLATFORM_TELEGRAM)
                .where(
                    or_(User.report_enabled.is_(True), User.report_enabled.is_(None))
                )
                .where(or_(*time_match))
                .where(
                    or_(User.last_report_date.is_(None), User.last_report_date != today)
                )
            )
            rows = session.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def list_users_for_weather_alerts(self) -> list[tuple[str, str]]:
        """Users with active daily report and weather module (Telegram)."""
        with get_session() as session:
            stmt = (
                select(User.id, UserIdentity.platform_user_id)
                .join(UserIdentity, UserIdentity.user_id == User.id)
                .where(UserIdentity.platform == PLATFORM_TELEGRAM)
                .where(User.report_enabled.isnot(False))
                .where(User.include_weather.isnot(False))
            )
            rows = session.execute(stmt).all()
        return [(row[0], row[1]) for row in rows]

    def mark_report_sent(self, user_id: str, sent_date: date) -> None:
        self.update_settings(user_id, last_report_date=sent_date)


_settings_service: Optional[UserSettingsService] = None


def get_user_settings_service() -> UserSettingsService:
    global _settings_service
    if _settings_service is None:
        _settings_service = UserSettingsService()
    return _settings_service
