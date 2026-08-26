"""Local-only Daily BMT draft autosave / recovery."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import local_appdata


def autosave_path() -> Path:
    path = local_appdata() / "daily"
    path.mkdir(parents=True, exist_ok=True)
    return path / "autosave.json"


def interrupt_marker() -> Path:
    path = local_appdata() / "daily"
    path.mkdir(parents=True, exist_ok=True)
    return path / "incomplete.json"


def save_draft(payload: dict[str, Any]) -> Path:
    data = dict(payload)
    data["saved_at"] = datetime.now().isoformat(timespec="seconds")
    target = autosave_path()
    target.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return target


def load_draft() -> dict[str, Any] | None:
    target = autosave_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def clear_draft() -> None:
    p = autosave_path()
    if p.exists():
        p.unlink()


def mark_incomplete(payload: dict[str, Any]) -> None:
    data = dict(payload)
    data["interrupted_at"] = datetime.now().isoformat(timespec="seconds")
    interrupt_marker().write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_incomplete() -> dict[str, Any] | None:
    p = interrupt_marker()
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_incomplete() -> None:
    p = interrupt_marker()
    if p.exists():
        p.unlink()


def draft_has_content(draft: dict[str, Any] | None) -> bool:
    if not draft:
        return False
    keys = ("english_text", "french_text", "swahili_text", "portuguese_text", "kinyarwanda_text", "english_caption_text")
    return any((draft.get(k) or "").strip() for k in keys)
