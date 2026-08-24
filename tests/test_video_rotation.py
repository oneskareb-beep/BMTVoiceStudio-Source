"""Portrait / rotation handling for phone and WhatsApp clips."""

from __future__ import annotations

from bmt_voice_studio.video.ffmpeg_renderer import build_video_scene_command, video_clip_filter
from bmt_voice_studio.video.rotation import (
    display_size,
    ffmpeg_autorotate_filter,
    normalize_rotation_degrees,
    parse_ffmpeg_rotation,
    prepend_autorotate,
)


def test_parse_rotate_tag():
    blob = (
        "Duration: 00:00:02.40, start: 0.000000, bitrate: 2500 kb/s\n"
        "Stream #0:0: Video: h264 (High), yuv420p, 1280x720, 30 fps\n"
        "    rotate          : 90\n"
    )
    assert parse_ffmpeg_rotation(blob) == 90
    assert display_size(1280, 720, 90) == (720, 1280)


def test_parse_displaymatrix_negative():
    blob = (
        "Stream #0:0: Video: h264, yuv420p, 1920x1080\n"
        "    Side data:\n"
        "      displaymatrix: rotation of -90.00 degrees\n"
    )
    assert parse_ffmpeg_rotation(blob) == 90


def test_normalize_and_filters():
    assert normalize_rotation_degrees(-90) == 270
    assert normalize_rotation_degrees(90.4) == 90
    assert ffmpeg_autorotate_filter(90) == "transpose=1"
    assert ffmpeg_autorotate_filter(270) == "transpose=2"
    assert ffmpeg_autorotate_filter(0) == ""
    assert prepend_autorotate("scale=2:2", 90) == "transpose=1,scale=2:2"
    assert prepend_autorotate("scale=2:2", 0) == "scale=2:2"


def test_video_clip_filter_includes_transpose():
    vf = video_clip_filter(2.0, 30, 1080, 1920, "fill", rotation=90)
    assert vf.startswith("transpose=1,")
    plain = video_clip_filter(2.0, 30, 1080, 1920, "fill", rotation=0)
    assert not plain.startswith("transpose")


def test_build_video_scene_uses_noautorotate():
    cmd = build_video_scene_command(
        "ffmpeg",
        "clip.mp4",
        "out.mp4",
        duration=2.0,
        fps=30,
        width=1080,
        height=1920,
        fit_mode="fill",
        rotation=90,
    )
    assert "-noautorotate" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert vf.startswith("transpose=1,")
