"""Helper functions for series occurrences and Telegram callbacks."""
from datetime import datetime

from services.calendar_service import CalendarService
from services.i18n_util import LocalizedError
from services.timezone_util import to_naive_local

OCCURRENCE_KEY_LEN = 12
UUID_LEN = 36


def normalize_occurrence(dt: datetime) -> datetime:
    return to_naive_local(dt).replace(second=0, microsecond=0)


def encode_occurrence(dt: datetime) -> str:
    return normalize_occurrence(dt).strftime("%Y%m%d%H%M")


def decode_occurrence(key: str) -> datetime:
    if len(key) != OCCURRENCE_KEY_LEN:
        raise LocalizedError("err_invalid_occurrence_key")
    return datetime.strptime(key, "%Y%m%d%H%M")


def build_view_evt_callback(event_id: str, original_start: datetime | None = None) -> str:
    if original_start is None:
        return f"view_evt_{event_id}"
    return f"view_evt_{event_id}_{encode_occurrence(original_start)}"


def parse_event_occ_callback(
    data: str, prefix: str
) -> tuple[str, datetime | None] | None:
    if not data.startswith(prefix):
        return None
    remainder = data[len(prefix) :]
    if len(remainder) == UUID_LEN and CalendarService.is_valid_event_id(remainder):
        return remainder, None
    if (
        len(remainder) >= UUID_LEN + 1 + OCCURRENCE_KEY_LEN
        and remainder[UUID_LEN] == "_"
    ):
        event_id = remainder[:UUID_LEN]
        occ_key = remainder[UUID_LEN + 1 : UUID_LEN + 1 + OCCURRENCE_KEY_LEN]
        if CalendarService.is_valid_event_id(event_id):
            return event_id, decode_occurrence(occ_key)
    return None


def parse_view_evt_callback(data: str) -> tuple[str, datetime | None] | None:
    return parse_event_occ_callback(data, "view_evt_")


def build_occ_callback(prefix: str, event_id: str, original_start: datetime) -> str:
    return f"{prefix}{event_id}_{encode_occurrence(original_start)}"


def build_event_callback(prefix: str, event_id: str) -> str:
    return f"{prefix}{event_id}"
