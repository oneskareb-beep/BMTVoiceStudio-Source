"""Meditation paysage stills — person with Bible in landscape (Sylvestre layout).

Files live under resources/meditation_paysage/{eng,fra,port}.jpeg.
Video placement uses FitMode.BAND (middle 2/4 of the 9:16 frame).
"""

from __future__ import annotations

import sys
from pathlib import Path

from bmt_voice_studio.video.media_probe import probe_media
from bmt_voice_studio.video.models import (
    AnimationMode,
    FitMode,
    MediaItem,
    language_still_code,
    normalize_language_id,
)

PAYSAGE_DIR_NAME = "meditation_paysage"
PAYSAGE_CODES = ("eng", "fra", "port")


def _resource_roots() -> list[Path]:
    here = Path(__file__).resolve().parent.parent / "resources"
    roots = [here / PAYSAGE_DIR_NAME]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        roots.extend(
            [
                meipass / "bmt_voice_studio" / "resources" / PAYSAGE_DIR_NAME,
                meipass / "resources" / PAYSAGE_DIR_NAME,
                Path(sys.executable).parent
                / "_internal"
                / "bmt_voice_studio"
                / "resources"
                / PAYSAGE_DIR_NAME,
            ]
        )
    return roots


def paysage_still_path(language: str | None) -> Path | None:
    """Resolve eng/fra/port still for a language (falls back to eng)."""
    code = language_still_code(language)
    if code not in PAYSAGE_CODES:
        code = "eng"
    for root in _resource_roots():
        for name in (f"{code}.jpeg", f"{code}.jpg", f"{code}.png"):
            path = root / name
            if path.is_file():
                return path
    if code != "eng":
        return paysage_still_path("en")
    return None


def paysage_still_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for code in PAYSAGE_CODES:
        path = paysage_still_path(code)
        if path is not None:
            out[code] = path
    return out


def media_item_for_language(language: str | None, *, order: int = 0) -> MediaItem | None:
    """One mid-band paysage still for the production language."""
    path = paysage_still_path(language)
    if path is None:
        return None
    try:
        item = probe_media(path)
    except Exception:
        item = MediaItem(
            path=str(path),
            media_type="image",
            duration=8.0,
            width=1080,
            height=900,
            order=order,
        )
    item.order = order
    item.fit_mode = FitMode.BAND.value
    item.animation_mode = AnimationMode.ZOOM_IN.value
    item.crop_x = 0.0
    item.crop_y = 0.0
    item.zoom = 1.0
    item.missing = False
    item.overlay = False
    return item


def default_paysage_items(language: str | None) -> list[MediaItem]:
    """Primary language still first, then the other available codes as follow-on scenes."""
    primary = normalize_language_id(language)
    primary_code = language_still_code(primary)
    ordered = [primary_code] + [c for c in PAYSAGE_CODES if c != primary_code]
    items: list[MediaItem] = []
    seen: set[str] = set()
    for code in ordered:
        if code in seen:
            continue
        seen.add(code)
        lid = {"eng": "en", "fra": "fr", "port": "pt"}.get(code, code)
        item = media_item_for_language(lid, order=len(items))
        if item is not None:
            items.append(item)
    return items
