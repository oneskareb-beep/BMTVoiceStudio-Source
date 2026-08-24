"""FFmpeg is the final Video Maker renderer. Commands are built as argv lists."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegError, FFmpegService
from bmt_voice_studio.config.paths import logs_dir
from bmt_voice_studio.video.composition import overlay_windows, window_is_active, xfade_offsets
from bmt_voice_studio.video.errors import RenderCancelled, VideoMakerError
from bmt_voice_studio.video.geometry import (
    ffmpeg_positioned_contain_filter,
    ffmpeg_cover_filter,
    ffmpeg_mid_band_filter,
    ffmpeg_positioned_cover_filter,
    scene_normalize_filter,
)
from bmt_voice_studio.video.models import (
    AnimationMode,
    CompositionPlan,
    FitMode,
    SceneKind,
    ScenePlan,
    VideoProject,
)
from bmt_voice_studio.video.encode import ffmpeg_crf_for, ffmpeg_x264_preset
from bmt_voice_studio.video.paths import unique_output_path, video_render_temp_dir
from bmt_voice_studio.video.rotation import prepend_autorotate
from bmt_voice_studio.video.title_cards import (
    render_intro_card,
    render_lower_third,
    render_outro_card,
    render_overlay_png,
    render_week_card,
)

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, str], None]

NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0


def ffmpeg_executable(ffmpeg: FFmpegService | None = None) -> str:
    ff = ffmpeg or FFmpegService()
    return ff.find()


def fit_filter(
    fit_mode: str,
    width: int,
    height: int,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    pad_color: str = "0x0F141C",
) -> str:
    mode = (fit_mode or "").lower()
    if mode == FitMode.BAND.value:
        # Mid-band paysage: ignore pan/zoom so the 1/4·2/4·1/4 layout stays locked.
        return ffmpeg_mid_band_filter(width, height, pad_color)
    if mode == FitMode.FIT.value:
        return ffmpeg_positioned_contain_filter(width, height, crop_x, crop_y, zoom, pad_color)
    if abs(float(crop_x or 0.0)) > 0.001 or abs(float(crop_y or 0.0)) > 0.001 or abs(float(zoom or 1.0) - 1.0) > 0.001:
        return ffmpeg_positioned_cover_filter(width, height, crop_x, crop_y, zoom, pad_color)
    return ffmpeg_cover_filter(width, height)


def ken_burns_filter(
    animation: str,
    duration: float,
    fps: int,
    width: int,
    height: int,
    fit_mode: str = FitMode.FILL.value,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    zoom_amount: float = 0.10,
    fade_in: float = 0.0,
) -> str:
    """Subtle Ken Burns. Work canvas is ~11% larger so zoom/pan never stretches."""
    frames = max(1, int(round(float(duration) * fps)))
    work_w = int(round(width * 1.12))
    work_h = int(round(height * 1.12))
    # Keep even dimensions for yuv420p / x264.
    work_w += work_w % 2
    work_h += work_h % 2
    base = fit_filter(fit_mode, work_w, work_h, crop_x, crop_y, zoom)
    mode = (animation or AnimationMode.ZOOM_IN.value).lower()
    amount = max(0.02, min(0.12, float(zoom_amount or 0.10)))
    zoom_step = amount / max(1, frames)
    zmax = 1.0 + amount
    if mode == AnimationMode.STATIC.value:
        zp = f"zoompan=z=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}"
    elif mode == AnimationMode.ZOOM_OUT.value:
        zp = (
            f"zoompan=z='max({zmax:.3f}-{zoom_step}*on,1.0)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}"
        )
    elif mode == AnimationMode.PAN_LR.value:
        zp = (
            f"zoompan=z={1.0 + amount * 0.8:.3f}:"
            f"x='(iw-iw/zoom)*on/{max(1, frames - 1)}':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}"
        )
    elif mode == AnimationMode.PAN_RL.value:
        zp = (
            f"zoompan=z={1.0 + amount * 0.8:.3f}:"
            f"x='(iw-iw/zoom)*(1-on/{max(1, frames - 1)})':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}"
        )
    else:
        zp = (
            f"zoompan=z='min(1.0+{zoom_step}*on,{zmax:.3f})':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps}"
        )
    vf = f"{base},{zp},{scene_normalize_filter(width, height, fps)}"
    fade = max(0.0, float(fade_in or 0.0))
    if fade > 0.04:
        vf = f"{vf},fade=t=in:st=0:d={min(fade, max(0.2, duration * 0.35)):.3f}"
    return vf


def video_clip_filter(
    duration: float,
    fps: int,
    width: int,
    height: int,
    fit_mode: str,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    rotation: int = 0,
) -> str:
    base = fit_filter(fit_mode, width, height, crop_x, crop_y, zoom)
    vf = (
        f"{base},{scene_normalize_filter(width, height, fps)},"
        f"trim=duration={duration:.3f},setpts=PTS-STARTPTS"
    )
    return prepend_autorotate(vf, rotation)


def overlay_keep_alpha_filter(
    width: int,
    height: int,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    fit_mode: str = FitMode.FILL.value,
) -> str:
    """Place a cutout on a transparent 9:16 canvas so zoom/move keep punch-through."""
    pad = "black@0"
    if (fit_mode or "").lower() == FitMode.FIT.value:
        geom = ffmpeg_positioned_contain_filter(width, height, crop_x, crop_y, zoom, pad)
    else:
        geom = ffmpeg_positioned_cover_filter(width, height, crop_x, crop_y, zoom, pad)
    return f"format=rgba,{geom}"


def build_image_scene_command(
    ffmpeg: str,
    image_path: str,
    dest: str,
    *,
    duration: float,
    fps: int,
    width: int,
    height: int,
    animation: str,
    fit_mode: str,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    zoom_amount: float = 0.10,
    fade_in: float = 0.0,
    overlay_path: str = "",
    overlay_zoom: float = 1.0,
    overlay_crop_x: float = 0.0,
    overlay_crop_y: float = 0.0,
    overlay_fit_mode: str = FitMode.FILL.value,
) -> list[str]:
    frames = max(1, int(round(float(duration) * fps)))
    vf = ken_burns_filter(
        animation,
        duration,
        fps,
        width,
        height,
        fit_mode,
        crop_x,
        crop_y,
        zoom,
        zoom_amount=zoom_amount,
        fade_in=fade_in,
    )
    if overlay_path and Path(overlay_path).is_file():
        ov = overlay_keep_alpha_filter(
            width,
            height,
            overlay_crop_x,
            overlay_crop_y,
            overlay_zoom,
            overlay_fit_mode,
        )
        return [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loop",
            "1",
            "-i",
            image_path,
            "-loop",
            "1",
            "-i",
            overlay_path,
            "-filter_complex",
            f"[0:v]{vf}[bg];[1:v]{ov}[ov];[bg][ov]overlay=0:0:format=auto,format=yuv420p,setsar=1",
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-movflags",
            "+faststart",
            dest,
        ]
    return [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loop",
        "1",
        "-i",
        image_path,
        "-vf",
        vf,
        "-frames:v",
        str(frames),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-color_range",
        "tv",
        "-movflags",
        "+faststart",
        dest,
    ]


def build_video_scene_command(
    ffmpeg: str,
    clip_path: str,
    dest: str,
    *,
    duration: float,
    fps: int,
    width: int,
    height: int,
    fit_mode: str,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
    zoom: float = 1.0,
    trim_start: float = 0.0,
    overlay_path: str = "",
    overlay_zoom: float = 1.0,
    overlay_crop_x: float = 0.0,
    overlay_crop_y: float = 0.0,
    overlay_fit_mode: str = FitMode.FILL.value,
    rotation: int = 0,
) -> list[str]:
    vf = video_clip_filter(
        duration, fps, width, height, fit_mode, crop_x, crop_y, zoom, rotation=rotation
    )
    cmd = [ffmpeg, "-y", "-hide_banner", "-noautorotate"]
    if float(trim_start or 0.0) > 0.04:
        cmd.extend(["-ss", f"{float(trim_start):.3f}"])
    if overlay_path and Path(overlay_path).is_file():
        ov = overlay_keep_alpha_filter(
            width,
            height,
            overlay_crop_x,
            overlay_crop_y,
            overlay_zoom,
            overlay_fit_mode,
        )
        cmd.extend(
            [
                "-stream_loop",
                "-1",
                "-i",
                clip_path,
                "-loop",
                "1",
                "-i",
                overlay_path,
                "-an",
                "-filter_complex",
                f"[0:v]{vf}[bg];[1:v]{ov}[ov];[bg][ov]overlay=0:0:format=auto,format=yuv420p,setsar=1",
                "-t",
                f"{duration:.3f}",
                "-r",
                str(fps),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-color_range",
                "tv",
                dest,
            ]
        )
        return cmd
    cmd.extend(
        [
            "-stream_loop",
            "-1",
            "-i",
            clip_path,
            "-an",  # mute original clip audio — master audio is the timeline
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
            "-r",
            str(fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            dest,
        ]
    )
    return cmd


def _opaque_photo_source(scene: ScenePlan, plan: CompositionPlan) -> str:
    """Flatten transparent PNG/GIF/WebP onto the template color before Ken Burns."""
    src = Path(scene.media_path)
    try:
        from bmt_voice_studio.video.image_io import pad_rgb_for_template, prepare_still_for_encode

        dest = Path(plan.temp_dir or src.parent) / f"opaque_{src.stem}.png"
        return str(prepare_still_for_encode(src, dest, pad_rgb_for_template(plan.template_id)))
    except Exception:
        return str(src)


def _normalize_stream(src: str, label: str, width: int, height: int, fps: int) -> str:
    return f"{src}{scene_normalize_filter(width, height, fps)}{label};"


def build_xfade_filter_script(
    scene_count: int,
    durations: list[float],
    xfade: float,
    overlay_index: int,
    overlay_enable_t: float,
    extra_overlays: list[tuple[int, str]] | None = None,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
    fps: int = 30,
) -> str:
    lines: list[str] = []
    for i in range(max(1, scene_count)):
        lines.append(_normalize_stream(f"[{i}:v]", f"[n{i}]", canvas_w, canvas_h, fps))
    if scene_count == 1:
        current = "[n0]"
    else:
        offsets = xfade_offsets(durations, xfade)
        current = "[n0]"
        for i in range(1, scene_count):
            nxt = f"[n{i}]"
            label = f"[x{i}]" if i < scene_count - 1 else "[xv]"
            off = max(0.0, offsets[i - 1])
            left = current if i == 1 else f"[x{i - 1}]"
            lines.append(
                f"{left}{nxt}xfade=transition=fade:duration={xfade:.3f}:offset={off:.3f}{label};"
            )
        current = "[xv]" if scene_count > 1 else "[n0]"
    overlays: list[tuple[int, str]] = [(overlay_index, f"gte(t,{overlay_enable_t:.3f})")]
    if extra_overlays:
        overlays = list(extra_overlays)
    dw = max(2, int(canvas_w) - int(canvas_w) % 2)
    dh = max(2, int(canvas_h) - int(canvas_h) % 2)
    for i, (idx, enable) in enumerate(overlays):
        scaled = f"[ov{i}]"
        lines.append(f"[{idx}:v]scale={dw}:{dh},format=rgba{scaled};")
        nxt_label = f"[o{i}]" if i < len(overlays) - 1 else "[vcomp]"
        lines.append(
            f"{current}{scaled}overlay=0:0:enable='{enable}':format=auto{nxt_label};"
        )
        current = f"[o{i}]"
    if overlays:
        current = "[vcomp]"
    lines.append(f"{current}setsar=1,format=yuv420p[vout]")
    return "\n".join(lines)


def build_branded_timeline_filter(
    intro_count: int,
    media_count: int,
    media_durations: list[float],
    xfade: float,
    outro_count: int,
    extra_overlays: list[tuple[int, str]] | None,
    *,
    canvas_w: int,
    canvas_h: int,
    fps: int = 30,
) -> str:
    """Concat exact intro/outro pads around an xfaded media bed."""
    intro_count = 1 if intro_count else 0
    outro_count = 1 if outro_count else 0
    media_count = max(1, int(media_count))
    lines: list[str] = []
    media_start = intro_count
    if intro_count:
        lines.append(_normalize_stream("[0:v]", "[intro]", canvas_w, canvas_h, fps))
    if media_count == 1:
        lines.append(
            _normalize_stream(f"[{media_start}:v]", "[media]", canvas_w, canvas_h, fps)
        )
        media_label = "[media]"
    else:
        for i in range(media_count):
            lines.append(
                _normalize_stream(
                    f"[{media_start + i}:v]",
                    f"[nm{i}]",
                    canvas_w,
                    canvas_h,
                    fps,
                )
            )
        offsets = xfade_offsets(media_durations, xfade)
        current = "[nm0]"
        for i in range(1, media_count):
            nxt = f"[nm{i}]"
            label = f"[mx{i}]" if i < media_count - 1 else "[media]"
            left = current if i == 1 else f"[mx{i - 1}]"
            lines.append(
                f"{left}{nxt}xfade=transition=fade:duration={xfade:.3f}:offset={max(0.0, offsets[i - 1]):.3f}{label};"
            )
            current = label
        media_label = "[media]"
    if outro_count:
        lines.append(
            _normalize_stream(
                f"[{intro_count + media_count}:v]",
                "[outro]",
                canvas_w,
                canvas_h,
                fps,
            )
        )
    pieces: list[str] = []
    if intro_count:
        pieces.append("[intro]")
    pieces.append(media_label)
    if outro_count:
        pieces.append("[outro]")
    if len(pieces) == 1:
        current = pieces[0]
    else:
        lines.append("".join(pieces) + f"concat=n={len(pieces)}:v=1:a=0[vcat];")
        current = "[vcat]"
    overlays = list(extra_overlays or [])
    dw = max(2, int(canvas_w) - int(canvas_w) % 2)
    dh = max(2, int(canvas_h) - int(canvas_h) % 2)
    for i, (idx, enable) in enumerate(overlays):
        scaled = f"[ov{i}]"
        lines.append(f"[{idx}:v]scale={dw}:{dh},format=rgba{scaled};")
        nxt_label = f"[o{i}]" if i < len(overlays) - 1 else "[vcomp]"
        lines.append(
            f"{current}{scaled}overlay=0:0:enable='{enable}':format=auto{nxt_label};"
        )
        current = f"[o{i}]"
    if overlays:
        current = "[vcomp]"
    lines.append(f"{current}setsar=1,format=yuv420p[vout]")
    return "\n".join(lines)


def build_final_command(
    ffmpeg: str,
    scene_paths: list[str],
    overlay_path: str,
    audio_path: str,
    filter_graph: str,
    dest: str,
    *,
    audio_duration: float,
    fps: int,
    crf: int,
    audio_bitrate_k: int,
    audio_sample_rate: int,
    extra_overlay_paths: list[str] | None = None,
    preset: str = "medium",
    audio_start: float = 0.0,
    caption_filter: str = "",
) -> list[str]:
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-progress",
        "pipe:1",
        "-stats_period",
        "0.5",
    ]
    for path in scene_paths:
        cmd.extend(["-i", path])
    cmd.extend(["-i", overlay_path])
    for extra in extra_overlay_paths or []:
        cmd.extend(["-i", extra])
    if float(audio_start or 0.0) > 0.04:
        cmd.extend(["-ss", f"{float(audio_start):.3f}"])
    cmd.extend(["-i", audio_path])
    graph = filter_graph.replace("\n", "")
    if caption_filter:
        graph = graph.replace("[vout]", "[vpre]", 1) + f";[vpre]{caption_filter}[vout]"
    audio_index = len(scene_paths) + 1 + len(extra_overlay_paths or [])
    cmd.extend(
        [
            "-filter_complex",
            graph,
            "-map",
            "[vout]",
            "-map",
            f"{audio_index}:a:0",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
            "-color_range",
            "tv",
            "-r",
            str(fps),
            "-c:a",
            "aac",
            "-b:a",
            f"{audio_bitrate_k}k",
            "-ar",
            str(audio_sample_rate),
            "-ac",
            "2",
            "-t",
            f"{audio_duration:.3f}",
            "-movflags",
            "+faststart",
            dest,
        ]
    )
    return cmd


def extract_video_frame_command(ffmpeg: str, clip_path: str, dest: str, width: int, height: int) -> list[str]:
    vf = f"{ffmpeg_cover_filter(width, height)},format=rgb24"
    return [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-ss",
        "0.3",
        "-i",
        clip_path,
        "-frames:v",
        "1",
        "-vf",
        vf,
        dest,
    ]


def _parse_progress_seconds(line: str) -> float | None:
    line = line.strip()
    if line.startswith("out_time_ms="):
        try:
            return max(0.0, int(line.split("=", 1)[1]) / 1_000_000.0)
        except Exception:
            return None
    if line.startswith("out_time_us="):
        try:
            return max(0.0, int(line.split("=", 1)[1]) / 1_000_000.0)
        except Exception:
            return None
    if line.startswith("out_time="):
        m = re.match(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return None


def ensure_disk_space(target: Path, needed_bytes: int = 400 * 1024 * 1024) -> None:
    try:
        usage = shutil.disk_usage(target.anchor or str(target))
    except Exception:
        return
    if usage.free < needed_bytes:
        raise VideoMakerError("There is not enough free disk space to generate this video.")


def ensure_output_writable(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        try:
            with dest.open("ab"):
                pass
        except OSError as exc:
            raise VideoMakerError(
                "The output file is in use. Close the video player and try again."
            ) from exc


class VideoRenderer:
    def __init__(self, ffmpeg: FFmpegService | None = None) -> None:
        self.ff = ffmpeg or FFmpegService()
        self._proc: subprocess.Popen[str] | None = None
        self._cancelled = False
        self.last_log_path: Path | None = None
        self.ffmpeg_path: str = ""
        self.last_metrics: dict = {}

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise RenderCancelled()

    def _run(
        self,
        cmd: list[str],
        *,
        log_path: Path,
        timeout: float = 3600,
        progress: ProgressCb | None = None,
        stage: str = "Rendering...",
        stage_start: int = 0,
        stage_end: int = 100,
        expected_duration: float = 0.0,
    ) -> None:
        self._raise_if_cancelled()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n$ " + " ".join(cmd) + "\n")
            log.flush()
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=NO_WINDOW,
                )
            except FileNotFoundError as exc:
                raise VideoMakerError("FFmpeg was not found. Reinstall BMT Voice Studio.") from exc
            assert self._proc.stdout is not None
            start = time.time()
            combined: list[str] = []
            last_pct = stage_start
            last_beat = start
            last_output = start
            stop_watch = False

            def _watchdog() -> None:
                nonlocal last_pct, last_beat
                while not stop_watch:
                    time.sleep(1.0)
                    proc = self._proc
                    if proc is None or proc.poll() is not None:
                        return
                    now = time.time()
                    if now - start > timeout:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        return
                    # Silent FFmpeg (no stdout) still needs a live progress pulse.
                    if progress and now - last_output >= 3.0 and now - last_beat >= 2.5:
                        last_pct = min(stage_end - 1, max(stage_start, last_pct + 1))
                        try:
                            progress(last_pct, f"{stage} (working…)")
                        except Exception:
                            pass
                        last_beat = now

            watcher = threading.Thread(target=_watchdog, name="ffmpeg-watch", daemon=True)
            watcher.start()
            try:
                for line in self._proc.stdout:
                    combined.append(line)
                    log.write(line)
                    last_output = time.time()
                    sec = _parse_progress_seconds(line)
                    now = last_output
                    if progress and expected_duration > 0 and sec is not None:
                        frac = min(1.0, sec / expected_duration)
                        pct = stage_start + int((stage_end - stage_start) * frac)
                        last_pct = min(99, pct)
                        progress(last_pct, stage)
                        last_beat = now
                    elif progress and now - last_beat >= 2.5:
                        last_pct = min(stage_end - 1, max(stage_start, last_pct + 1))
                        progress(last_pct, f"{stage} (working…)")
                        last_beat = now
                    if self._cancelled:
                        self.cancel()
                        raise RenderCancelled()
                    if time.time() - start > timeout:
                        self.cancel()
                        raise VideoMakerError("Video rendering timed out.")
                code = self._proc.wait(timeout=30)
            finally:
                stop_watch = True
                self._proc = None
            if code != 0:
                tail = "".join(combined)[-1200:]
                raise VideoMakerError(
                    "Video could not be generated. See Troubleshooting for the technical log.",
                    technical=tail,
                )

    def render(
        self,
        project: VideoProject,
        plan: CompositionPlan,
        *,
        progress: ProgressCb | None = None,
        keep_temp_on_success: bool = False,
    ) -> Path:
        self._cancelled = False
        ffmpeg = ffmpeg_executable(self.ff)
        self.ffmpeg_path = ffmpeg
        dest = Path(plan.output_path)
        ensure_disk_space(dest)
        dest = unique_output_path(dest)
        plan.output_path = str(dest)
        ensure_output_writable(dest)

        job_id = plan.job_id or dest.stem
        temp = Path(plan.temp_dir) if plan.temp_dir else video_render_temp_dir(job_id)
        temp.mkdir(parents=True, exist_ok=True)
        plan.temp_dir = str(temp)
        log_path = temp / "render.log"
        self.last_log_path = log_path
        log_path.write_text(f"ffmpeg={ffmpeg}\njob={job_id}\n", encoding="utf-8")
        started = time.time()
        self.last_metrics = {}

        def report(pct: int, msg: str) -> None:
            if progress:
                progress(pct, msg)

        try:
            report(2, "Preparing")
            intro_png = render_intro_card(project, temp / "intro.png", width=plan.width, height=plan.height)
            outro_png = render_outro_card(project, temp / "outro.png", width=plan.width, height=plan.height)
            overlay_png = render_overlay_png(project, temp / "overlay_compact.png", width=plan.width, height=plan.height)
            lower_png = render_lower_third(project, temp / "overlay_lower.png", width=plan.width, height=plan.height)
            week_png = render_week_card(project, temp / "overlay_week.png", width=plan.width, height=plan.height)
            plan.overlay_path = str(overlay_png)

            scene_files: list[Path] = []
            n = max(1, len(plan.scenes))
            report(8, "Composing")
            for i, scene in enumerate(plan.scenes):
                self._raise_if_cancelled()
                report(8 + int(36 * i / n), "Composing")
                out = temp / f"scene_{i:02d}.mp4"
                self._render_scene(
                    ffmpeg,
                    scene,
                    out,
                    plan,
                    intro_png=intro_png,
                    outro_png=outro_png,
                    log_path=log_path,
                    progress=progress,
                    stage_start=8 + int(36 * i / n),
                    stage_end=8 + int(36 * (i + 1) / n),
                )
                scene_files.append(out)

            report(45, "Preparing overlays")
            has_verse = bool(
                (project.memory_verse or "").strip()
                or (project.branding.week_focus and (project.week_focus or "").strip())
            )
            windows = overlay_windows(
                plan.intro_duration,
                plan.audio_duration,
                plan.outro_duration,
                crossfade_seconds=plan.crossfade_seconds,
                has_verse=has_verse,
            )
            intro_files = [p for p, s in zip(scene_files, plan.scenes, strict=False) if s.kind == SceneKind.INTRO.value]
            outro_files = [p for p, s in zip(scene_files, plan.scenes, strict=False) if s.kind == SceneKind.OUTRO.value]
            media_files = [
                p
                for p, s in zip(scene_files, plan.scenes, strict=False)
                if s.kind not in {SceneKind.INTRO.value, SceneKind.OUTRO.value}
            ]
            media_durs = [
                s.duration
                for s in plan.scenes
                if s.kind not in {SceneKind.INTRO.value, SceneKind.OUTRO.value}
            ]
            ordered_files = intro_files + media_files + outro_files
            n_scenes = len(ordered_files)
            extra: list[tuple[int, str]] = []
            extra_paths: list[str] = []

            def _add_overlay(path: Path, window: tuple[float, float]) -> None:
                if not window_is_active(window):
                    return
                extra.append(
                    (
                        n_scenes + len(extra_paths),
                        f"between(t,{window[0]:.3f},{window[1]:.3f})",
                    )
                )
                extra_paths.append(str(path))

            _add_overlay(lower_png, windows["lower_third"])
            _add_overlay(overlay_png, windows["compact"])
            if has_verse:
                _add_overlay(week_png, windows["week_card"])
            if not extra_paths:
                extra.append((n_scenes, "0"))
                extra_paths.append(str(overlay_png))
            script = build_branded_timeline_filter(
                len(intro_files),
                max(1, len(media_files)),
                media_durs or [plan.audio_duration],
                plan.crossfade_seconds,
                len(outro_files),
                extra,
                canvas_w=plan.width,
                canvas_h=plan.height,
                fps=plan.fps,
            )
            (temp / "xfade.txt").write_text(script, encoding="utf-8")
            first_overlay = extra_paths[0]
            rest_overlays = extra_paths[1:]
            caption_filter = ""
            if project.show_captions or project.branding.captions:
                from bmt_voice_studio.video.captions import (
                    captions_for_language,
                    clip_caption_cues,
                    ffmpeg_ass_filter,
                    shift_caption_cues,
                    write_ass,
                )

                cues = captions_for_language(
                    project.devotional_date,
                    project.language,
                    audio_duration=plan.audio_duration,
                    skip_header=bool(getattr(project, "skip_caption_header", True)),
                    caption_mode=str(getattr(project, "caption_content", "") or ""),
                )
                if cues:
                    offset = float(plan.intro_duration or 0.0) - float(plan.audio_start or 0.0)
                    cues = shift_caption_cues(cues, offset)
                    # Hide only on exclusive intro/outro cards so school text
                    # starts and finishes with the spoken voice (not lower-third gaps).
                    hide = [
                        windows["intro"],
                        windows.get("outro", (0.0, 0.0)),
                        (-3600.0, 0.0),
                    ]
                    cues = clip_caption_cues(cues, hide_ranges=hide)
                if cues:
                    ass_path = temp / "captions.ass"
                    write_ass(
                        cues,
                        ass_path,
                        width=plan.width,
                        height=plan.height,
                        style=getattr(project, "text_style", None),
                    )
                    plan.caption_path = str(ass_path)
                    caption_filter = ffmpeg_ass_filter(ass_path)
            mixed = temp / "branded_audio.m4a"
            report(48, "Mixing branded audio")
            from bmt_voice_studio.video.branding_audio import mix_branding_audio, resolve_music_path

            music = Path(getattr(project, "music_path", "") or plan.music_path or "")
            resolved_music = resolve_music_path(music if music.is_file() else None)
            mix_branding_audio(
                Path(plan.audio_path),
                mixed,
                music_path=resolved_music,
                intro_sec=plan.intro_duration,
                outro_sec=plan.outro_duration,
                master_duration=plan.audio_duration,
                sample_rate=project.output_profile.audio_sample_rate,
                intro_start=float(getattr(project, "music_intro_start", 0.0) or 0.0),
                outro_start=float(getattr(project, "music_outro_start", -1.0)),
            )
            plan.mixed_audio_path = str(mixed)
            total = float(plan.total_duration or (plan.intro_duration + plan.audio_duration + plan.outro_duration))
            plan.total_duration = total
            report(49, "Preparing export")
            final_cmd = build_final_command(
                ffmpeg,
                [str(p) for p in ordered_files],
                first_overlay,
                str(mixed),
                script,
                str(dest),
                audio_duration=total,
                fps=plan.fps,
                crf=ffmpeg_crf_for(
                    project.output_profile.video_crf, getattr(project, "render_speed", "standard")
                ),
                audio_bitrate_k=project.output_profile.audio_bitrate_k,
                audio_sample_rate=project.output_profile.audio_sample_rate,
                extra_overlay_paths=rest_overlays,
                preset=ffmpeg_x264_preset(
                    getattr(project, "render_speed", "standard"),
                    preview=plan.width < 800,
                    width=plan.width,
                ),
                audio_start=float(plan.audio_start or 0.0),
                caption_filter=caption_filter,
            )
            # xfade + SAR/yuv420p normalize can run ~0.1x realtime on long WhatsApp jobs
            report(50, "Exporting video — please wait, this step can take several minutes")
            self._run(
                final_cmd,
                log_path=log_path,
                timeout=max(1800, float(total) * 20 + 300),
                progress=progress,
                stage="Exporting video",
                stage_start=50,
                stage_end=92,
                expected_duration=total,
            )
            if not dest.is_file() or dest.stat().st_size < 1024:
                raise VideoMakerError("Video could not be generated because the output file was empty.")
            report(94, "Writing output file")
            elapsed = max(0.01, time.time() - started)
            self.last_metrics = {
                "render_start": started,
                "render_end": time.time(),
                "elapsed_sec": round(elapsed, 2),
                "video_duration": round(float(plan.total_duration or plan.audio_duration or 0.0), 2),
                "output_bytes": dest.stat().st_size,
                "speed": round(float(plan.audio_duration or 0.0) / elapsed, 2),
                "scenes": len(plan.scenes),
                "width": plan.width,
                "height": plan.height,
                "language": project.language,
                "template_id": project.template_id,
                "render_speed": getattr(project, "render_speed", "standard"),
                "x264_preset": ffmpeg_x264_preset(
                    getattr(project, "render_speed", "standard"),
                    preview=plan.width < 800,
                    width=plan.width,
                ),
            }
            self._copy_failure_log = False  # type: ignore[attr-defined]
            report(97, "Cleaning temporary files")
            if not keep_temp_on_success:
                self._cleanup_temp(temp, keep_log=False)
            report(100, "Export complete")
            return dest
        except RenderCancelled:
            self._preserve_log(log_path)
            raise
        except VideoMakerError:
            self._preserve_log(log_path)
            raise
        except Exception as exc:
            self._preserve_log(log_path)
            raise VideoMakerError(
                "Video could not be generated. See Troubleshooting for the technical log.",
                technical=str(exc),
            ) from exc

    def _render_scene(
        self,
        ffmpeg: str,
        scene: ScenePlan,
        dest: Path,
        plan: CompositionPlan,
        *,
        intro_png: Path,
        outro_png: Path,
        log_path: Path,
        progress: ProgressCb | None,
        stage_start: int,
        stage_end: int,
    ) -> None:
        kind = scene.kind
        if kind in {SceneKind.INTRO.value, SceneKind.OUTRO.value}:
            src = intro_png if kind == SceneKind.INTRO.value else outro_png
            cmd = build_image_scene_command(
                ffmpeg,
                str(src),
                str(dest),
                duration=scene.duration,
                fps=plan.fps,
                width=plan.width,
                height=plan.height,
                animation=scene.animation_mode,
                fit_mode=FitMode.FILL.value,
                zoom_amount=0.045 if kind == SceneKind.INTRO.value else 0.05,
                fade_in=0.85 if kind == SceneKind.INTRO.value else 0.55,
            )
        elif kind == SceneKind.VIDEO.value:
            if not Path(scene.media_path).is_file():
                raise VideoMakerError(
                    "Video could not be generated because one of the selected clips is unavailable."
                )
            cmd = build_video_scene_command(
                ffmpeg,
                scene.media_path,
                str(dest),
                duration=scene.duration,
                fps=plan.fps,
                width=plan.width,
                height=plan.height,
                fit_mode=scene.fit_mode,
                crop_x=scene.crop_x,
                crop_y=scene.crop_y,
                zoom=scene.zoom,
                trim_start=scene.trim_start,
                overlay_path=scene.overlay_path,
                overlay_zoom=scene.overlay_zoom,
                overlay_crop_x=getattr(scene, "overlay_crop_x", 0.0),
                overlay_crop_y=getattr(scene, "overlay_crop_y", 0.0),
                overlay_fit_mode=getattr(scene, "overlay_fit_mode", FitMode.FILL.value),
                rotation=int(getattr(scene, "rotation", 0) or 0),
            )
        else:
            if not Path(scene.media_path).is_file():
                raise VideoMakerError(
                    "Video could not be generated because one of the selected photos is unavailable."
                )
            cmd = build_image_scene_command(
                ffmpeg,
                _opaque_photo_source(scene, plan),
                str(dest),
                duration=scene.duration,
                fps=plan.fps,
                width=plan.width,
                height=plan.height,
                animation=scene.animation_mode,
                fit_mode=scene.fit_mode,
                crop_x=scene.crop_x,
                crop_y=scene.crop_y,
                zoom=scene.zoom,
                overlay_path=scene.overlay_path,
                overlay_zoom=scene.overlay_zoom,
                overlay_crop_x=getattr(scene, "overlay_crop_x", 0.0),
                overlay_crop_y=getattr(scene, "overlay_crop_y", 0.0),
                overlay_fit_mode=getattr(scene, "overlay_fit_mode", FitMode.FILL.value),
            )
        self._run(
            cmd,
            log_path=log_path,
            # Real photos/clips (esp. large stills + Ken Burns) can encode well below realtime.
            timeout=max(480, scene.duration * 30 + 180),
            progress=progress,
            stage="Composing",
            stage_start=stage_start,
            stage_end=stage_end,
            expected_duration=scene.duration,
        )

    def _preserve_log(self, log_path: Path) -> None:
        try:
            if log_path.is_file():
                dest = logs_dir() / f"video_render_{log_path.parent.name}.log"
                shutil.copy2(log_path, dest)
                self.last_log_path = dest
        except Exception:
            logger.debug("Could not copy video render log", exc_info=True)

    def _cleanup_temp(self, temp: Path, *, keep_log: bool) -> None:
        try:
            if keep_log:
                return
            shutil.rmtree(temp, ignore_errors=True)
        except Exception:
            logger.debug("Temp cleanup failed for %s", temp, exc_info=True)


def last_video_render_log() -> Path | None:
    folder = logs_dir()
    logs = sorted(folder.glob("video_render_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return logs[0] if logs else None
