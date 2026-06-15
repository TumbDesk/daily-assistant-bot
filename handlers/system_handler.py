import logging

from telegram import Chat, Update
from telegram.ext import Application, ContextTypes

from services.bot_commands import setup_bot_commands
from services.locale_service import resolve_locale_for_handler
from services.scheduler_service import restore_jobs
from views.message_factory import MessageFactory

logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unbehandelte Ausnahme aufgetreten:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_chat:
        if update.effective_chat.type == Chat.PRIVATE and update.message:
            locale = MessageFactory.DEFAULT_LOCALE
            if update.effective_user is not None:
                locale = resolve_locale_for_handler(context, update.effective_user)
            await update.message.reply_text(
                MessageFactory.generic_error(locale=locale)
            )


async def post_init(application: Application) -> None:
    from services.chat_membership_service import get_chat_membership_service

    get_chat_membership_service().bootstrap_bot_chats_from_events()
    restore_jobs(application)
    await setup_bot_commands(application)
