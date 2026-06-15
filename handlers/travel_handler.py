"""Travel commands for vacation weather in the agenda."""
import re

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.travel_ui import render_trip_detail, render_trips_list
from services.auth_service import restricted
from services.calendar_service import CalendarService
from services.i18n_util import LocalizedError
from services.travel import get_travel_service
from services.weather import LocationNotFoundError, WeatherServiceError, resolve_location
from views.message_factory import MessageFactory

_REISE_PATTERN = re.compile(
    r"^(.+?)\s+(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})$"
)
_DATE_RANGE_PATTERN = re.compile(
    r"^(\d{1,2}\.\d{1,2}\.\d{4})\s*-\s*(\d{1,2}\.\d{1,2}\.\d{4})$"
)


def _private_only(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


def parse_date_range(text: str) -> tuple[object, object]:
    match = _DATE_RANGE_PATTERN.match(text.strip())
    if not match:
        raise LocalizedError("err_trip_date_format")

    start_date = CalendarService.parse_date(match.group(1))
    end_date = CalendarService.parse_date(match.group(2))
    if end_date < start_date:
        raise LocalizedError("err_trip_end_before_start")

    return start_date, end_date


def _parse_reise_args(args: list[str]) -> tuple[str, object, object]:
    if not args:
        raise LocalizedError("err_trip_location_period")

    text = " ".join(args).strip()
    match = _REISE_PATTERN.match(text)
    if not match:
        raise LocalizedError("err_trip_format")

    destination = match.group(1).strip()
    if not destination:
        raise LocalizedError("err_location_empty")

    start_date = CalendarService.parse_date(match.group(2))
    end_date = CalendarService.parse_date(match.group(3))
    if end_date < start_date:
        raise LocalizedError("err_trip_end_before_start")

    return destination, start_date, end_date


@restricted
async def reise_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return

    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not context.args:
        await update.message.reply_text(MessageFactory.reise_usage(locale=locale))
        return

    global_user_id = context.user_data["global_user_id"]

    try:
        destination, start_date, end_date = _parse_reise_args(context.args)
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.agenda_parse_error(exc, locale=locale)
        )
        return

    try:
        location = await resolve_location(destination)
    except LocationNotFoundError:
        await update.message.reply_text(
            MessageFactory.weather_location_not_found(destination, locale=locale)
        )
        return
    except WeatherServiceError:
        await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))
        return

    get_travel_service().add_trip(
        global_user_id,
        location.name,
        location.latitude,
        location.longitude,
        start_date,
        end_date,
    )
    await update.message.reply_text(
        MessageFactory.reise_success(
            location.name, start_date, end_date, locale=locale
        )
    )


@restricted
async def reisen_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return
    await render_trips_list(update, context)


@restricted
async def travel_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    if query is None or not query.data or not _private_only(update):
        return

    await query.answer()
    data = query.data
    global_user_id = context.user_data.get("global_user_id")
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not global_user_id:
        return

    service = get_travel_service()

    if data == "list_trips":
        await render_trips_list(update, context)
        return

    if data.startswith("view_trip_"):
        trip_id = int(data[len("view_trip_") :])
        trip = service.get_trip(global_user_id, trip_id)
        if trip is None:
            await query.edit_message_text(MessageFactory.trip_not_found(locale=locale))
            return
        await render_trip_detail(update, context, trip)
        return

    if data.startswith("del_trip_"):
        trip_id = int(data[len("del_trip_") :])
        if not service.delete_trip(global_user_id, trip_id):
            await query.edit_message_text(MessageFactory.trip_not_found(locale=locale))
            return
        await render_trips_list(update, context)
        return


def register_travel_handlers(application: Application) -> None:
    application.add_handler(CommandHandler(["trip", "reise"], reise_command))
    application.add_handler(CommandHandler(["trips", "reisen"], reisen_command))
    application.add_handler(
        CallbackQueryHandler(
            travel_callback_handler,
            pattern=r"^(view_trip_\d+|del_trip_\d+|list_trips)$",
        )
    )
