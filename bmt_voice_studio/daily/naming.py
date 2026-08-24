"""Date-based Daily BMT project and filename helpers."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

_MONTHS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


def devotional_date(year: int, month: int, day: int) -> date:
    """Build a calendar devotional date from explicit Y/M/D only.

    Never derive the production date from UTC timestamps, timezone offsets,
    or ``datetime.now()``. The UI-selected calendar day is the sole source of truth.
    """
    return date(int(year), int(month), int(day))


def parse_iso_date(value: str) -> date:
    """Parse YYYY-MM-DD as a calendar date (ignore any time / timezone suffix)."""
    text = (value or "").strip()
    if not text:
        raise ValueError("Empty date string")
    # Strip time portion if present — calendar day only.
    calendar = text[:10]
    y, m, d = calendar.split("-")
    return devotional_date(int(y), int(m), int(d))


def freeze_devotional_date(value: date | datetime | str | Any) -> date:
    """Normalize any job/UI date input to a pure ``date`` (no time, no TZ)."""
    if isinstance(value, datetime):
        # Use calendar components only — do not convert timezone.
        return devotional_date(value.year, value.month, value.day)
    if isinstance(value, date):
        return devotional_date(value.year, value.month, value.day)
    if isinstance(value, str):
        return parse_iso_date(value)
    # Duck-typed QDate / objects with year()/month()/day() methods
    if all(hasattr(value, attr) for attr in ("year", "month", "day")):
        y = value.year() if callable(value.year) else value.year
        m = value.month() if callable(value.month) else value.month
        d = value.day() if callable(value.day) else value.day
        return devotional_date(int(y), int(m), int(d))
    raise TypeError(f"Unsupported date value: {type(value)!r}")


def project_id(d: date) -> str:
    d = freeze_devotional_date(d)
    return f"BMT_{d.strftime('%Y_%m_%d')}"


def display_date(d: date) -> str:
    d = freeze_devotional_date(d)
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def short_display_date(d: date) -> str:
    d = freeze_devotional_date(d)
    return f"{d.day} {_MONTHS[d.month - 1].title()} {d.year}"


def final_stem(d: date, language: str) -> str:
    d = freeze_devotional_date(d)
    raw = (language or "").strip().upper()
    if raw.startswith("SW") or raw == "SWAHILI":
        lang = "SWAHILI"
    elif raw.startswith("FR") or raw == "FRENCH":
        lang = "FRENCH"
    elif raw.startswith("PT") or "PORTUG" in raw:
        lang = "PORTUGUESE"
    elif raw in {"ENGLISH", "FRENCH", "SWAHILI", "PORTUGUESE"}:
        lang = raw
    else:
        lang = "ENGLISH"
    mon = _MONTHS[d.month - 1]
    return f"BMT_{d.day:02d}_{mon}_{d.year}_{lang}_FINAL"


def final_mp3_name(d: date, language: str) -> str:
    return final_stem(d, language) + ".mp3"


def final_wav_name(d: date, language: str) -> str:
    return final_stem(d, language) + ".wav"
