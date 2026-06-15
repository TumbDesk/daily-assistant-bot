"""Inline editing of birthday names and dates."""
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from handlers.birthday_ui import render_birthday_detail
from services.agenda import get_agenda_service
from services.auth_service import restricted
from services.calendar_service import CalendarService
from views.message_factory import MessageFactory

calendar_service = CalendarService()

BNAME, BDATE = range(2)


def _store_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data["bday_edit_chat_id"] = query.message.chat_id
    context.user_data["bday_edit_message_id"] = query.message.message_id


@restricted
async def edit_bday_name_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    birthday_id = int(query.data[len("edit_bday_name_") :])
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    birthday = get_agenda_service().get_birthday(global_user_id, birthday_id)
    if birthday is None:
        await query.edit_message_text(MessageFactory.birthday_not_found(locale=locale))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["bday_edit_id"] = birthday_id
    await query.edit_message_text(
        MessageFactory.conversation_edit_birthday_name(locale=locale)
    )
    return BNAME


@restricted
async def edit_bday_name_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text(MessageFactory.conversation_title_empty(locale=locale))
        return BNAME

    global_user_id = context.user_data["global_user_id"]
    birthday_id = context.user_data["bday_edit_id"]
    try:
        birthday = get_agenda_service().update_birthday(
            global_user_id, birthday_id, name=name
        )
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.localized_exception_message(exc, locale=locale)
        )
        return BNAME

    await render_birthday_detail(update, context, birthday)
    context.user_data.pop("bday_edit_id", None)
    context.user_data.pop("bday_edit_chat_id", None)
    context.user_data.pop("bday_edit_message_id", None)
    return ConversationHandler.END


@restricted
async def edit_bday_date_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    birthday_id = int(query.data[len("edit_bday_date_") :])
    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    birthday = get_agenda_service().get_birthday(global_user_id, birthday_id)
    if birthday is None:
        await query.edit_message_text(MessageFactory.birthday_not_found(locale=locale))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["bday_edit_id"] = birthday_id
    current = birthday.birth_date.strftime("%d.%m.%Y")
    await query.edit_message_text(
        MessageFactory.conversation_edit_birthday_date(current, locale=locale)
    )
    return BDATE


@restricted
async def edit_bday_date_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    try:
        birth_date = calendar_service.parse_date(update.message.text)
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.agenda_parse_error(exc, locale=locale)
        )
        return BDATE

    global_user_id = context.user_data["global_user_id"]
    birthday_id = context.user_data["bday_edit_id"]
    try:
        birthday = get_agenda_service().update_birthday(
            global_user_id, birthday_id, birth_date=birth_date
        )
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.localized_exception_message(exc, locale=locale)
        )
        return BDATE

    await render_birthday_detail(update, context, birthday)
    context.user_data.pop("bday_edit_id", None)
    context.user_data.pop("bday_edit_chat_id", None)
    context.user_data.pop("bday_edit_message_id", None)
    return ConversationHandler.END


@restricted
async def birthday_edit_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.pop("bday_edit_id", None)
    context.user_data.pop("bday_edit_chat_id", None)
    context.user_data.pop("bday_edit_message_id", None)
    await update.message.reply_text(
        MessageFactory.conversation_cancelled(
            locale=context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
        )
    )
    return ConversationHandler.END


def build_birthday_name_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_bday_name_start, pattern=r"^edit_bday_name_\d+$"
            )
        ],
        states={
            BNAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_bday_name_save)
            ],
        },
        fallbacks=[CommandHandler("cancel", birthday_edit_cancel)],
        allow_reentry=True,
    )


def build_birthday_date_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                edit_bday_date_start, pattern=r"^edit_bday_date_\d+$"
            )
        ],
        states={
            BDATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_bday_date_save)
            ],
        },
        fallbacks=[CommandHandler("cancel", birthday_edit_cancel)],
        allow_reentry=True,
    )


def register_birthday_edit_handlers(application) -> None:
    application.add_handler(build_birthday_name_conversation())
    application.add_handler(build_birthday_date_conversation())
