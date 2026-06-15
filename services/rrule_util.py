"""RRULE helpers (no dependency on calendar service)."""
from datetime import date, datetime, time
from typing import Any, Optional, Tuple

from services.i18n_util import DEFAULT_LOCALE, t


def _weekday_label(code: str, locale: str) -> str:
    from services.i18n_util import _lang_dict

    weekdays = _lang_dict(locale).get("weekday_full")
    if not isinstance(weekdays, dict):
        weekdays = _lang_dict(DEFAULT_LOCALE).get("weekday_full", {})
    if isinstance(weekdays, dict):
        return str(weekdays.get(code, code))
    return code


def _parse_rrule_parts(rrule: Optional[str]) -> dict[str, str]:
    parts: dict[str, str] = {}
    if not rrule:
        return parts
    for segment in rrule.split(";"):
        if "=" in segment:
            key, value = segment.split("=", 1)
            parts[key] = value
    return parts


def strip_until(rrule: Optional[str]) -> Optional[str]:
    if not rrule:
        return None
    segments = [s for s in rrule.split(";") if s and not s.startswith("UNTIL=")]
    return ";".join(segments) if segments else None


def format_until_datetime(until_date: date) -> str:
    until_dt = datetime.combine(until_date, time(22, 59, 59))
    return until_dt.strftime("%Y%m%dT%H%M%S")


def apply_until(rrule: Optional[str], until_date: Optional[date]) -> Optional[str]:
    base = strip_until(rrule)
    if not base:
        return None
    if until_date is None:
        return base
    return f"{base};UNTIL={format_until_datetime(until_date)}"


def parse_until_from_rrule(rrule: Optional[str]) -> Optional[date]:
    parts = _parse_rrule_parts(rrule)
    until_raw = parts.get("UNTIL")
    if not until_raw:
        return None
    date_part = until_raw.split("T", 1)[0]
    if len(date_part) != 8 or not date_part.isdigit():
        return None
    return date(
        int(date_part[0:4]),
        int(date_part[4:6]),
        int(date_part[6:8]),
    )


def parse_rrule_to_freq_key(rrule: Optional[str]) -> Tuple[str, Optional[str], Optional[int]]:
    if not rrule:
        return "none", None, None
    parts = _parse_rrule_parts(strip_until(rrule))
    freq = parts.get("FREQ")
    if freq == "DAILY":
        return "daily", None, None
    if freq == "WEEKLY":
        if parts.get("INTERVAL") == "2":
            return "biweekly", None, None
        return "weekly", None, None
    if freq == "MONTHLY":
        byday = parts.get("BYDAY")
        bysetpos = parts.get("BYSETPOS")
        if byday and bysetpos:
            return "monthly_byweekday", byday, int(bysetpos)
        return "monthly", None, None
    return "none", None, None


def recurrence_label(rrule: Optional[str], locale: str = DEFAULT_LOCALE) -> str:
    if not rrule:
        return ""

    until_date = parse_until_from_rrule(rrule)
    parts = _parse_rrule_parts(strip_until(rrule))
    until_suffix = ""
    if until_date:
        until_suffix = t(
            "recur_until_suffix",
            locale,
            date=until_date.strftime("%d.%m.%Y"),
        )

    freq = parts.get("FREQ")
    interval_raw = parts.get("INTERVAL")
    interval = int(interval_raw) if interval_raw and interval_raw.isdigit() else 1

    if freq == "DAILY":
        if interval > 1:
            return t("recur_every_n_days", locale, n=interval) + until_suffix
        return t("recur_daily_short", locale) + until_suffix
    if freq == "WEEKLY":
        byday = parts.get("BYDAY")
        day_suffix = ""
        if byday:
            day_label = _weekday_label(byday, locale)
            day_suffix = t("recur_every_weekday_suffix", locale, weekday=day_label)
        if interval == 2:
            return t("recur_every_2_weeks", locale) + day_suffix + until_suffix
        if interval > 1:
            return (
                t("recur_every_n_weeks", locale, n=interval)
                + day_suffix
                + until_suffix
            )
        if byday:
            day_label = _weekday_label(byday, locale)
            return t("recur_every_weekday", locale, weekday=day_label) + until_suffix
        return t("recur_weekly_short", locale) + until_suffix
    if freq == "MONTHLY":
        if interval > 1:
            return t("recur_every_n_months", locale, n=interval) + until_suffix
        byday = parts.get("BYDAY")
        bysetpos = parts.get("BYSETPOS")
        if byday and bysetpos:
            pos = int(bysetpos)
            day_label = _weekday_label(byday, locale)
            if pos == -1:
                return (
                    t("recur_monthly_last", locale, weekday=day_label) + until_suffix
                )
            pos_label = f"{pos}."
            return (
                t("recur_monthly_nth", locale, pos=pos_label, weekday=day_label)
                + until_suffix
            )
        return t("recur_monthly_short", locale) + until_suffix
    return t("recur_series_fallback", locale) + until_suffix
