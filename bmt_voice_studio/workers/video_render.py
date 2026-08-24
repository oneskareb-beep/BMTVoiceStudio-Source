"""Background Video Maker render worker (does not block the UI)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from bmt_voice_studio.video.composition import (
    build_composition_plan,
    build_preview_plan,
    validate_project_for_render,
)
from bmt_voice_studio.video.errors import RenderCancelled, VideoMakerError
from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
from bmt_voice_studio.video.models import QUEUE_FINALIZING, QUEUE_PREPARING, QUEUE_RENDERING, VideoProject
from bmt_voice_studio.video.paths import new_job_id, preview_output_path, video_output_path, video_render_temp_dir


class VideoRenderSignals(QObject):
    progress = Signal(int, str)
    language_progress = Signal(str, int, str)
    finished = Signal(object)
    error = Signal(str, str)  # human, technical


class VideoRenderWorker(QRunnable):
    def __init__(
        self,
        project: VideoProject,
        signals: VideoRenderSignals | None = None,
        *,
        preview: bool = False,
        preview_start: float = 0.0,
        language: str = "",
    ) -> None:
        super().__init__()
        self.project = project
        self.signals = signals or VideoRenderSignals()
        self.renderer = VideoRenderer()
        self._cancelled = False
        self.preview = bool(preview)
        self.preview_start = float(preview_start or 0.0)
        self.language = (language or project.language or "en").strip().lower()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True
        self.renderer.cancel()

    @Slot()
    def run(self) -> None:
        try:
            validate_project_for_render(self.project)
            job_id = new_job_id()
            temp = video_render_temp_dir(job_id)
            if self.preview:
                dest = preview_output_path(self.project.devotional_date, self.project.language)
                plan = build_preview_plan(
                    self.project,
                    output_path=dest,
                    temp_dir=temp,
                    job_id=job_id,
                    preview_start=self.preview_start,
                )
            else:
                dest = video_output_path(
                    self.project.devotional_date,
                    self.project.language,
                    profile_id=self.project.output_profile.id,
                )
                plan = build_composition_plan(
                    self.project,
                    output_path=dest,
                    temp_dir=temp,
                    job_id=job_id,
                )

            def on_progress(pct: int, msg: str) -> None:
                stage = msg
                if "Prepar" in msg:
                    stage = QUEUE_PREPARING
                elif "Final" in msg:
                    stage = QUEUE_FINALIZING
                elif "Render" in msg or "Compos" in msg:
                    stage = QUEUE_RENDERING
                self.signals.progress.emit(int(pct), msg)
                self.signals.language_progress.emit(self.language, int(pct), stage)

            out = self.renderer.render(self.project, plan, progress=on_progress)
            self.signals.finished.emit(
                {
                    "output": str(out),
                    "ffmpeg": self.renderer.ffmpeg_path,
                    "job_id": job_id,
                    "plan": plan.to_dict(),
                    "preview": self.preview,
                    "language": self.language,
                    "metrics": dict(self.renderer.last_metrics or {}),
                }
            )
        except RenderCancelled:
            self.signals.error.emit("Video rendering was cancelled.", "")
        except VideoMakerError as exc:
            tech = exc.technical
            if self.renderer.last_log_path:
                tech = f"{tech}\nlog={self.renderer.last_log_path}"
            self.signals.error.emit(exc.message, tech)
        except Exception:
            import traceback

            self.signals.error.emit(
                "Video could not be generated. See Troubleshooting for the technical log.",
                traceback.format_exc(),
            )
