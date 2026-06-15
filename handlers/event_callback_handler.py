"""Callback controller for event detail, deletion, and back to list."""
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from handlers.termine_ui import render_termine_list
from services.auth_service import get_auth_service, restricted
from services.calendar_service import (
    CalendarService,
    can_access_event,
    can_modify_event,
    visible_context_ids_from_user_data,
)
from services.event_exceptions import (
    get_exception_service,
    resolve_occurrence_times,
)
from services.occurrence_util import (
    parse_event_occ_callback,
    parse_view_evt_callback,
)
from services.scheduler_service import cancel_reminder, reschedule_event_reminder, schedule_reminder
from services.user_service import event_source_label, visible_context_chat_id
from views.message_factory import MessageFactory

calendar_service = CalendarService()
exception_service = get_exception_service()


async def _show_event_detail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    event,
    *,
    occurrence_original_start: datetime | None = None,
) -> None:
    query = update.callback_query
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    view_context_chat_id = visible_context_chat_id(chat_id, user_id)
    source_label = event_source_label(event.context_chat_id, view_context_chat_id)
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if occurrence_original_start is not None and event.is_recurring:
        start, end, is_moved, original = resolve_occurrence_times(
            event, occurrence_original_start
        )
        text = MessageFactory.event_detail_text(
            event,
            occurrence_start=start,
            occurrence_end=end,
            occurrence_is_moved=is_moved,
            occurrence_original_start=original if is_moved else None,
            source_label=source_label,
            locale=locale,
        )
        keyboard = MessageFactory.create_event_detail_keyboard(
            event.id,
            occurrence_original_start=occurrence_original_start,
            is_recurring=True,
            locale=locale,
        )
    else:
        text = MessageFactory.event_detail_text(
            event, source_label=source_label, locale=locale
        )
        keyboard = MessageFactory.create_event_detail_keyboard(
            event.id, is_recurring=event.is_recurring, locale=locale
        )
    await query.edit_message_text(text, reply_markup=keyboard)


def _reschedule_reminder(context, event) -> None:
    reschedule_event_reminder(context.application.job_queue, event)


async def _return_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from services.event_filter import parsed_filter_from_dict

    stored = context.user_data.get("termine_filter")
    ui_filter = context.user_data.get("termine_ui_filter", "future")
    if stored:
        await render_termine_list(
            update, context, parsed_filter_from_dict(stored)
        )
    else:
        await render_termine_list(update, context, ui_filter=ui_filter)


@restricted
async def event_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data["global_user_id"]
    auth = get_auth_service()
    visible_context_ids = visible_context_ids_from_user_data(context.user_data)
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)

    if data == "list_all_events":
        await _return_to_list(update, context)
        return

    parsed = parse_view_evt_callback(data)
    if parsed is not None:
        event_id, occurrence_original_start = parsed
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        await _show_event_detail(
            update, context, event, occurrence_original_start=occurrence_original_start
        )
        return

    parsed = parse_event_occ_callback(data, "del_ask_")
    if parsed is not None:
        event_id, occurrence_original_start = parsed
        if occurrence_original_start is None:
            return
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        await query.edit_message_text(
            MessageFactory._t("delete_scope_prompt", locale),
            reply_markup=MessageFactory.delete_scope_keyboard(
                event_id, occurrence_original_start, locale=locale
            ),
        )
        return

    parsed = parse_event_occ_callback(data, "del_one_")
    if parsed is not None:
        event_id, occurrence_original_start = parsed
        if occurrence_original_start is None:
            return
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        if not can_modify_event(
            event,
            chat_id,
            user_id,
            global_user_id,
            auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_permission_denied(locale=locale))
            return
        try:
            exception_service.cancel_occurrence(
                event_id,
                occurrence_original_start,
                chat_id,
                user_id,
                global_user_id,
                is_admin=auth.is_admin(user_id),
                visible_context_ids=visible_context_ids,
            )
        except (ValueError, PermissionError) as exc:
            await query.edit_message_text(
                MessageFactory.localized_exception_message(exc, locale=locale)
            )
            return
        _reschedule_reminder(context, event)
        await query.edit_message_text(MessageFactory.occurrence_cancelled(locale=locale))
        await _return_to_list(update, context)
        return

    if data.startswith("del_all_"):
        event_id = data[len("del_all_") :]
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        if not can_modify_event(
            event,
            chat_id,
            user_id,
            global_user_id,
            auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_permission_denied(locale=locale))
            return
        cancel_reminder(context.application.job_queue, event_id)
        if not calendar_service.delete_event(
            chat_id,
            event_id,
            global_user_id,
            user_id,
            is_admin=auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_permission_denied(locale=locale))
            return
        await _return_to_list(update, context)
        return

    if data.startswith("del_cfm_"):
        event_id = data[len("del_cfm_") :]
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        if not can_modify_event(
            event,
            chat_id,
            user_id,
            global_user_id,
            auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_permission_denied(locale=locale))
            return
        cancel_reminder(context.application.job_queue, event_id)
        if not calendar_service.delete_event(
            chat_id,
            event_id,
            global_user_id,
            user_id,
            is_admin=auth.is_admin(user_id),
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_permission_denied(locale=locale))
            return
        await _return_to_list(update, context)
        return

    parsed = parse_event_occ_callback(data, "tme_ask_")
    if parsed is not None:
        event_id, occurrence_original_start = parsed
        if occurrence_original_start is None:
            return
        event = calendar_service.get_event_by_id(event_id)
        if event is None or not can_access_event(
            event,
            chat_id,
            user_id,
            visible_context_ids=visible_context_ids,
        ):
            await query.edit_message_text(MessageFactory.event_not_found(locale=locale))
            return
        await query.edit_message_text(
            MessageFactory._t("time_edit_scope_prompt", locale),
            reply_markup=MessageFactory.time_edit_scope_keyboard(
                event_id, occurrence_original_start, locale=locale
            ),
        )
        return


def register_event_callbacks(application) -> None:
    application.add_handler(
        CallbackQueryHandler(
            event_callback_handler,
            pattern=r"^(view_evt_|del_ask_|del_one_|del_all_|del_cfm_|tme_ask_|list_all_events)",
        )
    )
