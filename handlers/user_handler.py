from telegram import Chat, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from services.auth_service import restricted
from services.locale_service import resolve_locale_for_handler
from services.user_service import get_user_service
from services.weather import (
    LocationNotFoundError,
    WeatherServiceError,
    resolve_location,
)
from views.message_factory import MessageFactory
from services.calendar_service import CalendarService

calendar_service = CalendarService()

# Show the user's ID, needed for the whitelist (no @restricted — works before allowlist)
async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_user is None:
        return
    if update.effective_chat is None or update.effective_chat.type != Chat.PRIVATE:
        return
    locale = resolve_locale_for_handler(context, update.effective_user)
    await update.message.reply_text(
        MessageFactory.my_id(update.effective_user.id, locale=locale)
    )

# Activate the bot
@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    await update.message.reply_text(MessageFactory.welcome(locale=locale))

# Show the help text for the bot
@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    await update.message.reply_text(MessageFactory.help_text(locale=locale))

# Set the home location for the user, used for the weather command
@restricted
async def set_home_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not context.args:
        await update.message.reply_text(MessageFactory.set_home_usage(locale=locale))
        return

    location_query = " ".join(context.args).strip()
    global_user_id = context.user_data["global_user_id"]
    user_service = get_user_service()

    try:
        location = await resolve_location(location_query)
    except LocationNotFoundError:
        await update.message.reply_text(
            MessageFactory.weather_location_not_found(location_query, locale=locale)
        )
        return
    except WeatherServiceError:
        await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))
        return

    user_service.set_home_location(
        global_user_id,
        location.latitude,
        location.longitude,
        location.name,
    )
    await update.message.reply_text(
        MessageFactory.set_home_success(location.name, locale=locale)
    )

# Add a personal category for the user
@restricted
async def kategorie_add_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if not context.args:
        await update.message.reply_text(MessageFactory.kategorie_add_usage(locale=locale))
        return

    name = " ".join(context.args).strip()
    if not name:
        await update.message.reply_text(MessageFactory.kategorie_add_empty_name(locale=locale))
        return

    global_user_id = context.user_data["global_user_id"]
    status, _dto = calendar_service.create_personal_category(global_user_id, name)

    if status == "created":
        await update.message.reply_text(MessageFactory.kategorie_add_success(name, locale=locale))
    elif status == "duplicate":
        await update.message.reply_text(
            MessageFactory.kategorie_add_duplicate(name, locale=locale)
        )
    elif status == "global_collision":
        await update.message.reply_text(
            MessageFactory.kategorie_add_global_collision(name, locale=locale)
        )
    else:
        await update.message.reply_text(MessageFactory.kategorie_add_empty_name(locale=locale))

# Entry point called from main.py
def register_base_user_handlers(application: Application) -> None:
    application.add_handler(CommandHandler(["myid", "my_id"], myid_command))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("home", set_home_command))
    application.add_handler(CommandHandler(["category", "kategorie"], kategorie_add_command))