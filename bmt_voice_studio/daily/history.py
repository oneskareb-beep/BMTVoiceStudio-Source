"""Daily production history (local JSON index)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import local_appdata, user_data_root


def history_file() -> Path:
    path = user_data_root() / "History"
    path.mkdir(parents=True, exist_ok=True)
    return path / "daily.json"


def _legacy_history_file() -> Path:
    path = local_appdata() / "daily"
    return path / "history.json"


def load_history() -> list[dict[str, Any]]:
    p = history_file()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    legacy = _legacy_history_file()
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else []
            if entries:
                save_history(entries)
            return entries
        except Exception:
            return []
    return []


def save_history(entries: list[dict[str, Any]]) -> None:
    history_file().write_text(json.dumps(entries, indent=2), encoding="utf-8")


def upsert_entry(entry: dict[str, Any]) -> None:
    entries = load_history()
    key = entry.get("project_id") or entry.get("date")
    rest = [e for e in entries if (e.get("project_id") or e.get("date")) != key]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    rest.insert(0, entry)
    save_history(rest[:400])


def filter_history(
    entries: list[dict[str, Any]] | None = None,
    *,
    year: int | None = None,
    month: int | None = None,
    status: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    rows = entries if entries is not None else load_history()
    needle = (query or "").strip().lower()
    want_status = (status or "").strip().upper()
    if want_status in {"", "ALL", "ANY"}:
        want_status = ""
    out: list[dict[str, Any]] = []
    for item in rows:
        date_s = str(item.get("date") or "")
        if year is not None and not date_s.startswith(f"{year:04d}"):
            continue
        if month is not None and (len(date_s) < 7 or date_s[5:7] != f"{month:02d}"):
            continue
        if want_status and str(item.get("status") or "").upper() != want_status:
            continue
        if needle:
            blob = " ".join(str(v) for v in item.values()).lower()
            if needle not in blob:
                continue
        out.append(item)
    return out
