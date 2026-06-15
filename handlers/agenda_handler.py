"""Agenda commands, settings, and manual fetch."""

from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from handlers.telegram_util import safe_edit_message_text
from services.agenda import build_daily_report, get_agenda_service
from services.auth_service import restricted
from services.calendar_service import CalendarService
from services.i18n_util import LocalizedError
from services.chat_membership_service import get_chat_membership_service
from services.locale_service import resolve_user_locale
from services.user_settings import get_user_settings_service
from views.message_factory import MessageFactory


def _private_only(update: Update) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.type == ChatType.PRIVATE


def _parse_geburtstag_args(args: list[str]) -> tuple[str, object]:
    if len(args) < 2:
        raise LocalizedError("err_name_and_date_required")
    name = " ".join(args[:-1]).strip()
    if not name:
        raise LocalizedError("err_name_empty")
    birth_date = CalendarService.parse_date(args[-1])
    return name, birth_date


async def _send_settings_view(
    update: Update,
    global_user_id: str,
    *,
    query=None,
) -> None:
    settings_service = get_user_settings_service()
    settings = settings_service.get_settings(global_user_id)
    telegram_lang = update.effective_user.language_code if update.effective_user else None
    locale = resolve_user_locale(settings.locale, telegram_lang)
    text = MessageFactory.settings_overview(settings, locale)
    keyboard = MessageFactory.settings_keyboard(settings, locale)

    if query is not None:
        await safe_edit_message_text(
            query,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    elif update.message is not None:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )


@restricted
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return

    global_user_id = context.user_data["global_user_id"]
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    settings_service = get_user_settings_service()

    if context.args:
        if len(context.args) >= 2 and context.args[0].lower() == "lang":
            try:
                updated = settings_service.set_locale(global_user_id, context.args[1])
                context.user_data["locale"] = updated.locale
            except ValueError as exc:
                await update.message.reply_text(
                    MessageFactory.agenda_parse_error(exc, locale=locale)
                )
                return
        else:
            try:
                settings_service.set_report_time(global_user_id, context.args[0])
            except ValueError as exc:
                await update.message.reply_text(
                    MessageFactory.agenda_parse_error(exc, locale=locale)
                )
                return

    await _send_settings_view(update, global_user_id)


@restricted
async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data or not _private_only(update):
        return

    await query.answer()
    if query.data == "settings:noop":
        return

    global_user_id = context.user_data.get("global_user_id")
    if not global_user_id:
        return

    settings_service = get_user_settings_service()
    parts = query.data.split(":")

    try:
        if len(parts) == 3 and parts[1] == "toggle":
            settings_service.toggle_setting(global_user_id, parts[2])
        elif len(parts) == 3 and parts[1] == "time":
            direction = -1 if parts[2] == "prev" else 1
            settings_service.cycle_report_time(global_user_id, direction)
        elif len(parts) == 3 and parts[1] == "lang":
            updated = settings_service.set_locale(global_user_id, parts[2])
            context.user_data["locale"] = updated.locale
        else:
            return
    except ValueError:
        return

    await _send_settings_view(update, global_user_id, query=query)


@restricted
async def geburtstag_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not context.args:
        await update.message.reply_text(
            MessageFactory.agenda_usage_geburtstag(locale=locale)
        )
        return

    global_user_id = context.user_data["global_user_id"]
    try:
        name, birth_date = _parse_geburtstag_args(context.args)
        get_agenda_service().add_birthday(global_user_id, name, birth_date)
    except ValueError as exc:
        await update.message.reply_text(
            MessageFactory.agenda_parse_error(exc, locale=locale)
        )
        return

    await update.message.reply_text(
        MessageFactory.geburtstag_success(name, birth_date, locale=locale)
    )


@restricted
async def agenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _private_only(update):
        return

    global_user_id = context.user_data["global_user_id"]
    settings = get_user_settings_service().get_settings(global_user_id)
    visible_context_ids = await get_chat_membership_service().sync_memberships(
        context.bot, update.effective_user.id
    )
    text = await build_daily_report(
        global_user_id,
        settings,
        context_chat_ids=visible_context_ids,
        view_context_chat_id=update.effective_user.id,
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


def register_agenda_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler(["birthday", "geburtstag"], geburtstag_command))
    application.add_handler(CommandHandler("agenda", agenda_command))
    application.add_handler(
        CallbackQueryHandler(settings_callback, pattern=r"^settings:")
    )
