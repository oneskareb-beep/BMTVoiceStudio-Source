"""Music 10-second intro/outro crops + job percent mapping."""

from __future__ import annotations

from bmt_voice_studio.core.job_progress import batch_job_percent, language_job_percent
from bmt_voice_studio.video.branding_audio import (
    AUTO_OUTRO_START,
    MUSIC_DUCK_DB,
    MUSIC_LOUD_DB,
    _volume_envelope_expr,
    clamp_music_window,
    default_outro_start,
    default_soft_music_path,
    mix_branding_audio,
    resolve_music_path,
    resolve_music_window_starts,
)
from bmt_voice_studio.video.models import VideoProject
from bmt_voice_studio.video.project_store import load_project, save_project

import pytest


def test_clamp_music_window_stays_inside_file():
    assert clamp_music_window(0, 10, 90) == 0
    assert clamp_music_window(85, 10, 90) == 80
    assert clamp_music_window(-4, 10, 90) == 0
    assert clamp_music_window(0, 10, 8) == 0


def test_default_outro_uses_end_when_file_is_long():
    assert default_outro_start(90, 10) == 79.85
    assert default_outro_start(12, 10) == 0.0


def test_resolve_auto_outro_when_start_is_negative():
    intro, outro = resolve_music_window_starts(
        source_duration=120,
        intro_sec=10,
        outro_sec=10,
        intro_start=5,
        outro_start=AUTO_OUTRO_START,
    )
    assert intro == 5
    assert outro == default_outro_start(120, 10)


def test_resolve_manual_outro_crop():
    intro, outro = resolve_music_window_starts(
        source_duration=120,
        intro_sec=10,
        outro_sec=10,
        intro_start=12,
        outro_start=40,
    )
    assert intro == 12
    assert outro == 40


def test_project_roundtrip_music_windows(tmp_path):
    project = VideoProject(
        music_path=str(tmp_path / "bed.mp3"),
        music_intro_start=8.5,
        music_outro_start=44.0,
        intro_enabled=True,
        outro_enabled=True,
    )
    dest = tmp_path / "proj.json"
    save_project(project, dest)
    loaded = load_project(dest)
    assert loaded.music_intro_start == 8.5
    assert loaded.music_outro_start == 44.0


def test_language_job_percent_fills_selected_languages():
    assert language_job_percent("ENGLISH", 5, 10, ["en", "fr"]) == 25
    assert language_job_percent("FRENCH", 10, 10, ["en", "fr"]) == 100
    assert language_job_percent("OVERALL", 1, 4, ["en", "fr"]) == 25


def test_batch_job_percent_spans_queue():
    assert batch_job_percent(0, 2, 50) == 25
    assert batch_job_percent(1, 2, 50) == 75
    assert batch_job_percent(1, 2, 100) == 100


def test_default_soft_music_is_bundled():
    path = default_soft_music_path()
    assert path is not None
    assert path.is_file()
    assert path.name == "soft_background.mp3"
    assert resolve_music_path(None) == path
    assert resolve_music_path(str(path)) == path
    assert resolve_music_path("C:/missing/nope.mp3") == path


def test_volume_envelope_loud_intro_outro_duck_mid():
    expr = _volume_envelope_expr(10.0, 50.0, 10.0)
    assert "10.000" in expr
    assert "40.000" in expr
    loud = 10 ** (MUSIC_LOUD_DB / 20.0)
    duck = 10 ** (MUSIC_DUCK_DB / 20.0)
    assert f"{loud:.6f}" in expr
    assert f"{duck:.6f}" in expr
    assert MUSIC_DUCK_DB < MUSIC_LOUD_DB


def test_mix_branding_audio_length_matches_timeline(tmp_path):
    """Music bed is trimmed to intro + speech + outro (never longer/shorter)."""
    from mutagen.mp4 import MP4

    speech = tmp_path / "speech.wav"
    dest = tmp_path / "mixed.m4a"
    # 2s mono speech tone via ffmpeg
    ff = __import__("bmt_voice_studio.audio.ffmpeg_service", fromlist=["FFmpegService"]).FFmpegService()
    ff.run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(speech),
        ],
        check=True,
    )
    music = default_soft_music_path()
    assert music is not None
    intro = 10.0
    outro = 10.0
    master = 2.0
    mix_branding_audio(
        speech,
        dest,
        music_path=music,
        intro_sec=intro,
        outro_sec=outro,
        master_duration=master,
    )
    assert dest.is_file()
    meta = MP4(str(dest))
    length = float(meta.info.length)
    expected = intro + master + outro
    assert length == pytest.approx(expected, abs=0.35)
