from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from handlers import wizard_shared as wz
from services.auth_service import get_auth_service, restricted
from services.calendar_service import (
    CalendarService,
    can_modify_event,
    parse_until_from_rrule,
    visible_context_ids_from_user_data,
)
from services.chat_membership_service import get_chat_membership_service
from services.locale_service import resolve_locale_for_handler
from telegram.constants import ChatType
from views.message_factory import MessageFactory

calendar_service = CalendarService()


@restricted
async def termin_bearbeiten_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not context.args:
        await update.message.reply_text(MessageFactory.termin_bearbeiten_usage(locale=locale))
        return ConversationHandler.END

    event_id = context.args[0].strip()
    if not calendar_service.is_valid_event_id(event_id):
        await update.message.reply_text(MessageFactory.termin_bearbeiten_usage(locale=locale))
        return ConversationHandler.END

    event = calendar_service.get_event_by_id(event_id)
    if event is None:
        await update.message.reply_text(MessageFactory.event_not_found(locale=locale))
        return ConversationHandler.END

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data["global_user_id"]
    auth = get_auth_service()
    visible_context_ids = None
    if update.effective_chat and update.effective_chat.type == ChatType.PRIVATE:
        visible_context_ids = await get_chat_membership_service().sync_memberships(
            context.bot, user_id
        )
        context.user_data["visible_context_ids"] = list(visible_context_ids)
    else:
        visible_context_ids = visible_context_ids_from_user_data(context.user_data)
    if not can_modify_event(
        event,
        chat_id,
        user_id,
        global_user_id,
        auth.is_admin(user_id),
        visible_context_ids=visible_context_ids,
    ):
        await update.message.reply_text(MessageFactory.event_permission_denied(locale=locale))
        return ConversationHandler.END

    saved_locale = locale
    saved_global_user_id = context.user_data.get("global_user_id")
    saved_visible_context_ids = context.user_data.get("visible_context_ids")
    context.user_data.clear()
    context.user_data["locale"] = saved_locale
    if saved_global_user_id is not None:
        context.user_data["global_user_id"] = saved_global_user_id
    if saved_visible_context_ids is not None:
        context.user_data["visible_context_ids"] = saved_visible_context_ids
    context.user_data["wizard_mode"] = "edit"
    context.user_data["event_id"] = event_id
    context.user_data["title"] = event.title
    context.user_data["starts_at"] = event.starts_at
    context.user_data["event_date"] = event.starts_at.date()
    context.user_data["is_recurring"] = event.is_recurring
    context.user_data["rrule"] = event.rrule
    context.user_data["until_date"] = parse_until_from_rrule(event.rrule)

    await update.message.reply_text(
        MessageFactory.conversation_edit_title(event.title, locale=locale)
    )
    return wz.TITLE


async def termin_bearbeiten_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = MessageFactory.DEFAULT_LOCALE
    if update.effective_user is not None:
        locale = resolve_locale_for_handler(context, update.effective_user)
    context.user_data.clear()
    await update.message.reply_text(
        MessageFactory.conversation_cancelled(locale=locale)
    )
    return ConversationHandler.END


@restricted
async def termin_bearbeiten_title(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text(MessageFactory.conversation_title_empty(locale=locale))
        return wz.TITLE

    context.user_data["title"] = title
    await update.message.reply_text(
        MessageFactory.conversation_edit_date(
            context.user_data["event_date"].strftime("%d.%m.%Y"), locale=locale
        )
    )
    return wz.DATE


@restricted
async def termin_bearbeiten_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    try:
        context.user_data["event_date"] = calendar_service.parse_date(
            update.message.text
        )
    except ValueError:
        await update.message.reply_text(
            MessageFactory.parse_error("Datum (DD.MM.YYYY)", locale=locale)
        )
        return wz.DATE

    current_time = context.user_data["starts_at"].strftime("%H:%M")
    await update.message.reply_text(
        MessageFactory.conversation_edit_time(current_time, locale=locale)
    )
    return wz.TIME


@restricted
async def termin_bearbeiten_time(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    try:
        event_time = calendar_service.parse_time(update.message.text)
        context.user_data["starts_at"] = calendar_service.build_datetime(
            context.user_data["event_date"], event_time
        )
    except ValueError:
        await update.message.reply_text(
            MessageFactory.parse_error("Uhrzeit (HH:MM)", locale=locale)
        )
        return wz.TIME

    await update.message.reply_text(
        MessageFactory.conversation_ask_recurring(locale=locale),
        reply_markup=wz.recurring_keyboard(locale=locale),
    )
    return wz.RECURRING


@restricted
async def termin_bearbeiten_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_recurring_callback(update, context, calendar_service)


@restricted
async def termin_bearbeiten_weekday_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_weekday_flow(update, context, calendar_service)


@restricted
async def termin_bearbeiten_until_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_until_callback(update, context)


@restricted
async def termin_bearbeiten_until_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_until_date_message(update, context, calendar_service)


@restricted
async def termin_bearbeiten_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_reminder_callback(update, context, calendar_service)


def build_termin_bearbeiten_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CommandHandler("termin_bearbeiten", termin_bearbeiten_start)
        ],
        states={
            wz.TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_bearbeiten_title)
            ],
            wz.DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_bearbeiten_date)
            ],
            wz.TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_bearbeiten_time)
            ],
            wz.RECURRING: [
                CallbackQueryHandler(
                    termin_bearbeiten_recurring, pattern=r"^recur:"
                ),
            ],
            wz.RECURRING_WEEKDAY: [
                CallbackQueryHandler(
                    termin_bearbeiten_weekday_flow, pattern=r"^recur:(wd|pos):"
                ),
            ],
            wz.RECUR_UNTIL: [
                CallbackQueryHandler(
                    termin_bearbeiten_until_callback, pattern=r"^recuruntil:"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, termin_bearbeiten_until_date
                ),
            ],
            wz.REMINDER: [
                CallbackQueryHandler(
                    termin_bearbeiten_reminder, pattern=r"^remind:"
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", termin_bearbeiten_cancel)],
        per_chat=True,
        per_user=True,
    )
