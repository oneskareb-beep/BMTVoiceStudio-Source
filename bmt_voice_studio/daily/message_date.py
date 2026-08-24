"""Detect the calendar date printed in a pasted Daily BMT / WhatsApp message.

The production date must come from the message header, never from the clock.
WhatsApp chat stamps ([13/08/2026, 09:14]) are ignored in favour of the
devotional date printed in the script (Tuesday, 19 August 2026).
"""

from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1, "januari": 1,
    "feb": 2, "february": 2, "fev": 2, "fév": 2, "fevrier": 2, "février": 2, "februari": 2,
    "mar": 3, "march": 3, "mars": 3, "machi": 3, "marco": 3, "março": 3,
    "apr": 4, "april": 4, "avr": 4, "avril": 4, "aprili": 4, "abril": 4,
    "may": 5, "mai": 5, "mei": 5, "maio": 5,
    "jun": 6, "june": 6, "juin": 6, "juni": 6, "junho": 6,
    "jul": 7, "july": 7, "juil": 7, "juillet": 7, "juli": 7, "julho": 7,
    "aug": 8, "august": 8, "aout": 8, "août": 8, "agosti": 8, "agosto": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9, "septemba": 9, "setembro": 9,
    "oct": 10, "october": 10, "octobre": 10, "oktoba": 10, "outubro": 10,
    "nov": 11, "november": 11, "novembre": 11, "novemba": 11, "novembro": 11,
    "dec": 12, "december": 12, "déc": 12, "decembre": 12, "décembre": 12, "desemba": 12, "dezembro": 12,
}

_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORDINAL = re.compile(r"(\d{1,2})(?:st|nd|rd|th)", re.IGNORECASE)
_CHAT_TIME = re.compile(r"\s*,\s*\d{1,2}:\d{2}")

_ISO = re.compile(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b")
_DMY_NUM = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b")
_MONTH_FIRST = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+(20\d{{2}})\b",
    re.IGNORECASE,
)
_DAY_FIRST = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:de\s+)?({_MONTH_ALT})\.?[,]?\s+(?:de\s+)?(20\d{{2}})\b",
    re.IGNORECASE,
)
_MONTH_DAY_NOYEAR = re.compile(
    rf"\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!\s*,?\s*20\d{{2}})",
    re.IGNORECASE,
)
_DAY_MONTH_NOYEAR = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:de\s+)?({_MONTH_ALT})\.?\b(?!\s*,?\s*20\d{{2}})",
    re.IGNORECASE,
)
_LABELED = re.compile(
    r"(?:^|\n)\s*(?:date|dated|devotional date|jour|tarehe|data)\s*[:\-–]\s*(.+)$",
    re.IGNORECASE,
)
_HEADER_HINT = re.compile(
    r"believers\s+manna|daily\s+devotional|written\s+by|topic\s*:",
    re.IGNORECASE,
)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        if year < 2020 or year > 2100:
            return None
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _from_month_name(month: str, day: int, year: int) -> date | None:
    m = _MONTHS.get((month or "").strip().lower().rstrip("."))
    if not m:
        return None
    return _safe_date(year, m, day)


def _is_chat_stamp(blob: str, end: int) -> bool:
    return bool(_CHAT_TIME.match(blob[end : end + 12]))


def _collect_named(blob: str) -> list[date]:
    found: list[date] = []
    for m in _MONTH_FIRST.finditer(blob):
        d = _from_month_name(m.group(1), int(m.group(2)), int(m.group(3)))
        if d:
            found.append(d)
    for m in _DAY_FIRST.finditer(blob):
        d = _from_month_name(m.group(2), int(m.group(1)), int(m.group(3)))
        if d:
            found.append(d)
    return found


def _collect_numeric(blob: str) -> list[date]:
    found: list[date] = []
    for m in _ISO.finditer(blob):
        if _is_chat_stamp(blob, m.end()):
            continue
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append(d)
    for m in _DMY_NUM.finditer(blob):
        if _is_chat_stamp(blob, m.end()):
            continue
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12:
            d = _safe_date(y, b, a)
        elif b > 12:
            d = _safe_date(y, a, b)
        else:
            d = _safe_date(y, b, a)  # day-month-year (ministry default)
        if d:
            found.append(d)
    return found


def _year_hint(today: date | None) -> int | None:
    if today is None:
        return None
    if isinstance(today, datetime):
        return today.year
    return today.year


def _collect_noyear(blob: str, year: int) -> list[date]:
    found: list[date] = []
    for m in _MONTH_DAY_NOYEAR.finditer(blob):
        d = _from_month_name(m.group(1), int(m.group(2)), year)
        if d:
            found.append(d)
    for m in _DAY_MONTH_NOYEAR.finditer(blob):
        d = _from_month_name(m.group(2), int(m.group(1)), year)
        if d:
            found.append(d)
    return found


def parse_date_token(text: str, *, today: date | None = None) -> date | None:
    blob = _ORDINAL.sub(r"\1", (text or "").strip())
    if not blob:
        return None
    named = _collect_named(blob)
    if named:
        return named[0]
    numeric = _collect_numeric(blob)
    if numeric:
        return numeric[0]
    year = _year_hint(today)
    if year:
        noyear = _collect_noyear(blob, year)
        if noyear:
            return noyear[0]
    return None


def detect_message_date(text: str, *, today: date | None = None) -> date | None:
    """Return the calendar date printed in the message — never ``date.today()``.

    ``today`` is only a year hint when the script prints a day/month with no year.
    """
    blob = _ORDINAL.sub(r"\1", text or "")
    if not blob.strip():
        return None

    labeled = _LABELED.search(blob)
    if labeled:
        found = parse_date_token(labeled.group(1), today=today)
        if found:
            return found

    lines = blob.splitlines()
    header = "\n".join(lines[:18])
    # Prefer the block around the BMT title so chat stamps above the paste lose.
    hinted = [i for i, line in enumerate(lines[:40]) if _HEADER_HINT.search(line)]
    if hinted:
        start = max(0, hinted[0] - 2)
        end = min(len(lines), hinted[0] + 14)
        header = "\n".join(lines[start:end])

    named = _collect_named(header) or _collect_named(blob)
    if named:
        return named[0]
    numeric = _collect_numeric(header)
    if numeric:
        return numeric[0]
    year = _year_hint(today)
    if year:
        noyear = _collect_noyear(header, year)
        if noyear:
            return noyear[0]
    return None
