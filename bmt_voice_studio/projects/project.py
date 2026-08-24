"""Project save/load and export folder layout."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.config.paths import default_exports_dir, projects_dir
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.core.filenames import sanitize_project_folder_name, unique_path
from bmt_voice_studio.core.models import Segment


@dataclass
class ProjectData:
    name: str = "Untitled Project"
    created_at: str = ""
    updated_at: str = ""
    source_text: str = ""
    language: str = "en-NG"
    preset_id: str = "bmt_english"
    provider: str = "edge"
    male_voice: str = ""
    female_voice: str = ""
    rate: str = "-10%"
    pitch: str = "-3Hz"
    volume: str = "+0%"
    pause_ms: int = 450
    mp3_bitrate: int = 128
    normalize_loudness: bool = True
    target_lufs: float = -16.0
    remove_silence: bool = False
    fade_in_ms: int = 0
    fade_out_ms: int = 120
    peak_limiter: bool = True
    segments: list[dict[str, Any]] = field(default_factory=list)
    output_folder: str = ""
    final_mp3: str = ""
    final_wav: str = ""
    version: int = 1

    def __post_init__(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})

    def get_segments(self) -> list[Segment]:
        return [Segment.from_dict(s) for s in self.segments]

    def set_segments(self, segments: list[Segment]) -> None:
        self.segments = [s.to_dict() for s in segments]


class ProjectService:
    def new_project(self, name: str | None = None) -> ProjectData:
        settings = get_settings()
        stamp = datetime.now().strftime("%Y_%m_%d")
        return ProjectData(
            name=name or f"BMT_{stamp}",
            language=settings.default_language,
            preset_id=settings.default_preset,
            provider=settings.default_provider,
            male_voice=settings.default_male_voice,
            female_voice=settings.default_female_voice,
            rate=settings.rate,
            pitch=settings.pitch,
            volume=settings.volume,
            pause_ms=settings.pause_ms,
            mp3_bitrate=settings.mp3_bitrate,
            normalize_loudness=settings.normalize_loudness,
            target_lufs=settings.target_lufs,
            remove_silence=settings.remove_silence,
            fade_in_ms=settings.fade_in_ms,
            fade_out_ms=settings.fade_out_ms,
            peak_limiter=settings.peak_limiter,
        )

    def project_root(self, project: ProjectData, base: Path | None = None) -> Path:
        # Prefer an already-assigned project folder so exports stay together.
        if project.output_folder:
            return Path(project.output_folder)
        base = base or Path(get_settings().output_directory or default_exports_dir())
        folder = sanitize_project_folder_name(project.name)
        return base / folder

    def ensure_layout(self, project: ProjectData, base: Path | None = None) -> Path:
        if project.output_folder:
            root = Path(project.output_folder)
        elif base is not None:
            root = base / sanitize_project_folder_name(project.name)
        else:
            root = Path(get_settings().output_directory or default_exports_dir()) / sanitize_project_folder_name(
                project.name
            )
        for sub in ("final", "segments", "project", "logs"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        project.output_folder = str(root)
        return root

    def save(self, project: ProjectData, path: Path | None = None) -> Path:
        project.updated_at = datetime.now().isoformat(timespec="seconds")
        if path is None:
            root = self.ensure_layout(project)
            path = root / "project" / "project.json"
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Also ensure layout near path if under exports
        path.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        # Mirror source text
        if project.output_folder:
            src = Path(project.output_folder) / "project" / "source.txt"
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(project.source_text, encoding="utf-8")
        # Also keep a copy under app projects dir
        mirror = projects_dir() / f"{sanitize_project_folder_name(project.name)}.json"
        mirror.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
        self._add_recent(str(path))
        return path

    def load(self, path: Path) -> ProjectData:
        data = json.loads(path.read_text(encoding="utf-8"))
        project = ProjectData.from_dict(data)
        self._add_recent(str(path))
        return project

    def _add_recent(self, path: str) -> None:
        settings = get_settings()
        recent = [p for p in settings.recent_projects if p != path]
        recent.insert(0, path)
        settings.recent_projects = recent[:12]
        settings.save()

    def recent(self) -> list[str]:
        return list(get_settings().recent_projects)

    def export_final_names(self, project: ProjectData) -> tuple[Path, Path]:
        root = self.ensure_layout(project)
        base = sanitize_project_folder_name(project.name) + "_FINAL"
        mp3 = root / "final" / f"{base}.mp3"
        wav = root / "final" / f"{base}.wav"
        return mp3, wav
