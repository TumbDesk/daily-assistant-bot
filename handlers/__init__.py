from telegram.ext import Application

from handlers.agenda_handler import register_agenda_handlers
from handlers.admin_handler import register_admin_handlers
from handlers.birthday_edit_handler import register_birthday_edit_handlers
from handlers.birthday_handler import register_birthday_handlers
from handlers.category_callback_handler import register_category_callbacks
from handlers.conversation_handler import build_termin_neu_conversation
from handlers.event_callback_handler import register_event_callbacks
from handlers.field_edit_handler import register_field_edit_handlers
from handlers.termine_handler import register_termine_handlers
from handlers.travel_edit_handler import register_travel_edit_handlers
from handlers.travel_handler import register_travel_handlers
from handlers.user_handler import register_base_user_handlers
from handlers.weather_handler import register_weather_handlers


def register_all_handlers(application: Application) -> None:
    register_base_user_handlers(application)
    register_admin_handlers(application)
    register_termine_handlers(application)
    register_category_callbacks(application)
    register_event_callbacks(application)
    register_field_edit_handlers(application)
    register_weather_handlers(application)
    register_agenda_handlers(application)
    register_birthday_handlers(application)
    register_birthday_edit_handlers(application)
    register_travel_handlers(application)
    register_travel_edit_handlers(application)
    application.add_handler(build_termin_neu_conversation())


__all__ = [
    "register_all_handlers",
    "register_agenda_handlers",
    "register_admin_handlers",
    "register_birthday_edit_handlers",
    "register_birthday_handlers",
    "register_category_callbacks",
    "build_termin_neu_conversation",
    "register_event_callbacks",
    "register_field_edit_handlers",
    "register_termine_handlers",
    "register_travel_edit_handlers",
    "register_travel_handlers",
    "register_base_user_handlers",
    "register_weather_handlers",
]