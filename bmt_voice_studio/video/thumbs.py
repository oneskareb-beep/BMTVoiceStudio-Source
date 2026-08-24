"""FFmpeg thumbnail extraction and disk cache (never decode whole videos in UI)."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.config.paths import cache_dir
from bmt_voice_studio.video.models import MediaType
from bmt_voice_studio.video.rotation import prepend_autorotate

NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
THUMB_SIZE = 160
PREVIEW_LONG_EDGE = 720


def thumbs_dir() -> Path:
    path = cache_dir() / "video_thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def thumb_cache_key(path: str, mtime: float, size: int, *, rotation: int = 0, square: bool = True) -> str:
    kind = "sq" if square else "fr"
    raw = f"{path}|{mtime:.0f}|{size}|{THUMB_SIZE}|r{int(rotation or 0)}|{kind}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:20]


def thumbnail_path_for(media_path: str, *, rotation: int = 0, square: bool = True) -> Path | None:
    p = Path(media_path)
    if not p.is_file():
        return None
    try:
        st = p.stat()
    except OSError:
        return None
    return thumbs_dir() / f"{thumb_cache_key(str(p.resolve()), st.st_mtime, st.st_size, rotation=rotation, square=square)}.jpg"


def extract_thumbnail(
    media_path: str,
    *,
    media_type: str = "",
    rotation: int = 0,
    square: bool = True,
    ffmpeg: FFmpegService | None = None,
) -> Path | None:
    src = Path(media_path)
    dest = thumbnail_path_for(str(src), rotation=rotation, square=square)
    if dest is None:
        return None
    if dest.is_file() and dest.stat().st_size > 32:
        return dest
    kind = (media_type or "").lower()
    if not kind:
        kind = MediaType.VIDEO.value if src.suffix.lower() in {".mp4", ".mov", ".m4v", ".avi", ".mkv"} else MediaType.IMAGE.value
    if kind == MediaType.IMAGE.value:
        try:
            from bmt_voice_studio.video.image_io import DEFAULT_PAD_RGB, flatten_rgba, open_rgba
            from PIL import Image

            im = flatten_rgba(open_rgba(src), DEFAULT_PAD_RGB)
            if square:
                im.thumbnail((THUMB_SIZE, THUMB_SIZE))
                canvas = Image.new("RGB", (THUMB_SIZE, THUMB_SIZE), DEFAULT_PAD_RGB)
                x = (THUMB_SIZE - im.width) // 2
                y = (THUMB_SIZE - im.height) // 2
                canvas.paste(im, (x, y))
                canvas.save(dest, "JPEG", quality=82)
            else:
                im.thumbnail((PREVIEW_LONG_EDGE, PREVIEW_LONG_EDGE))
                im.save(dest, "JPEG", quality=88)
            if dest.is_file() and dest.stat().st_size > 32:
                return dest
        except Exception:
            pass
    if square:
        geom = (
            f"scale={THUMB_SIZE}:{THUMB_SIZE}:force_original_aspect_ratio=increase,"
            f"crop={THUMB_SIZE}:{THUMB_SIZE}"
        )
    else:
        geom = f"scale={PREVIEW_LONG_EDGE}:{PREVIEW_LONG_EDGE}:force_original_aspect_ratio=decrease"
    vf = prepend_autorotate(geom, rotation)
    try:
        exe = (ffmpeg or FFmpegService()).find()
        cmd = [exe, "-y", "-hide_banner", "-loglevel", "error"]
        if kind == MediaType.VIDEO.value:
            # Seek after input so rotation metadata is applied consistently.
            cmd.extend(["-noautorotate", "-i", str(src), "-ss", "0.8"])
        else:
            cmd.extend(["-i", str(src)])
        cmd.extend(
            [
                "-frames:v",
                "1",
                "-vf",
                vf,
                "-pix_fmt",
                "yuvj420p",
                str(dest),
            ]
        )
        subprocess.run(cmd, capture_output=True, timeout=20, creationflags=NO_WINDOW, check=False)
        if dest.is_file() and dest.stat().st_size > 32:
            return dest
    except Exception:
        pass
    return None
