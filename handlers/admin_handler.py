from telegram import Update, ChatMember
from telegram.ext import Application, ChatMemberHandler, CommandHandler, ContextTypes

from services.auth_service import get_auth_service, restricted
from services.calendar_service import CalendarService, normalize_category_names
from views.message_factory import MessageFactory
from version import __version__

calendar_service = CalendarService()

# Show the version of the bot
@restricted
async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    auth = get_auth_service()
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not auth.is_admin(update.effective_user.id):
        await update.message.reply_text(MessageFactory.allow_denied(locale=locale))
        return
    await update.message.reply_text(MessageFactory.version_text(__version__))

# Set the global categories for the bot
@restricted
async def kategorie_set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    auth = get_auth_service()
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not auth.is_admin(update.effective_user.id):
        await update.message.reply_text(MessageFactory.allow_denied(locale=locale))
        return

    if not context.args:
        await update.message.reply_text(MessageFactory.kategorie_set_usage(locale=locale))
        return

    names = normalize_category_names(context.args)
    if not names:
        await update.message.reply_text(MessageFactory.kategorie_set_empty_names(locale=locale))
        return

    result = calendar_service.create_global_categories(names)
    await update.message.reply_text(
        MessageFactory.kategorie_set_success(
            result.created_count,
            result.total_global,
            result.names,
            locale=locale,
        )
    )

# Allow a user to use the bot
@restricted
async def allow_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if len(context.args) < 2:
        await update.message.reply_text(MessageFactory.allow_usage(locale=locale))
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(MessageFactory.allow_invalid_id(locale=locale))
        return

    name = " ".join(context.args[1:])
    auth = get_auth_service()
    success, message = auth.add_allowed_user(update.effective_user.id, target_id, name)
    await update.message.reply_text(message)

# Check if the user is allowed to use the bot, if not, leave the group
async def on_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    member_update = update.my_chat_member
    if member_update is None:
        return

    old_status = member_update.old_chat_member.status
    new_status = member_update.new_chat_member.status
    joined_statuses = (ChatMember.MEMBER, ChatMember.ADMINISTRATOR)
    left_statuses = (ChatMember.LEFT, ChatMember.BANNED, ChatMember.RESTRICTED)

    if old_status not in left_statuses or new_status not in joined_statuses:
        return

    adder = member_update.from_user
    chat = member_update.chat
    auth = get_auth_service()
    locale = MessageFactory.DEFAULT_LOCALE

    if auth.is_allowed(adder.id):
        from services.chat_membership_service import get_chat_membership_service

        membership_service = get_chat_membership_service()
        membership_service.record_bot_joined(chat.id, chat.title)
        membership_service.record_user_seen(adder.id, chat.id)
        logger.info(
            "Bot zu Gruppe %s (%s) hinzugefügt durch %s (%s).",
            chat.title,
            chat.id,
            adder.full_name,
            adder.id,
        )
        await auth.notify_admin(
            context,
            MessageFactory.admin_group_success_alert(
                chat.title or "Unbekannt",
                chat.id,
                adder.full_name,
                adder.id,
                locale=locale,
            ),
        )
        return

    logger.warning(
        "Unautorisierter Gruppenbeitritt: %s (%s) durch %s (%s).",
        chat.title,
        chat.id,
        adder.full_name,
        adder.id,
    )
    await context.bot.send_message(
        chat_id=chat.id,
        text=MessageFactory.group_intruder_warning(locale=locale),
    )
    await context.bot.leave_chat(chat_id=chat.id)
    await auth.notify_admin(
        context,
        MessageFactory.admin_group_intrusion_alert(
            chat.title or "Unbekannt",
            chat.id,
            adder.full_name,
            adder.id,
            locale=locale,
        ),
    )

# Entry point called from main.py
def register_admin_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("version", version_command))
    application.add_handler(CommandHandler(["gcategory", "gkategorie"], kategorie_set_command))
    application.add_handler(CommandHandler("allow", allow_command))
    # To fully encapsulate, append at the bottom of this file:
    application.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))