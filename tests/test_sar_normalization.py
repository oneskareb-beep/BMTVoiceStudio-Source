"""SAR / pixel-format normalization — concat and xfade must see identical geometry."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bmt_voice_studio.video.ffmpeg_renderer import (
    build_branded_timeline_filter,
    build_image_scene_command,
    build_video_scene_command,
    build_xfade_filter_script,
    ken_burns_filter,
    video_clip_filter,
)
from bmt_voice_studio.video.geometry import (
    CANVAS_FPS,
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    ffmpeg_contain_filter,
    ffmpeg_cover_filter,
    scene_normalize_filter,
)
from bmt_voice_studio.video.models import PROFILE_WHATSAPP, output_profile_for


def _ffmpeg_or_skip() -> str:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    try:
        return FFmpegService().find()
    except Exception:
        pytest.skip("FFmpeg not available")


def test_normalize_helper_forces_square_sar_and_yuv420p():
    filt = scene_normalize_filter(1080, 1920, 30)
    assert "scale=1080:1920" in filt
    assert "in_range=auto" in filt
    assert "out_range=tv" in filt
    assert "setsar=1" in filt
    assert "fps=30" in filt
    assert "format=yuv420p" in filt
    assert "settb=1/30" in filt


def test_ken_burns_and_clip_filters_end_with_normalize():
    kb = ken_burns_filter("zoom_in", 12, 30, 1080, 1920, "fill")
    assert "force_original_aspect_ratio=increase" in kb
    assert kb.split("zoompan")[-1].count("setsar=1") == 1
    assert "format=yuv420p" in kb
    clip = video_clip_filter(8, 30, 1080, 1920, "fill")
    assert "setsar=1" in clip
    assert "format=yuv420p" in clip
    assert "fps=30" in clip


def test_fit_then_normalize_does_not_leave_calculated_sar():
    contain = ffmpeg_contain_filter(1080, 1920)
    cover = ffmpeg_cover_filter(1080, 1920)
    finished = f"{cover},{scene_normalize_filter()}"
    assert "force_original_aspect_ratio=increase" in finished
    assert finished.endswith("format=yuv420p")
    assert "setsar=1" in finished
    assert contain.startswith("scale=1080:1920:force_original_aspect_ratio=decrease")


def test_xfade_inputs_are_normalized_before_transition():
    script = build_xfade_filter_script(3, [5.0, 10.0, 10.0], 0.75, 3, 4.6)
    assert "[0:v]" in script and "[n0]" in script
    assert script.index("setsar=1") < script.index("xfade=transition=fade")
    assert "[n0][n1]xfade" in script.replace("\n", "")
    assert "format=rgba" in script
    assert script.strip().endswith("setsar=1,format=yuv420p[vout]")


def test_intro_main_outro_concat_normalizes_all_three():
    script = build_branded_timeline_filter(
        1,
        2,
        [10.0, 10.0],
        0.75,
        1,
        [(4, "between(t,1,8)")],
        canvas_w=1080,
        canvas_h=1920,
        fps=30,
    )
    joined = script.replace("\n", "")
    assert "[0:v]" in script
    assert "[intro]" in script
    assert "[outro]" in script
    assert "[media]" in script
    assert "concat=n=3:v=1:a=0[vcat]" in joined
    assert script.index("setsar=1") < script.index("concat=n=3")
    assert "format=rgba" in script
    assert "[vcomp]setsar=1,format=yuv420p[vout]" in joined


def test_whatsapp_profile_uses_same_geometry_normalize():
    wa = output_profile_for(PROFILE_WHATSAPP)
    std = output_profile_for("standard_1080p")
    assert wa.width == std.width == CANVAS_WIDTH
    assert wa.height == std.height == CANVAS_HEIGHT
    assert wa.fps == std.fps == CANVAS_FPS
    assert scene_normalize_filter(wa.width, wa.height, wa.fps) == scene_normalize_filter(
        std.width, std.height, std.fps
    )
    img = build_image_scene_command(
        "ffmpeg",
        "photo.jpg",
        "out.mp4",
        duration=8,
        fps=wa.fps,
        width=wa.width,
        height=wa.height,
        animation="zoom_in",
        fit_mode="fill",
    )
    vid = build_video_scene_command(
        "ffmpeg",
        "clip.mp4",
        "out.mp4",
        duration=8,
        fps=wa.fps,
        width=wa.width,
        height=wa.height,
        fit_mode="fill",
    )
    assert "setsar=1" in " ".join(img)
    assert "setsar=1" in " ".join(vid)
    assert "yuv420p" in img
    assert "-color_range" in img and "tv" in img


def _probe_stream(ffmpeg: str, path: Path) -> str:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return (proc.stderr or "") + (proc.stdout or "")


def test_jpeg_yuvj_and_odd_aspect_normalize_to_square_sar_yuv420p(tmp_path: Path):
    ffmpeg = _ffmpeg_or_skip()
    pytest.importorskip("PIL")
    from PIL import Image

    jpeg = tmp_path / "odd.jpg"
    Image.new("RGB", (736, 1308), (40, 80, 120)).save(jpeg, quality=85)
    dest = tmp_path / "scene.mp4"
    cmd = build_image_scene_command(
        ffmpeg,
        str(jpeg),
        str(dest),
        duration=1.0,
        fps=30,
        width=1080,
        height=1920,
        animation="static",
        fit_mode="fill",
    )
    subprocess.run(cmd, check=True, capture_output=True)
    text = _probe_stream(ffmpeg, dest)
    assert "1080x1920" in text
    assert "SAR 1:1" in text
    assert "DAR 9:16" in text
    assert "yuvj420p" not in text
    assert "yuv420p" in text


def test_landscape_and_portrait_media_normalize(tmp_path: Path):
    ffmpeg = _ffmpeg_or_skip()
    land = tmp_path / "land.mp4"
    port = tmp_path / "port.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=1920x1080:d=1.2",
            "-pix_fmt",
            "yuv420p",
            str(land),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=720x1280:d=1.2",
            "-pix_fmt",
            "yuv420p",
            str(port),
        ],
        check=True,
        capture_output=True,
    )
    for src, name in ((land, "land_out.mp4"), (port, "port_out.mp4")):
        dest = tmp_path / name
        cmd = build_video_scene_command(
            ffmpeg,
            str(src),
            str(dest),
            duration=0.8,
            fps=30,
            width=1080,
            height=1920,
            fit_mode="fill",
        )
        subprocess.run(cmd, check=True, capture_output=True)
        text = _probe_stream(ffmpeg, dest)
        assert "1080x1920" in text
        assert "SAR 1:1" in text
        assert "yuv420p" in text


def test_concat_accepts_mismatched_source_sar_after_normalize(tmp_path: Path):
    ffmpeg = _ffmpeg_or_skip()
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    out = tmp_path / "cat.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=green:s=1080x1920:d=0.6,setsar=39560/39567",
            "-pix_fmt",
            "yuvj420p",
            str(a),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=yellow:s=1080x1920:d=0.6,setsar=1",
            "-pix_fmt",
            "yuv420p",
            str(b),
        ],
        check=True,
        capture_output=True,
    )
    graph = (
        f"[0:v]{scene_normalize_filter()}[a];"
        f"[1:v]{scene_normalize_filter()}[b];"
        "[a][b]concat=n=2:v=1:a=0[vcat];"
        "[vcat]setsar=1,format=yuv420p[vout]"
    )
    proc = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(a),
            "-i",
            str(b),
            "-filter_complex",
            graph,
            "-map",
            "[vout]",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr[-1500:]
    assert "Parsed_concat" not in (proc.stderr or "") or "do not match" not in (proc.stderr or "")
    assert out.is_file() and out.stat().st_size > 1024
    text = _probe_stream(ffmpeg, out)
    assert "SAR 1:1" in text
    assert "1080x1920" in text
