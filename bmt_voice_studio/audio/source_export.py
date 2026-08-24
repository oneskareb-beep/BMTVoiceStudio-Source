"""Original reference pipeline export — no BMT mastering chain."""

from __future__ import annotations

import shutil
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.config.pipeline_config import PipelineSettings


def export_original_pipeline(
    src: Path,
    mp3_dest: Path | None,
    wav_dest: Path | None,
    pipeline: PipelineSettings,
    *,
    ffmpeg: FFmpegService | None = None,
    overwrite: bool = True,
) -> dict[str, Path]:
    """Export joined audio using reference pipeline rules only."""
    ff = ffmpeg or FFmpegService()
    results: dict[str, Path] = {}
    working = src

    if pipeline.lowpass_hz and pipeline.lowpass_hz > 0:
        filtered = src.with_name(src.stem + ".__lowpass__" + src.suffix)
        if filtered.exists() and overwrite:
            filtered.unlink()
        ff.run(
            [
                "-y",
                "-i",
                str(src),
                "-af",
                f"lowpass=f={pipeline.lowpass_hz}",
                "-ac",
                str(pipeline.wav_channels),
                "-ar",
                str(pipeline.wav_sample_rate),
                str(filtered),
            ]
        )
        working = filtered

    if pipeline.export_wav and wav_dest is not None:
        wav_dest.parent.mkdir(parents=True, exist_ok=True)
        if wav_dest.exists() and overwrite:
            wav_dest.unlink()
        ff.run(
            [
                "-y",
                "-i",
                str(working),
                "-ac",
                str(pipeline.wav_channels),
                "-ar",
                str(pipeline.wav_sample_rate),
                str(wav_dest),
            ]
        )
        results["wav"] = wav_dest

    if pipeline.export_mp3 and mp3_dest is not None:
        mp3_dest.parent.mkdir(parents=True, exist_ok=True)
        if mp3_dest.exists() and overwrite:
            mp3_dest.unlink()
        args = [
            "-y",
            "-i",
            str(working),
            "-ac",
            str(pipeline.wav_channels),
            "-ar",
            str(pipeline.wav_sample_rate),
            "-c:a",
            "libmp3lame",
        ]
        if pipeline.mp3_bitrate_kbps:
            args.extend(["-b:a", f"{pipeline.mp3_bitrate_kbps}k"])
        args.append(str(mp3_dest))
        ff.run(args)
        results["mp3"] = mp3_dest
    elif not pipeline.export_mp3 and mp3_dest is not None and working.resolve() != mp3_dest.resolve():
        if mp3_dest.exists() and overwrite:
            mp3_dest.unlink()
        shutil.copy2(working, mp3_dest)
        results["mp3"] = mp3_dest

    return results
