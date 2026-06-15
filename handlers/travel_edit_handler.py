"""Inline editing of travel destination and date range."""
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from handlers.travel_handler import parse_date_range
from handlers.travel_ui import render_trip_detail
from services.auth_service import restricted
from services.travel import get_travel_service
from services.weather import LocationNotFoundError, WeatherServiceError, resolve_location
from views.message_factory import MessageFactory

TDEST, TDATES = range(2)


def _store_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data["trip_edit_chat_id"] = query.message.chat_id
    context.user_data["trip_edit_message_id"] = query.message.message_id


def _clear_edit_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("trip_edit_id", None)
    context.user_data.pop("trip_edit_chat_id", None)
    context.user_data.pop("trip_edit_message_id", None)


@restricted
async def edit_trip_dest_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data[len("edit_trip_dest_") :])
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    trip = get_travel_service().get_trip(global_user_id, trip_id)
    if trip is None:
        await query.edit_message_text(MessageFactory.trip_not_found(locale=locale))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["trip_edit_id"] = trip_id
    await query.edit_message_text(
        MessageFactory.conversation_edit_trip_destination(locale=locale)
    )
    return TDEST


@restricted
async def edit_trip_dest_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    destination = update.message.text.strip()
    if not destination:
        await update.message.reply_text(MessageFactory.conversation_title_empty(locale=locale))
        return TDEST

    global_user_id = context.user_data["global_user_id"]
    trip_id = context.user_data["trip_edit_id"]

    try:
        location = await resolve_location(destination)
    except LocationNotFoundError:
        await update.message.reply_text(
            MessageFactory.weather_location_not_found(destination, locale=locale)
        )
        return TDEST
    except WeatherServiceError:
        await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))
        return TDEST

    try:
        trip = get_travel_service().update_trip(
            global_user_id,
            trip_id,
            destination=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
        )
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.localized_exception_message(exc, locale=locale)
        )
        return TDEST

    await render_trip_detail(update, context, trip)
    _clear_edit_state(context)
    return ConversationHandler.END


@restricted
async def edit_trip_dates_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    trip_id = int(query.data[len("edit_trip_dates_") :])
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    trip = get_travel_service().get_trip(global_user_id, trip_id)
    if trip is None:
        await query.edit_message_text(MessageFactory.trip_not_found(locale=locale))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["trip_edit_id"] = trip_id
    current = (
        f"{trip.start_date.strftime('%d.%m.%Y')} – "
        f"{trip.end_date.strftime('%d.%m.%Y')}"
    )
    await query.edit_message_text(
        MessageFactory.conversation_edit_trip_dates(current, locale=locale)
    )
    return TDATES


@restricted
async def edit_trip_dates_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    try:
        start_date, end_date = parse_date_range(update.message.text)
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.agenda_parse_error(exc, locale=locale)
        )
        return TDATES

    global_user_id = context.user_data["global_user_id"]
    trip_id = context.user_data["trip_edit_id"]
    try:
        trip = get_travel_service().update_trip(
            global_user_id,
            trip_id,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.localized_exception_message(exc, locale=locale)
        )
        return TDATES

    await render_trip_detail(update, context, trip)
    _clear_edit_state(context)
    return ConversationHandler.END


@restricted
async def trip_edit_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_edit_state(context)
    await update.message.reply_text(
        MessageFactory.conversation_cancelled(
            locale=context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
        )
    )
    return ConversationHandler.END


def build_trip_dest_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_trip_dest_start, pattern=r"^edit_trip_dest_\d+$"
            )
        ],
        states={
            TDEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_trip_dest_save)
            ],
        },
        fallbacks=[CommandHandler("cancel", trip_edit_cancel)],
        allow_reentry=True,
    )


def build_trip_dates_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_trip_dates_start, pattern=r"^edit_trip_dates_\d+$"
            )
        ],
        states={
            TDATES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_trip_dates_save)
            ],
        },
        fallbacks=[CommandHandler("cancel", trip_edit_cancel)],
        allow_reentry=True,
    )


def register_travel_edit_handlers(application) -> None:
    application.add_handler(build_trip_dest_conversation())
    application.add_handler(build_trip_dates_conversation())
