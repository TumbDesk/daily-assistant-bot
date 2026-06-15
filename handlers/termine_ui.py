"""Shared rendering of the interactive event list."""
from typing import Optional

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from services.calendar_service import CalendarService
from services.chat_membership_service import get_chat_membership_service
from services.user_service import visible_context_chat_id
from services.event_filter import (
    EventFilterPreset,
    ParsedFilter,
    apply_filter,
    filter_events_for_ui,
    parsed_filter_from_dict,
    parsed_filter_to_dict,
    ui_filter_empty_label,
)
from handlers.telegram_util import safe_edit_message_text
from views.message_factory import MessageFactory

calendar_service = CalendarService()

VALID_UI_FILTERS = frozenset({"all", "future", "recurring"})

def active_period_key(parsed: Optional[ParsedFilter]) -> Optional[str]:
    if parsed is None:
        return None
    preset = parsed.preset
    if preset == EventFilterPreset.TODAY:
        return "today"
    if preset == EventFilterPreset.THIS_WEEK:
        return "this_week"
    if preset == EventFilterPreset.NEXT_WEEK:
        return "next_week"
    if preset in (
        EventFilterPreset.THIS_MONTH,
        EventFilterPreset.MONTH_OFFSET,
        EventFilterPreset.CALENDAR_MONTH,
        EventFilterPreset.CALENDAR_YEAR,
    ):
        return "month_year"
    return None


def _normalize_ui_filter(ui_filter: Optional[str]) -> str:
    if ui_filter in VALID_UI_FILTERS:
        return ui_filter
    return "future"


def _load_events(
    chat_id: int,
    user_id: int,
    *,
    ui_filter: str,
    parsed: Optional[ParsedFilter] = None,
    visible_context_ids: frozenset[int] | None = None,
) -> list:
    if visible_context_ids is not None:
        base = calendar_service.list_events_for_contexts(visible_context_ids)
    else:
        base = calendar_service.list_events_for_chat(chat_id, user_id)
    if parsed is not None:
        return apply_filter(
            base,
            parsed.preset,
            year=parsed.year,
            month=parsed.month,
            month_offset=parsed.month_offset,
        )
    return filter_events_for_ui(base, ui_filter)


async def render_termine_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    parsed: Optional[ParsedFilter] = None,
    *,
    ui_filter: Optional[str] = None,
) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    chat = update.effective_chat

    visible_context_ids: frozenset[int] | None = None
    if chat is not None and chat.type == ChatType.PRIVATE:
        membership_service = get_chat_membership_service()
        visible_context_ids = await membership_service.sync_memberships(
            context.bot, user_id
        )
        context.user_data["visible_context_ids"] = list(visible_context_ids)
    else:
        context.user_data.pop("visible_context_ids", None)

    active_period: Optional[str] = None

    if parsed is not None:
        context.user_data["termine_filter"] = parsed_filter_to_dict(parsed)
        active_filter = _normalize_ui_filter(
            context.user_data.get("termine_ui_filter", "future")
        )
        active_period = active_period_key(parsed)
    else:
        active_filter = _normalize_ui_filter(
            ui_filter or context.user_data.get("termine_ui_filter", "future")
        )
        context.user_data["termine_ui_filter"] = active_filter
        context.user_data.pop("termine_filter", None)

    events = _load_events(
        chat_id,
        user_id,
        ui_filter=active_filter,
        parsed=parsed,
        visible_context_ids=visible_context_ids,
    )

    view_context_chat_id = visible_context_chat_id(chat_id, user_id)

    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)

    if events:
        text, keyboard = MessageFactory.create_events_view(
            events,
            active_filter=active_filter,
            active_period=active_period,
            view_context_chat_id=view_context_chat_id,
            locale=locale,
        )
    else:
        if parsed is not None:
            from services.event_filter import filter_label

            label = filter_label(
                parsed.preset,
                year=parsed.year,
                month=parsed.month,
                month_offset=parsed.month_offset,
                locale=locale,
            )
        else:
            label = ui_filter_empty_label(active_filter, locale=locale)
        text, keyboard = MessageFactory.create_events_view_empty(
            active_filter=active_filter,
            filter_label=label,
            active_period=active_period,
            locale=locale,
        )

    if update.callback_query:
        await safe_edit_message_text(
            update.callback_query, text, reply_markup=keyboard
        )
    elif update.message:
        await update.message.reply_text(text, reply_markup=keyboard)
