"""Single authority for the active BMT data root. No per-module Documents guessing."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from bmt_voice_studio.config.paths import (
    EXPORT_DIR_NAME,
    documents_location,
    ensure_data_layout,
    local_appdata,
    settings_file,
)

KIND_CANONICAL = "canonical"
KIND_LEGACY = "legacy"
KIND_CUSTOM = "custom"


def physical_documents_location() -> Path:
    """User-profile Documents folder without following OneDrive Known Folder redirection."""
    override = (os.environ.get("BMT_PHYSICAL_DOCUMENTS_DIR") or "").strip()
    if override:
        return Path(override)
    # Isolated Documents override (tests) should not scan the real user profile.
    if (os.environ.get("BMT_DOCUMENTS_DIR") or "").strip():
        return documents_location()
    profile = os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
    return Path(profile) / "Documents"


def canonical_documents_location() -> Path:
    """Qt/Windows resolved Documents (follows OneDrive redirection when present)."""
    return documents_location()


def _norm(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except Exception:
        return path.expanduser()


def _same_path(a: Path, b: Path) -> bool:
    return _norm(a) == _norm(b)


def is_populated_library(root: Path | None) -> bool:
    """True when a folder holds real BMT user content, not just an empty layout."""
    if root is None:
        return False
    try:
        path = Path(root)
        if not path.is_dir():
            return False
    except Exception:
        return False
    daily = path / "Exports" / "Daily"
    video = path / "Exports" / "Video"
    aud = path / "Auditions"
    hist = path / "History"
    try:
        if any(daily.glob("*_FINAL.mp3")) or any(daily.rglob("*_FINAL.mp3")):
            return True
        if any(daily.rglob("production.json")) or any(daily.rglob("*_source.txt")):
            return True
        if any(video.rglob("*.mp4")):
            return True
        if any(p.is_file() for p in aud.rglob("*") if p.is_file()):
            return True
        if any(hist.glob("*.json")):
            return True
    except Exception:
        return False
    return False


def library_file_count(root: Path) -> int:
    n = 0
    try:
        for p in Path(root).rglob("*"):
            if p.is_file():
                n += 1
    except Exception:
        return 0
    return n


@dataclass
class LibraryCandidate:
    path: Path
    kind: str
    populated: bool
    file_count: int = 0
    label: str = ""

    def display_path(self) -> str:
        return str(self.path)


@dataclass
class RootDecision:
    root: Path
    mode: str  # default | custom
    needs_prompt: bool = False
    candidates: list[LibraryCandidate] = field(default_factory=list)
    reason: str = ""


def _settings_blob() -> dict:
    try:
        target = settings_file()
        if not target.is_file():
            return {}
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def custom_folder_from_settings() -> Path | None:
    data = _settings_blob()
    mode = str(data.get("data_folder_mode") or "default").strip().lower()
    custom = str(data.get("custom_data_folder") or "").strip()
    if mode == "custom" and custom:
        return Path(custom)
    return None


def library_choice_complete() -> bool:
    data = _settings_blob()
    return bool(data.get("data_library_choice_complete"))


def discover_library_candidates() -> list[LibraryCandidate]:
    """Known locations only — never guess extra drive letters."""
    raw: list[tuple[Path, str, str]] = []
    canonical = canonical_documents_location() / EXPORT_DIR_NAME
    raw.append((canonical, KIND_CANONICAL, "Default Documents location"))
    physical = physical_documents_location() / EXPORT_DIR_NAME
    if not _same_path(physical, canonical):
        raw.append((physical, KIND_LEGACY, "Documents folder"))
    custom = custom_folder_from_settings()
    if custom is not None and not any(_same_path(custom, p) for p, _, _ in raw):
        raw.append((custom, KIND_CUSTOM, "Chosen folder"))
    seen: set[str] = set()
    out: list[LibraryCandidate] = []
    for path, kind, label in raw:
        key = str(_norm(path)).lower()
        if key in seen:
            continue
        seen.add(key)
        populated = is_populated_library(path)
        out.append(
            LibraryCandidate(
                path=path,
                kind=kind,
                populated=populated,
                file_count=library_file_count(path) if populated else 0,
                label=label,
            )
        )
    return out


def populated_libraries(candidates: list[LibraryCandidate] | None = None) -> list[LibraryCandidate]:
    items = candidates if candidates is not None else discover_library_candidates()
    return [c for c in items if c.populated]


def persist_active_root(root: Path, *, mode: str) -> Path:
    """Write the choice to user preferences (AppData settings.json — not the app folder)."""
    from bmt_voice_studio.config.settings import get_settings, save_settings

    path = Path(root)
    ensure_data_layout(path)
    s = get_settings()
    if mode == "custom":
        s.data_folder_mode = "custom"
        s.custom_data_folder = str(path)
    else:
        s.data_folder_mode = "default"
        s.custom_data_folder = ""
    s.data_library_choice_complete = True
    s.output_directory = str(path / "Exports")
    save_settings(s)
    seed_indexes_into_root(path)
    return path


def seed_indexes_into_root(root: Path) -> None:
    """Copy AppData history/project indexes into the data root if the root has none yet."""
    dest_hist = root / "History"
    dest_hist.mkdir(parents=True, exist_ok=True)
    dest_proj = root / "Projects"
    dest_proj.mkdir(parents=True, exist_ok=True)
    app = local_appdata()
    pairs = [
        (app / "daily" / "history.json", dest_hist / "daily.json"),
        (app / "video" / "history.json", dest_hist / "video.json"),
        (app / "video" / "autosave.json", dest_proj / "autosave.json"),
    ]
    for src, dest in pairs:
        try:
            if src.is_file() and not dest.is_file():
                dest.write_bytes(src.read_bytes())
        except Exception:
            continue
    src_slots = app / "video" / "projects"
    if src_slots.is_dir():
        for item in src_slots.glob("*.json"):
            dest = dest_proj / item.name
            if not dest.exists():
                try:
                    dest.write_bytes(item.read_bytes())
                except Exception:
                    continue


def decide_startup_root(*, allow_prompt: bool = True) -> RootDecision:
    env = (os.environ.get("BMT_DATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        return RootDecision(root=path, mode="custom", needs_prompt=False, reason="env")

    custom = custom_folder_from_settings()
    data = _settings_blob()
    mode = str(data.get("data_folder_mode") or "default").strip().lower()
    if mode == "custom" and custom is not None:
        return RootDecision(root=custom, mode="custom", needs_prompt=False, reason="saved-custom")

    if library_choice_complete() and mode != "custom":
        root = canonical_documents_location() / EXPORT_DIR_NAME
        return RootDecision(root=root, mode="default", needs_prompt=False, reason="saved-default")

    candidates = discover_library_candidates()
    populated = populated_libraries(candidates)
    canonical = canonical_documents_location() / EXPORT_DIR_NAME

    if len(populated) == 0:
        return RootDecision(root=canonical, mode="default", needs_prompt=False, candidates=candidates, reason="fresh")
    if len(populated) == 1:
        chosen = populated[0]
        use_custom = not _same_path(chosen.path, canonical)
        return RootDecision(
            root=chosen.path,
            mode="custom" if use_custom else "default",
            needs_prompt=False,
            candidates=candidates,
            reason="single",
        )
    skip = (os.environ.get("BMT_SKIP_LIBRARY_DIALOG") or "").strip().lower() in {"1", "true", "yes"}
    if skip or not allow_prompt:
        chosen = max(populated, key=lambda c: (c.file_count, 1 if c.kind == KIND_LEGACY else 0))
        use_custom = not _same_path(chosen.path, canonical)
        return RootDecision(
            root=chosen.path,
            mode="custom" if use_custom else "default",
            needs_prompt=False,
            candidates=candidates,
            reason="unattended-multi",
        )
    return RootDecision(root=canonical, mode="default", needs_prompt=True, candidates=candidates, reason="multi")


def activate_decided_root(decision: RootDecision) -> Path:
    if decision.reason in {"saved-custom", "saved-default", "env"}:
        ensure_data_layout(decision.root)
        seed_indexes_into_root(decision.root)
        return decision.root
    return persist_active_root(decision.root, mode=decision.mode)


def apply_startup_root(*, allow_prompt: bool = False) -> Path:
    decision = decide_startup_root(allow_prompt=allow_prompt)
    if decision.needs_prompt:
        return decision.root
    return activate_decided_root(decision)
