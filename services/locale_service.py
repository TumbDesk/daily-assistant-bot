"""Locale resolution and list of supported languages."""
from typing import Optional, TYPE_CHECKING

from views.message_factory import MessageFactory

if TYPE_CHECKING:
    from telegram import User
    from telegram.ext import ContextTypes


def list_supported_locales() -> list[str]:
    return sorted(MessageFactory._TRANSLATIONS.keys())


def normalize_locale(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    return code[:2].lower()


def resolve_user_locale(saved: Optional[str], telegram: Optional[str]) -> str:
    normalized_saved = normalize_locale(saved)
    if normalized_saved and normalized_saved in MessageFactory._TRANSLATIONS:
        return normalized_saved

    normalized_telegram = normalize_locale(telegram)
    if normalized_telegram and normalized_telegram in MessageFactory._TRANSLATIONS:
        return normalized_telegram

    return MessageFactory.DEFAULT_LOCALE


def resolve_locale_for_handler(
    context: "ContextTypes.DEFAULT_TYPE",
    user: Optional["User"],
) -> str:
    """Locale for handlers — includes stored DB setting even without @restricted."""
    cached = context.user_data.get("locale")
    if cached:
        return cached

    telegram_lang = user.language_code if user else None
    saved_locale: Optional[str] = None

    if user is not None:
        from services.user_service import PLATFORM_TELEGRAM, get_user_service
        from services.user_settings import get_user_settings_service

        global_user_id = get_user_service().get_global_user_id(
            PLATFORM_TELEGRAM, str(user.id)
        )
        if global_user_id is not None:
            try:
                saved_locale = get_user_settings_service().get_settings(
                    global_user_id
                ).locale
            except ValueError:
                pass

    return resolve_user_locale(saved_locale, telegram_lang)


def locale_label(code: str) -> str:
    translations = MessageFactory._TRANSLATIONS.get(code, {})
    label = translations.get("locale_label")
    if label:
        return label
    return code.upper()
