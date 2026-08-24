"""Windows-safe filename helpers."""

from __future__ import annotations

import re
from pathlib import Path

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_filename(name: str, replacement: str = "_", max_length: int = 120) -> str:
    name = (name or "").strip()
    if not name:
        return "untitled"
    name = INVALID_CHARS.sub(replacement, name)
    name = name.rstrip(" .")
    stem = name
    suffix = ""
    if "." in name and not name.startswith("."):
        # Preserve last extension only when caller included one
        parts = name.rsplit(".", 1)
        if len(parts[1]) <= 5 and parts[1].isalnum():
            stem, suffix = parts[0], "." + parts[1]
    stem = stem.strip(" .") or "untitled"
    if stem.upper() in RESERVED:
        stem = f"_{stem}"
    full = stem + suffix
    if len(full) > max_length:
        keep = max_length - len(suffix)
        full = stem[: max(1, keep)] + suffix
    return full


def unique_path(path: Path, ask_confirm: bool = False) -> Path:
    """Return a non-colliding path by appending _2, _3, ...

    ask_confirm is reserved for UI layers; this helper never overwrites.
    """
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    n = 2
    while True:
        candidate = parent / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def sanitize_project_folder_name(name: str) -> str:
    cleaned = sanitize_filename(name.replace(" ", "_"), max_length=80)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "project"
