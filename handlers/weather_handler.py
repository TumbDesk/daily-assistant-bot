"""Weather command and inline callbacks for daily/trend views."""
from telegram import Update
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from handlers.telegram_util import safe_edit_message_text
from services.auth_service import restricted
from services.user_service import get_user_service
from services.weather import (
    LocationNotFoundError,
    WeatherServiceError,
    get_five_day_trend,
    get_tomorrow_weather,
    get_weather_service,
    parse_todays_weather,
    resolve_location,
)
from views.message_factory import (
    WEATHER_VIEW_TODAY,
    WEATHER_VIEW_TOMORROW,
    WEATHER_VIEW_TREND,
    MessageFactory,
)

_awaiting_home_user_ids: set[int] = set()


class AwaitingHomeLocationFilter(filters.MessageFilter):
    def filter(self, message) -> bool:
        user = message.from_user
        return user is not None and user.id in _awaiting_home_user_ids


_awaiting_home_filter = AwaitingHomeLocationFilter()


def _start_awaiting_home(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    _awaiting_home_user_ids.add(user_id)
    context.user_data["awaiting_home_location"] = True


def _clear_awaiting_home(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    _awaiting_home_user_ids.discard(user_id)
    context.user_data.pop("awaiting_home_location", None)


async def _send_weather_to_chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    reply_markup=None,
) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )
    elif update.message is not None:
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup,
        )


async def _render_weather_message(
    *,
    view: str,
    location_name: str,
    latitude: float,
    longitude: float,
    context: ContextTypes.DEFAULT_TYPE,
    update: Update | None = None,
    query=None,
    locale: str = MessageFactory.DEFAULT_LOCALE,
) -> None:
    data = await get_weather_service().get_forecast(latitude, longitude)

    if view == WEATHER_VIEW_TODAY:
        weather = parse_todays_weather(data)
        text = MessageFactory.weather_forecast(location_name, weather, locale=locale)
    elif view == WEATHER_VIEW_TOMORROW:
        weather = get_tomorrow_weather(data, location_name)
        text = MessageFactory.weather_tomorrow(location_name, weather, locale=locale)
    else:
        days = get_five_day_trend(data, location_name)
        text = MessageFactory.weather_five_day_trend(location_name, days, locale=locale)

    keyboard = MessageFactory.weather_view_keyboard(
        view, location_name, latitude, longitude, locale=locale
    )

    if query is not None:
        await safe_edit_message_text(
            query,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
    elif update is not None:
        await _send_weather_to_chat(
            update, context, text, reply_markup=keyboard
        )


@restricted
async def wetter_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global_user_id = context.user_data["global_user_id"]
    user_service = get_user_service()
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)

    if context.args:
        location_query = " ".join(context.args).strip()
        try:
            location = await resolve_location(location_query)
            await _render_weather_message(
                view=WEATHER_VIEW_TODAY,
                location_name=location.name,
                latitude=location.latitude,
                longitude=location.longitude,
                context=context,
                update=update,
                locale=locale,
            )
        except LocationNotFoundError:
            await update.message.reply_text(
                MessageFactory.weather_location_not_found(
                    location_query, locale=locale
                )
            )
            return
        except WeatherServiceError:
            await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))
            return

        if not user_service.has_home_location(global_user_id):
            user_service.set_home_location(
                global_user_id,
                location.latitude,
                location.longitude,
                location.name,
            )
        return

    home = user_service.get_home_location(global_user_id)
    if home is not None:
        latitude, longitude, name = home
        try:
            await _render_weather_message(
                view=WEATHER_VIEW_TODAY,
                location_name=name,
                latitude=latitude,
                longitude=longitude,
                context=context,
                update=update,
                locale=locale,
            )
        except WeatherServiceError:
            await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))
        return

    _start_awaiting_home(update.effective_user.id, context)
    await update.message.reply_text(MessageFactory.weather_ask_home(locale=locale))


@restricted
async def weather_home_reply_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user_id = update.effective_user.id
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)
    if user_id not in _awaiting_home_user_ids:
        return

    location_query = update.message.text.strip()
    if not location_query:
        await update.message.reply_text(MessageFactory.weather_ask_home(locale=locale))
        return

    global_user_id = context.user_data["global_user_id"]
    user_service = get_user_service()

    try:
        location = await resolve_location(location_query)
        user_service.set_home_location(
            global_user_id,
            location.latitude,
            location.longitude,
            location.name,
        )
        await _render_weather_message(
            view=WEATHER_VIEW_TODAY,
            location_name=location.name,
            latitude=location.latitude,
            longitude=location.longitude,
            context=context,
            update=update,
            locale=locale,
        )
        _clear_awaiting_home(user_id, context)
    except LocationNotFoundError:
        await update.message.reply_text(
            MessageFactory.weather_location_not_found(location_query, locale=locale)
        )
    except WeatherServiceError:
        await update.message.reply_text(MessageFactory.weather_api_error(locale=locale))


@restricted
async def weather_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or not query.data:
        return

    await query.answer()
    locale = context.user_data.get("locale", MessageFactory.DEFAULT_LOCALE)

    parsed = MessageFactory.parse_weather_callback(query.data)
    if parsed is None:
        return

    view, latitude, longitude, location_name = parsed

    try:
        await _render_weather_message(
            view=view,
            location_name=location_name,
            latitude=latitude,
            longitude=longitude,
            context=context,
            query=query,
            locale=locale,
        )
    except WeatherServiceError:
        await safe_edit_message_text(
            query,
            MessageFactory.weather_api_error(locale=locale),
            parse_mode=ParseMode.HTML,
        )


def register_weather_handlers(application: Application) -> None:
    application.add_handler(CommandHandler(["weather", "wetter"], wetter_command))
    application.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND
            & _awaiting_home_filter,
            weather_home_reply_handler,
        )
    )
    application.add_handler(
        CallbackQueryHandler(
            weather_callback,
            pattern=r"^wetter_(heute|morgen|trend):",
        )
    )
