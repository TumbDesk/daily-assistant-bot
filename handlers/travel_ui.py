"""Shared rendering of the interactive travel list."""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from handlers.telegram_util import safe_edit_message_text
from services.travel import get_travel_service
from views.message_factory import MessageFactory


async def render_trips_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    trips = get_travel_service().list_trips(global_user_id)
    text, keyboard = MessageFactory.create_trips_view(trips, locale=locale)

    if update.callback_query:
        await safe_edit_message_text(
            update.callback_query,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )


async def render_trip_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    trip,
) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    text = MessageFactory.trip_detail_text(trip, locale=locale)
    keyboard = MessageFactory.create_trip_detail_keyboard(trip.id, locale=locale)
    query = update.callback_query

    if query is not None:
        await safe_edit_message_text(
            query, text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
    else:
        chat_id = context.user_data.get("trip_edit_chat_id")
        message_id = context.user_data.get("trip_edit_message_id")
        if chat_id and message_id:
            await update.get_bot().edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        elif update.message:
            await update.message.reply_text(
                text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
            )
