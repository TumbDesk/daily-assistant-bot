from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.telegram_util import safe_edit_message_text
from handlers.termine_ui import render_termine_list
from services.auth_service import restricted
from services.calendar_service import CalendarService
from services.event_filter import EventFilterPreset, parse_callback_data, parse_filter_arg
from views.message_factory import MessageFactory

calendar_service = CalendarService()


@restricted
async def termine_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    parsed = parse_filter_arg(context.args) if context.args else None
    if parsed is not None and parsed.preset not in (
        EventFilterPreset.PICK_MONTH,
        EventFilterPreset.PICK_YEAR,
    ):
        await render_termine_list(update, context, parsed)
    else:
        await render_termine_list(update, context)


@restricted
async def termine_ui_filter_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "noop":
        return

    ui_filter = query.data.removeprefix("filter_")
    context.user_data.pop("termine_filter", None)
    await render_termine_list(update, context, ui_filter=ui_filter)


@restricted
async def termine_filter_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)

    parts = query.data.split(":")
    if len(parts) >= 3 and parts[1] == "yy":
        text = MessageFactory.year_picker_text(int(parts[2]), locale=locale)
        keyboard = MessageFactory.year_picker_keyboard(int(parts[2]), locale=locale)
        await safe_edit_message_text(query, text, reply_markup=keyboard)
        return

    parsed = parse_callback_data(query.data)

    if parsed.preset == EventFilterPreset.PICK_MONTH:
        year = parsed.picker_year or parsed.year
        text = MessageFactory.month_picker_text(year, locale=locale)
        keyboard = MessageFactory.month_picker_keyboard(year, locale=locale)
        await safe_edit_message_text(query, text, reply_markup=keyboard)
        return

    if parsed.preset == EventFilterPreset.PICK_YEAR:
        year = parsed.picker_year or parsed.year
        text = MessageFactory.year_picker_text(year, locale=locale)
        keyboard = MessageFactory.year_picker_keyboard(year, locale=locale)
        await safe_edit_message_text(query, text, reply_markup=keyboard)
        return

    await render_termine_list(update, context, parsed)


def register_termine_handlers(application) -> None:
    application.add_handler(CommandHandler(["events", "termine"], termine_command))

    application.add_handler(
        CallbackQueryHandler(
            termine_ui_filter_callback, pattern=r"^(filter_|noop)"
        )
    )
    application.add_handler(
        CallbackQueryHandler(termine_filter_callback, pattern=r"^termfilter:")
    )