"""Lightweight Video Maker project persistence (paths only — never media bytes)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from bmt_voice_studio.config.paths import local_appdata, projects_dir
from bmt_voice_studio.video.models import VideoProject


def video_autosave_path() -> Path:
    dest = projects_dir() / "autosave.json"
    if not dest.exists():
        legacy = local_appdata() / "video" / "autosave.json"
        try:
            if legacy.is_file():
                dest.write_bytes(legacy.read_bytes())
        except Exception:
            pass
    return dest


def _day_key(devotional_date: str) -> str:
    return re.sub(r"[^0-9\-]", "", (devotional_date or "")[:10]) or "undated"


def _key(devotional_date: str, language: str) -> str:
    lang = re.sub(r"[^a-z]", "", (language or "en").lower()) or "en"
    return f"{_day_key(devotional_date)}_{lang}"


def shared_slot_path(devotional_date: str) -> Path:
    folder = projects_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_day_key(devotional_date)}.json"


def project_slot_path(devotional_date: str, language: str) -> Path:
    folder = projects_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_key(devotional_date, language)}.json"


def save_project(project: VideoProject, path: Path | None = None) -> Path:
    target = path or video_autosave_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = project.to_dict()
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if path is None and project.devotional_date:
        shared_slot_path(project.devotional_date).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        slot = project_slot_path(project.devotional_date, project.language)
        slot.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_project(path: Path | None = None) -> VideoProject:
    target = path or video_autosave_path()
    if not target.exists():
        return VideoProject()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return VideoProject()
        project = VideoProject.from_dict(data)
        for item in project.media_items:
            item.missing = not item.exists()
        return project
    except Exception:
        return VideoProject()


def load_project_for(devotional_date: str, language: str) -> VideoProject | None:
    slot = project_slot_path(devotional_date, language)
    if slot.exists():
        project = load_project(slot)
        if project.audio_path or project.media_items or project.topic:
            return project
    shared = shared_slot_path(devotional_date)
    if shared.exists():
        project = load_project(shared)
        lang = (language or "en").lower()
        selected = [x.lower() for x in (project.selected_languages or [project.language])]
        if lang in selected or project.track_for(lang):
            return project
        if project.media_items and lang == (project.language or "en").lower():
            return project
    return None


def has_previous_project(devotional_date: str, language: str) -> bool:
    return load_project_for(devotional_date, language) is not None


def clear_project(path: Path | None = None) -> None:
    target = path or video_autosave_path()
    if target.exists():
        target.unlink()
