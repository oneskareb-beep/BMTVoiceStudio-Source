"""Video Maker Phase 1 — models, probe, composition, paths, FFmpeg commands."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bmt_voice_studio.video.composition import (
    build_composition_plan,
    choose_scene_count,
    photo_scene_duration,
    xfade_offsets,
    xfade_output_duration,
)
from bmt_voice_studio.video.errors import MediaValidationError, MissingMediaError, VideoMakerError
from bmt_voice_studio.video.ffmpeg_renderer import (
    build_final_command,
    build_image_scene_command,
    build_video_scene_command,
    build_xfade_filter_script,
    ken_burns_filter,
)
from bmt_voice_studio.video.geometry import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    center_crop_rect,
    landscape_center_crop,
    portrait_center_crop,
)
from bmt_voice_studio.video.media_probe import (
    parse_ffmpeg_duration,
    parse_ffmpeg_video_size,
    probe_audio_duration,
    probe_image,
    probe_media,
    probe_video,
)
from bmt_voice_studio.video.models import MediaItem, MediaType, VideoProject
from bmt_voice_studio.video.paths import video_filename, video_output_path, video_project_dir
from bmt_voice_studio.video.project_store import load_project, save_project


def test_video_model_serialization(tmp_path: Path):
    project = VideoProject(
        devotional_date="2026-08-14",
        language="en",
        audio_path=str(tmp_path / "a.mp3"),
        audio_duration=123.4,
        topic="Faith That Works",
        week_focus="Obedience",
        month_theme="Harvest",
        logo_path=str(tmp_path / "logo.png"),
        media_items=[
            MediaItem(path=str(tmp_path / "p.jpg"), media_type="image", order=0),
            MediaItem(path=str(tmp_path / "v.mp4"), media_type="video", order=1),
        ],
    )
    data = project.to_dict()
    blob = json.dumps(data)
    assert "video bytes" not in blob.lower()
    restored = VideoProject.from_dict(json.loads(blob))
    assert restored.topic == "Faith That Works"
    assert restored.week_focus == "Obedience"
    assert restored.month_theme == "Harvest"
    assert len(restored.media_items) == 2
    assert restored.media_items[1].media_type == "video"
    assert restored.media_items[0].missing is True


def test_metadata_persistence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    from bmt_voice_studio.video import project_store as store

    target = tmp_path / "autosave.json"
    project = VideoProject(topic="Peace", language="fr", audio_path=r"D:\media\devotional.mp3")
    save_project(project, target)
    raw = target.read_text(encoding="utf-8")
    assert "Peace" in raw
    assert "fr" in raw
    loaded = load_project(target)
    assert loaded.topic == "Peace"
    assert loaded.language == "fr"
    assert "\\x00" not in raw


def test_missing_media_recovery(tmp_path: Path):
    gone = tmp_path / "deleted.jpg"
    project = VideoProject.from_dict(
        {
            "media_items": [{"path": str(gone), "media_type": "image", "order": 0}],
            "audio_path": str(tmp_path / "missing.mp3"),
        }
    )
    assert project.media_items[0].missing is True
    assert project.missing_media()
    assert project.available_media() == []


def test_parse_ffmpeg_identity():
    blob = (
        "Duration: 00:01:04.20, start: 0.000000, bitrate: 128 kb/s\n"
        "Stream #0:0: Video: h264 (High), yuv420p, 1920x1080, 30 fps\n"
        "Stream #0:1: Audio: aac, 48000 Hz, stereo\n"
    )
    assert parse_ffmpeg_duration(blob) == pytest.approx(64.2)
    assert parse_ffmpeg_video_size(blob) == (1920, 1080)


def test_image_probing(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    portrait = tmp_path / "portrait.png"
    Image.new("RGB", (800, 1400), (20, 40, 80)).save(portrait)
    info = probe_image(portrait)
    assert info["width"] == 800
    assert info["height"] == 1400
    assert info["media_type"] == "image"
    item = probe_media(portrait)
    assert item.media_type == MediaType.IMAGE.value


def test_transparent_png_is_accepted(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    from bmt_voice_studio.video.image_io import flatten_rgba, image_has_transparency, open_rgba, prepare_still_for_encode
    from bmt_voice_studio.video.models import IMAGE_EXTENSIONS

    assert ".png" in IMAGE_EXTENSIONS
    assert ".gif" in IMAGE_EXTENSIONS
    logo = tmp_path / "logo.png"
    im = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    for x in range(20, 100):
        for y in range(10, 70):
            im.putpixel((x, y), (212, 160, 23, 255))
    im.save(logo)
    info = probe_image(logo)
    assert info["width"] == 120
    assert info["has_alpha"] is True
    rgba = open_rgba(logo)
    assert image_has_transparency(rgba)
    flat = flatten_rgba(rgba, (15, 20, 28))
    assert flat.mode == "RGB"
    assert flat.getpixel((0, 0)) == (15, 20, 28)
    assert flat.getpixel((40, 30)) == (212, 160, 23)
    dest = tmp_path / "opaque.png"
    out = prepare_still_for_encode(logo, dest, (15, 20, 28))
    assert Path(out).is_file()


def test_invalid_image(tmp_path: Path):
    bad = tmp_path / "fake.jpg"
    bad.write_text("not an image", encoding="utf-8")
    with pytest.raises(MediaValidationError):
        probe_image(bad)


def test_invalid_media_extension(tmp_path: Path):
    doc = tmp_path / "notes.txt"
    doc.write_text("hello", encoding="utf-8")
    with pytest.raises(MediaValidationError):
        probe_media(doc)


def _ffmpeg_or_skip():
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    try:
        return FFmpegService().find()
    except Exception:
        pytest.skip("FFmpeg not available")


def test_video_probing(tmp_path: Path):
    ffmpeg = _ffmpeg_or_skip()
    import subprocess

    dest = tmp_path / "clip.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=640x360:d=1.2",
            "-pix_fmt",
            "yuv420p",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    info = probe_video(dest)
    assert info["width"] == 640
    assert info["height"] == 360
    assert info["duration"] > 1.0


def test_invalid_video(tmp_path: Path):
    _ffmpeg_or_skip()
    bad = tmp_path / "broken.mp4"
    bad.write_bytes(b"not a video file at all")
    with pytest.raises(MediaValidationError):
        probe_video(bad)


def test_audio_duration_probing(tmp_path: Path):
    ffmpeg = _ffmpeg_or_skip()
    import subprocess

    dest = tmp_path / "tone.wav"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2.5",
            "-ar",
            "48000",
            str(dest),
        ],
        check=True,
        capture_output=True,
    )
    dur = probe_audio_duration(dest)
    assert 2.3 <= dur <= 2.7


def test_9_16_composition_geometry():
    assert CANVAS_WIDTH == 1080
    assert CANVAS_HEIGHT == 1920
    assert abs(CANVAS_WIDTH / CANVAS_HEIGHT - 9 / 16) < 1e-6


def test_landscape_crop_math():
    x, y, w, h = landscape_center_crop(1920, 1080)
    assert h == 1080
    assert w < 1920
    assert abs((w / h) - (9 / 16)) < 0.02
    assert x > 0
    assert y == 0


def test_portrait_crop_math():
    x, y, w, h = portrait_center_crop(1080, 1920)
    assert (x, y, w, h) == (0, 0, 1080, 1920)
    x2, y2, w2, h2 = center_crop_rect(1080, 1350)
    assert h2 == 1350
    assert w2 < 1080
    assert y2 == 0
    assert x2 > 0


def test_photo_scene_duration_and_distribution():
    assert choose_scene_count(400, 4) >= 4
    n = choose_scene_count(400, 4)
    each = photo_scene_duration(400, n)
    assert 12 <= each <= 30
    assert choose_scene_count(40, 4) == 4
    assert photo_scene_duration(40, 4) == pytest.approx(10.0)
    assert choose_scene_count(20, 4) <= 4
    assert photo_scene_duration(20, choose_scene_count(20, 4)) >= 4.0


def test_crossfade_calculations():
    durations = [5.5, 12.0, 12.0, 2.5]
    xfade = 0.75
    out = xfade_output_duration(durations, xfade)
    assert out == pytest.approx(sum(durations) - 3 * xfade)
    offsets = xfade_offsets(durations, xfade)
    assert len(offsets) == 3
    assert offsets[0] == pytest.approx(5.5 - 0.75)
    assert offsets[1] == pytest.approx(5.5 + 12.0 - 1.5)


def test_output_path_generation(tmp_path: Path):
    d = date(2026, 8, 14)
    folder = video_project_dir(d, "en", base=tmp_path)
    assert folder.as_posix().endswith("2026/08/BMT_2026_08_14/ENGLISH")
    name = video_filename(d, "en")
    assert name == "BMT_14_AUG_2026_ENGLISH_VIDEO.mp4"
    path = video_output_path(d, "fr", base=tmp_path)
    assert path.name == "BMT_14_AUG_2026_FRENCH_VIDEO.mp4"
    assert "FRENCH" in path.parts


def test_ffmpeg_command_construction(tmp_path: Path):
    ffmpeg = "ffmpeg"
    img = str(tmp_path / "photo.jpg")
    clip = str(tmp_path / "clip.mp4")
    dest = str(tmp_path / "scene.mp4")
    img_cmd = build_image_scene_command(
        ffmpeg, img, dest, duration=12, fps=30, width=1080, height=1920, animation="zoom_in", fit_mode="fill"
    )
    assert img_cmd[0] == "ffmpeg"
    assert "-an" in img_cmd
    assert "libx264" in img_cmd
    assert "yuv420p" in img_cmd
    assert "1080x1920" in " ".join(img_cmd)
    vid_cmd = build_video_scene_command(
        ffmpeg, clip, dest, duration=10, fps=30, width=1080, height=1920, fit_mode="fill"
    )
    assert "-an" in vid_cmd
    assert "-stream_loop" in vid_cmd
    script = build_xfade_filter_script(3, [5.0, 10.0, 10.0], 0.75, 3, 4.6)
    assert "xfade=transition=fade" in script
    assert "overlay=" in script
    final = build_final_command(
        ffmpeg,
        [str(tmp_path / "s0.mp4"), str(tmp_path / "s1.mp4")],
        str(tmp_path / "ov.png"),
        str(tmp_path / "a.mp3"),
        script,
        str(tmp_path / "out.mp4"),
        audio_duration=40.0,
        fps=30,
        crf=20,
        audio_bitrate_k=192,
        audio_sample_rate=48000,
    )
    joined = " ".join(final)
    assert "libx264" in final
    assert "aac" in final
    assert "yuv420p" in final
    assert "48000" in final
    assert "-filter_complex" in final
    assert "xfade=transition=fade" in joined
    assert "-map" in final
    assert "[vout]" in final


def test_ken_burns_is_subtle():
    vf = ken_burns_filter("zoom_in", 12, 30, 1080, 1920, "fill")
    assert "zoompan" in vf
    assert "1.10" in vf
    assert "force_original_aspect_ratio=increase" in vf


def test_no_developer_absolute_paths_in_video_package():
    root = Path(__file__).resolve().parents[1] / "bmt_voice_studio" / "video"
    forbidden = ("C:\\Users\\aganz", "C:/Users/aganz", "/Users/aganz")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token.lower() not in text.lower(), f"{path} contains developer path {token}"


def test_composition_plan_uses_audio_as_master(tmp_path: Path):
    pytest.importorskip("PIL")
    from PIL import Image

    audio = tmp_path / "master.wav"
    audio.write_bytes(b"RIFF")  # placeholder existence; duration set on project
    photo = tmp_path / "p.png"
    Image.new("RGB", (900, 1600), (10, 20, 30)).save(photo)
    # Duration probing would fail on fake wav — set duration explicitly and skip validate.
    project = VideoProject(
        devotional_date="2026-08-14",
        language="en",
        audio_path=str(audio),
        audio_duration=60.0,
        topic="Hope",
        media_items=[MediaItem(path=str(photo), media_type="image", order=0, width=900, height=1600)],
    )
    plan = build_composition_plan(project, output_path=tmp_path / "out.mp4", temp_dir=tmp_path / "tmp", job_id="t")
    assert plan.scenes[0].kind == "intro"
    assert plan.audio_duration == pytest.approx(60.0)
    assert plan.total_duration == pytest.approx(80.0, abs=0.15)
    assert plan.intro_duration == 10.0
    assert plan.outro_duration == 10.0


def test_extract_metadata_from_script():
    from bmt_voice_studio.video.discovery import extract_metadata

    text = (
        "BELIEVERS MANNA TODAY\n"
        "Topic: The God Who Provides\n"
        "Week Focus: Trust\n"
        "Month Theme: Abundance\n"
        "Body of the message...\n"
    )
    meta = extract_metadata(text)
    assert meta["topic"] == "The God Who Provides"
    assert meta["week_focus"] == "Trust"
    assert meta["month_theme"] == "Abundance"


def test_validate_missing_audio_and_media(tmp_path: Path):
    from bmt_voice_studio.video.composition import validate_project_for_render

    with pytest.raises(VideoMakerError):
        validate_project_for_render(VideoProject())
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"xx")
    with pytest.raises(VideoMakerError):
        validate_project_for_render(VideoProject(audio_path=str(audio)))
    gone = tmp_path / "gone.jpg"
    with pytest.raises(MissingMediaError):
        validate_project_for_render(
            VideoProject(
                audio_path=str(audio),
                media_items=[MediaItem(path=str(gone), media_type="image")],
            )
        )
