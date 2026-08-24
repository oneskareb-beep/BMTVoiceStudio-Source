"""Build the single final AAC bed: continuous soft music under branded video.

Sylvestre mix rule:
- Music plays for the whole timeline (intro + speech + outro), trimmed/looped to exact length.
- First 10s (intro) and last 10s (outro): music LOUD.
- Middle (speech): music LOW under the voice.
"""

from __future__ import annotations

import sys
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

# Loud pads (intro/outro) vs ducked under speech.
MUSIC_LOUD_DB = -4.0
MUSIC_DUCK_DB = -20.0
INTRO_FADE_IN = 0.85
OUTRO_FADE_OUT = 1.35
BRANDED_PAD_SECONDS = 10.0
AUTO_OUTRO_START = -1.0
# Legacy alias used by older UI copy / tests.
MUSIC_GAIN_DB = MUSIC_LOUD_DB

SOFT_MUSIC_NAME = "soft_background.mp3"
SOFT_MUSIC_DIR = "music"


def default_soft_music_path() -> Path | None:
    """Packaged Sylvestre soft bed (resources/music/soft_background.mp3)."""
    here = Path(__file__).resolve().parent.parent / "resources" / SOFT_MUSIC_DIR / SOFT_MUSIC_NAME
    roots = [here]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        roots.extend(
            [
                meipass / "bmt_voice_studio" / "resources" / SOFT_MUSIC_DIR / SOFT_MUSIC_NAME,
                meipass / "resources" / SOFT_MUSIC_DIR / SOFT_MUSIC_NAME,
                Path(sys.executable).parent
                / "_internal"
                / "bmt_voice_studio"
                / "resources"
                / SOFT_MUSIC_DIR
                / SOFT_MUSIC_NAME,
            ]
        )
    for path in roots:
        if path.is_file():
            return path
    return None


def resolve_music_path(preferred: str | Path | None = None) -> Path | None:
    """Prefer an explicit file; otherwise the packaged soft background."""
    if preferred:
        path = Path(preferred)
        if path.is_file():
            return path
    return default_soft_music_path()


def music_display_name(path: str | Path | None) -> str:
    raw = Path(path or "")
    if not raw.name:
        soft = default_soft_music_path()
        if soft is not None:
            return "Soft background (default)"
        return "No music selected"
    if raw.name.lower() == SOFT_MUSIC_NAME:
        return "Soft background (Sylvestre)"
    name = raw.stem.replace("(freetouse.com)", "").replace("(1)", "").strip(" -_")
    return name or raw.name


def clamp_music_window(start: float, pad: float, source_duration: float) -> float:
    """Keep a 10s (or pad) crop inside the music file."""
    window = max(0.05, float(pad or 0.0))
    dur = max(0.0, float(source_duration or 0.0))
    if dur <= 0:
        return max(0.0, float(start or 0.0))
    max_start = max(0.0, dur - min(window, dur))
    return min(max(0.0, float(start or 0.0)), max_start)


def default_outro_start(source_duration: float, outro: float) -> float:
    """Same rule as the old automatic outro: last 10 seconds when the file is long enough."""
    outro = max(0.0, float(outro or 0.0))
    dur = max(0.0, float(source_duration or 0.0))
    if dur >= outro * 2 + 1:
        return max(0.0, dur - outro - 0.15)
    return 0.0


def resolve_music_window_starts(
    *,
    source_duration: float,
    intro_sec: float,
    outro_sec: float,
    intro_start: float = 0.0,
    outro_start: float | None = None,
) -> tuple[float, float]:
    """Resolved crop starts for the intro and outro pads (UI crop windows)."""
    intro = max(0.0, float(intro_sec or 0.0))
    outro = max(0.0, float(outro_sec or 0.0))
    dur = max(0.0, float(source_duration or 0.0))
    intro_at = clamp_music_window(intro_start, intro, dur) if intro > 0.05 else 0.0
    if outro <= 0.05:
        outro_at = 0.0
    elif outro_start is None or float(outro_start) < 0:
        outro_at = clamp_music_window(default_outro_start(dur, outro), outro, dur)
    else:
        outro_at = clamp_music_window(float(outro_start), outro, dur)
    return intro_at, outro_at


def music_source_duration(path: Path | str | None) -> float:
    """Duration of a branding music file (mp3 / wav / m4a / mpeg)."""
    if not path:
        return 0.0
    music = Path(path)
    if not music.is_file():
        return 0.0
    try:
        from mutagen import File as mutagen_file

        meta = mutagen_file(str(music))
        if meta is not None and getattr(meta, "info", None) is not None:
            dur = float(getattr(meta.info, "length", 0.0) or 0.0)
            if dur > 0:
                return dur
    except Exception:
        pass
    try:
        from bmt_voice_studio.video.media_probe import parse_ffmpeg_duration

        probe = FFmpegService().run(["-hide_banner", "-i", str(music)], check=False)
        return parse_ffmpeg_duration((probe.stderr or "") + (probe.stdout or ""))
    except Exception:
        return 0.0


def _volume_envelope_expr(intro: float, total: float, outro: float) -> str:
    """FFmpeg volume expression: loud on intro/outro pads, ducked under speech."""
    loud = 10 ** (MUSIC_LOUD_DB / 20.0)
    duck = 10 ** (MUSIC_DUCK_DB / 20.0)
    intro = max(0.0, float(intro))
    outro = max(0.0, float(outro))
    total = max(0.05, float(total))
    outro_start = max(0.0, total - outro) if outro > 0.05 else total + 1.0
    # if(t < intro) loud; else if(t >= outro_start) loud; else duck
    return (
        f"if(lt(t\\,{intro:.3f})\\,{loud:.6f}\\,"
        f"if(gte(t\\,{outro_start:.3f})\\,{loud:.6f}\\,{duck:.6f}))"
    )


def mix_branding_audio(
    master_path: Path,
    dest: Path,
    *,
    music_path: Path | None,
    intro_sec: float,
    outro_sec: float,
    master_duration: float,
    sample_rate: int = 48000,
    intro_start: float = 0.0,
    outro_start: float | None = None,
) -> Path:
    """Continuous music under speech: loud 10s intro/outro, ducked mid; length = total timeline.

    Music is always trimmed (or looped) to exactly intro + master + outro so it never
    overruns or undershoots the branded video length.
    """
    del intro_start, outro_start  # crop windows kept for UI; full-bed uses loop/trim.
    dest.parent.mkdir(parents=True, exist_ok=True)
    ff = FFmpegService()
    intro = max(0.0, float(intro_sec or 0.0))
    outro = max(0.0, float(outro_sec or 0.0))
    master = Path(master_path)
    speech_dur = max(0.05, float(master_duration or 0.0))
    if speech_dur <= 0.05:
        try:
            from bmt_voice_studio.video.media_probe import probe_audio_duration

            speech_dur = max(0.05, float(probe_audio_duration(master) or 0.0))
        except Exception:
            speech_dur = 0.05
    total = intro + speech_dur + outro
    music = resolve_music_path(music_path)

    if music is None:
        # No music file — speech only, padded with silence for intro/outro cards.
        return _speech_only_bed(ff, master, dest, intro=intro, outro=outro, sample_rate=sample_rate)

    vol_expr = _volume_envelope_expr(intro, total, outro)
    fade_out_st = max(0.05, total - OUTRO_FADE_OUT)

    # Loop the soft bed as needed, then hard-trim to the exact video length.
    music_filter = (
        f"[0:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo,"
        f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
        f"volume='{vol_expr}':eval=frame,"
        f"afade=t=in:st=0:d={INTRO_FADE_IN:.2f},"
        f"afade=t=out:st={fade_out_st:.2f}:d={min(OUTRO_FADE_OUT, total):.2f}"
        f"[music]"
    )
    # Speech sits after the intro pad; trailing silence covers the outro pad.
    speech_filter = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo,"
        f"adelay={int(round(intro * 1000))}|{int(round(intro * 1000))},"
        f"apad=pad_dur={outro:.3f},atrim=0:{total:.3f},asetpts=PTS-STARTPTS[speech]"
    )
    graph = f"{music_filter};{speech_filter};[music][speech]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    cmd = [
        "-y",
        "-hide_banner",
        "-stream_loop",
        "-1",
        "-i",
        str(music),
        "-i",
        str(master),
        "-filter_complex",
        graph,
        "-map",
        "[aout]",
        "-t",
        f"{total:.3f}",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(dest),
    ]
    ff.run(cmd, check=True)
    if not dest.is_file() or dest.stat().st_size < 256:
        raise RuntimeError("branding audio mix produced an empty file")
    return dest


def _speech_only_bed(
    ff: FFmpegService,
    master: Path,
    dest: Path,
    *,
    intro: float,
    outro: float,
    sample_rate: int,
) -> Path:
    parts: list[str] = []
    inputs: list[str] = ["-y", "-hide_banner"]
    idx = 0
    labels: list[str] = []
    if intro > 0.05:
        inputs.extend(["-f", "lavfi", "-t", f"{intro:.3f}", "-i", f"anullsrc=r={sample_rate}:cl=stereo"])
        parts.append(
            f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo[intro]"
        )
        labels.append("[intro]")
        idx += 1
    inputs.extend(["-i", str(master)])
    parts.append(
        f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo[speech]"
    )
    labels.append("[speech]")
    idx += 1
    if outro > 0.05:
        inputs.extend(["-f", "lavfi", "-t", f"{outro:.3f}", "-i", f"anullsrc=r={sample_rate}:cl=stereo"])
        parts.append(
            f"[{idx}:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo[outro]"
        )
        labels.append("[outro]")
    concat = "".join(labels) + f"concat=n={len(labels)}:v=0:a=1[aout]"
    graph = ";".join(parts + [concat])
    cmd = [
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        "[aout]",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(dest),
    ]
    ff.run(cmd, check=True)
    if not dest.is_file() or dest.stat().st_size < 256:
        raise RuntimeError("branding audio mix produced an empty file")
    return dest


def _pad_inputs(music: Path | None, duration: float, *, start: float) -> list[str]:
    if music is None:
        return ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
    return ["-ss", f"{max(0.0, start):.3f}", "-t", f"{duration:.3f}", "-i", str(music)]


def _pad_filter(
    index: int,
    duration: float,
    *,
    fade_in: float,
    fade_out: float,
    sample_rate: int,
    label: str = "intro",
) -> str:
    fade_out_st = max(0.05, duration - fade_out)
    return (
        f"[{index}:a]aformat=sample_fmts=fltp:sample_rates={sample_rate}:channel_layouts=stereo,"
        f"volume={MUSIC_LOUD_DB}dB,"
        f"afade=t=in:st=0:d={fade_in:.2f},"
        f"afade=t=out:st={fade_out_st:.2f}:d={min(fade_out, duration):.2f},"
        f"atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[{label}]"
    )
