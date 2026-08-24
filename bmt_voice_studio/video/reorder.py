"""Reorder helpers for the media strip (used by UI and tests)."""

from __future__ import annotations

from bmt_voice_studio.video.models import MediaItem


def reorder_items(items: list[MediaItem], source: int, dest: int) -> list[MediaItem]:
    """Move item at source index to dest index. Clamps; preserves relative order of others."""
    if not items:
        return []
    n = len(items)
    src = max(0, min(int(source), n - 1))
    dst = max(0, min(int(dest), n - 1))
    if src == dst:
        out = list(items)
    else:
        out = list(items)
        item = out.pop(src)
        out.insert(dst, item)
    for i, item in enumerate(out):
        item.order = i
    return out
