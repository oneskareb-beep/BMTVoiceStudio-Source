"""Application data and export path helpers — no developer machine hardcoding."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


APP_DIR_NAME = "BMTVoiceStudio"
EXPORT_DIR_NAME = "BMT Voice Studio"

_LAYOUT_DIRS = (
    "Exports",
    "Exports/Daily",
    "Exports/Video",
    "Auditions",
    "Logs",
    "Reports",
    "Reports/DataMigration",
    "Temp",
    "History",
    "Projects",
)


def documents_location() -> Path:
    """Canonical Windows/Qt Documents folder (follows OneDrive redirection)."""
    override = (os.environ.get("BMT_DOCUMENTS_DIR") or "").strip()
    if override:
        return Path(override)
    try:
        from PySide6.QtCore import QStandardPaths

        loc = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        if loc:
            return Path(loc)
    except Exception:
        pass
    home_docs = Path.home() / "Documents"
    if home_docs.is_dir():
        return home_docs
    return Path.home()


def _custom_data_root_from_settings() -> Path | None:
    """Read custom data folder from settings.json without importing AppSettings."""
    try:
        target = settings_file()
        if not target.is_file():
            return None
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        mode = str(data.get("data_folder_mode") or "default").strip().lower()
        custom = str(data.get("custom_data_folder") or "").strip()
        if mode == "custom" and custom:
            return Path(custom)
    except Exception:
        return None
    return None


def default_data_root() -> Path:
    """<Documents>/BMT Voice Studio — Qt/Windows Documents, including OneDrive."""
    return documents_location() / EXPORT_DIR_NAME


_RESOLVING_ROOT = False


def user_data_root() -> Path:
    """The one active BMT data root. Daily Audio, Video Maker, history, and temp share this."""
    global _RESOLVING_ROOT
    env = (os.environ.get("BMT_DATA_ROOT") or "").strip()
    if env:
        path = Path(env)
        ensure_data_layout(path)
        return path
    custom = _custom_data_root_from_settings()
    if custom is not None:
        ensure_data_layout(custom)
        return custom
    if _RESOLVING_ROOT:
        path = default_data_root()
        ensure_data_layout(path)
        return path
    _RESOLVING_ROOT = True
    try:
        from bmt_voice_studio.config.data_root import apply_startup_root

        path = apply_startup_root(allow_prompt=False)
        ensure_data_layout(path)
        return path
    finally:
        _RESOLVING_ROOT = False


def ensure_data_layout(root: Path) -> Path:
    """Create the standard BMT Voice Studio folder tree."""
    root.mkdir(parents=True, exist_ok=True)
    for rel in _LAYOUT_DIRS:
        (root / Path(rel)).mkdir(parents=True, exist_ok=True)
    return root


def data_root_display() -> str:
    return str(user_data_root())


def app_config_location() -> Path:
    """Per-user application config directory (preferences / cache)."""
    return local_appdata()


def local_appdata() -> Path:
    """Writable per-user config/cache root (not Documents outputs)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    path = Path(base) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = local_appdata() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = local_appdata() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = user_data_root() / "Logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reports_dir() -> Path:
    path = user_data_root() / "Reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def auditions_dir() -> Path:
    path = user_data_root() / "Auditions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def daily_exports_root() -> Path:
    """Canonical Daily output root under Exports/Daily (validated layout)."""
    path = default_exports_dir() / "Daily"
    path.mkdir(parents=True, exist_ok=True)
    return path


def projects_dir() -> Path:
    path = user_data_root() / "Projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def temp_work_dir() -> Path:
    path = user_data_root() / "Temp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_exports_dir() -> Path:
    path = user_data_root() / "Exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def video_exports_root() -> Path:
    """Canonical Video Maker output root under Exports/Video."""
    path = default_exports_dir() / "Video"
    path.mkdir(parents=True, exist_ok=True)
    return path


def video_temp_root() -> Path:
    """Temporary render workspace under the canonical data root (not install dir)."""
    path = user_data_root() / "Temp" / "VideoRender"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return local_appdata() / "settings.json"


def first_run_marker() -> Path:
    return local_appdata() / ".first_run_complete"


def daily_v11_welcome_marker() -> Path:
    return local_appdata() / ".daily_v11_welcome"


def bundled_resource_roots() -> list[Path]:
    """PyInstaller-safe roots for packaged resources (no source-repo assumption)."""
    roots: list[Path] = []
    here = Path(__file__).resolve().parent
    roots.append(here)
    roots.append(here.parent)
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        roots.extend(
            [
                meipass,
                meipass / "bmt_voice_studio",
                meipass / "bmt_voice_studio" / "config",
                exe_dir,
                exe_dir / "_internal",
                exe_dir / "_internal" / "bmt_voice_studio",
                exe_dir / "_internal" / "bmt_voice_studio" / "config",
            ]
        )
    return roots
