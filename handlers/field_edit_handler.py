"""Inline field editing from the event detail view."""
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
    visible_context_ids_from_user_data,
)
from services.event_exceptions import get_exception_service, resolve_occurrence_times
from services.i18n_util import LocalizedError
from services.occurrence_util import parse_event_occ_callback
from services.scheduler_service import cancel_reminder, reschedule_event_reminder, schedule_reminder
from views.message_factory import MessageFactory

calendar_service = CalendarService()
exception_service = get_exception_service()

TTL, TME_DATE, TME_TIME = range(3)
RRC_RECUR, RRC_WD, RRC_UNTIL = range(3, 6)


def _locale(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)


def _store_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    context.user_data["field_edit_chat_id"] = query.message.chat_id
    context.user_data["field_edit_message_id"] = query.message.message_id


async def _edit_detail_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard
) -> None:
    chat_id = context.user_data.get("field_edit_chat_id")
    message_id = context.user_data.get("field_edit_message_id")
    if chat_id and message_id:
        await update.get_bot().edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)


def _load_event_for_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE, event_id: str
):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data.get("global_user_id")
    auth = get_auth_service()
    event = calendar_service.get_event_by_id(event_id)
    if event is None or global_user_id is None:
        return None, None
    visible_context_ids = visible_context_ids_from_user_data(context.user_data)
    if not can_modify_event(
        event,
        chat_id,
        user_id,
        global_user_id,
        auth.is_admin(user_id),
        visible_context_ids=visible_context_ids,
    ):
        return None, auth
    return event, auth


async def _save_and_show_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    title: str,
    starts_at,
    reminder_offset: int,
    is_recurring: bool,
    rrule,
) -> int:
    event_id = context.user_data["field_edit_event_id"]
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data["global_user_id"]
    auth = get_auth_service()

    visible_context_ids = visible_context_ids_from_user_data(context.user_data)
    cancel_reminder(context.application.job_queue, event_id)
    event = calendar_service.update_event(
        chat_id,
        event_id,
        global_user_id,
        user_id,
        is_admin=auth.is_admin(user_id),
        visible_context_ids=visible_context_ids,
        title=title,
        starts_at=starts_at,
        reminder_offset=reminder_offset,
        is_recurring=is_recurring,
        rrule=rrule,
    )
    if event is None:
        await _edit_detail_message(
            update, context, MessageFactory.event_permission_denied(locale=_locale(context)), None
        )
        return ConversationHandler.END

    schedule_reminder(context.application.job_queue, event, event.starts_at)
    locale = _locale(context)
    text = MessageFactory.event_detail_text(event, locale=locale)
    keyboard = MessageFactory.create_event_detail_keyboard(
        event.id, is_recurring=event.is_recurring, locale=locale
    )
    await _edit_detail_message(update, context, text, keyboard)
    context.user_data.pop("field_edit_event_id", None)
    context.user_data.pop("field_edit_occurrence_original", None)
    context.user_data.pop("field_edit_chat_id", None)
    context.user_data.pop("field_edit_message_id", None)
    return ConversationHandler.END


async def _save_occurrence_move(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    new_start,
    event,
) -> int:
    event_id = context.user_data["field_edit_event_id"]
    original_start = context.user_data["field_edit_occurrence_original"]
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data["global_user_id"]
    auth = get_auth_service()
    duration = event.ends_at - event.starts_at
    new_end = new_start + duration

    visible_context_ids = visible_context_ids_from_user_data(context.user_data)
    try:
        exception_service.move_occurrence(
            event_id,
            original_start,
            new_start,
            chat_id,
            user_id,
            global_user_id,
            new_end=new_end,
            is_admin=auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        )
    except (ValueError, PermissionError) as exc:
        await _edit_detail_message(
            update,
            context,
            MessageFactory.localized_exception_message(exc, locale=_locale(context)),
            None,
        )
        return ConversationHandler.END

    updated = calendar_service.get_event_by_id(event_id)
    if updated is not None:
        reschedule_event_reminder(context.application.job_queue, updated)

    text = MessageFactory.event_detail_text(
        event,
        occurrence_start=new_start,
        occurrence_end=new_end,
        occurrence_is_moved=True,
        occurrence_original_start=original_start,
        locale=_locale(context),
    )
    keyboard = MessageFactory.create_event_detail_keyboard(
        event_id,
        occurrence_original_start=original_start,
        is_recurring=True,
        locale=_locale(context),
    )
    await _edit_detail_message(update, context, text, keyboard)
    context.user_data.pop("field_edit_event_id", None)
    context.user_data.pop("field_edit_occurrence_original", None)
    context.user_data.pop("field_edit_chat_id", None)
    context.user_data.pop("field_edit_message_id", None)
    return ConversationHandler.END


# --- Title ---


@restricted
async def edit_ttl_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = query.data[len("edit_ttl_") :]
    event, _ = _load_event_for_edit(update, context, event_id)
    if event is None:
        await query.edit_message_text(MessageFactory.event_permission_denied(locale=_locale(context)))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["field_edit_event_id"] = event_id
    context.user_data["field_edit_snapshot"] = event
    await query.edit_message_text(
        MessageFactory.conversation_edit_field_title(locale=_locale(context))
    )
    return TTL


@restricted
async def edit_ttl_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text(MessageFactory.conversation_title_empty(locale=_locale(context)))
        return TTL

    event = context.user_data["field_edit_snapshot"]
    return await _save_and_show_detail(
        update,
        context,
        title=title,
        starts_at=event.starts_at,
        reminder_offset=event.reminder_offset,
        is_recurring=event.is_recurring,
        rrule=event.rrule,
    )


# --- Time ---


@restricted
async def edit_tme_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = query.data[len("edit_tme_") :]
    context.user_data.pop("field_edit_occurrence_original", None)
    return await _begin_tme_edit(update, context, event_id)


@restricted
async def edit_tme_one_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    parsed = parse_event_occ_callback(query.data or "", "tme_one_")
    if parsed is None:
        return ConversationHandler.END
    event_id, occurrence_original = parsed
    if occurrence_original is None:
        return ConversationHandler.END
    context.user_data["field_edit_occurrence_original"] = occurrence_original
    return await _begin_tme_edit(update, context, event_id, occurrence_original)


async def _begin_tme_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    event_id: str,
    occurrence_original=None,
) -> int:
    event, _ = _load_event_for_edit(update, context, event_id)
    if event is None:
        await update.callback_query.edit_message_text(
            MessageFactory.event_permission_denied(locale=_locale(context))
        )
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["field_edit_event_id"] = event_id
    context.user_data["field_edit_snapshot"] = event

    if occurrence_original is not None:
        display_start, _, _, _ = resolve_occurrence_times(event, occurrence_original)
        current_date = display_start.strftime("%d.%m.%Y")
    else:
        current_date = event.starts_at.strftime("%d.%m.%Y")

    await update.callback_query.edit_message_text(
        MessageFactory.conversation_edit_field_date(
            current_date, locale=_locale(context)
        )
    )
    return TME_DATE


@restricted
async def edit_tme_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        context.user_data["field_edit_date"] = calendar_service.parse_date(
            update.message.text
        )
    except ValueError:
        await update.message.reply_text(
            MessageFactory.parse_error("Datum (DD.MM.YYYY)", locale=_locale(context))
        )
        return TME_DATE

    event = context.user_data["field_edit_snapshot"]
    occ_original = context.user_data.get("field_edit_occurrence_original")
    if occ_original is not None:
        display_start, _, _, _ = resolve_occurrence_times(event, occ_original)
        current_time = display_start.strftime("%H:%M")
    else:
        current_time = event.starts_at.strftime("%H:%M")
    await update.message.reply_text(
        MessageFactory.conversation_edit_field_time(
            current_time, locale=_locale(context)
        )
    )
    return TME_TIME


@restricted
async def edit_tme_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        event_time = calendar_service.parse_time(update.message.text)
        starts_at = calendar_service.build_datetime(
            context.user_data["field_edit_date"], event_time
        )
    except ValueError:
        await update.message.reply_text(
            MessageFactory.parse_error("Uhrzeit (HH:MM)", locale=_locale(context))
        )
        return TME_TIME

    event = context.user_data["field_edit_snapshot"]
    occ_original = context.user_data.get("field_edit_occurrence_original")
    if occ_original is not None:
        return await _save_occurrence_move(
            update, context, new_start=starts_at, event=event
        )

    return await _save_and_show_detail(
        update,
        context,
        title=event.title,
        starts_at=starts_at,
        reminder_offset=event.reminder_offset,
        is_recurring=event.is_recurring,
        rrule=event.rrule,
    )


# --- Recurrence ---


@restricted
async def edit_rrc_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = query.data[len("edit_rrc_") :]
    event, _ = _load_event_for_edit(update, context, event_id)
    if event is None:
        await query.edit_message_text(MessageFactory.event_permission_denied(locale=_locale(context)))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["field_edit_event_id"] = event_id
    context.user_data["field_edit_snapshot"] = event
    await query.edit_message_text(
        MessageFactory.conversation_ask_recurring(locale=_locale(context)),
        reply_markup=wz.recurring_keyboard(locale=_locale(context)),
    )
    return RRC_RECUR


@restricted
async def edit_rrc_recurring(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) >= 3 and parts[1] == "pick" and parts[2] == "weekday":
        await query.edit_message_text(
            MessageFactory.conversation_ask_weekday(locale=_locale(context)),
            reply_markup=wz.weekday_keyboard(locale=_locale(context)),
        )
        return RRC_WD

    freq_key = parts[1] if len(parts) > 1 else ""
    if freq_key not in wz.SIMPLE_RECUR_KEYS:
        await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
        return RRC_RECUR

    try:
        is_recurring, rrule = calendar_service.build_rrule(freq_key)
    except ValueError:
        await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
        return RRC_RECUR

    context.user_data["is_recurring"] = is_recurring
    context.user_data["rrule"] = rrule
    if not is_recurring:
        context.user_data.pop("until_date", None)
        return await _finish_rrc_edit(update, context)

    await query.edit_message_text(
        MessageFactory.conversation_ask_recur_until(locale=_locale(context)),
        reply_markup=wz.until_keyboard(locale=_locale(context)),
    )
    return RRC_UNTIL


@restricted
async def edit_rrc_weekday(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) >= 3 and parts[1] == "wd":
        context.user_data["recur_weekday"] = parts[2]
        await query.edit_message_text(
            MessageFactory.conversation_ask_position(locale=_locale(context)),
            reply_markup=wz.position_keyboard(locale=_locale(context)),
        )
        return RRC_WD

    if len(parts) >= 3 and parts[1] == "pos":
        try:
            position = int(parts[2])
            weekday = context.user_data.get("recur_weekday")
            if not weekday:
                raise LocalizedError("err_weekday_missing")
            is_recurring, rrule = calendar_service.build_rrule(
                "monthly_byweekday", weekday=weekday, position=position
            )
        except (ValueError, TypeError):
            await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
            return RRC_WD

        context.user_data["is_recurring"] = is_recurring
        context.user_data["rrule"] = rrule
        await query.edit_message_text(
            MessageFactory.conversation_ask_recur_until(locale=_locale(context)),
            reply_markup=wz.until_keyboard(locale=_locale(context)),
        )
        return RRC_UNTIL

    await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
    return RRC_WD


@restricted
async def edit_rrc_until_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) < 2:
        await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
        return RRC_UNTIL

    action = parts[1]
    if action == "none":
        context.user_data["until_date"] = None
        return await _finish_rrc_edit(update, context)

    if action == "pick":
        context.user_data["awaiting_until_date"] = True
        await query.edit_message_text(
            MessageFactory.conversation_ask_until_date(locale=_locale(context))
        )
        return RRC_UNTIL

    await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
    return RRC_UNTIL


@restricted
async def edit_rrc_until_date(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    if not context.user_data.get("awaiting_until_date"):
        await update.message.reply_text(MessageFactory.generic_error(locale=_locale(context)))
        return RRC_UNTIL

    event = context.user_data["field_edit_snapshot"]
    try:
        until_date = calendar_service.parse_date(update.message.text)
        if until_date < event.starts_at.date():
            raise LocalizedError("err_end_date_before_start")
    except ValueError:
        await update.message.reply_text(
            MessageFactory.parse_error(
                MessageFactory._t("parse_error_until_date", _locale(context)),
                locale=_locale(context),
            )
        )
        return RRC_UNTIL

    context.user_data["until_date"] = until_date
    context.user_data.pop("awaiting_until_date", None)
    return await _finish_rrc_edit(update, context)


async def _finish_rrc_edit(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    event = context.user_data["field_edit_snapshot"]
    is_recurring = context.user_data.get("is_recurring", False)
    base_rrule = context.user_data.get("rrule")
    until_date = context.user_data.get("until_date")

    try:
        is_recurring, rrule = calendar_service.finalize_rrule(
            is_recurring, base_rrule, until_date, event.starts_at
        )
    except ValueError:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                MessageFactory.generic_error(locale=_locale(context))
            )
        else:
            await update.message.reply_text(MessageFactory.generic_error(locale=_locale(context)))
        return RRC_UNTIL

    return await _save_and_show_detail(
        update,
        context,
        title=event.title,
        starts_at=event.starts_at,
        reminder_offset=event.reminder_offset,
        is_recurring=is_recurring,
        rrule=rrule,
    )


# --- Reminder ---


@restricted
async def edit_rem_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_id = query.data[len("edit_rem_") :]
    event, _ = _load_event_for_edit(update, context, event_id)
    if event is None:
        await query.edit_message_text(MessageFactory.event_permission_denied(locale=_locale(context)))
        return ConversationHandler.END

    _store_edit_message(update, context)
    context.user_data["field_edit_event_id"] = event_id
    context.user_data["field_edit_snapshot"] = event
    await query.edit_message_text(
        MessageFactory.conversation_ask_reminder(locale=_locale(context)),
        reply_markup=wz.reminder_keyboard(locale=_locale(context)),
    )
    return wz.REMINDER


@restricted
async def edit_rem_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    try:
        reminder_offset = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
        return wz.REMINDER

    from services.scheduler_service import (
        REMINDER_15_MIN,
        REMINDER_1_DAY,
        REMINDER_1_HOUR,
        REMINDER_NONE,
    )

    if reminder_offset not in (
        REMINDER_NONE,
        REMINDER_15_MIN,
        REMINDER_1_HOUR,
        REMINDER_1_DAY,
    ):
        await query.edit_message_text(MessageFactory.generic_error(locale=_locale(context)))
        return wz.REMINDER

    event = context.user_data["field_edit_snapshot"]
    return await _save_and_show_detail(
        update,
        context,
        title=event.title,
        starts_at=event.starts_at,
        reminder_offset=reminder_offset,
        is_recurring=event.is_recurring,
        rrule=event.rrule,
    )


async def field_edit_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.clear()
    await update.message.reply_text(MessageFactory.conversation_cancelled(locale=_locale(context)))
    return ConversationHandler.END


def build_field_edit_ttl_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_ttl_start, pattern=r"^edit_ttl_")
        ],
        states={
            TTL: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_ttl_save)],
        },
        fallbacks=[CommandHandler("cancel", field_edit_cancel)],
        per_chat=True,
        per_user=True,
    )


def build_field_edit_tme_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_tme_start, pattern=r"^edit_tme_"),
            CallbackQueryHandler(edit_tme_one_start, pattern=r"^tme_one_"),
        ],
        states={
            TME_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tme_date)
            ],
            TME_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_tme_time)
            ],
        },
        fallbacks=[CommandHandler("cancel", field_edit_cancel)],
        per_chat=True,
        per_user=True,
    )


def build_field_edit_rrc_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_rrc_start, pattern=r"^edit_rrc_")
        ],
        states={
            RRC_RECUR: [
                CallbackQueryHandler(edit_rrc_recurring, pattern=r"^recur:")
            ],
            RRC_WD: [
                CallbackQueryHandler(edit_rrc_weekday, pattern=r"^recur:(wd|pos):")
            ],
            RRC_UNTIL: [
                CallbackQueryHandler(
                    edit_rrc_until_callback, pattern=r"^recuruntil:"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, edit_rrc_until_date
                ),
            ],
        },
        fallbacks=[CommandHandler("cancel", field_edit_cancel)],
        per_chat=True,
        per_user=True,
    )


def build_field_edit_rem_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_rem_start, pattern=r"^edit_rem_")
        ],
        states={
            wz.REMINDER: [
                CallbackQueryHandler(edit_rem_save, pattern=r"^remind:")
            ],
        },
        fallbacks=[CommandHandler("cancel", field_edit_cancel)],
        per_chat=True,
        per_user=True,
    )


def register_field_edit_handlers(application) -> None:
    application.add_handler(build_field_edit_ttl_conversation())
    application.add_handler(build_field_edit_tme_conversation())
    application.add_handler(build_field_edit_rrc_conversation())
    application.add_handler(build_field_edit_rem_conversation())
