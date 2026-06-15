"""Inline callbacks for category follow-up selection after free-text creation."""
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from handlers.telegram_util import safe_edit_message_text
from services.auth_service import restricted
from services.calendar_service import CalendarService
from services.user_service import PLATFORM_TELEGRAM, get_user_service
from views.message_factory import MessageFactory

logger = logging.getLogger(__name__)
calendar_service = CalendarService()


@restricted
async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 2:
        return
    action = parts[0]
    event_id = parts[1]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    global_user_id = context.user_data.get("global_user_id")
    if not global_user_id:
        return

    user_service = get_user_service()
    platform_user_id = str(update.effective_user.id)
    is_admin = user_service.is_admin(PLATFORM_TELEGRAM, platform_user_id)

    event = calendar_service.get_event_by_id(event_id)
    if event is None or (
        event.owner_id != global_user_id and not is_admin
    ):
        await safe_edit_message_text(
            query, MessageFactory.event_permission_denied(locale=locale)
        )
        return

    if action == "cat_skip":
        await safe_edit_message_text(
            query,
            MessageFactory.category_skipped(event.title, locale=locale),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if action == "cat_set" and len(parts) >= 3:
        try:
            category_id = int(parts[2])
        except ValueError:
            return
        updated = calendar_service.assign_category(
            event_id,
            category_id,
            global_user_id,
            is_admin=is_admin,
        )
        if updated is None:
            await safe_edit_message_text(
                query, MessageFactory.event_permission_denied(locale=locale)
            )
            return
        await safe_edit_message_text(
            query,
            MessageFactory.category_assigned(
                updated.title,
                updated.category_name or "",
                locale=locale,
            ),
            parse_mode=ParseMode.MARKDOWN,
        )


def register_category_callbacks(application: Application) -> None:
    application.add_handler(
        CallbackQueryHandler(category_callback, pattern=r"^cat_(set|skip):")
    )
