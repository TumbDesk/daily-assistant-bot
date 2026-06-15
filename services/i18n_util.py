"""Central translation helpers (JSON locales)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "de"
LOCALES_DIR = "locales"
_TRANSLATIONS: dict[str, dict[str, Any]] = {}


class LocalizedError(ValueError):
    def __init__(self, key: str, **params: Any) -> None:
        self.key = key
        self.params = params
        super().__init__(key)


def load_locales() -> None:
    if not os.path.exists(LOCALES_DIR):
        logger.warning("Locales-Verzeichnis '%s' nicht gefunden.", LOCALES_DIR)
        return

    for filename in os.listdir(LOCALES_DIR):
        if not filename.endswith(".json"):
            continue
        locale = filename[:-5]
        path = os.path.join(LOCALES_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as handle:
                _TRANSLATIONS[locale] = json.load(handle)
        except Exception as exc:
            logger.error("Fehler beim Laden von %s: %s", filename, exc)


def _text_value(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(line) for line in value)
    if value is None:
        return ""
    return str(value)


def _lang_dict(locale: str) -> dict[str, Any]:
    lang = locale[:2].lower() if locale else DEFAULT_LOCALE
    return _TRANSLATIONS.get(lang, _TRANSLATIONS.get(DEFAULT_LOCALE, {}))


def t(key: str, locale: str = DEFAULT_LOCALE, **kwargs: Any) -> str:
    lang_dict = _lang_dict(locale)
    text = lang_dict.get(key)
    if text is None:
        default_dict = _TRANSLATIONS.get(DEFAULT_LOCALE, {})
        text = default_dict.get(key, key)
    text = _text_value(text)
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def t_list(key: str, locale: str = DEFAULT_LOCALE) -> list[str]:
    lang_dict = _lang_dict(locale)
    value = lang_dict.get(key)
    if value is None:
        default_dict = _TRANSLATIONS.get(DEFAULT_LOCALE, {})
        value = default_dict.get(key, [])
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def localized_message(exc: BaseException, locale: str = DEFAULT_LOCALE) -> str:
    if isinstance(exc, LocalizedError):
        return t(exc.key, locale, **exc.params)
    return t("generic_error", locale)


load_locales()
