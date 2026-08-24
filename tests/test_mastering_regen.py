"""Regression tests for mastering and smart regeneration."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.models import Segment, Speaker


def _make_tone(path: Path, seconds: float = 2.0) -> Path:
    ff = FFmpegService()
    path.parent.mkdir(parents=True, exist_ok=True)
    ff.run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(path),
        ]
    )
    return path


def test_mastering_silence_trim_preserves_duration(tmp_path: Path):
    src = _make_tone(tmp_path / "src.mp3", 3.0)
    dest = tmp_path / "out.mp3"
    master_audio(
        src,
        dest,
        MasteringOptions(
            normalize_loudness=False,
            remove_silence=True,
            fade_in_ms=0,
            fade_out_ms=0,
            peak_limiter=False,
            bitrate_kbps=128,
        ),
        overwrite=True,
    )
    # Should remain roughly the same length (not collapsed)
    result = FFmpegService().run(["-i", str(dest)], check=False)
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr or "")
    assert m
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    assert dur > 2.0


def test_mastering_produces_playable_audio(tmp_path: Path):
    src = _make_tone(tmp_path / "src.mp3", 2.0)
    dest = tmp_path / "out.mp3"
    out = master_audio(
        src,
        dest,
        MasteringOptions(
            normalize_loudness=True,
            target_lufs=-16.0,
            remove_silence=False,
            fade_in_ms=50,
            fade_out_ms=100,
            peak_limiter=True,
            bitrate_kbps=128,
        ),
        overwrite=True,
    )
    assert out.exists()
    assert out.stat().st_size > 500
    assert FFmpegService().probe_is_audio(out)


def test_smart_regen_only_changed_segment(tmp_path: Path):
    segs = [
        Segment(index=1, speaker=Speaker.MALE, text="One", voice="v", rate="-10%", pitch="-3Hz"),
        Segment(index=2, speaker=Speaker.FEMALE, text="Two", voice="v", rate="-10%", pitch="-3Hz"),
        Segment(index=3, speaker=Speaker.MALE, text="Three", voice="v", rate="-10%", pitch="-3Hz"),
    ]
    for s in segs:
        p = tmp_path / f"{s.index}.mp3"
        p.write_bytes(b"ID3" + b"\x00" * 200)
        s.audio_path = str(p)
        s.cache_hash = segment_cache_hash(s)

    # Edit only segment 2
    segs[1].text = "Two edited"
    to_regen = []
    to_reuse = []
    for s in segs:
        h = segment_cache_hash(s)
        if needs_regeneration(s, h):
            to_regen.append(s.index)
        else:
            to_reuse.append(s.index)
    assert to_regen == [2]
    assert to_reuse == [1, 3]

    # Voice change invalidates
    segs[0].voice = "other"
    assert needs_regeneration(segs[0], segment_cache_hash(segs[0]))
