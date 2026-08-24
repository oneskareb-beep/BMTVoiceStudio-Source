"""Overlay priority: verse vs lower-third vs outro exclusivity."""

from __future__ import annotations

import pytest

from bmt_voice_studio.video.captions import CaptionCue, clip_caption_cues
from bmt_voice_studio.video.composition import (
    overlay_windows,
    ranges_overlap,
    window_is_active,
)


def test_verse_hides_lower_third_and_closes_before_outro():
    windows = overlay_windows(10.0, 50.0, 10.0, has_verse=True)
    assert window_is_active(windows["verse_card"])
    assert window_is_active(windows["lower_third"])
    assert window_is_active(windows["outro"])
    assert not ranges_overlap(windows["verse_card"], windows["lower_third"])
    assert not ranges_overlap(windows["verse_card"], windows["outro"])
    assert not ranges_overlap(windows["lower_third"], windows["outro"])
    assert not ranges_overlap(windows["compact"], windows["verse_card"])
    assert not ranges_overlap(windows["compact"], windows["outro"])
    assert windows["verse_card"][0] >= windows["intro"][1] - 0.01
    assert windows["lower_third"][0] >= windows["verse_card"][1] - 0.01
    assert windows["verse_card"][1] <= windows["outro"][0]
    assert windows["lower_third"][1] <= windows["outro"][0]


def test_short_12s_sequence_is_verse_then_lower_then_outro():
    windows = overlay_windows(10.0, 12.0, 10.0, has_verse=True)
    assert window_is_active(windows["intro"])
    assert window_is_active(windows["verse_card"])
    assert window_is_active(windows["lower_third"])
    assert window_is_active(windows["outro"])
    assert windows["verse_card"][1] <= windows["lower_third"][0] + 0.001
    assert windows["lower_third"][1] <= windows["outro"][0]
    assert not ranges_overlap(windows["verse_card"], windows["lower_third"])
    assert not ranges_overlap(windows["verse_card"], windows["outro"])
    assert not ranges_overlap(windows["lower_third"], windows["outro"])
    assert windows["outro"][0] == pytest.approx(22.0)


def window_duration_safe(window: tuple[float, float]) -> float:
    return max(0.0, window[1] - window[0])


def test_no_verse_allows_lower_third_after_intro():
    windows = overlay_windows(10.0, 40.0, 10.0, has_verse=False)
    assert not window_is_active(windows["verse_card"])
    assert window_is_active(windows["lower_third"])
    assert windows["lower_third"][0] >= windows["intro"][1] - 0.01
    assert windows["lower_third"][1] <= windows["outro"][0]


def test_clip_caption_cues_leaves_intro_and_outro_clear():
    cues = [
        CaptionCue(start=0.0, end=6.0, text="during intro", language="en"),
        CaptionCue(start=8.0, end=20.0, text="body", language="en"),
        CaptionCue(start=47.0, end=50.0, text="during outro", language="en"),
    ]
    clipped = clip_caption_cues(cues, hide_ranges=[(0.0, 5.5), (47.5, 50.0)])
    assert all(c.start >= 5.5 - 0.001 for c in clipped)
    assert all(c.end <= 47.5 + 0.001 for c in clipped)
    assert any(c.text == "body" for c in clipped)


def test_clip_caption_cues_yields_to_verse_and_lower_third():
    cues = [
        CaptionCue(start=10.0, end=18.0, text="verse window", language="en"),
        CaptionCue(start=19.0, end=28.0, text="lower window", language="en"),
        CaptionCue(start=30.0, end=40.0, text="clear body", language="en"),
    ]
    clipped = clip_caption_cues(cues, hide_ranges=[(10.0, 18.5), (19.0, 29.0)])
    assert all(c.text == "clear body" for c in clipped)
    assert clipped[0].start >= 29.0 - 0.05
