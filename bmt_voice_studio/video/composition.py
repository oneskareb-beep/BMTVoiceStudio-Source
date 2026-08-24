"""Auto-compose algorithm: distribute media across the master audio timeline."""

from __future__ import annotations

import math
from pathlib import Path

from bmt_voice_studio.video.errors import MediaValidationError, MissingMediaError, VideoMakerError
from bmt_voice_studio.video.models import (
    AnimationMode,
    CompositionPlan,
    FitMode,
    MediaItem,
    MediaType,
    SceneKind,
    ScenePlan,
    VideoProject,
)
from bmt_voice_studio.video.paths import preview_output_path, video_output_path, video_render_temp_dir


def parse_timecode(raw: str | float | None) -> float:
    """Parse mm:ss or seconds into a non-negative start offset."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return max(0.0, float(raw))
    text = str(raw).strip()
    if not text:
        return 0.0
    if ":" in text:
        parts = text.split(":")
        try:
            nums = [float(p) for p in parts]
        except (TypeError, ValueError):
            return 0.0
        if len(nums) == 2:
            return max(0.0, nums[0] * 60.0 + nums[1])
        if len(nums) == 3:
            return max(0.0, nums[0] * 3600.0 + nums[1] * 60.0 + nums[2])
        return 0.0
    try:
        return max(0.0, float(text))
    except (TypeError, ValueError):
        return 0.0


MIN_SCENE_SECONDS = 8.0
TARGET_SCENE_SECONDS = 18.0
MAX_SCENE_SECONDS = 30.0
HARD_MIN_SCENE_SECONDS = 4.0
DEFAULT_XFADE = 0.75
DEFAULT_INTRO = 10.0
DEFAULT_OUTRO = 10.0
BRANDED_INTRO_SECONDS = 10.0
BRANDED_OUTRO_SECONDS = 10.0
INTRO_MIN = 4.0
INTRO_MAX = 10.0


def xfade_output_duration(scene_durations: list[float], xfade: float) -> float:
    if not scene_durations:
        return 0.0
    n = len(scene_durations)
    overlap = max(0.0, float(xfade)) * max(0, n - 1)
    return max(0.0, sum(float(d) for d in scene_durations) - overlap)


def xfade_offsets(scene_durations: list[float], xfade: float) -> list[float]:
    """FFmpeg xfade offset for each transition (len = n-1)."""
    xfade = max(0.0, float(xfade))
    offsets: list[float] = []
    acc = 0.0
    for i, duration in enumerate(scene_durations[:-1]):
        acc += float(duration)
        offsets.append(acc - xfade * (i + 1))
    return offsets


def choose_scene_count(bed_duration: float, n_assets: int) -> int:
    """How many visual sections to place on the media bed (excluding intro/outro)."""
    n_assets = max(1, int(n_assets))
    bed = max(0.0, float(bed_duration))
    if bed <= 0:
        return 1
    n_min_ok = max(1, int(bed / MIN_SCENE_SECONDS))  # max scenes still >= 8s
    n_hard = max(1, int(bed / HARD_MIN_SCENE_SECONDS))
    n_for_max = max(1, math.ceil(bed / MAX_SCENE_SECONDS))  # min scenes to stay <= 30s
    n_for_target = max(1, round(bed / TARGET_SCENE_SECONDS))

    if n_assets <= n_min_ok:
        n = max(n_assets, n_for_max, n_for_target)
        return max(n_assets, min(n, n_min_ok if n_min_ok >= n_assets else n))
    # Not enough time for every asset at 8s — still try to use as many as 4s allows.
    return max(1, min(n_assets, n_hard))


def photo_scene_duration(bed_duration: float, n_scenes: int) -> float:
    n_scenes = max(1, int(n_scenes))
    return max(HARD_MIN_SCENE_SECONDS, float(bed_duration) / n_scenes)


def resolve_animation(mode: str, index: int) -> str:
    raw = (mode or AnimationMode.AUTO.value).lower()
    if raw == AnimationMode.AUTO.value:
        cycle = (
            AnimationMode.ZOOM_IN.value,
            AnimationMode.PAN_LR.value,
            AnimationMode.ZOOM_OUT.value,
            AnimationMode.PAN_RL.value,
        )
        return cycle[index % len(cycle)]
    if raw in {m.value for m in AnimationMode}:
        return raw
    return AnimationMode.ZOOM_IN.value


def resolve_fit(mode: str) -> str:
    raw = (mode or FitMode.FILL.value).lower()
    if raw == FitMode.AUTO.value:
        return FitMode.FILL.value
    if raw in {m.value for m in FitMode}:
        return raw
    return FitMode.FILL.value


def branding_pads(project: VideoProject) -> tuple[float, float]:
    """Exact branded intro/outro pads added around the master audio."""
    intro = 0.0
    outro = 0.0
    if getattr(project, "intro_enabled", True):
        try:
            raw = project.intro_duration
            intro = BRANDED_INTRO_SECONDS if raw is None else float(raw)
        except (TypeError, ValueError):
            intro = BRANDED_INTRO_SECONDS
        if intro <= 0:
            intro = 0.0
        elif intro >= 8.0:
            intro = BRANDED_INTRO_SECONDS
    if getattr(project, "outro_enabled", True):
        try:
            raw = project.outro_duration
            outro = BRANDED_OUTRO_SECONDS if raw is None else float(raw)
        except (TypeError, ValueError):
            outro = BRANDED_OUTRO_SECONDS
        if outro <= 0:
            outro = 0.0
        elif outro >= 8.0:
            outro = BRANDED_OUTRO_SECONDS
    return intro, outro


def _intro_outro_for_audio(audio_duration: float, intro: float, outro: float) -> tuple[float, float]:
    audio_duration = max(0.0, float(audio_duration))
    try:
        intro = float(intro)
    except (TypeError, ValueError):
        intro = DEFAULT_INTRO
    try:
        outro = float(outro)
    except (TypeError, ValueError):
        outro = DEFAULT_OUTRO
    if intro <= 0:
        intro = 0.0
    else:
        intro = min(INTRO_MAX, max(INTRO_MIN, intro))
    outro = max(0.0, outro)
    if audio_duration < 10:
        intro = min(intro, max(3.0, audio_duration * 0.35)) if intro else 0.0
        outro = 0.0 if audio_duration < 12 else min(outro, 1.5)
    if intro + outro >= audio_duration * 0.55:
        intro = min(intro, max(3.0, audio_duration * 0.28)) if intro else 0.0
        outro = min(outro, max(0.0, audio_duration * 0.12))
    return intro, outro


def _template_color_bed(temp: Path, template_id: str, width: int, height: int) -> Path:
    """Solid template canvas so a cutout-only project can keep punch-through."""
    from PIL import Image

    from bmt_voice_studio.video.image_io import pad_rgb_for_template

    dest = Path(temp)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "template_bed.png"
    Image.new("RGB", (max(2, int(width)), max(2, int(height))), pad_rgb_for_template(template_id)).save(path, "PNG")
    return path


def build_composition_plan(
    project: VideoProject,
    *,
    output_path: Path | None = None,
    temp_dir: Path | None = None,
    job_id: str = "",
) -> CompositionPlan:
    audio_path = Path(project.audio_path) if project.audio_path else None
    if audio_path is None or not audio_path.is_file():
        raise VideoMakerError("No audio selected. Generate today's devotional or choose an audio file.")

    media = project.available_media()
    missing = project.missing_media()
    if not media:
        if missing:
            raise MissingMediaError(
                "Video could not be generated because one of the selected clips is unavailable."
            )
        raise VideoMakerError("No media selected. Add photos or videos before generating.")

    overlays = [m for m in media if getattr(m, "overlay", False)]
    beds = [m for m in media if not getattr(m, "overlay", False)]
    if not beds:
        overlays = overlays or list(media)
        bed_png = _template_color_bed(
            temp_dir or video_render_temp_dir(job_id or "preview"),
            project.template_id,
            project.output_profile.width,
            project.output_profile.height,
        )
        beds = [
            MediaItem(
                path=str(bed_png),
                media_type=MediaType.IMAGE.value,
                width=int(project.output_profile.width),
                height=int(project.output_profile.height),
            )
        ]

    audio_duration = float(project.audio_duration or 0.0)
    if audio_duration <= 0.4:
        raise VideoMakerError("The selected audio is missing or too short to build a video.")

    xfade = min(1.0, max(0.5, float(project.crossfade_seconds or DEFAULT_XFADE)))
    intro, outro = branding_pads(project)

    # Media bed matches the master audio exactly. Intro/outro are added around it.
    bed = max(HARD_MIN_SCENE_SECONDS, audio_duration)
    n_scenes = choose_scene_count(bed, len(beds))
    required_sum = bed + xfade * max(0, n_scenes - 1)
    each = photo_scene_duration(required_sum, n_scenes)

    scenes: list[ScenePlan] = []
    if intro > 0.2:
        scenes.append(
            ScenePlan(
                kind=SceneKind.INTRO.value,
                duration=intro,
                animation_mode=AnimationMode.ZOOM_IN.value,
                fit_mode=FitMode.FILL.value,
                order=0,
            )
        )
    for i in range(n_scenes):
        item = beds[i % len(beds)]
        overlay = overlays[i % len(overlays)] if overlays else None
        kind = SceneKind.VIDEO.value if item.media_type == MediaType.VIDEO.value else SceneKind.PHOTO.value
        scenes.append(
            ScenePlan(
                kind=kind,
                duration=each,
                media_path=item.path,
                media_type=item.media_type,
                fit_mode=resolve_fit(item.fit_mode),
                animation_mode=resolve_animation(item.animation_mode, i),
                order=i + 1,
                crop_x=item.crop_x,
                crop_y=item.crop_y,
                zoom=item.zoom,
                trim_start=item.trim_start,
                trim_end=item.trim_end,
                overlay_path=overlay.path if overlay else "",
                overlay_zoom=float(overlay.zoom) if overlay else 1.0,
                overlay_crop_x=float(overlay.crop_x) if overlay else 0.0,
                overlay_crop_y=float(overlay.crop_y) if overlay else 0.0,
                overlay_fit_mode=resolve_fit(overlay.fit_mode) if overlay else FitMode.FILL.value,
                rotation=int(getattr(item, "rotation", 0) or 0),
            )
        )
    if outro > 0.2:
        scenes.append(
            ScenePlan(
                kind=SceneKind.OUTRO.value,
                duration=outro,
                animation_mode=AnimationMode.ZOOM_OUT.value,
                fit_mode=FitMode.FILL.value,
                order=len(scenes),
            )
        )

    dest = output_path or video_output_path(
        project.devotional_date,
        project.language,
        profile_id=project.output_profile.id,
    )
    temp = temp_dir or video_render_temp_dir(job_id or "preview")
    return CompositionPlan(
        width=project.output_profile.width,
        height=project.output_profile.height,
        fps=project.output_profile.fps,
        intro_duration=intro,
        outro_duration=outro if outro > 0.2 else 0.0,
        crossfade_seconds=xfade,
        scenes=scenes,
        audio_path=str(audio_path),
        audio_duration=audio_duration,
        total_duration=intro + audio_duration + outro,
        output_path=str(dest),
        logo_path=project.logo_path,
        template_id=project.template_id,
        job_id=job_id,
        temp_dir=str(temp),
        music_path=str(getattr(project, "music_path", "") or ""),
    )


OVERLAY_GAP = 0.35
VERSE_TARGET = 10.0
VERSE_MIN = 2.4
LOWER_TARGET = 8.0
LOWER_MIN = 2.0
DISABLED_WINDOW = (0.0, 0.0)


def window_duration(window: tuple[float, float]) -> float:
    return max(0.0, float(window[1]) - float(window[0]))


def window_is_active(window: tuple[float, float], *, min_duration: float = 0.15) -> bool:
    return window_duration(window) >= min_duration


def ranges_overlap(
    a: tuple[float, float],
    b: tuple[float, float],
    *,
    eps: float = 0.02,
) -> bool:
    """True when two active windows share open time. Touching endpoints do not overlap."""
    if not window_is_active(a) or not window_is_active(b):
        return False
    return float(a[0]) < float(b[1]) - eps and float(b[0]) < float(a[1]) - eps


def overlay_windows(
    intro_duration: float,
    audio_duration: float,
    outro_duration: float = 0.0,
    *,
    crossfade_seconds: float = DEFAULT_XFADE,
    has_verse: bool = False,
) -> dict[str, tuple[float, float]]:
    """Timed overlay windows on the muxed timeline.

    Timeline is additive: [intro] + [master audio] + [outro].
    Priority: intro (exclusive) → memory-verse card → lower-third → outro (exclusive).
    Caption/verse/lower-third times are relative to speech start (intro offset).
    """
    del crossfade_seconds
    intro = max(0.0, float(intro_duration or 0.0))
    audio = max(0.0, float(audio_duration or 0.0))
    outro = max(0.0, float(outro_duration or 0.0))
    if outro <= 0.2:
        outro = 0.0
    main_start = intro
    outro_start = intro + audio
    total = outro_start + outro
    overlay_end = max(0.0, outro_start - OVERLAY_GAP) if outro else outro_start
    available = max(0.0, overlay_end - main_start)

    verse = DISABLED_WINDOW
    lower = DISABLED_WINDOW
    if has_verse and available >= VERSE_MIN:
        verse_delay = 0.25 if available > VERSE_MIN + 0.4 else 0.12
        if available >= VERSE_MIN + OVERLAY_GAP + LOWER_MIN:
            usable = max(VERSE_MIN + LOWER_MIN, available - verse_delay - OVERLAY_GAP)
            verse_dur = min(VERSE_TARGET, usable - LOWER_MIN)
            verse_dur = max(VERSE_MIN, verse_dur)
            verse_start = main_start + verse_delay
            verse_end = min(overlay_end, verse_start + verse_dur)
            lower_start = verse_end + OVERLAY_GAP
            if overlay_end - lower_start >= LOWER_MIN - 0.05:
                lower_end = min(overlay_end, lower_start + max(LOWER_MIN, min(LOWER_TARGET, overlay_end - lower_start)))
                verse = (verse_start, verse_end)
                lower = (lower_start, lower_end)
            else:
                verse = (verse_start, min(overlay_end, verse_start + min(VERSE_TARGET, overlay_end - verse_start)))
        else:
            verse_start = main_start + verse_delay
            verse = (verse_start, min(overlay_end, verse_start + min(VERSE_TARGET, overlay_end - verse_start)))
    elif available >= LOWER_MIN:
        lower_start = main_start + 0.15
        lower = (lower_start, min(overlay_end, lower_start + 11.0))

    compact_start = main_start + 0.4
    if window_is_active(verse):
        compact_start = max(compact_start, verse[1] + 0.12)
    compact_end = overlay_end
    compact = (compact_start, compact_end) if compact_end - compact_start >= 0.2 else DISABLED_WINDOW

    header_end = min(overlay_end, intro + 10.0)
    header_start = intro
    header = (header_start, header_end) if header_end - header_start >= 0.2 else DISABLED_WINDOW

    return {
        "intro": (0.0, intro),
        "outro": (outro_start, total) if outro else DISABLED_WINDOW,
        "header": header,
        "lower_third": lower,
        "compact": compact,
        "week_card": verse,
        "verse_card": verse,
    }


def validate_project_for_render(project: VideoProject) -> None:
    if not project.audio_path:
        raise VideoMakerError("No audio selected. Use today's generated audio or choose an external file.")
    if not Path(project.audio_path).is_file():
        raise VideoMakerError("The selected audio file is missing. Choose another file.")
    if not project.media_items:
        raise VideoMakerError("No media selected. Add photos or videos before generating.")
    missing = [m for m in project.media_items if not m.exists()]
    if missing:
        raise MissingMediaError(
            "Video could not be generated because one of the selected clips is unavailable."
        )
    unsupported = [
        m
        for m in project.media_items
        if Path(m.path).suffix.lower()
        not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".mp4", ".mov", ".m4v", ".avi", ".mkv"}
    ]
    if unsupported:
        raise MediaValidationError(
            "One of the selected files is not a supported photo or video format."
        )


def build_preview_plan(
    project: VideoProject,
    *,
    output_path: Path | None = None,
    temp_dir: Path | None = None,
    job_id: str = "",
    preview_seconds: float = 12.0,
    preview_start: float = 0.0,
) -> CompositionPlan:
    """Short representative plan. preview_start seeks into the master audio."""
    from copy import deepcopy

    from bmt_voice_studio.video.models import PREVIEW_DURATION, PREVIEW_HEIGHT, PREVIEW_WIDTH, output_profile_for

    preview = deepcopy(project)
    cap = max(8.0, min(float(preview_seconds or project.preview_duration or PREVIEW_DURATION), 20.0))
    start = max(0.0, float(preview_start if preview_start is not None else project.preview_start or 0.0))
    master = max(cap, float(project.audio_duration or cap))
    if start >= master:
        start = max(0.0, master - cap)
    remaining = max(3.0, master - start)
    preview.audio_duration = min(cap, remaining)
    if start >= 4.0:
        preview.intro_enabled = False
        preview.outro_enabled = False
        preview.intro_duration = 0.0
        preview.outro_duration = 0.0
    else:
        preview.intro_enabled = True
        preview.outro_enabled = False
        preview.intro_duration = min(3.2, preview.audio_duration * 0.28)
        preview.outro_duration = 0.0
    preview.output_profile = output_profile_for("preview")
    dest = output_path or preview_output_path(project.devotional_date, project.language)
    plan = build_composition_plan(preview, output_path=dest, temp_dir=temp_dir, job_id=job_id or "preview")
    plan.width = PREVIEW_WIDTH
    plan.height = PREVIEW_HEIGHT
    plan.audio_duration = preview.audio_duration
    plan.audio_start = start
    return plan
