"""Percent helpers for the top-of-window generation bar."""

from __future__ import annotations

# After the last TTS segment, Daily BMT still joins, exports, and finalizes.
# Keep those steps visible on the bar instead of jumping to 100% at "Exporting…".
LANGUAGE_POST_STEPS = 4  # join → export → finalize → complete

_LANG_ALIASES = {
    "en": ("en", "english"),
    "fr": ("fr", "french"),
    "sw": ("sw", "swahili"),
    "pt": ("pt", "portuguese"),
}


def clamp_percent(value: float) -> int:
    return max(0, min(100, int(round(value))))


def language_work_total(segment_count: int) -> int:
    """Segments + reserved post-TTS steps (join/export/finalize/complete)."""
    return max(1, int(segment_count)) + LANGUAGE_POST_STEPS


def language_job_percent(
    language: str,
    current: int,
    total: int,
    selected: list[str],
    order: tuple[str, ...] = ("en", "fr", "sw", "pt"),
) -> int:
    """Map Daily BMT language/segment progress onto a 0–100 bar."""
    langs = [lid for lid in order if lid in {x.strip().lower() for x in selected}]
    n = max(1, len(langs) or 1)
    inner = min(1.0, max(0.0, float(current) / float(max(1, total))))
    key = (language or "").strip().lower()
    if key == "overall":
        return clamp_percent(100 * inner)
    lid = ""
    for cand, aliases in _LANG_ALIASES.items():
        if key in aliases or key.startswith(cand):
            lid = cand
            break
    if lid not in langs:
        return clamp_percent(100 * inner)
    idx = langs.index(lid)
    return clamp_percent(100.0 * (idx + inner) / n)


def batch_job_percent(index: int, count: int, item_pct: int) -> int:
    """Map Video Maker language-queue progress onto a 0–100 bar."""
    n = max(1, int(count))
    i = max(0, min(int(index), n - 1))
    piece = max(0, min(100, int(item_pct)))
    return clamp_percent((i * 100 + piece) / n)
