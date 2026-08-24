"""Media-aware output size estimates. Approximate — never guaranteed."""

from __future__ import annotations

from pathlib import Path

from bmt_voice_studio.video.models import PROFILE_WHATSAPP, MediaType, VideoProject
from bmt_voice_studio.video.paths import estimate_output_mb


def estimate_project_mb(project: VideoProject, *, preview_path: str = "") -> float:
    duration = max(0.0, float(project.audio_duration or 0.0))
    if duration <= 0:
        return 0.1
    profile_id = project.output_profile.id
    items = project.available_media()
    n_video = sum(1 for m in items if m.media_type == MediaType.VIDEO.value)
    n_still = max(0, len(items) - n_video)
    video_ratio = n_video / max(1, len(items))
    pid = (profile_id or "").strip().lower()
    if pid in {"whatsapp", "whatsapp_optimized", PROFILE_WHATSAPP}:
        video_kbps = 700 + 900 * video_ratio
        audio_kbps = 128
    elif pid in {"preview", "preview_540"}:
        video_kbps = 450 + 250 * video_ratio
        audio_kbps = 96
    else:
        video_kbps = 1400 + 1600 * video_ratio
        audio_kbps = 192
    if n_still and not n_video:
        video_kbps *= 0.55
    table = estimate_output_mb(duration, profile_id)
    computed = duration * (video_kbps + audio_kbps) / 8.0 / 1024.0
    preview = Path(preview_path) if preview_path else Path()
    if preview.is_file() and preview.stat().st_size > 1000:
        prev_mb = preview.stat().st_size / (1024 * 1024)
        scale = max(1.0, duration / 12.0) * (1080 * 1920) / (540 * 960)
        from_preview = prev_mb * scale * (0.55 if pid in {"whatsapp", PROFILE_WHATSAPP} else 0.85)
        computed = (computed * 2 + from_preview) / 3.0
    return max(0.1, round((computed + table) / 2.0, 1))
