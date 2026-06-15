"""Register Telegram bot menu commands from locale files."""
from __future__ import annotations

import json
import logging
import os

from telegram import BotCommand
from telegram.ext import Application

from services.i18n_util import LOCALES_DIR, load_locales

logger = logging.getLogger(__name__)

_SUPPORTED_MENU_LOCALES = ("de", "en")


async def setup_bot_commands(app: Application) -> None:
    load_locales()

    for lang_code in _SUPPORTED_MENU_LOCALES:
        path = os.path.join(LOCALES_DIR, f"{lang_code}.json")
        try:
            with open(path, encoding="utf-8") as handle:
                menu = json.load(handle).get("menu_commands", {})
        except OSError as exc:
            logger.error("Locale-Datei nicht lesbar: %s (%s)", path, exc)
            continue
        except json.JSONDecodeError as exc:
            logger.error("Ungültiges JSON in %s: %s", path, exc)
            continue

        if not isinstance(menu, dict) or not menu:
            logger.warning("menu_commands fehlt oder leer: %s", path)
            continue

        commands = [
            BotCommand(command=cmd, description=str(desc))
            for cmd, desc in menu.items()
        ]
        await app.bot.set_my_commands(commands, language_code=lang_code)
        logger.info(
            "Bot-Menübefehle registriert: %d für language_code=%s",
            len(commands),
            lang_code,
        )
