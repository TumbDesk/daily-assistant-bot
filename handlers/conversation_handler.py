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
from handlers.termin_neu_handler import create_from_parsed_text
from services.auth_service import restricted
from services.calendar_service import CalendarService
from services.locale_service import resolve_locale_for_handler
from views.message_factory import MessageFactory

calendar_service = CalendarService()


@restricted
async def termin_neu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if context.args:
        await create_from_parsed_text(
            update, context, " ".join(context.args)
        )
        return ConversationHandler.END

    saved_locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    saved_global_user_id = context.user_data.get("global_user_id")
    context.user_data.clear()
    context.user_data["locale"] = saved_locale
    if saved_global_user_id is not None:
        context.user_data["global_user_id"] = saved_global_user_id
    context.user_data["wizard_mode"] = "create"
    await update.message.reply_text(
        MessageFactory.conversation_ask_title(locale=saved_locale)
    )
    return wz.TITLE


async def termin_neu_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    locale = MessageFactory.DEFAULT_LOCALE
    if update.effective_user is not None:
        locale = resolve_locale_for_handler(context, update.effective_user)
    context.user_data.clear()
    await update.message.reply_text(
        MessageFactory.conversation_cancelled(locale=locale)
    )
    return ConversationHandler.END


@restricted
async def termin_neu_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text(MessageFactory.conversation_title_empty(locale=locale))
        return wz.TITLE

    context.user_data["title"] = title
    await update.message.reply_text(MessageFactory.conversation_ask_date(locale=locale))
    return wz.DATE


@restricted
async def termin_neu_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    await update.message.reply_text(MessageFactory.conversation_ask_time(locale=locale))
    return wz.TIME


@restricted
async def termin_neu_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
async def termin_neu_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_recurring_callback(update, context, calendar_service)


@restricted
async def termin_neu_weekday_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_weekday_flow(update, context, calendar_service)


@restricted
async def termin_neu_until_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_until_callback(update, context)


@restricted
async def termin_neu_until_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_until_date_message(update, context, calendar_service)


@restricted
async def termin_neu_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    return await wz.handle_reminder_callback(update, context, calendar_service)


def build_termin_neu_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler(["event", "termin"], termin_neu_command)],
        states={
            wz.TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_neu_title)
            ],
            wz.DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_neu_date)
            ],
            wz.TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, termin_neu_time)
            ],
            wz.RECURRING: [
                CallbackQueryHandler(termin_neu_recurring, pattern=r"^recur:")
            ],
            wz.RECURRING_WEEKDAY: [
                CallbackQueryHandler(
                    termin_neu_weekday_flow, pattern=r"^recur:(wd|pos):"
                ),
            ],
            wz.RECUR_UNTIL: [
                CallbackQueryHandler(
                    termin_neu_until_callback, pattern=r"^recuruntil:"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, termin_neu_until_date
                ),
            ],
            wz.REMINDER: [
                CallbackQueryHandler(termin_neu_reminder, pattern=r"^remind:")
            ],
        },
        fallbacks=[CommandHandler("cancel", termin_neu_cancel)],
        per_chat=True,
        per_user=True,
    )
