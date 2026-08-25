"""Join segment audio files with silence between speaker changes."""

from __future__ import annotations

import logging
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegError, FFmpegService
from bmt_voice_studio.core.filenames import unique_path
from bmt_voice_studio.core.models import Segment

logger = logging.getLogger(__name__)


def join_segments(
    segments: list[Segment],
    output_path: Path,
    *,
    pause_ms: int = 450,
    bitrate_kbps: int = 128,
    also_wav: bool = True,
    ffmpeg: FFmpegService | None = None,
) -> dict[str, Path]:
    """Merge enabled segments in order using FFmpeg concat demuxer.

    Inserts silence between consecutive segments when the speaker changes
    (and also between all segments if pause_ms > 0 — configurable globally).
    """
    ff = ffmpeg or FFmpegService()
    enabled = [s for s in segments if s.enabled and s.audio_path and Path(s.audio_path).exists()]
    if not enabled:
        raise FFmpegError("No generated segments available to join.")

    work = output_path.parent / "_join_work"
    work.mkdir(parents=True, exist_ok=True)
    silence_path = work / f"silence_{pause_ms}.mp3"
    if pause_ms > 0 and not silence_path.exists():
        ff.generate_silence(silence_path, pause_ms)

    # Normalize each input to consistent PCM-compatible mp3 first
    normalized: list[Path] = []
    for i, seg in enumerate(enabled):
        src = Path(seg.audio_path)
        norm = work / f"norm_{i:03d}.mp3"
        ff.convert(src, norm, bitrate_kbps=bitrate_kbps)
        if i > 0 and pause_ms > 0:
            # Always insert pause between sections for clearer devotionals
            normalized.append(silence_path)
        normalized.append(norm)

    list_file = work / "concat.txt"
    lines = []
    for p in normalized:
        # FFmpeg concat demuxer requires forward slashes / escaped quotes
        escaped = str(p.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    list_file.write_text("\n".join(lines), encoding="utf-8")

    output_path = unique_path(output_path) if output_path.exists() else output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".wav":
        ff.run(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-ac",
                "1",
                "-ar",
                "44100",
                str(output_path),
            ]
        )
        result = {"final": output_path}
    else:
        ff.run(
            [
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{bitrate_kbps}k",
                "-ac",
                "1",
                "-ar",
                "44100",
                str(output_path),
            ]
        )
        result = {"final": output_path}
        if also_wav:
            wav_path = output_path.with_suffix(".wav")
            wav_path = unique_path(wav_path) if wav_path.exists() else wav_path
            ff.convert(output_path, wav_path, bitrate_kbps=bitrate_kbps)
            result["wav"] = wav_path

    return result
