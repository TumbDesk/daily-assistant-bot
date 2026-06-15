"""Compatibility re-export — use services.parser instead."""
from services.types import CategoryDTO
from services.parser import (
    ParsedEvent,
    ParsedTermin,
    TerminParseError,
    parse_event_text,
    parse_termin_text,
)

__all__ = [
    "CategoryDTO",
    "ParsedEvent",
    "ParsedTermin",
    "TerminParseError",
    "parse_event_text",
    "parse_termin_text",
]
