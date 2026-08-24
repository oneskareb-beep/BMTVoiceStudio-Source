"""Video Maker output and temp path helpers — no developer-machine hardcoding."""

from __future__ import annotations

import re
import uuid
from datetime import date
from pathlib import Path

from bmt_voice_studio.config.paths import video_exports_root, video_temp_root
from bmt_voice_studio.daily.naming import freeze_devotional_date, project_id
from bmt_voice_studio.video.models import PROFILE_WHATSAPP, language_folder

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


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return freeze_devotional_date(value)
    return freeze_devotional_date(value)


def video_project_dir(d: date | str, language: str, *, base: Path | None = None) -> Path:
    day = _as_date(d)
    root = base if base is not None else video_exports_root()
    folder = language_folder(language)
    path = root / f"{day.year:04d}" / f"{day.month:02d}" / project_id(day) / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def video_filename(d: date | str, language: str, *, profile_id: str = "") -> str:
    day = _as_date(d)
    folder = language_folder(language)
    mon = _MONTHS[day.month - 1]
    pid = (profile_id or "").strip().lower()
    if pid in {"whatsapp", "whatsapp_optimized", PROFILE_WHATSAPP}:
        suffix = "WHATSAPP"
    elif pid in {"preview", "preview_540"}:
        suffix = "PREVIEW"
    else:
        suffix = "VIDEO"
    return f"BMT_{day.day:02d}_{mon}_{day.year}_{folder}_{suffix}.mp4"


def video_output_path(
    d: date | str,
    language: str,
    *,
    base: Path | None = None,
    profile_id: str = "",
) -> Path:
    return video_project_dir(d, language, base=base) / video_filename(d, language, profile_id=profile_id)


def preview_output_path(d: date | str, language: str, *, base: Path | None = None) -> Path:
    return video_output_path(d, language, base=base, profile_id="preview")


def estimate_output_mb(duration_sec: float, profile_id: str = "") -> float:
    """Rough sharing-size estimate. Not a promise."""
    dur = max(0.0, float(duration_sec or 0.0))
    pid = (profile_id or "").strip().lower()
    if pid in {"whatsapp", "whatsapp_optimized", PROFILE_WHATSAPP}:
        kbps = 900 + 128
    elif pid in {"preview", "preview_540"}:
        kbps = 600 + 96
    else:
        kbps = 2200 + 192
    return max(0.1, round(dur * kbps / 8.0 / 1024.0, 1))


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def video_render_temp_dir(job_id: str | None = None) -> Path:
    jid = re.sub(r"[^a-zA-Z0-9_-]", "", job_id or new_job_id()) or new_job_id()
    path = video_temp_root() / jid
    path.mkdir(parents=True, exist_ok=True)
    return path


def unique_output_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 2
    while True:
        candidate = dest.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1
