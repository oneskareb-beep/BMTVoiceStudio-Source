"""Daily BMT output folder layout."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bmt_voice_studio.config.paths import default_exports_dir
from bmt_voice_studio.daily.naming import (
    final_mp3_name,
    final_wav_name,
    project_id,
)

DAILY_FOLDER_NAME = "Daily"


def daily_exports_root(base: Path | None = None) -> Path:
    """Canonical Daily export root: ``<Exports>/Daily``.

    ``base`` must be the Exports directory (parent of Daily). If a caller
    already passes a path ending in ``Daily``, it is used as-is so the folder
    is never doubled (``Exports/Daily/Daily/...``).
    """
    if base is None:
        root = default_exports_dir() / DAILY_FOLDER_NAME
    else:
        base = Path(base)
        if base.name.lower() == DAILY_FOLDER_NAME.lower():
            root = base
        else:
            root = base / DAILY_FOLDER_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def daily_project_dir(d: date, base: Path | None = None) -> Path:
    root = daily_exports_root(base)
    path = root / f"{d.year:04d}" / f"{d.month:02d}" / project_id(d)
    return path


def ensure_daily_layout(d: date, base: Path | None = None) -> Path:
    root = daily_project_dir(d, base)
    for sub in (
        "ENGLISH/segments",
        "FRENCH/segments",
        "SWAHILI/segments",
        "PORTUGUESE/segments",
        "REPORTS",
        "SOURCE",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def language_dir(root: Path, language: str) -> Path:
    u = (language or "").strip().upper()
    if u.startswith("SW") or u == "SWAHILI":
        name = "SWAHILI"
    elif u.startswith("FR") or u == "FRENCH":
        name = "FRENCH"
    elif u.startswith("PT") or "PORTUG" in u:
        name = "PORTUGUESE"
    else:
        name = "ENGLISH"
    path = root / name
    (path / "segments").mkdir(parents=True, exist_ok=True)
    return path


def final_paths(root: Path, d: date, language: str) -> tuple[Path, Path]:
    folder = language_dir(root, language)
    return folder / final_mp3_name(d, language), folder / final_wav_name(d, language)
