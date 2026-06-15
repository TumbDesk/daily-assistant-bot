"""Natural-language parser for /event|/termin <free text>."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence

from services.parser.base import (
    BaseEventParser,
    ParsedEvent,
    ParsedTermin,
    TerminParseError,
)
from services.parser.factory import get_parser
from services.timezone_util import now
from services.types import CategoryDTO

__all__ = [
    "BaseEventParser",
    "ParsedEvent",
    "ParsedTermin",
    "TerminParseError",
    "get_parser",
    "now",
    "parse_event_text",
    "parse_termin_text",
]


def parse_event_text(
    text: str,
    *,
    user_categories: Sequence[CategoryDTO] = (),
    base: Optional[datetime] = None,
    locale: str = "en",
) -> ParsedEvent:
    """Parse free text into title, start time, recurrence, category, and flags."""
    return get_parser(locale).parse(text, user_categories, base)


def parse_termin_text(
    text: str,
    *,
    base: Optional[datetime] = None,
    locale: str = "en",
) -> ParsedEvent:
    """Compatibility alias without category lookup."""
    return parse_event_text(text, user_categories=(), base=base, locale=locale)
