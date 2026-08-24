"""Download remote playlist items and merge into one audio file."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import httpx

from bmt_voice_studio.audio.ffmpeg_service import FFmpegError, FFmpegService
from bmt_voice_studio.core.filenames import sanitize_filename, unique_path
from bmt_voice_studio.core.models import PlaylistItem
from bmt_voice_studio.m3u.parser import is_url, validate_audio_magic

logger = logging.getLogger(__name__)

ProgressCb = Callable[[int, int, str], None]
CancelCb = Callable[[], bool]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "BMTVoiceStudio/1.0 (desktop; httpx)"
)


class DownloadError(Exception):
    def __init__(self, message: str, *, technical: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.technical = technical or message


async def download_item(
    item: PlaylistItem,
    dest_dir: Path,
    *,
    timeout: float = 120.0,
    client: httpx.AsyncClient | None = None,
) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not is_url(item.source):
        local = Path(item.source)
        if not local.exists():
            raise DownloadError(f"Local file not found: {item.source}")
        return local

    name = sanitize_filename(item.title or f"track_{item.index:02d}")
    # Guess extension from URL
    url_path = item.source.split("?", 1)[0]
    ext = Path(url_path).suffix.lower() or ".bin"
    if ext not in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}:
        ext = ".bin"
    dest = dest_dir / f"{item.index:02d}_{name}{ext}"

    owns_client = client is None
    client = client or httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        resp = await client.get(item.source)
        if resp.status_code >= 400:
            raise DownloadError(
                f"Download failed for item {item.index:02d} (HTTP {resp.status_code})."
            )
        data = resp.content
        ok, kind = validate_audio_magic(data)
        if not ok:
            raise DownloadError(f"Item {item.index:02d}: {kind}")
        if ext == ".bin":
            mapped = {".mp3": "mp3", ".wav": "wav", "mp3": ".mp3", "wav": ".wav"}
            if kind in ("mp3", "wav"):
                dest = dest.with_suffix(f".{kind}")
        dest.write_bytes(data)
        item.local_path = str(dest)
        return dest
    finally:
        if owns_client:
            await client.aclose()


async def download_and_merge(
    items: list[PlaylistItem],
    output_path: Path,
    *,
    pause_ms: int = 0,
    bitrate_kbps: int = 128,
    is_hls: bool = False,
    hls_url: str = "",
    timeout: float = 120.0,
    on_progress: ProgressCb | None = None,
    cancel_check: CancelCb | None = None,
    ffmpeg: FFmpegService | None = None,
) -> Path:
    ff = ffmpeg or FFmpegService()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    work = output_path.parent / "_download_work"
    work.mkdir(parents=True, exist_ok=True)

    if is_hls and hls_url:
        if on_progress:
            on_progress(0, 1, "Ingesting HLS stream with FFmpeg…")
        out = unique_path(output_path) if output_path.exists() else output_path
        try:
            ff.run(
                [
                    "-y",
                    "-i",
                    hls_url,
                    "-c:a",
                    "libmp3lame",
                    "-b:a",
                    f"{bitrate_kbps}k",
                    "-ac",
                    "1",
                    "-vn",
                    str(out),
                ],
                timeout=1800,
            )
        except FFmpegError as exc:
            msg = exc.message
            tech = (exc.technical or "").lower()
            if "403" in tech or "401" in tech or "encrypt" in tech:
                raise DownloadError(
                    "This HLS stream appears protected, expired, or unavailable.",
                    technical=exc.technical,
                ) from exc
            raise DownloadError(
                "Could not ingest the HLS stream. It may be expired or unsupported.",
                technical=exc.technical,
            ) from exc
        return out

    enabled = [i for i in items if i.enabled]
    paths: list[Path] = []
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        total = len(enabled)
        for idx, item in enumerate(enabled, start=1):
            if cancel_check and cancel_check():
                raise DownloadError("Cancelled.")
            if on_progress:
                on_progress(idx, total, f"Downloading {idx} of {total}…")
            path = await download_item(item, work, timeout=timeout, client=client)
            # Validate with ffmpeg when magic was unknown
            paths.append(path)

    if not paths:
        raise DownloadError("No audio items to merge.")

    list_file = work / "concat.txt"
    lines = []
    silence = None
    if pause_ms > 0:
        silence = work / f"silence_{pause_ms}.mp3"
        ff.generate_silence(silence, pause_ms)

    for i, p in enumerate(paths):
        # Normalize
        norm = work / f"norm_{i:03d}.mp3"
        try:
            ff.convert(p, norm, bitrate_kbps=bitrate_kbps)
        except FFmpegError as exc:
            raise DownloadError(
                f"Item {i + 1} is not valid audio or could not be decoded.",
                technical=exc.technical,
            ) from exc
        if i > 0 and silence is not None:
            esc_s = str(silence.resolve()).replace("\\", "/").replace("'", "'\\''")
            lines.append(f"file '{esc_s}'")
        esc = str(norm.resolve()).replace("\\", "/").replace("'", "'\\''")
        lines.append(f"file '{esc}'")

    list_file.write_text("\n".join(lines), encoding="utf-8")
    out = unique_path(output_path) if output_path.exists() else output_path
    if on_progress:
        on_progress(len(paths), len(paths), "Merging audio…")
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
            str(out),
        ]
    )
    return out
