"""Shared rendering of the interactive birthday list."""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from handlers.telegram_util import safe_edit_message_text
from services.agenda import get_agenda_service
from views.message_factory import MessageFactory


async def render_birthdays_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    birthdays = get_agenda_service().list_birthdays(global_user_id)
    text, keyboard = MessageFactory.create_birthdays_view(birthdays, locale=locale)

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


async def render_birthday_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    birthday,
) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    text = MessageFactory.birthday_detail_text(birthday, locale=locale)
    keyboard = MessageFactory.create_birthday_detail_keyboard(birthday.id, locale=locale)
    query = update.callback_query

    if query is not None:
        await safe_edit_message_text(
            query, text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
    else:
        chat_id = context.user_data.get("bday_edit_chat_id")
        message_id = context.user_data.get("bday_edit_message_id")
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
