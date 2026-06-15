import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram.ext import Application, ContextTypes

from services.calendar_service import CalendarService, EventDTO
from services.timezone_util import as_local, now, to_naive_local
from views.message_factory import MessageFactory

logger = logging.getLogger(__name__)

REMINDER_NONE = 0
REMINDER_15_MIN = 15
REMINDER_1_HOUR = 60
REMINDER_1_DAY = 1440

calendar_service = CalendarService()


def _resolve_owner_locale(owner_id: str | None) -> str:
    if not owner_id:
        return MessageFactory.DEFAULT_LOCALE
    try:
        from services.locale_service import resolve_user_locale
        from services.user_settings import get_user_settings_service

        settings = get_user_settings_service().get_settings(owner_id)
        return resolve_user_locale(settings.locale, None)
    except Exception:
        return MessageFactory.DEFAULT_LOCALE


def _job_name(event_id: str) -> str:
    return f"reminder-{event_id}"


def compute_reminder_time(occurrence_start: datetime, offset_minutes: int) -> datetime:
    return as_local(occurrence_start) - timedelta(minutes=offset_minutes)


def _resolve_next_schedulable_occurrence(
    event: EventDTO, current: datetime, exceptions=None
) -> Optional[datetime]:
    from datetime import timedelta

    from services.event_exceptions import get_exception_service
    from services.event_filter import resolve_occurrences_in_range

    current_local = as_local(current)
    starts_at = as_local(event.starts_at)
    if not event.is_recurring or not event.rrule:
        if starts_at <= current_local:
            return None
        return starts_at

    if exceptions is None:
        exceptions = get_exception_service().get_exceptions_for_event(event.id)

    window_end = to_naive_local(current) + timedelta(days=730)
    for inst in resolve_occurrences_in_range(
        event, to_naive_local(current), window_end, exceptions
    ):
        occurrence = as_local(inst.starts_at)
        if occurrence <= current_local:
            continue
        reminder_at = compute_reminder_time(occurrence, event.reminder_offset)
        if reminder_at > current_local:
            return inst.starts_at
    return None


def cancel_reminder(job_queue, event_id: str) -> None:
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(_job_name(event_id)):
        job.schedule_removal()


def schedule_reminder(job_queue, event: EventDTO, occurrence_at: datetime) -> None:
    if job_queue is None:
        logger.warning("Keine Job-Queue – Erinnerung für Event %s nicht planbar.", event.id)
        return
    if event.reminder_offset <= 0:
        return

    current = now()
    occurrence_local = as_local(occurrence_at)
    reminder_at = compute_reminder_time(occurrence_local, event.reminder_offset)
    if reminder_at <= current:
        logger.warning(
            "Erinnerung für Event %s übersprungen (liegt in der Vergangenheit). "
            "Jetzt=%s, Erinnerung=%s, Termin=%s, TZ=%s",
            event.id,
            current.strftime("%d.%m.%Y %H:%M %Z"),
            reminder_at.strftime("%d.%m.%Y %H:%M %Z"),
            occurrence_local.strftime("%d.%m.%Y %H:%M %Z"),
            current.tzinfo,
        )
        return

    cancel_reminder(job_queue, event.id)
    job_queue.run_once(
        reminder_callback,
        when=reminder_at,
        data={
            "event_id": event.id,
            "occurrence_iso": occurrence_local.isoformat(),
        },
        name=_job_name(event.id),
    )
    logger.info(
        "Erinnerung für Event %s geplant: %s (Termin: %s, TZ=%s)",
        event.id,
        reminder_at.strftime("%d.%m.%Y %H:%M %Z"),
        occurrence_local.strftime("%d.%m.%Y %H:%M %Z"),
        current.tzinfo,
    )


def reschedule_event_reminder(job_queue, event: EventDTO) -> None:
    cancel_reminder(job_queue, event.id)
    if event.reminder_offset <= 0:
        return
    from services.event_exceptions import get_exception_service

    exceptions = get_exception_service().get_exceptions_for_event(event.id)
    next_occ = _resolve_next_schedulable_occurrence(event, now(), exceptions)
    if next_occ is not None:
        schedule_reminder(job_queue, event, next_occ)


async def reminder_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data or {}
    event_id = data.get("event_id")
    occurrence_iso = data.get("occurrence_iso")
    if not event_id or not occurrence_iso:
        return

    event = calendar_service.get_event_by_id(event_id)
    if event is None:
        cancel_reminder(context.job_queue, event_id)
        return

    occurrence_at = datetime.fromisoformat(occurrence_iso)
    locale = _resolve_owner_locale(getattr(event, "owner_id", None))
    await context.bot.send_message(
        chat_id=event.context_chat_id,
        text=MessageFactory.reminder_notification(
            event.title, occurrence_at, locale=locale
        ),
    )

    if event.is_recurring and event.rrule:
        from services.event_exceptions import get_exception_service

        exceptions = get_exception_service().get_exceptions_for_event(event_id)
        next_occ = _resolve_next_schedulable_occurrence(
            event, occurrence_at, exceptions
        )
        if next_occ is not None:
            schedule_reminder(context.job_queue, event, next_occ)


DAILY_REPORT_JOB_NAME = "daily-report-tick"


def _cancel_daily_report_tick(job_queue) -> None:
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(DAILY_REPORT_JOB_NAME):
        job.schedule_removal()


def schedule_daily_reports(job_queue) -> None:
    if job_queue is None:
        logger.warning(
            "Job-Queue nicht verfügbar – tägliche Agenda-Berichte nicht planbar."
        )
        return

    _cancel_daily_report_tick(job_queue)
    job_queue.run_repeating(
        daily_report_callback,
        interval=60,
        first=10,
        name=DAILY_REPORT_JOB_NAME,
    )
    logger.info("Minuten-Tick für tägliche Agenda-Berichte gestartet.")


async def daily_report_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.constants import ParseMode

    from services.agenda import build_daily_report
    from services.user_settings import get_user_settings_service

    settings_service = get_user_settings_service()
    current = now()
    due_users = settings_service.list_users_due_for_report(
        current.strftime("%H:%M"),
        current.date(),
    )

    from services.chat_membership_service import get_chat_membership_service

    membership_service = get_chat_membership_service()
    for user_id, platform_user_id in due_users:
        try:
            settings = settings_service.get_settings(user_id)
            visible_context_ids = await membership_service.sync_memberships(
                context.bot, int(platform_user_id)
            )
            text = await build_daily_report(
                user_id,
                settings,
                context_chat_ids=visible_context_ids,
                view_context_chat_id=int(platform_user_id),
            )
            await context.bot.send_message(
                chat_id=int(platform_user_id),
                text=text,
                parse_mode=ParseMode.MARKDOWN,
            )
            settings_service.mark_report_sent(user_id, current.date())
        except Exception:
            logger.exception(
                "Täglicher Agenda-Bericht fehlgeschlagen für User %s.", user_id
            )


WEATHER_ALERT_JOB_NAME = "weather-alert-tick"
WEATHER_ALERT_LOOKAHEAD = timedelta(hours=1)


def _cancel_weather_alert_tick(job_queue) -> None:
    if job_queue is None:
        return
    for job in job_queue.get_jobs_by_name(WEATHER_ALERT_JOB_NAME):
        job.schedule_removal()


def schedule_weather_alerts(job_queue) -> None:
    if job_queue is None:
        logger.warning(
            "Job-Queue nicht verfügbar – stündliche Regen-Warnungen nicht planbar."
        )
        return

    _cancel_weather_alert_tick(job_queue)
    job_queue.run_repeating(
        check_weather_alerts,
        interval=3600,
        first=30,
        name=WEATHER_ALERT_JOB_NAME,
    )
    logger.info("Stündlicher Tick für Regen-Warnungen gestartet.")


def _imminent_rain_blocks(rain_blocks, current: datetime):
    from services.weather import RAIN_PROBABILITY_THRESHOLD

    window_end = current + WEATHER_ALERT_LOOKAHEAD
    imminent = []
    for block in rain_blocks:
        if block.max_probability < RAIN_PROBABILITY_THRESHOLD:
            continue
        if current <= block.start <= window_end:
            imminent.append(block)
    return imminent


async def check_weather_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram.constants import ParseMode

    from services.agenda import _resolve_weather_location
    from services.user_settings import get_user_settings_service
    from services.weather import (
        WeatherServiceError,
        format_rain_risk_lines,
        get_weather_service,
        parse_todays_weather,
    )

    settings_service = get_user_settings_service()
    current = now()

    for user_id, platform_user_id in settings_service.list_users_for_weather_alerts():
        try:
            settings = settings_service.get_settings(user_id)
            locale = _resolve_owner_locale(user_id)
            if not settings.report_enabled or not settings.include_weather:
                continue

            location = _resolve_weather_location(user_id, on_date=current.date())
            if location is None:
                continue

            latitude, longitude, name, _is_travel = location
            data = await get_weather_service().get_forecast(latitude, longitude)
            weather = parse_todays_weather(data)
            imminent = _imminent_rain_blocks(weather.rain_blocks, current)
            if not imminent:
                continue

            rain_lines = format_rain_risk_lines(
                max(block.max_probability for block in imminent),
                tuple(imminent),
                locale=locale,
            )
            await context.bot.send_message(
                chat_id=int(platform_user_id),
                text=MessageFactory.weather_rain_alert(
                    name, rain_lines, locale=locale
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except WeatherServiceError:
            logger.warning("Regen-Warnung: Wetter-API für User %s fehlgeschlagen.", user_id)
        except Exception:
            logger.exception("Regen-Warnung fehlgeschlagen für User %s.", user_id)


def restore_jobs(application: Application) -> None:
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning(
            "Job-Queue nicht verfügbar. Installiere python-telegram-bot[job-queue]."
        )
        return

    current = now()
    events = calendar_service.list_events_with_reminders()
    restored = 0

    for event in events:
        occurrence = _resolve_next_schedulable_occurrence(event, current)
        if occurrence is not None:
            schedule_reminder(job_queue, event, occurrence)
            restored += 1

    logger.info("%s Erinnerungs-Job(s) wiederhergestellt.", restored)
    schedule_daily_reports(job_queue)
    schedule_weather_alerts(job_queue)
