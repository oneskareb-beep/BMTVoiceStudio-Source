"""Multi-language Video Maker batch selection and sequential queue."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from bmt_voice_studio.video.models import (
    LANGUAGE_FOLDERS,
    LANGUAGE_LABELS,
    QUEUE_CANCELLED,
    QUEUE_COMPLETE,
    QUEUE_FAILED,
    QUEUE_PREPARING,
    QUEUE_WAITING,
    LanguageTrack,
    VideoProject,
)


def ready_languages(tracks: list[LanguageTrack] | list[dict]) -> list[str]:
    out: list[str] = []
    for item in tracks:
        if isinstance(item, LanguageTrack):
            if item.ready and item.audio_path:
                out.append(item.language)
        elif isinstance(item, dict) and item.get("ready") and item.get("path"):
            out.append(str(item.get("language") or "").lower())
    return [x for x in out if x in LANGUAGE_FOLDERS]


def filter_selected_ready(selected: list[str], ready: list[str]) -> list[str]:
    ready_set = {r.lower() for r in ready}
    seen: set[str] = set()
    out: list[str] = []
    for lang in selected:
        key = (lang or "").strip().lower()
        if key in ready_set and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def metadata_incomplete(track: LanguageTrack) -> bool:
    return not bool((track.topic or "").strip())


@dataclass
class QueueItem:
    language: str
    label: str = ""
    status: str = QUEUE_WAITING
    percent: int = 0
    message: str = ""
    output: str = ""
    error: str = ""
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "label": self.label or LANGUAGE_LABELS.get(self.language, self.language),
            "status": self.status,
            "percent": int(self.percent),
            "message": self.message,
            "output": self.output,
            "error": self.error,
            "metrics": dict(self.metrics),
        }


def build_queue(selected: list[str], ready: list[str]) -> list[QueueItem]:
    langs = filter_selected_ready(selected, ready)
    return [
        QueueItem(language=lang, label=LANGUAGE_LABELS.get(lang, lang), status=QUEUE_WAITING)
        for lang in langs
    ]


def isolate_failure(items: list[QueueItem], failed_language: str, message: str) -> list[QueueItem]:
    """Mark one language failed; leave completed items intact; keep later items waiting."""
    failed = (failed_language or "").lower()
    for item in items:
        if item.language == failed:
            if item.status != QUEUE_COMPLETE:
                item.status = QUEUE_FAILED
                item.error = message
                item.message = message
        elif item.status not in {QUEUE_COMPLETE, QUEUE_CANCELLED, QUEUE_FAILED}:
            if item.status == QUEUE_PREPARING:
                item.status = QUEUE_WAITING
    return items


def cancel_pending(items: list[QueueItem]) -> list[QueueItem]:
    for item in items:
        if item.status in {QUEUE_WAITING, QUEUE_PREPARING}:
            item.status = QUEUE_CANCELLED
            item.message = "Cancelled"
    return items


def failed_languages(items: list[QueueItem]) -> list[str]:
    return [i.language for i in items if i.status == QUEUE_FAILED]


def retry_failed(items: list[QueueItem]) -> list[QueueItem]:
    for item in items:
        if item.status == QUEUE_FAILED:
            item.status = QUEUE_WAITING
            item.percent = 0
            item.error = ""
            item.message = ""
    return items


def projects_for_batch(project: VideoProject, selected: list[str] | None = None) -> list[VideoProject]:
    """One bound clone per selected ready language. Shared media is not duplicated on disk."""
    project.ensure_tracks()
    ready = [t.language for t in project.languages if t.ready]
    langs = filter_selected_ready(selected or project.selected_languages or [project.language], ready)
    bound: list[VideoProject] = []
    for lang in langs:
        clone = project.bind_language(lang)
        track = project.track_for(lang)
        # Sylvestre: FR/PT topics must reflect on video like English.
        if not (clone.topic or "").strip():
            try:
                from bmt_voice_studio.video.discovery import metadata_for_language

                meta = metadata_for_language(
                    project.devotional_date,
                    lang,
                    audio_path=str(getattr(clone, "audio_path", "") or ""),
                )
                if meta.get("topic"):
                    clone.topic = meta["topic"]
                if not (clone.week_focus or "").strip() and meta.get("week_focus"):
                    clone.week_focus = meta["week_focus"]
                if not (clone.month_theme or "").strip() and meta.get("month_theme"):
                    clone.month_theme = meta["month_theme"]
                if not (clone.memory_verse or "").strip() and meta.get("memory_verse"):
                    clone.memory_verse = meta["memory_verse"]
                if not (clone.title or "").strip() and meta.get("title"):
                    clone.title = meta["title"]
            except Exception:
                if track and track.topic:
                    clone.topic = track.topic
        bound.append(clone)
    return bound


def language_output_exists(path: str | Path) -> bool:
    try:
        p = Path(path)
        return p.is_file() and p.stat().st_size > 1024
    except Exception:
        return False


def snapshot_shared(project: VideoProject) -> VideoProject:
    """Keep one in-memory project; clones used for render do not rewrite media lists."""
    return deepcopy(project)


def batch_completion_summary(items: list[QueueItem]) -> dict:
    """User-facing batch result: complete vs failed counts and per-language rows."""
    complete = [i for i in items if i.status == QUEUE_COMPLETE]
    failed = [i for i in items if i.status == QUEUE_FAILED]
    if failed:
        headline = f"{len(complete)} Complete\n{len(failed)} Failed"
    elif complete:
        headline = f"{len(complete)} VIDEOS COMPLETE"
    else:
        headline = "No videos complete"
    return {
        "headline": headline,
        "complete": len(complete),
        "failed": len(failed),
        "total": len(items),
        "rows": [
            {
                "language": i.language,
                "label": i.label,
                "status": i.status,
                "output": i.output,
                "ok": i.status == QUEUE_COMPLETE,
            }
            for i in items
        ],
    }
