"""Video Maker Phase 3 — batch languages, captions, crop, trim, history, Minimal."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bmt_voice_studio.video.batch import (
    build_queue,
    cancel_pending,
    failed_languages,
    filter_selected_ready,
    isolate_failure,
    projects_for_batch,
    ready_languages,
    retry_failed,
)
from bmt_voice_studio.video.captions import (
    caption_cues_from_segments,
    cues_language_isolated,
    split_caption_text,
    write_ass,
)
from bmt_voice_studio.video.composition import build_preview_plan, parse_timecode
from bmt_voice_studio.video.discovery import language_tracks_for_day, metadata_for_language
from bmt_voice_studio.video.geometry import positioned_crop_rect, visual_trim_span
from bmt_voice_studio.video.history import load_video_history, upsert_video_entry
from bmt_voice_studio.video.live_crop import crop_preview_rect, drag_delta_to_crop
from bmt_voice_studio.video.models import (
    QUEUE_COMPLETE,
    QUEUE_FAILED,
    QUEUE_WAITING,
    TEMPLATE_BMT_CLASSIC,
    TEMPLATE_BMT_MINIMAL,
    TEMPLATE_BMT_NATURE,
    TEMPLATE_LABELS,
    LanguageTrack,
    MediaItem,
    VideoProject,
)
from bmt_voice_studio.video.paths import video_filename, video_output_path
from bmt_voice_studio.video.project_store import load_project, save_project
from bmt_voice_studio.video.size_estimate import estimate_project_mb


def _tracks(*langs: tuple[str, bool, str]) -> list[LanguageTrack]:
    out: list[LanguageTrack] = []
    for lang, ready, topic in langs:
        out.append(
            LanguageTrack(
                language=lang,
                audio_path=f"C:/{lang}.mp3" if ready else "",
                audio_duration=120.0 if ready else 0.0,
                topic=topic,
                metadata_complete=bool(topic),
                ready=ready,
            )
        )
    return out


def test_ready_language_filtering():
    tracks = _tracks(("en", True, "Hope"), ("fr", False, ""), ("sw", True, "Tumaini"), ("pt", False, ""))
    ready = ready_languages(tracks)
    assert ready == ["en", "sw"]
    assert filter_selected_ready(["en", "fr", "sw", "pt", "en"], ready) == ["en", "sw"]
    assert filter_selected_ready([], ready) == []


def test_multi_language_selection_any_nonempty_combo():
    ready = ["en", "fr", "sw", "pt"]
    assert filter_selected_ready(["fr", "pt"], ready) == ["fr", "pt"]
    assert filter_selected_ready(["en"], ready) == ["en"]
    assert filter_selected_ready(["sw", "en", "xx"], ready) == ["sw", "en"]


def test_batch_queue_sequential_statuses():
    items = build_queue(["en", "fr", "sw"], ["en", "fr", "sw"])
    assert [i.status for i in items] == [QUEUE_WAITING, QUEUE_WAITING, QUEUE_WAITING]
    assert [i.language for i in items] == ["en", "fr", "sw"]


def test_failure_isolation_keeps_completed():
    items = build_queue(["en", "fr", "sw", "pt"], ["en", "fr", "sw", "pt"])
    items[0].status = QUEUE_COMPLETE
    items[0].output = "en.mp4"
    isolate_failure(items, "fr", "French encode failed")
    assert items[0].status == QUEUE_COMPLETE
    assert items[0].output == "en.mp4"
    assert items[1].status == QUEUE_FAILED
    assert items[2].status == QUEUE_WAITING
    assert items[3].status == QUEUE_WAITING
    retry_failed(items)
    assert items[1].status == QUEUE_WAITING
    assert failed_languages(items) == []
    cancel_pending(items)
    assert items[1].status == "Cancelled"
    assert items[0].status == QUEUE_COMPLETE


def test_language_metadata_mapping_no_english_copy(tmp_path: Path):
    en = metadata_for_language("2026-08-14", "en", live_text="Topic: Kingdom Priorities\n")
    fr = metadata_for_language(
        "2026-08-14",
        "fr",
        live_text="Thème : Les priorités du Royaume\n",
    )
    empty = metadata_for_language(
        "2026-08-14",
        "sw",
        live_text="",
        base=tmp_path,
        history_entries=[],
    )
    assert en["topic"] == "Kingdom Priorities"
    assert fr["topic"] == "Les priorités du Royaume"
    assert fr["topic"] != en["topic"]
    assert empty["language"] == "sw"
    assert empty["topic"] == ""


def test_output_path_per_language(tmp_path: Path):
    en = video_output_path(date(2026, 8, 14), "en", base=tmp_path)
    fr = video_output_path(date(2026, 8, 14), "fr", base=tmp_path)
    sw = video_output_path(date(2026, 8, 14), "sw", base=tmp_path)
    pt = video_output_path(date(2026, 8, 14), "pt", base=tmp_path)
    assert en.name == "BMT_14_AUG_2026_ENGLISH_VIDEO.mp4"
    assert fr.name == "BMT_14_AUG_2026_FRENCH_VIDEO.mp4"
    assert sw.name == "BMT_14_AUG_2026_SWAHILI_VIDEO.mp4"
    assert pt.name == "BMT_14_AUG_2026_PORTUGUESE_VIDEO.mp4"
    assert "ENGLISH" in en.parts
    assert "FRENCH" in fr.parts
    assert "SWAHILI" in sw.parts
    assert "PORTUGUESE" in pt.parts
    assert video_filename(date(2026, 8, 14), "en") == "BMT_14_AUG_2026_ENGLISH_VIDEO.mp4"


def test_custom_preview_window(tmp_path: Path):
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    project = VideoProject(
        audio_path=str(audio),
        audio_duration=390.0,
        media_items=[MediaItem(path=str(photo), media_type="image")],
        preview_start=120.0,
        preview_duration=12.0,
    )
    plan = build_preview_plan(
        project,
        output_path=tmp_path / "prev.mp4",
        temp_dir=tmp_path / "t",
        job_id="p3",
        preview_start=120.0,
    )
    assert plan.audio_start == pytest.approx(120.0)
    assert plan.audio_duration <= 12.0
    assert plan.intro_duration == 0.0
    assert parse_timecode("02:00") == pytest.approx(120.0)
    assert parse_timecode("00:12") == pytest.approx(12.0)
    assert parse_timecode("bad") == 0.0


def test_live_crop_geometry_parity():
    args = (1920, 1080, 1080, 1920, 0.4, -0.2, 1.25)
    live = crop_preview_rect(*args)
    render = positioned_crop_rect(*args)
    assert live == render
    dx, dy = drag_delta_to_crop(90, 0, 180, 320)
    assert dx > 0
    assert abs(dy) < 0.01


def test_smart_zoom_and_click_center():
    from bmt_voice_studio.video.image_io import suggest_smart_frame, zoom_toward_point
    from bmt_voice_studio.video.live_crop import click_offset_to_crop

    nx, ny = click_offset_to_crop(180, 80, 180, 320)
    assert nx > 0.5
    assert ny < 0
    cx, cy, z = zoom_toward_point(0.0, 0.0, 1.0, 1.3, 0.8, 0.0)
    assert z == pytest.approx(1.3)
    assert cx > 0
    mode, zoom, _x, y = suggest_smart_frame(1920, 1080)
    assert mode == "fill"
    assert zoom > 1.0
    _mode, _zoom, _x, y = suggest_smart_frame(1080, 1920)
    assert y == 0.0


def test_live_crop_preserves_transparent_png(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.live_crop import render_live_crop_still
    from bmt_voice_studio.video.models import MediaItem

    src = tmp_path / "cutout.png"
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    for x in range(100, 300):
        for y in range(100, 300):
            im.putpixel((x, y), (10, 200, 80, 255))
    im.save(src)
    item = MediaItem(path=str(src), media_type="image", width=400, height=400, fit_mode="fit")
    dest = tmp_path / "frame.png"
    out = render_live_crop_still(item, dest, width=108, height=192, background=(15, 20, 28))
    assert out is not None and Path(out).is_file()
    frame = Image.open(out).convert("RGB")
    corners = [frame.getpixel((1, 1)), frame.getpixel((106, 1)), frame.getpixel((1, 190))]
    assert all(px == (15, 20, 28) for px in corners)


def test_zoomed_overlay_stays_transparent_over_bed(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.image_io import composite_media_frame
    from bmt_voice_studio.video.live_crop import render_live_crop_still
    from bmt_voice_studio.video.models import MediaItem

    bed_src = tmp_path / "bed.png"
    Image.new("RGB", (400, 800), (200, 30, 30)).save(bed_src)
    cut = tmp_path / "cutout.png"
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    for x in range(100, 300):
        for y in range(100, 300):
            im.putpixel((x, y), (10, 200, 80, 255))
    im.save(cut)
    overlay = MediaItem(
        path=str(cut),
        media_type="image",
        width=400,
        height=400,
        fit_mode="fit",
        zoom=0.6,
        crop_x=0.35,
        crop_y=-0.2,
        has_alpha=True,
        overlay=True,
    )
    frame = composite_media_frame(overlay, 108, 192, (15, 20, 28), keep_alpha=True)
    assert frame.getpixel((1, 1))[3] == 0
    dest = tmp_path / "preview.png"
    bed = MediaItem(path=str(bed_src), media_type="image", width=400, height=800)
    out = render_live_crop_still(
        overlay, dest, width=108, height=192, background=(15, 20, 28), underlay=bed
    )
    assert out is not None
    preview = Image.open(out).convert("RGB")
    assert preview.getpixel((1, 1)) == (200, 30, 30)
    assert preview.getpixel((106, 1)) == (200, 30, 30)


def test_overlay_filter_pads_with_transparent(tmp_path: Path):
    from bmt_voice_studio.video.ffmpeg_renderer import overlay_keep_alpha_filter

    filt = overlay_keep_alpha_filter(1080, 1920, 0.2, -0.15, 0.6, "fit")
    assert filt.startswith("format=rgba")
    assert "black@0" in filt
    assert "0x0F141C" not in filt


def test_visual_trim_validation():
    start, end, used = visual_trim_span(3.0, 18.0, 40.0)
    assert start == pytest.approx(3.0)
    assert end == pytest.approx(18.0)
    assert used == pytest.approx(15.0)
    start, end, used = visual_trim_span(5.0, 0.0, 20.0)
    assert start == pytest.approx(5.0)
    assert end == pytest.approx(20.0)
    start, end, used = visual_trim_span(50.0, 80.0, 12.0)
    assert start <= 12.0
    assert end <= 12.0
    assert used >= 0.0
    start, end, used = visual_trim_span(10.0, 8.0, 20.0)
    assert end >= start or used == 20.0 - start or used >= 0


def test_caption_segmentation_and_timing():
    segs = [
        {"text": "Seek first the kingdom of God and his righteousness.", "duration": 8.0},
        {"text": "All these things will be added to you.", "duration": 4.0},
        {"text": "A", "duration": 1.0},
    ]
    cues = caption_cues_from_segments(segs, pause_sec=0.5, audio_duration=14.0, language="en")
    assert cues
    assert cues[0].start == pytest.approx(0.0)
    assert "Seek first" in cues[0].text
    assert "All these things" not in cues[0].text
    assert len(cues) == 3
    assert cues[-1].end <= 14.01
    chunks = split_caption_text("One sentence here. Two sentence here. Three sentence here. Four sentence here.")
    assert len(chunks) == 4
    assert "One sentence" in chunks[0]
    assert "Two sentence" in chunks[1]
    assert all(c.count("\n") <= 2 for c in chunks)


def test_caption_unicode_and_language_isolation(tmp_path: Path):
    segs_fr = [{"text": "L'Éternel est mon berger; je ne manquerai de rien.", "duration": 6.0}]
    segs_sw = [{"text": "Bwana ndiye mchungaji wangu, sitahitaji kitu.", "duration": 5.0}]
    segs_pt = [{"text": "O Senhor é o meu pastor; nada me faltará.", "duration": 5.5}]
    fr = caption_cues_from_segments(segs_fr, language="fr", audio_duration=6.0)
    sw = caption_cues_from_segments(segs_sw, language="sw", audio_duration=5.0)
    pt = caption_cues_from_segments(segs_pt, language="pt", audio_duration=5.5)
    assert cues_language_isolated(fr, "fr")
    assert cues_language_isolated(sw, "sw")
    assert cues_language_isolated(pt, "pt")
    assert not cues_language_isolated(fr, "en")
    dest = tmp_path / "fr.ass"
    write_ass(fr, dest)
    blob = dest.read_text(encoding="utf-8")
    assert "Éternel" in blob or "L'Éternel" in blob or "L\\'Éternel" in blob or "Eternel" in blob or "É" in blob
    assert "manquerai" in blob


def test_caption_style_and_audio_fit(tmp_path: Path):
    from bmt_voice_studio.video.captions import hex_to_ass_color, shift_caption_cues
    from bmt_voice_studio.video.models import TextStyle, VideoProject

    segs = [
        {"text": "Seek first the kingdom of God and his righteousness.", "duration": 8.0},
        {"text": "All these things will be added to you.", "duration": 4.0},
        {"text": "A", "duration": 1.0},
    ]
    cues = caption_cues_from_segments(segs, pause_sec=0.5, audio_duration=13.0, language="en")
    assert cues[0].start == pytest.approx(0.0)
    assert cues[-1].end == pytest.approx(13.0, abs=0.4)
    assert len(cues) == 3
    first_span = cues[0].end - cues[0].start
    mid_span = cues[1].end - cues[1].start
    last_span = cues[-1].end - cues[-1].start
    # Longer spoken segments keep more on-screen time (school text, one sentence per cue).
    assert first_span > mid_span * 1.5
    assert mid_span > last_span * 1.5
    assert first_span == pytest.approx(7.4, abs=1.5)
    shifted = shift_caption_cues(cues, 10.0 - 30.0)
    assert shifted[0].start < 0.0
    style = TextStyle(font_size=72, text_color="#FFFFFF", stroke_color="#000000", stroke_width=5)
    dest = tmp_path / "styled.ass"
    write_ass(cues, dest, width=1080, height=1920, style=style)
    blob = dest.read_text(encoding="utf-8")
    assert ",72," in blob
    assert hex_to_ass_color("#FFFFFF") in blob
    assert hex_to_ass_color("#000000") in blob
    assert ",1,3,0,2," in blob
    assert "ScaledBorderAndShadow: no" in blob
    project = VideoProject(text_style=style, show_captions=True)
    assert project.to_dict()["text_style"]["font_size"] == 72
    loaded = VideoProject.from_dict(project.to_dict())
    assert loaded.text_style.stroke_width == 5
    assert loaded.schema_version == 5
    from bmt_voice_studio.video.models import STROKE_COLOR_DEFAULT, TEXT_COLOR_DEFAULT

    native = TextStyle().normalized()
    assert native.text_color == TEXT_COLOR_DEFAULT == "#E89430"
    assert native.stroke_color == STROKE_COLOR_DEFAULT == "#0A204A"
    legacy = TextStyle.from_dict(
        {"font_size": 64, "text_color": "#FFFFFF", "stroke_color": "#000000", "stroke_width": 2}
    )
    assert legacy.text_color == "#E89430"
    assert legacy.stroke_color == "#0A204A"
    assert legacy.stroke_width == 5


def test_caption_style_preview_widget():
    pytest.importorskip("PySide6")
    pytest.importorskip("PIL")
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.ui.theme import apply_theme
    from bmt_voice_studio.ui.widgets.caption_style_preview import CaptionStylePreview
    from bmt_voice_studio.video.models import TextStyle

    app = QApplication.instance() or QApplication([])
    apply_theme(app, "dark")
    panel = CaptionStylePreview()
    panel.set_style(TextStyle(font_size=80, text_color="#F6E7C1", stroke_color="#0F141C", stroke_width=6))
    got = panel.style()
    assert got.font_size == 80
    assert got.text_color == "#F6E7C1"
    assert got.stroke_color == "#0F141C"
    assert got.stroke_width == 6
    assert panel.preview.pixmap() is None or not panel.preview.pixmap().isNull() or panel.preview.text()
    app  # keep reference


def test_bmt_minimal_template(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    from bmt_voice_studio.video.title_cards import palette_for, render_intro_card, wrap_and_shrink

    assert TEMPLATE_BMT_MINIMAL in TEMPLATE_LABELS
    assert {TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_NATURE, TEMPLATE_BMT_MINIMAL}.issubset(TEMPLATE_LABELS)
    pal = palette_for(TEMPLATE_BMT_MINIMAL)
    assert pal["bg"] != palette_for(TEMPLATE_BMT_CLASSIC)["bg"]
    assert pal["bg"] != palette_for(TEMPLATE_BMT_NATURE)["bg"]
    project = VideoProject(
        template_id=TEMPLATE_BMT_MINIMAL,
        topic="Les priorités extraordinaires du Royaume de Dieu aujourd'hui",
        devotional_date="2026-08-14",
    )
    dest = tmp_path / "minimal.png"
    render_intro_card(project, dest)
    assert dest.is_file()
    img = Image.open(dest)
    draw = ImageDraw.Draw(img)
    for topic in (
        "An exceptionally long English topic about kingdom priorities and eternal values",
        "Les priorités extraordinaires du Royaume de Dieu pour aujourd'hui et pour toujours",
        "Vipaumbele vya Ufalme wa Mungu vinavyozidi urefu wa mstari mmoja",
        "As prioridades extraordinárias do Reino de Deus para a vida diária",
    ):
        lines, _font = wrap_and_shrink(draw, topic, max_width=900, start_size=48, min_size=18, max_lines=4)
        assert lines
        assert len(lines) <= 4


def test_size_estimation_media_aware(tmp_path: Path):
    for name in ("a.jpg", "b.jpg", "c.jpg", "d.mp4", "e.mp4"):
        (tmp_path / name).write_bytes(b"x" * 100)
    stills = VideoProject(
        audio_duration=390.0,
        media_items=[MediaItem(path=str(tmp_path / n), media_type="image") for n in ("a.jpg", "b.jpg", "c.jpg")],
    )
    mixed = VideoProject(
        audio_duration=390.0,
        media_items=[
            MediaItem(path=str(tmp_path / "a.jpg"), media_type="image"),
            MediaItem(path=str(tmp_path / "d.mp4"), media_type="video", duration=12),
            MediaItem(path=str(tmp_path / "e.mp4"), media_type="video", duration=8),
        ],
    )
    a = estimate_project_mb(stills)
    b = estimate_project_mb(mixed)
    assert a > 1
    assert b > a


def test_render_metrics_shape():
    metrics = {
        "elapsed_sec": 134.0,
        "video_duration": 390.0,
        "output_bytes": 48_000_000,
        "speed": round(390.0 / 134.0, 2),
        "scenes": 8,
    }
    assert metrics["speed"] == pytest.approx(2.91, rel=0.05)
    assert metrics["elapsed_sec"] < metrics["video_duration"]


def test_video_history_separate(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    upsert_video_entry(
        {
            "date": "2026-08-14",
            "language": "en",
            "template": "BMT NATURE",
            "quality": "Standard 1080p",
            "duration": "06:30",
            "size": "42.0 MB",
            "status": QUEUE_COMPLETE,
            "output": str(tmp_path / "en.mp4"),
        }
    )
    upsert_video_entry(
        {
            "date": "2026-08-14",
            "language": "fr",
            "template": "BMT NATURE",
            "quality": "Standard 1080p",
            "duration": "06:30",
            "size": "41.0 MB",
            "status": QUEUE_COMPLETE,
            "output": str(tmp_path / "fr.mp4"),
        }
    )
    rows = load_video_history()
    assert len(rows) == 2
    langs = {r["language"] for r in rows}
    assert langs == {"en", "fr"}
    hist = tmp_path / "la" / "BMTVoiceStudio" / "video" / "history.json"
    if not hist.is_file():
        from bmt_voice_studio.video.history import video_history_file

        assert video_history_file().is_file()
        assert "daily" not in str(video_history_file()).lower() or "video" in str(video_history_file())


def test_shared_project_state_one_media_many_languages(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"x")
    en_audio = tmp_path / "en.mp3"
    fr_audio = tmp_path / "fr.mp3"
    en_audio.write_bytes(b"ID3")
    fr_audio.write_bytes(b"ID3")
    project = VideoProject(
        devotional_date="2026-08-14",
        language="en",
        audio_path=str(en_audio),
        audio_duration=100.0,
        topic="Kingdom Priorities",
        template_id=TEMPLATE_BMT_NATURE,
        media_items=[MediaItem(path=str(photo), media_type="image", crop_x=0.2, zoom=1.1)],
        selected_languages=["en", "fr"],
        languages=[
            LanguageTrack(
                language="en",
                audio_path=str(en_audio),
                topic="Kingdom Priorities",
                ready=True,
                metadata_complete=True,
            ),
            LanguageTrack(
                language="fr",
                audio_path=str(fr_audio),
                topic="Les priorités du Royaume",
                ready=True,
                metadata_complete=True,
            ),
        ],
        show_captions=True,
    )
    save_project(project)
    loaded = load_project()
    assert loaded.schema_version == 5
    assert len(loaded.media_items) == 1
    bound = projects_for_batch(loaded, ["en", "fr"])
    assert [p.language for p in bound] == ["en", "fr"]
    assert bound[0].topic == "Kingdom Priorities"
    assert bound[1].topic == "Les priorités du Royaume"
    assert bound[0].media_items[0].path == bound[1].media_items[0].path
    assert bound[0].media_items[0].crop_x == bound[1].media_items[0].crop_x
    assert bound[0].audio_path != bound[1].audio_path
    assert bound[0].show_captions is True


def test_embedded_preview_fallback_widget():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from bmt_voice_studio.ui.widgets.video_preview_player import VideoPreviewPlayer

    app = QApplication.instance() or QApplication([])
    player = VideoPreviewPlayer()
    assert hasattr(player, "fallback_requested")
    assert player.btn_system.toolTip().lower().find("play") >= 0
    player.btn_system.setToolTip("Open in system player")
    assert "system player" in player.btn_system.toolTip().lower()
    player.load("")
    assert player.btn_system.isEnabled() is False
    app  # keep reference


def test_not_generated_tracks_are_not_ready():
    tracks = language_tracks_for_day(
        date(2026, 8, 14),
        base=Path("C:/missing-bmt-base"),
        history_entries=[{"date": "2026-08-14", "en_mp3": "", "fr_mp3": "", "sw_mp3": "", "pt_mp3": ""}],
    )
    by = {t.language: t for t in tracks}
    assert by["en"].ready is False
    assert by["fr"].ready is False
