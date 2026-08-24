"""Video render history — separate from Daily Audio history."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import local_appdata, user_data_root


def video_history_file() -> Path:
    path = user_data_root() / "History"
    path.mkdir(parents=True, exist_ok=True)
    return path / "video.json"


def _legacy_video_history_file() -> Path:
    return local_appdata() / "video" / "history.json"


def load_video_history() -> list[dict[str, Any]]:
    p = video_history_file()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []
    legacy = _legacy_video_history_file()
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            entries = data if isinstance(data, list) else []
            if entries:
                save_video_history(entries)
            return entries
        except Exception:
            return []
    return []


def save_video_history(entries: list[dict[str, Any]]) -> None:
    video_history_file().write_text(json.dumps(entries, indent=2), encoding="utf-8")


def is_preview_output(path: str | Path) -> bool:
    name = Path(str(path or "")).name.upper()
    return "PREVIEW" in name


def upsert_video_entry(entry: dict[str, Any]) -> None:
    if entry.get("preview") or is_preview_output(entry.get("output") or ""):
        return
    entries = load_video_history()
    key = (
        str(entry.get("date") or ""),
        str(entry.get("language") or ""),
        str(entry.get("output") or ""),
    )
    rest = [
        e
        for e in entries
        if (str(e.get("date") or ""), str(e.get("language") or ""), str(e.get("output") or "")) != key
    ]
    entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
    rest.insert(0, entry)
    save_video_history(rest[:400])
