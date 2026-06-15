import logging
import os
from functools import wraps
from typing import Callable, Optional

from telegram import Chat, Update
from telegram.ext import ContextTypes

from services.chat_membership_service import get_chat_membership_service
from services.locale_service import resolve_locale_for_handler, resolve_user_locale
from services.user_service import PLATFORM_TELEGRAM, get_user_service
from services.user_settings import get_user_settings_service
from views.message_factory import MessageFactory

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self) -> None:
        self.admin_id = int(os.environ["ADMIN_ID"])
        self._users = get_user_service()

    def is_allowed(self, user_id: int) -> bool:
        return self._users.is_allowed(PLATFORM_TELEGRAM, str(user_id))

    def ensure_bootstrap_admin(self, user_id: int, full_name: Optional[str]) -> None:
        uid = self._users.ensure_bootstrap_admin(
            PLATFORM_TELEGRAM, str(user_id), full_name
        )
        if uid:
            logger.info(
                "Admin %s (%s) in der Datenbank registriert.",
                full_name or user_id,
                user_id,
            )

    def is_admin(self, user_id: int) -> bool:
        return self._users.is_admin(PLATFORM_TELEGRAM, str(user_id))

    def resolve_global_user_id(
        self, user_id: int, full_name: Optional[str]
    ) -> Optional[str]:
        return self._users.resolve_user_id(
            PLATFORM_TELEGRAM, str(user_id), full_name
        )

    def add_allowed_user(
        self, admin_id: int, target_id: int, name: str
    ) -> tuple[bool, str]:
        return self._users.add_allowed_user(
            str(admin_id), str(target_id), name, platform=PLATFORM_TELEGRAM
        )

    async def notify_admin(self, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
        try:
            await context.bot.send_message(chat_id=self.admin_id, text=text)
        except Exception:
            logger.exception("Admin-Benachrichtigung fehlgeschlagen.")


_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


def restricted(handler: Callable):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        auth = get_auth_service()
        user = update.effective_user
        if user is None:
            return

        if not auth.is_allowed(user.id):
            if update.effective_chat and update.effective_chat.type == Chat.PRIVATE:
                if update.message:
                    locale = resolve_locale_for_handler(context, user)
                    await update.message.reply_text(
                        MessageFactory.access_denied(locale=locale)
                    )
            return

        auth.ensure_bootstrap_admin(user.id, user.full_name)
        global_user_id = auth.resolve_global_user_id(user.id, user.full_name)
        if global_user_id is None:
            if update.effective_chat and update.effective_chat.type == Chat.PRIVATE:
                if update.message:
                    locale = resolve_locale_for_handler(context, user)
                    await update.message.reply_text(
                        MessageFactory.access_denied(locale=locale)
                    )
            return

        context.user_data["global_user_id"] = global_user_id
        settings = get_user_settings_service().get_settings(global_user_id)
        context.user_data["locale"] = resolve_user_locale(
            settings.locale, user.language_code
        )

        chat = update.effective_chat
        if chat is not None and chat.type in (Chat.GROUP, Chat.SUPERGROUP):
            get_chat_membership_service().record_user_seen(user.id, chat.id)

        return await handler(update, context)

    return wrapper
