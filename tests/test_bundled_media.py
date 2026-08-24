"""Bundled default 16:9 video clips per template."""

from __future__ import annotations

import pytest

from bmt_voice_studio.video.bundled_media import (
    BUNDLED_CLIP_COUNT,
    bundled_clip_path,
    bundled_clip_paths,
    default_media_items,
    media_uses_template_defaults,
    merge_saved_layout,
    resolve_clip_path,
)
from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_NATURE, TEMPLATE_BMT_MINIMAL


@pytest.mark.parametrize("template_id", [TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_NATURE, TEMPLATE_BMT_MINIMAL])
def test_bundled_clips_exist_per_template(template_id: str):
    paths = bundled_clip_paths(template_id)
    assert len(paths) == BUNDLED_CLIP_COUNT
    for path in paths:
        assert path.is_file()
        assert path.suffix.lower() == ".mp4"


def test_default_media_items_are_16x9_videos():
    items = default_media_items(TEMPLATE_BMT_CLASSIC)
    assert len(items) == BUNDLED_CLIP_COUNT
    for item in items:
        assert item.media_type == "video"
        assert item.width >= 1280
        assert item.height >= 720
        assert item.width >= item.height
        assert not item.missing


def test_media_uses_template_defaults():
    items = default_media_items(TEMPLATE_BMT_CLASSIC)
    assert media_uses_template_defaults(items, TEMPLATE_BMT_CLASSIC)
    assert not media_uses_template_defaults(items, TEMPLATE_BMT_NATURE)


def test_merge_saved_layout_keeps_crop():
    saved = default_media_items(TEMPLATE_BMT_CLASSIC)
    saved[0].crop_x = 0.25
    saved[0].zoom = 0.75
    merged = merge_saved_layout(saved, TEMPLATE_BMT_CLASSIC)
    assert len(merged) == BUNDLED_CLIP_COUNT
    assert merged[0].crop_x == pytest.approx(0.25)
    assert merged[0].zoom == pytest.approx(0.75)
    assert media_uses_template_defaults(merged, TEMPLATE_BMT_CLASSIC)


def test_resolve_clip_path_matches_bundled():
    bundled = bundled_clip_path(TEMPLATE_BMT_CLASSIC, 1)
    assert bundled is not None
    assert resolve_clip_path(TEMPLATE_BMT_CLASSIC, 1) == bundled
