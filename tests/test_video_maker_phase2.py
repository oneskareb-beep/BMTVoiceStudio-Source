"""Video Maker Phase 2 — discovery, crop, preview, templates, autosave."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bmt_voice_studio.video.composition import build_preview_plan, overlay_windows
from bmt_voice_studio.video.discovery import (
    extract_metadata,
    find_generated_audio,
    metadata_for_language,
    todays_audio_status,
)
from bmt_voice_studio.video.geometry import (
    SAFE_BOTTOM,
    SAFE_SIDE,
    SAFE_TOP,
    ZOOM_MIN,
    clamp_crop,
    clamp_trim,
    clamp_zoom,
    contain_relative_zoom,
    ffmpeg_positioned_contain_filter,
    ffmpeg_positioned_cover_filter,
    positioned_crop_rect,
    safe_rect,
)
from bmt_voice_studio.video.models import (
    PROFILE_WHATSAPP,
    TEMPLATE_BMT_CLASSIC,
    TEMPLATE_BMT_NATURE,
    MediaItem,
    VideoProject,
    output_profile_for,
)
from bmt_voice_studio.video.paths import estimate_output_mb, preview_output_path, video_filename
from bmt_voice_studio.video.project_store import load_project, load_project_for, save_project
from bmt_voice_studio.video.reorder import reorder_items
from bmt_voice_studio.video.thumbs import extract_thumbnail, thumbnail_path_for, thumbs_dir
from bmt_voice_studio.video.title_cards import wrap_and_shrink, wrap_text


def test_daily_audio_discovery_uses_history(tmp_path: Path):
    audio = tmp_path / "BMT_14_AUG_2026_ENGLISH_FINAL.mp3"
    audio.write_bytes(b"ID3")
    history = [
        {
            "date": "2026-08-14",
            "project_id": "BMT_2026_08_14",
            "en_mp3": str(audio),
            "en_duration": 461.2,
            "fr_mp3": "",
            "sw_mp3": "",
            "pt_mp3": "",
        }
    ]
    found = find_generated_audio(date(2026, 8, 14), "en", base=tmp_path, history_entries=history)
    assert found == audio
    rows = todays_audio_status(date(2026, 8, 14), base=tmp_path, history_entries=history)
    by_lang = {r["language"]: r for r in rows}
    assert by_lang["en"]["ready"] is True
    assert by_lang["en"]["status"] == "Ready"
    assert by_lang["en"]["name"] == audio.name
    assert by_lang["fr"]["ready"] is False
    assert by_lang["fr"]["status"] == "Not generated"
    assert by_lang["sw"]["ready"] is False
    assert by_lang["pt"]["ready"] is False


def test_metadata_binding_prefers_labeled_fields():
    text = (
        "BELIEVERS MANNA TODAY\n"
        "Topic: Kingdom Priorities\n"
        "Week Focus: Living With Eternal Values\n"
        "Month Theme: Purposeful Living and Eternal Perspective\n"
        "{Memory Verse: Matthew 6:33 Seek first the kingdom}\n"
        "Devotional Insight\n"
    )
    meta = extract_metadata(text)
    assert meta["topic"] == "Kingdom Priorities"
    assert meta["week_focus"] == "Living With Eternal Values"
    assert meta["month_theme"] == "Purposeful Living and Eternal Perspective"
    assert "Matthew" in meta["memory_verse"]
    bound = metadata_for_language("2026-08-14", "en", live_text=text)
    assert bound["date"] == "2026-08-14"
    assert bound["language"] == "en"
    assert bound["topic"] == "Kingdom Priorities"


def test_phase1_project_backwards_compatible():
    data = {
        "schema_version": 1,
        "topic": "Hope",
        "week_focus": "Trust",
        "month_theme": "Harvest",
        "language": "en",
        "devotional_date": "2026-08-14",
        "media_items": [{"path": "C:\\missing.jpg", "media_type": "image", "order": 0}],
    }
    project = VideoProject.from_dict(data)
    assert project.topic == "Hope"
    assert project.template_id == TEMPLATE_BMT_CLASSIC
    item = project.media_items[0]
    assert item.crop_x == 0.0
    assert item.crop_y == 0.0
    assert item.zoom == 1.0
    assert item.trim_start == 0.0
    assert item.trim_end == 0.0
    assert item.fit_mode == "fill"
    assert item.missing is True


def test_drag_drop_model_reorder():
    items = [
        MediaItem(path="a.jpg", order=0),
        MediaItem(path="b.jpg", order=1),
        MediaItem(path="c.jpg", order=2),
        MediaItem(path="d.jpg", order=3),
    ]
    moved = reorder_items(items, 0, 2)
    assert [m.path for m in moved] == ["b.jpg", "c.jpg", "a.jpg", "d.jpg"]
    assert [m.order for m in moved] == [0, 1, 2, 3]
    same = reorder_items(moved, 1, 1)
    assert [m.path for m in same] == ["b.jpg", "c.jpg", "a.jpg", "d.jpg"]


def test_normalized_crop_coordinates():
    x, y, w, h = positioned_crop_rect(1920, 1080, 1080, 1920, 0.0, 0.0, 1.0)
    assert w > 0 and h > 0
    assert x >= 0 and y >= 0
    xl, _, wl, _ = positioned_crop_rect(1920, 1080, 1080, 1920, -1.0, 0.0, 1.0)
    xr, _, wr, _ = positioned_crop_rect(1920, 1080, 1080, 1920, 1.0, 0.0, 1.0)
    assert xl == 0
    assert xr + wr == 1920
    assert wl == wr


def test_crop_clamping_never_negative():
    assert clamp_crop(-4, 9) == (-1.0, 1.0)
    assert clamp_crop("nope", None) == (0.0, 0.0)
    x, y, w, h = positioned_crop_rect(800, 600, 1080, 1920, -3, 5, 9)
    assert w >= 1 and h >= 1
    assert x >= 0 and y >= 0
    assert x + w <= 800
    assert y + h <= 600
    filt = ffmpeg_positioned_cover_filter(1080, 1920, -2, 4, 3)
    assert "crop=1080:1920" in filt
    assert ":-" not in filt.split("crop=")[-1].split(":")[0]


def test_zoom_bounds():
    assert ZOOM_MIN == pytest.approx(0.15)
    assert clamp_zoom(0.10) == pytest.approx(0.15)
    assert clamp_zoom(0.32) == pytest.approx(0.32)
    assert clamp_zoom(1.2) == pytest.approx(1.2)
    assert clamp_zoom(3.0) == 2.5
    assert clamp_zoom("bad") == 1.0
    out = ffmpeg_positioned_cover_filter(1080, 1920, 0, 0, 0.32)
    assert "pad=1080:1920" in out
    assert "force_original_aspect_ratio=increase,crop=1080:1920,scale=" not in out.replace(" ", "")
    fit = ffmpeg_positioned_contain_filter(1080, 1920, 0.2, -0.1, 0.5)
    assert "pad=1080:1920" in fit


def test_landscape_fill_zoom_out_shows_full_image(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.image_io import composite_media_frame
    from bmt_voice_studio.video.models import FitMode, MediaItem

    photo = tmp_path / "wide.png"
    im = Image.new("RGB", (1920, 1080), (12, 24, 40))
    for y in range(1080):
        im.putpixel((0, y), (255, 0, 0))
        im.putpixel((1919, y), (0, 255, 0))
    im.save(photo)
    z = contain_relative_zoom(1920, 1080)
    assert z == pytest.approx(0.3164, abs=0.01)
    item = MediaItem(path=str(photo), media_type="image", zoom=z, fit_mode=FitMode.FILL.value)
    frame = composite_media_frame(item, 1080, 1920)
    mid_y = 1920 // 2
    left = frame.getpixel((0, mid_y))[:3]
    right = frame.getpixel((1079, mid_y))[:3]
    pad = frame.getpixel((0, 0))[:3]
    assert pad == (15, 20, 28)
    assert left != pad and right != pad
    assert left[0] > left[1] and left[0] > left[2]
    assert right[1] > right[0] and right[1] > right[2]
    x, y, w, h = positioned_crop_rect(1920, 1080, 1080, 1920, 0.0, 0.0, z)
    assert w == 1920 and h == 1080


def test_trim_validation():
    assert clamp_trim(-2, 9, 8) == (0.0, 8.0)
    start, end = clamp_trim(4, 4, 10)
    assert start == 4.0
    assert end == 0.0
    start, end = clamp_trim(1.5, 3.0, 10)
    assert start == 1.5
    assert end == 3.0


def test_preview_composition_is_short(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    audio = tmp_path / "master.wav"
    audio.write_bytes(b"RIFF")
    photo = tmp_path / "p.png"
    Image.new("RGB", (900, 1600), (10, 20, 30)).save(photo)
    project = VideoProject(
        devotional_date="2026-08-14",
        language="en",
        audio_path=str(audio),
        audio_duration=390.0,
        topic="Kingdom Priorities",
        media_items=[MediaItem(path=str(photo), media_type="image", order=0)],
    )
    plan = build_preview_plan(project, output_path=tmp_path / "prev.mp4", temp_dir=tmp_path / "t", job_id="p2")
    assert plan.width == 540
    assert plan.height == 960
    assert plan.audio_duration <= 12.0
    assert plan.audio_duration >= 8.0
    windows = overlay_windows(plan.intro_duration, plan.audio_duration, plan.outro_duration)
    assert windows["lower_third"][1] <= plan.intro_duration + plan.audio_duration + plan.outro_duration + 0.01


def test_preview_output_path(tmp_path: Path):
    path = preview_output_path(date(2026, 8, 14), "en", base=tmp_path)
    assert path.name == "BMT_14_AUG_2026_ENGLISH_PREVIEW.mp4"
    assert "ENGLISH" in path.parts


def test_bmt_nature_template(tmp_path: Path):
    pytest.importorskip("PIL")
    from bmt_voice_studio.video.title_cards import palette_for, render_intro_card

    project = VideoProject(template_id=TEMPLATE_BMT_NATURE, topic="Peace", devotional_date="2026-08-14")
    pal = palette_for(project)
    assert pal["bg"] != palette_for(TEMPLATE_BMT_CLASSIC)["bg"]
    dest = tmp_path / "nature_intro.png"
    render_intro_card(project, dest)
    assert dest.is_file()
    assert dest.stat().st_size > 1000


def test_safe_zone_text_wrapping():
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    from bmt_voice_studio.video.geometry import CANVAS_HEIGHT, CANVAS_WIDTH

    sx, sy, sw, sh = safe_rect()
    assert sy >= SAFE_TOP
    assert sx >= SAFE_SIDE
    assert (CANVAS_HEIGHT - (sy + sh)) >= SAFE_BOTTOM
    img = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT))
    draw = ImageDraw.Draw(img)
    samples = [
        "Kingdom Priorities and the Call to Seek First What Lasts Forever",
        "Les priorités du Royaume et la vie tournée vers l'éternité aujourd'hui",
        "Vipaumbele vya Ufalme na kuishi kwa maadili ya milele katika Kristo",
        "Prioridades do Reino e o chamado para viver com valores eternos",
    ]
    for text in samples:
        lines, font = wrap_and_shrink(draw, text, sw, start_size=48, min_size=16, max_lines=4)
        assert lines
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            assert bbox[2] - bbox[0] <= sw + 2
        wrapped = wrap_text(draw, text, font, sw, max_lines=4)
        assert wrapped


def test_whatsapp_output_profile():
    profile = output_profile_for("whatsapp")
    assert profile.id == PROFILE_WHATSAPP
    assert profile.width == 1080
    assert profile.height == 1920
    assert profile.video_crf >= 24
    assert profile.audio_bitrate_k >= 96
    assert video_filename(date(2026, 8, 14), "en", profile_id="whatsapp") == (
        "BMT_14_AUG_2026_ENGLISH_WHATSAPP.mp4"
    )
    std = estimate_output_mb(461, "standard_1080p")
    wa = estimate_output_mb(461, "whatsapp")
    assert wa < std
    assert wa > 1


def test_project_autosave_and_restore(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.video import project_store as store

    photo = tmp_path / "keep.jpg"
    photo.write_bytes(b"x")
    project = VideoProject(
        devotional_date="2026-08-14",
        language="en",
        topic="Kingdom Priorities",
        audio_path=str(tmp_path / "a.mp3"),
        template_id=TEMPLATE_BMT_NATURE,
        media_items=[MediaItem(path=str(photo), media_type="image", crop_x=0.25, zoom=1.2)],
    )
    save_project(project)
    loaded = load_project()
    assert loaded.topic == "Kingdom Priorities"
    assert loaded.template_id == TEMPLATE_BMT_NATURE
    assert loaded.media_items[0].crop_x == pytest.approx(0.25)
    restored = load_project_for("2026-08-14", "en")
    assert restored is not None
    assert restored.topic == "Kingdom Priorities"
    assert load_project_for("2026-08-14", "fr") is None


def test_thumbnail_caching(tmp_path: Path, monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    img = tmp_path / "photo.png"
    Image.new("RGB", (800, 600), (20, 80, 40)).save(img)
    first = extract_thumbnail(str(img), media_type="image")
    assert first is not None and first.is_file()
    cached = thumbnail_path_for(str(img))
    assert cached == first
    mtime = first.stat().st_mtime
    second = extract_thumbnail(str(img), media_type="image")
    assert second == first
    assert second.stat().st_mtime == mtime
    assert thumbs_dir().exists()


def test_missing_media_replacement(tmp_path: Path):
    gone = tmp_path / "deleted.jpg"
    present = tmp_path / "present.jpg"
    present.write_bytes(b"jpeg")
    project = VideoProject.from_dict(
        {
            "media_items": [
                {"path": str(gone), "media_type": "image", "order": 0, "crop_x": 0.4, "zoom": 1.1}
            ]
        }
    )
    assert project.media_items[0].missing is True
    replacement = MediaItem.from_dict(
        {"path": str(present), "media_type": "image", "crop_x": 0.4, "zoom": 1.1}
    )
    project.media_items[0] = replacement
    assert project.media_items[0].missing is False
    assert project.media_items[0].crop_x == pytest.approx(0.4)
    assert project.available_media()
    raw = json.dumps(project.to_dict())
    assert "deleted.jpg" not in raw
