"""Optional speech mastering: loudness, fades, silence, limiter."""

from __future__ import annotations

import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.core.filenames import unique_path

logger = logging.getLogger(__name__)


@dataclass
class MasteringOptions:
    normalize_loudness: bool = True
    target_lufs: float = -16.0
    remove_silence: bool = False
    fade_in_ms: int = 0
    fade_out_ms: int = 120
    peak_limiter: bool = True
    bitrate_kbps: int = 128
    lowpass_hz: int | None = None


def _probe_duration_seconds(ff: FFmpegService, path: Path) -> float | None:
    try:
        result = ff.run(["-i", str(path)], check=False, timeout=30)
        combined = (result.stderr or "") + (result.stdout or "")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", combined)
        if not m:
            return None
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    except Exception:
        return None


def master_audio(
    src: Path,
    dest: Path,
    options: MasteringOptions,
    *,
    ffmpeg: FFmpegService | None = None,
    overwrite: bool = True,
) -> Path:
    ff = ffmpeg or FFmpegService()
    if dest.exists() and not overwrite:
        dest = unique_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    filters: list[str] = []
    if options.remove_silence:
        # Trim only leading/trailing hush — never strip mid-speech pauses
        filters.append(
            "silenceremove=start_periods=1:start_silence=0.4:start_threshold=-40dB:"
            "detection=peak,"
            "areverse,"
            "silenceremove=start_periods=1:start_silence=0.4:start_threshold=-40dB:"
            "detection=peak,"
            "areverse"
        )
    if options.normalize_loudness:
        filters.append(f"loudnorm=I={options.target_lufs}:TP=-1.5:LRA=11")
    if options.peak_limiter:
        filters.append("alimiter=limit=0.95:attack=5:release=50")
    if options.lowpass_hz and options.lowpass_hz > 0:
        filters.append(f"lowpass=f={options.lowpass_hz}")
    if options.fade_in_ms and options.fade_in_ms > 0:
        filters.append(f"afade=t=in:st=0:d={options.fade_in_ms / 1000.0:.3f}")
    if options.fade_out_ms and options.fade_out_ms > 0:
        dur = _probe_duration_seconds(ff, src)
        fade = options.fade_out_ms / 1000.0
        if dur and dur > fade + 0.05:
            start = max(0.0, dur - fade)
            filters.append(f"afade=t=out:st={start:.3f}:d={fade:.3f}")
        else:
            logger.info("Skipping fade-out; duration unavailable or too short")

    if not filters:
        if Path(src).resolve() != dest.resolve():
            shutil.copy2(src, dest)
        return dest

    filter_complex = ",".join(filters)
    same_path = Path(src).resolve() == Path(dest).resolve()
    write_dest = dest
    tmp_dest: Path | None = None
    if same_path:
        tmp_dest = dest.with_name(dest.stem + ".__mastering_tmp__" + dest.suffix)
        write_dest = tmp_dest

    def _run(af: str) -> None:
        args = ["-y", "-i", str(src), "-af", af]
        if write_dest.suffix.lower() == ".wav":
            args += ["-ac", "1", "-ar", "44100", str(write_dest)]
        else:
            args += [
                "-ac",
                "1",
                "-ar",
                "44100",
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{options.bitrate_kbps}k",
                str(write_dest),
            ]
        ff.run(args)

    try:
        _run(filter_complex)
    except Exception as exc:
        logger.warning("Full mastering failed (%s); retrying without silence remove / fade-out", exc)
        safe = [
            f
            for f in filters
            if not f.startswith("silenceremove") and not f.startswith("afade=t=out")
        ]
        if not safe:
            if tmp_dest and tmp_dest.exists():
                tmp_dest.unlink(missing_ok=True)
            if Path(src).resolve() != dest.resolve():
                shutil.copy2(src, dest)
            return dest
        _run(",".join(safe))

    if tmp_dest is not None:
        if not tmp_dest.exists() or tmp_dest.stat().st_size < 64:
            raise RuntimeError(f"Mastering produced empty output: {tmp_dest}")
        tmp_dest.replace(dest)
    elif not dest.exists() or dest.stat().st_size < 64:
        raise RuntimeError(f"Mastering produced empty output: {dest}")
    return dest
