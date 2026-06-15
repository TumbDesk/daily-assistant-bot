"""Factory for locale-specific event parsers."""
from __future__ import annotations

from typing import Optional

from services.parser.base import BaseEventParser
from services.parser.de_parser import GermanEventParser
from services.parser.en_parser import EnglishEventParser


def get_parser(lang: Optional[str]) -> BaseEventParser:
    """Return the parser for the given locale code (defaults to English)."""
    if lang == "de":
        return GermanEventParser()
    return EnglishEventParser()
