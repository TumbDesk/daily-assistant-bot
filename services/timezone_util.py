import os
from datetime import datetime
from zoneinfo import ZoneInfo

_DEFAULT_TZ = "Europe/Berlin"


def get_timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("TZ", _DEFAULT_TZ))


def now() -> datetime:
    """Current time in the configured timezone (e.g. Europe/Berlin)."""
    return datetime.now(get_timezone())


def as_local(dt: datetime) -> datetime:
    """Interpret naive datetimes from the DB as local time."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=get_timezone())
    return dt.astimezone(get_timezone())


def to_naive_local(dt: datetime) -> datetime:
    """For SQLite storage: local wall-clock time without tzinfo."""
    return as_local(dt).replace(tzinfo=None)
