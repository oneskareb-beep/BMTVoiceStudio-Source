"""M3U / M3U8 playlist parsing and HLS detection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from bmt_voice_studio.core.models import PlaylistItem

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".wma"}
URL_RE = re.compile(r"^https?://", re.I)


@dataclass
class PlaylistParseResult:
    items: list[PlaylistItem]
    is_hls: bool = False
    is_master_playlist: bool = False
    errors: list[str] | None = None
    raw_header: str = ""


def is_url(value: str) -> bool:
    return bool(URL_RE.match(value.strip()))


def is_probably_audio_url(url: str) -> bool:
    lower = url.lower().split("?", 1)[0]
    return any(lower.endswith(ext) for ext in AUDIO_EXTS) or "audio" in lower


def detect_hls(content: str) -> tuple[bool, bool]:
    """Return (is_hls, is_master)."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    tags = {ln for ln in lines if ln.startswith("#EXT")}
    has_m3u8_header = any(ln.startswith("#EXTM3U") for ln in lines)
    has_stream_inf = any(ln.startswith("#EXT-X-STREAM-INF") for ln in lines)
    has_target_duration = any(ln.startswith("#EXT-X-TARGETDURATION") for ln in lines)
    has_media_sequence = any(ln.startswith("#EXT-X-MEDIA-SEQUENCE") for ln in lines)
    has_inf = any(ln.startswith("#EXTINF") for ln in lines)
    # HLS media playlist typically has TARGETDURATION / MEDIA-SEQUENCE
    if has_stream_inf:
        return True, True
    if has_target_duration or has_media_sequence:
        return True, False
    # Simple M3U with EXTINF pointing to complete files is NOT HLS
    if has_m3u8_header and has_inf and not (has_target_duration or has_media_sequence):
        # Could still be HLS without those tags — check segment extensions
        uris = [ln for ln in lines if not ln.startswith("#")]
        if uris and all(u.lower().split("?", 1)[0].endswith(".ts") for u in uris):
            return True, False
        return False, False
    return False, False


def parse_m3u_content(content: str, *, base_url: str = "") -> PlaylistParseResult:
    errors: list[str] = []
    if content is None:
        return PlaylistParseResult(items=[], errors=["Empty playlist."])

    text = content.replace("\r\n", "\n").replace("\r", "\n")
    is_hls, is_master = detect_hls(text)
    items: list[PlaylistItem] = []
    title = ""
    duration: float | None = None
    index = 1

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            # #EXTINF:123.4,Title
            body = line[8:]
            if "," in body:
                dur_s, title = body.split(",", 1)
                title = title.strip()
                try:
                    duration = float(dur_s)
                except ValueError:
                    duration = None
            else:
                title = ""
                try:
                    duration = float(body)
                except ValueError:
                    duration = None
            continue
        if line.startswith("#"):
            continue

        source = line
        if base_url and not is_url(source) and not Path(source).exists():
            source = urljoin(base_url, source)

        items.append(
            PlaylistItem(
                index=index,
                source=source,
                title=title or Path(source.split("?", 1)[0]).name,
                duration=duration,
                is_hls=is_hls,
            )
        )
        index += 1
        title = ""
        duration = None

    if is_hls and is_master:
        errors.append(
            "This looks like an HLS master playlist. BMT Voice Studio will hand it to FFmpeg."
        )

    if not items and not is_hls:
        errors.append("No playlist entries found.")

    return PlaylistParseResult(
        items=items,
        is_hls=is_hls,
        is_master_playlist=is_master,
        errors=errors or None,
    )


def parse_m3u_file(path: Path) -> PlaylistParseResult:
    content = path.read_text(encoding="utf-8", errors="replace")
    base = path.parent.as_uri() + "/"
    result = parse_m3u_content(content, base_url=base)
    # Resolve relative local paths
    for item in result.items:
        if not is_url(item.source):
            candidate = Path(item.source)
            if not candidate.is_absolute():
                candidate = (path.parent / candidate).resolve()
            item.source = str(candidate)
    return result


def parse_url_list(text: str) -> PlaylistParseResult:
    """Parse one URL/path per line (PASTE AUDIO URLS)."""
    items: list[PlaylistItem] = []
    index = 1
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        items.append(
            PlaylistItem(
                index=index,
                source=line,
                title=Path(line.split("?", 1)[0]).name,
            )
        )
        index += 1
    errors = ["No URLs found."] if not items else None
    return PlaylistParseResult(items=items, errors=errors)


def validate_audio_magic(data: bytes) -> tuple[bool, str]:
    """Reject HTML error pages and other non-audio payloads."""
    if not data or len(data) < 12:
        return False, "Downloaded file is too small to be audio."
    head = data[:256]
    lower = head.lower()
    if lower.lstrip().startswith(b"<!doctype") or lower.lstrip().startswith(b"<html"):
        return False, "Server returned an HTML page instead of audio."
    if lower.lstrip().startswith(b"{") and b"error" in lower:
        return False, "Server returned a JSON error instead of audio."
    # Common audio signatures
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb" or head[:2] == b"\xff\xf3":
        return True, "mp3"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return True, "wav"
    if head[4:8] == b"ftyp":
        return True, "mp4/m4a"
    if head[:4] == b"OggS":
        return True, "ogg"
    if head[:4] == b"fLaC":
        return True, "flac"
    # Allow unknown binary that is not HTML
    if b"<html" in lower or b"<HTML" in head:
        return False, "Content looks like HTML, not audio."
    return True, "unknown-binary"
