"""Bundled 16:9 default video clips per Video Maker template."""

from __future__ import annotations

import sys
from pathlib import Path

from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.video.media_probe import probe_media
from bmt_voice_studio.video.models import (
    TEMPLATE_BMT_CLASSIC,
    TEMPLATE_BMT_MINIMAL,
    TEMPLATE_BMT_NATURE,
    TEMPLATE_HHR_GREEN,
    TEMPLATE_LABELS,
    MediaItem,
)

BUNDLED_CLIP_COUNT = 5
BUNDLED_DIR_NAME = "default_media"


def _resource_roots() -> list[Path]:
    here = Path(__file__).resolve().parent.parent / "resources"
    roots = [here / BUNDLED_DIR_NAME]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        roots.extend(
            [
                meipass / "bmt_voice_studio" / "resources" / BUNDLED_DIR_NAME,
                meipass / "resources" / BUNDLED_DIR_NAME,
                Path(sys.executable).parent / "_internal" / "bmt_voice_studio" / "resources" / BUNDLED_DIR_NAME,
            ]
        )
    return roots


def normalize_template_id(template_id: str | None) -> str:
    tid = (template_id or TEMPLATE_BMT_CLASSIC).strip().lower()
    if tid not in TEMPLATE_LABELS:
        return TEMPLATE_BMT_CLASSIC
    return tid


def bundled_clip_path(template_id: str, slot: int) -> Path | None:
    """Return packaged clip path for template slot (1-based)."""
    tid = normalize_template_id(template_id)
    slot = max(1, min(BUNDLED_CLIP_COUNT, int(slot)))
    name = f"clip_{slot:02d}.mp4"
    clip_tid = TEMPLATE_BMT_NATURE if tid == TEMPLATE_HHR_GREEN else tid
    for root in _resource_roots():
        path = root / clip_tid / name
        if path.is_file():
            return path
    return None


def bundled_clip_paths(template_id: str) -> list[Path]:
    return [
        p
        for i in range(1, BUNDLED_CLIP_COUNT + 1)
        if (p := bundled_clip_path(template_id, i)) is not None
    ]


def _settings_overrides(template_id: str) -> list[str]:
    settings = get_settings()
    raw = getattr(settings, "video_media_overrides", None) or {}
    if not isinstance(raw, dict):
        return []
    values = raw.get(normalize_template_id(template_id)) or []
    if not isinstance(values, list):
        return []
    return [str(v or "").strip() for v in values]


def resolve_clip_path(template_id: str, slot: int) -> Path | None:
    """Settings override first, then packaged bundled clip."""
    tid = normalize_template_id(template_id)
    idx = max(0, min(BUNDLED_CLIP_COUNT - 1, int(slot) - 1))
    overrides = _settings_overrides(tid)
    if idx < len(overrides):
        custom = Path(overrides[idx])
        if overrides[idx] and custom.is_file():
            return custom
    return bundled_clip_path(tid, idx + 1)


def resolved_clip_paths(template_id: str) -> list[Path]:
    return [
        p
        for i in range(1, BUNDLED_CLIP_COUNT + 1)
        if (p := resolve_clip_path(template_id, i)) is not None
    ]


def is_bundled_or_override_path(path: str | Path, template_id: str | None = None) -> bool:
    try:
        resolved = Path(path).resolve()
    except Exception:
        resolved = Path(path)
    tid = normalize_template_id(template_id) if template_id else None
    templates = [tid] if tid else list(TEMPLATE_LABELS)
    for check_tid in templates:
        for i in range(1, BUNDLED_CLIP_COUNT + 1):
            bundled = bundled_clip_path(check_tid, i)
            if bundled and resolved == bundled.resolve():
                return True
        for override in _settings_overrides(check_tid):
            if override and resolved == Path(override).resolve():
                return True
    return False


def media_uses_template_defaults(items: list[MediaItem], template_id: str) -> bool:
    """True when every item path matches bundled/override slots for this template."""
    if len(items) != BUNDLED_CLIP_COUNT:
        return False
    expected = resolved_clip_paths(template_id)
    if len(expected) != BUNDLED_CLIP_COUNT:
        return False
    for item, path in zip(items, expected, strict=False):
        try:
            if Path(item.path).resolve() != path.resolve():
                return False
        except Exception:
            if str(item.path) != str(path):
                return False
    return True


def default_media_items(template_id: str) -> list[MediaItem]:
    """Five probed 16:9 clips for the template (bundled + settings overrides)."""
    tid = normalize_template_id(template_id)
    items: list[MediaItem] = []
    for i in range(1, BUNDLED_CLIP_COUNT + 1):
        path = resolve_clip_path(tid, i)
        if path is None or not path.is_file():
            continue
        try:
            item = probe_media(path)
        except Exception:
            item = MediaItem(
                path=str(path),
                media_type="video",
                duration=12.0,
                width=1920,
                height=1080,
                order=i - 1,
            )
        item.order = i - 1
        item.missing = False
        items.append(item)
    return items


def merge_saved_layout(saved: list[MediaItem], template_id: str) -> list[MediaItem]:
    """Keep crop/zoom/trim from a saved project but bind paths to current defaults."""
    defaults = default_media_items(template_id)
    for i, item in enumerate(defaults):
        if i >= len(saved):
            break
        src = saved[i]
        item.crop_x = src.crop_x
        item.crop_y = src.crop_y
        item.zoom = src.zoom
        item.fit_mode = src.fit_mode
        item.animation_mode = src.animation_mode
        item.trim_start = src.trim_start
        item.trim_end = src.trim_end
        item.rotation = src.rotation
        item.order = i
    return defaults


def user_override_dir(template_id: str) -> Path:
    from bmt_voice_studio.config.paths import local_appdata

    return local_appdata() / "video_media" / normalize_template_id(template_id)


def save_override_clip(template_id: str, slot: int, source: Path) -> Path:
    """Copy a user-selected clip into the data folder and persist in settings."""
    tid = normalize_template_id(template_id)
    idx = max(0, min(BUNDLED_CLIP_COUNT - 1, int(slot) - 1))
    dest_dir = user_override_dir(tid)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"clip_{idx + 1:02d}{source.suffix.lower() or '.mp4'}"
    dest.write_bytes(source.read_bytes())
    settings = get_settings()
    overrides = dict(getattr(settings, "video_media_overrides", None) or {})
    slots = list(overrides.get(tid) or [""] * BUNDLED_CLIP_COUNT)
    while len(slots) < BUNDLED_CLIP_COUNT:
        slots.append("")
    slots[idx] = str(dest)
    overrides[tid] = slots
    settings.video_media_overrides = overrides
    from bmt_voice_studio.config.settings import save_settings

    save_settings(settings)
    return dest


def clear_override_clip(template_id: str, slot: int) -> None:
    tid = normalize_template_id(template_id)
    idx = max(0, min(BUNDLED_CLIP_COUNT - 1, int(slot) - 1))
    settings = get_settings()
    overrides = dict(getattr(settings, "video_media_overrides", None) or {})
    slots = list(overrides.get(tid) or [""] * BUNDLED_CLIP_COUNT)
    while len(slots) < BUNDLED_CLIP_COUNT:
        slots.append("")
    slots[idx] = ""
    overrides[tid] = slots
    settings.video_media_overrides = overrides
    from bmt_voice_studio.config.settings import save_settings

    save_settings(settings)


def reset_template_overrides(template_id: str) -> None:
    tid = normalize_template_id(template_id)
    settings = get_settings()
    overrides = dict(getattr(settings, "video_media_overrides", None) or {})
    overrides.pop(tid, None)
    settings.video_media_overrides = overrides
    from bmt_voice_studio.config.settings import save_settings

    save_settings(settings)
