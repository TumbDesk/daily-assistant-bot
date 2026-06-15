from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from services.calendar_service import CalendarService, visible_context_ids_from_user_data
from services.i18n_util import LocalizedError
from services.scheduler_service import (
    REMINDER_15_MIN,
    REMINDER_1_DAY,
    REMINDER_1_HOUR,
    REMINDER_NONE,
    cancel_reminder,
    schedule_reminder,
)
from views.message_factory import MessageFactory

TITLE, DATE, TIME, RECURRING, RECURRING_WEEKDAY, RECUR_UNTIL, REMINDER = range(7)

SIMPLE_RECUR_KEYS = frozenset({"none", "daily", "weekly", "biweekly", "monthly"})


def _locale(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)


def recurring_keyboard(locale: str = MessageFactory.DEFAULT_LOCALE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_no", locale),
                    callback_data="recur:none",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_daily", locale),
                    callback_data="recur:daily",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_weekly", locale),
                    callback_data="recur:weekly",
                ),
            ],
            [
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_biweekly", locale),
                    callback_data="recur:biweekly",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_monthly", locale),
                    callback_data="recur:monthly",
                ),
            ],
            [
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_by_weekday", locale),
                    callback_data="recur:pick:weekday",
                ),
            ],
        ]
    )


def weekday_keyboard(locale: str = MessageFactory.DEFAULT_LOCALE) -> InlineKeyboardMarkup:
    from services.calendar_service import WEEKDAY_CODES

    labels = MessageFactory._t_list("weekday_short", locale)
    if len(labels) < 7:
        labels = MessageFactory._t_list("weekday_short", MessageFactory.DEFAULT_LOCALE)
    row1 = [
        InlineKeyboardButton(
            labels[i], callback_data=f"recur:wd:{WEEKDAY_CODES[i]}"
        )
        for i in range(4)
    ]
    row2 = [
        InlineKeyboardButton(
            labels[i], callback_data=f"recur:wd:{WEEKDAY_CODES[i]}"
        )
        for i in range(4, 7)
    ]
    return InlineKeyboardMarkup([row1, row2])


def position_keyboard(locale: str = MessageFactory.DEFAULT_LOCALE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1.", callback_data="recur:pos:1"),
                InlineKeyboardButton("2.", callback_data="recur:pos:2"),
                InlineKeyboardButton("3.", callback_data="recur:pos:3"),
                InlineKeyboardButton("4.", callback_data="recur:pos:4"),
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_pos_last", locale),
                    callback_data="recur:pos:-1",
                ),
            ],
        ]
    )


def until_keyboard(locale: str = MessageFactory.DEFAULT_LOCALE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_until_none", locale),
                    callback_data="recuruntil:none",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("btn_recur_until_pick", locale),
                    callback_data="recuruntil:pick",
                ),
            ],
        ]
    )


def reminder_keyboard(locale: str = MessageFactory.DEFAULT_LOCALE) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    MessageFactory._t("btn_reminder_none", locale),
                    callback_data="remind:0",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("reminder_15_min", locale),
                    callback_data="remind:15",
                ),
            ],
            [
                InlineKeyboardButton(
                    MessageFactory._t("reminder_1_hour", locale),
                    callback_data="remind:60",
                ),
                InlineKeyboardButton(
                    MessageFactory._t("reminder_1_day", locale),
                    callback_data="remind:1440",
                ),
            ],
        ]
    )


async def go_to_reminder_step(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = _locale(context)
    query = update.callback_query
    await query.edit_message_text(
        MessageFactory.conversation_ask_reminder(locale=locale),
        reply_markup=reminder_keyboard(locale),
    )
    return REMINDER


async def go_to_recur_until_or_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = _locale(context)
    if context.user_data.get("is_recurring"):
        query = update.callback_query
        await query.edit_message_text(
            MessageFactory.conversation_ask_recur_until(locale=locale),
            reply_markup=until_keyboard(locale),
        )
        return RECUR_UNTIL
    context.user_data.pop("until_date", None)
    return await go_to_reminder_step(update, context)


async def handle_recurring_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    calendar_service: CalendarService,
) -> int:
    locale = _locale(context)
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) >= 3 and parts[1] == "pick" and parts[2] == "weekday":
        await query.edit_message_text(
            MessageFactory.conversation_ask_weekday(locale=locale),
            reply_markup=weekday_keyboard(locale),
        )
        return RECURRING_WEEKDAY

    freq_key = parts[1] if len(parts) > 1 else ""
    if freq_key not in SIMPLE_RECUR_KEYS:
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return RECURRING

    try:
        is_recurring, rrule = calendar_service.build_rrule(freq_key)
    except ValueError:
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return RECURRING

    context.user_data["is_recurring"] = is_recurring
    context.user_data["rrule"] = rrule
    if not is_recurring:
        context.user_data.pop("until_date", None)
    return await go_to_recur_until_or_reminder(update, context)


async def handle_weekday_flow(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    calendar_service: CalendarService,
) -> int:
    locale = _locale(context)
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) >= 3 and parts[1] == "wd":
        context.user_data["recur_weekday"] = parts[2]
        await query.edit_message_text(
            MessageFactory.conversation_ask_position(locale=locale),
            reply_markup=position_keyboard(locale),
        )
        return RECURRING_WEEKDAY

    if len(parts) >= 3 and parts[1] == "pos":
        try:
            position = int(parts[2])
            weekday = context.user_data.get("recur_weekday")
            if not weekday:
                raise LocalizedError("err_weekday_missing")
            is_recurring, rrule = calendar_service.build_rrule(
                "monthly_byweekday", weekday=weekday, position=position
            )
        except (ValueError, TypeError, LocalizedError):
            await query.edit_message_text(MessageFactory.generic_error(locale=locale))
            return RECURRING_WEEKDAY

        context.user_data["is_recurring"] = is_recurring
        context.user_data["rrule"] = rrule
        return await go_to_recur_until_or_reminder(update, context)

    await query.edit_message_text(MessageFactory.generic_error(locale=locale))
    return RECURRING_WEEKDAY


async def handle_until_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    locale = _locale(context)
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")

    if len(parts) < 2:
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return RECUR_UNTIL

    action = parts[1]
    if action == "none":
        context.user_data["until_date"] = None
        return await go_to_reminder_step(update, context)

    if action == "pick":
        context.user_data["awaiting_until_date"] = True
        await query.edit_message_text(
            MessageFactory.conversation_ask_until_date(locale=locale)
        )
        return RECUR_UNTIL

    await query.edit_message_text(MessageFactory.generic_error(locale=locale))
    return RECUR_UNTIL


async def handle_until_date_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    calendar_service: CalendarService,
) -> int:
    locale = _locale(context)
    if not context.user_data.get("awaiting_until_date"):
        await update.message.reply_text(MessageFactory.generic_error(locale=locale))
        return RECUR_UNTIL

    try:
        until_date = calendar_service.parse_date(update.message.text)
        starts_at = context.user_data["starts_at"]
        if until_date < starts_at.date():
            raise LocalizedError("err_end_date_before_start")
    except (ValueError, LocalizedError):
        await update.message.reply_text(
            MessageFactory.parse_error(
                MessageFactory._t("parse_error_until_date", locale),
                locale=locale,
            )
        )
        return RECUR_UNTIL

    context.user_data["until_date"] = until_date
    context.user_data.pop("awaiting_until_date", None)
    await update.message.reply_text(
        MessageFactory.conversation_ask_reminder(locale=locale),
        reply_markup=reminder_keyboard(locale),
    )
    return REMINDER


async def handle_reminder_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    calendar_service: CalendarService,
) -> int:
    from services.auth_service import get_auth_service

    locale = _locale(context)
    query = update.callback_query
    await query.answer()

    try:
        reminder_offset = int(query.data.split(":", 1)[1])
    except ValueError:
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return REMINDER

    if reminder_offset not in (
        REMINDER_NONE,
        REMINDER_15_MIN,
        REMINDER_1_HOUR,
        REMINDER_1_DAY,
    ):
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return REMINDER

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    global_user_id = context.user_data["global_user_id"]
    title = context.user_data["title"]
    starts_at = context.user_data["starts_at"]
    is_recurring = context.user_data.get("is_recurring", False)
    base_rrule = context.user_data.get("rrule")
    until_date = context.user_data.get("until_date")

    try:
        is_recurring, rrule = calendar_service.finalize_rrule(
            is_recurring, base_rrule, until_date, starts_at
        )
    except ValueError:
        await query.edit_message_text(MessageFactory.generic_error(locale=locale))
        return REMINDER

    mode = context.user_data.get("wizard_mode", "create")
    auth = get_auth_service()

    if mode == "edit":
        event_id = context.user_data["event_id"]
        cancel_reminder(context.application.job_queue, event_id)
        event = calendar_service.update_event(
            chat_id,
            event_id,
            global_user_id,
            user_id,
            is_admin=auth.is_admin(user_id),
            visible_context_ids=visible_context_ids_from_user_data(
                context.user_data
            ),
            title=title,
            starts_at=starts_at,
            reminder_offset=reminder_offset,
            is_recurring=is_recurring,
            rrule=rrule,
        )
        if event is None:
            await query.edit_message_text(
                MessageFactory.event_permission_denied(locale=locale)
            )
            return REMINDER

        schedule_reminder(context.application.job_queue, event, starts_at)
        context.user_data.clear()
        await query.edit_message_text(
            MessageFactory.event_updated(
                event.title,
                event.starts_at,
                event.is_recurring,
                event.rrule,
                event.reminder_offset,
                ends_at=event.ends_at,
                is_all_day=event.is_all_day,
                locale=locale,
            )
        )
        return ConversationHandler.END

    from services.user_service import visible_context_chat_id

    context_chat_id = visible_context_chat_id(chat_id, user_id)
    event = calendar_service.create_event(
        owner_id=global_user_id,
        context_chat_id=context_chat_id,
        title=title,
        starts_at=starts_at,
        reminder_offset=reminder_offset,
        is_recurring=is_recurring,
        rrule=rrule,
    )
    schedule_reminder(context.application.job_queue, event, starts_at)
    context.user_data.clear()
    await query.edit_message_text(
        MessageFactory.event_created(
            event.title,
            event.starts_at,
            event.is_recurring,
            event.rrule,
            event.reminder_offset,
            ends_at=event.ends_at,
            is_all_day=event.is_all_day,
            locale=locale,
        )
    )
    return ConversationHandler.END
