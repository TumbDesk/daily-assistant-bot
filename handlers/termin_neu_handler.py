"""Free-text event creation via /event|/termin <text>."""
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from services.calendar_service import CalendarService
from services.parser import TerminParseError, parse_event_text
from services.scheduler_service import schedule_reminder
from services.user_service import PLATFORM_TELEGRAM, get_user_service, visible_context_chat_id
from views.keyboards import build_category_suggestion_keyboard
from views.message_factory import MessageFactory

calendar_service = CalendarService()


async def create_from_parsed_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    user_service = get_user_service()
    platform_user_id = str(update.effective_user.id)
    global_user_id = user_service.resolve_user_id(
        PLATFORM_TELEGRAM,
        platform_user_id,
        update.effective_user.full_name,
    )
    if global_user_id is None:
        await update.message.reply_text(MessageFactory.access_denied(locale=locale))
        return

    categories = calendar_service.list_categories_dto(global_user_id)
    try:
        parsed = parse_event_text(text, user_categories=categories, locale=locale)
    except TerminParseError as exc:
        await update.message.reply_text(
            MessageFactory.termin_parse_error(exc, locale=locale),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    context_chat_id = visible_context_chat_id(
        update.effective_chat.id, update.effective_user.id
    )
    event = calendar_service.create_from_parsed(
        global_user_id, context_chat_id, parsed
    )
    schedule_reminder(context.application.job_queue, event, event.starts_at)

    body = MessageFactory.termin_parsed_success(
        event.title,
        event.starts_at,
        event.is_recurring,
        event.rrule,
        reminder_offset=event.reminder_offset,
        ends_at=event.ends_at,
        is_all_day=event.is_all_day,
        category_name=event.category_name,
        flag_names=event.flag_names,
        locale=context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE),
    )

    reply_markup = None
    if parsed.category_id is None and categories:
        suggestions = calendar_service.list_categories_for_suggestions(global_user_id)
        if suggestions:
            body = f"{body}\n\n{MessageFactory.category_pick_prompt(locale=locale)}"
            reply_markup = build_category_suggestion_keyboard(
                event.id, suggestions, locale=locale
            )

    await update.message.reply_text(
        body,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )
