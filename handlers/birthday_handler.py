"""Birthday list, detail view, and deletion."""
from telegram import Update
from telegram.constants import ChatType
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.birthday_ui import render_birthday_detail, render_birthdays_list
from services.agenda import get_agenda_service
from services.auth_service import restricted
from views.message_factory import MessageFactory


def _private_only(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


@restricted
async def geburtstage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return
    await render_birthdays_list(update, context)


@restricted
async def birthday_callback_handler(
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

    service = get_agenda_service()

    if data == "list_birthdays":
        await render_birthdays_list(update, context)
        return

    if data.startswith("view_bday_"):
        birthday_id = int(data[len("view_bday_") :])
        birthday = service.get_birthday(global_user_id, birthday_id)
        if birthday is None:
            await query.edit_message_text(MessageFactory.birthday_not_found(locale=locale))
            return
        await render_birthday_detail(update, context, birthday)
        return

    if data.startswith("del_bday_"):
        birthday_id = int(data[len("del_bday_") :])
        if not service.delete_birthday(global_user_id, birthday_id):
            await query.edit_message_text(MessageFactory.birthday_not_found(locale=locale))
            return
        await render_birthdays_list(update, context)
        return


def register_birthday_handlers(application: Application) -> None:
    application.add_handler(CommandHandler(["birthdays", "geburtstage"], geburtstage_command))
    application.add_handler(
        CallbackQueryHandler(
            birthday_callback_handler,
            pattern=r"^(view_bday_\d+|del_bday_\d+|list_birthdays)$",
        )
    )
