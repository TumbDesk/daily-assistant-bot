import logging
import os
import sys

from telegram import Update
from telegram.ext import Application

from database import init_db
from handlers import register_all_handlers
from handlers.system_handler import error_handler, post_init
from services.auth_service import get_auth_service

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment variables placeholders
_ENV_PLACEHOLDERS = {
    "BOT_TOKEN": "your_telegram_bot_token_here",
    "ADMIN_ID": "your_telegram_user_id_here",
}

# Require the environment variables
def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        logger.error("Umgebungsvariable %s fehlt.", name)
        sys.exit(1)
    if value.strip() == _ENV_PLACEHOLDERS.get(name):
        logger.error(
            "%s enthält noch den Platzhalter aus .env.example. "
            "Bitte in .env durch echte Werte ersetzen.",
            name,
        )
        sys.exit(1)
    return value.strip()

# Parse the admin ID from the environment variables
def _parse_admin_id() -> int:
    raw = _require_env("ADMIN_ID")
    try:
        admin_id = int(raw)
    except ValueError:
        logger.error(
            "ADMIN_ID must be a numeric Telegram user ID (use /myid in a private chat), "
            "got: %r",
            raw,
        )
        sys.exit(1)
    if admin_id <= 0:
        logger.error("ADMIN_ID muss eine positive Zahl sein.")
        sys.exit(1)
    return admin_id

def build_application(token: str) -> Application:
    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    register_all_handlers(application)
    application.add_error_handler(error_handler)

    return application


def main() -> None:
    _require_env("BOT_TOKEN")
    admin_id = _parse_admin_id()
    os.environ["ADMIN_ID"] = str(admin_id)

    init_db()
    get_auth_service()

    token = os.environ["BOT_TOKEN"]
    application = build_application(token)
    logger.info("Bot gestartet.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
