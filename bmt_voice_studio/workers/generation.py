"""Background workers for generation, download, and health checks."""

from __future__ import annotations

import asyncio
import logging
import traceback
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.joining import join_segments
from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.filenames import unique_path
from bmt_voice_studio.core.models import Segment, Speaker, SynthRequest
from bmt_voice_studio.m3u.downloader import download_and_merge
from bmt_voice_studio.m3u.parser import parse_m3u_content
from bmt_voice_studio.projects.project import ProjectData, ProjectService
from bmt_voice_studio.providers import get_provider
from bmt_voice_studio.providers.base import TTSProviderError

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    progress = Signal(int, int, str)  # current, total, message
    log = Signal(str)
    segment_done = Signal(int, str)  # index, path
    segment_failed = Signal(int, str)  # index, error
    finished = Signal(object)
    error = Signal(str, str)  # human, technical
    fallback_prompt = Signal(str)  # message asking to use piper


class AsyncWorker(QRunnable):
    def __init__(self, coro_factory, signals: WorkerSignals | None = None) -> None:
        super().__init__()
        self.coro_factory = coro_factory
        self.signals = signals or WorkerSignals()
        self._cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled

    @Slot()
    def run(self) -> None:
        try:
            result = asyncio.run(self.coro_factory(self))
            self.signals.finished.emit(result)
        except Exception as exc:
            tech = traceback.format_exc()
            logger.error(tech)
            human = str(exc) if str(exc) else "An unexpected error occurred."
            self.signals.error.emit(human, tech)


class GenerationController:
    """Orchestrates smart segment generation, join, and mastering."""

    def __init__(self) -> None:
        self.pool = QThreadPool.globalInstance()
        self.signals = WorkerSignals()
        self._worker: AsyncWorker | None = None
        self._pause_on_fail = True
        self._fail_action: str | None = None  # retry|skip|switch
        self._fail_event: asyncio.Event | None = None

    def cancel(self) -> None:
        if self._worker:
            self._worker.cancel()
        if self._fail_event:
            self._fail_action = "skip"
            self._fail_event.set()

    def resolve_failure(self, action: str) -> None:
        self._fail_action = action
        if self._fail_event:
            self._fail_event.set()

    def start(self, project: ProjectData, segments: list[Segment]) -> None:
        controller = self

        async def job(worker: AsyncWorker) -> dict[str, Any]:
            settings = get_settings()
            svc = ProjectService()
            root = svc.ensure_layout(project)
            seg_dir = root / "segments"
            log_path = root / "logs" / "production.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            def wlog(msg: str) -> None:
                controller.signals.log.emit(msg)
                with log_path.open("a", encoding="utf-8") as fh:
                    fh.write(msg + "\n")

            provider_id = project.provider or settings.default_provider
            provider = get_provider(provider_id)
            used_fallback = False

            # Assign voices per speaker
            for seg in segments:
                if not seg.voice:
                    seg.voice = (
                        project.male_voice
                        if seg.speaker == Speaker.MALE
                        else project.female_voice
                    )
                if not seg.rate:
                    seg.rate = project.rate
                if not seg.pitch:
                    seg.pitch = project.pitch
                if not seg.volume:
                    seg.volume = project.volume
                seg.provider = provider_id

            enabled = [s for s in segments if s.enabled]
            total = len(enabled)
            current = 0

            for seg in enabled:
                if worker.is_cancelled():
                    raise TTSProviderError("Generation cancelled.")

                new_hash = segment_cache_hash(seg)
                out_name = f"{seg.index:03d}_{seg.speaker.value}.mp3"
                out_path = seg_dir / out_name

                if (
                    not needs_regeneration(seg, new_hash)
                    and seg.audio_path
                    and Path(seg.audio_path).exists()
                ):
                    current += 1
                    wlog(f"Cached segment {seg.index:02d} — skipped regeneration.")
                    controller.signals.progress.emit(current, total, f"Using cache {current} of {total}…")
                    controller.signals.segment_done.emit(seg.index, seg.audio_path)
                    continue

                current += 1
                controller.signals.progress.emit(
                    current, total, f"Generating {current} of {total}…"
                )
                wlog(f"Generating segment {seg.index:02d} ({seg.speaker.value})…")

                async def synth_with_provider(prov) -> Any:
                    return await prov.synthesize(
                        SynthRequest(
                            text=seg.text,
                            voice=seg.voice,
                            rate=seg.rate,
                            pitch=seg.pitch,
                            volume=seg.volume,
                            output_path=str(out_path),
                        ),
                        cancel_check=worker.is_cancelled,
                        on_progress=lambda m: controller.signals.log.emit(m),
                    )

                result = await synth_with_provider(provider)

                if not result.success and not result.cancelled:
                    # Optional automatic piper fallback
                    if (
                        settings.auto_piper_fallback
                        and provider_id == "edge"
                        and not used_fallback
                    ):
                        wlog("ONLINE TTS UNAVAILABLE — trying Piper fallback…")
                        try:
                            piper = get_provider("piper")
                            # Map to piper models from settings if set
                            piper_voice = (
                                settings.piper_male_model
                                if seg.speaker == Speaker.MALE
                                else settings.piper_female_model
                            )
                            if piper_voice:
                                seg.voice = piper_voice
                                seg.provider = "piper"
                                result = await synth_with_provider(piper)
                                if result.success:
                                    used_fallback = True
                                    provider = piper
                                    provider_id = "piper"
                        except Exception as exc:
                            wlog(f"Piper fallback failed: {exc}")

                while not result.success and not result.cancelled:
                    controller.signals.segment_failed.emit(seg.index, result.error)
                    controller._fail_event = asyncio.Event()
                    controller._fail_action = None
                    # Also emit high-level prompt for UI
                    controller.signals.fallback_prompt.emit(result.error)
                    await controller._fail_event.wait()
                    action = controller._fail_action or "skip"
                    if action == "retry":
                        result = await synth_with_provider(provider)
                    elif action == "switch":
                        provider = get_provider("piper")
                        provider_id = "piper"
                        piper_voice = (
                            settings.piper_male_model
                            if seg.speaker == Speaker.MALE
                            else settings.piper_female_model
                        )
                        if piper_voice:
                            seg.voice = piper_voice
                        seg.provider = "piper"
                        result = await synth_with_provider(provider)
                    else:  # skip
                        seg.error = result.error
                        wlog(f"Skipped segment {seg.index:02d}: {result.error}")
                        break

                if result.cancelled:
                    raise TTSProviderError("Generation cancelled.")

                if result.success:
                    seg.audio_path = result.output_path
                    seg.cache_hash = segment_cache_hash(seg)
                    seg.error = ""
                    controller.signals.segment_done.emit(seg.index, result.output_path)
                    wlog(f"Segment {seg.index:02d} ready.")

            # Join to temp raw, then master into the final export path (no silent _2 rename)
            controller.signals.progress.emit(total, total, "Joining segments…")
            wlog("Joining segments with FFmpeg…")
            mp3_path, wav_path = svc.export_final_names(project)
            raw_path = root / "final" / "_raw_join.mp3"
            if raw_path.exists():
                raw_path.unlink(missing_ok=True)
            joined = join_segments(
                segments,
                raw_path,
                pause_ms=project.pause_ms,
                bitrate_kbps=project.mp3_bitrate,
                also_wav=False,
            )
            raw_final = joined["final"]

            # Mastering
            opts = MasteringOptions(
                normalize_loudness=project.normalize_loudness,
                target_lufs=project.target_lufs,
                remove_silence=project.remove_silence,
                fade_in_ms=project.fade_in_ms,
                fade_out_ms=project.fade_out_ms,
                peak_limiter=project.peak_limiter,
                bitrate_kbps=project.mp3_bitrate,
            )
            controller.signals.progress.emit(total, total, "Mastering final audio…")
            if mp3_path.exists():
                mp3_path = unique_path(mp3_path)
            mastered = master_audio(raw_final, mp3_path, opts, overwrite=True)
            # WAV export
            ff = FFmpegService()
            if wav_path.exists():
                wav_path = unique_path(wav_path)
            ff.convert(mastered, wav_path, bitrate_kbps=project.mp3_bitrate)

            project.set_segments(segments)
            project.final_mp3 = str(mastered)
            project.final_wav = str(wav_path)
            svc.save(project)
            wlog(f"Final MP3: {mastered}")
            wlog(f"Final WAV: {wav_path}")
            return {
                "project": project,
                "segments": segments,
                "mp3": str(mastered),
                "wav": str(wav_path),
                "raw": str(raw_final),
            }

        self._worker = AsyncWorker(job, self.signals)
        self.pool.start(self._worker)


class DownloadMergeController:
    def __init__(self) -> None:
        self.pool = QThreadPool.globalInstance()
        self.signals = WorkerSignals()
        self._worker: AsyncWorker | None = None

    def cancel(self) -> None:
        if self._worker:
            self._worker.cancel()

    def start(
        self,
        items,
        output_path: Path,
        *,
        pause_ms: int = 0,
        bitrate_kbps: int = 128,
        playlist_text: str = "",
        playlist_source: str = "",
    ) -> None:
        async def job(worker: AsyncWorker):
            parsed = parse_m3u_content(playlist_text) if playlist_text else None
            is_hls = bool(parsed and parsed.is_hls)
            hls_url = ""
            if is_hls:
                # Prefer original playlist file/URL so FFmpeg can resolve HLS correctly
                if playlist_source:
                    hls_url = playlist_source
                elif parsed and parsed.is_master_playlist and items:
                    hls_url = items[0].source
                elif playlist_source == "" and items:
                    # Single remote .m3u8 pasted as only entry
                    src = items[0].source.lower().split("?", 1)[0]
                    if src.endswith(".m3u8") or src.endswith(".m3u"):
                        hls_url = items[0].source
            result = await download_and_merge(
                items,
                output_path,
                pause_ms=pause_ms,
                bitrate_kbps=bitrate_kbps,
                is_hls=is_hls and bool(hls_url),
                hls_url=hls_url,
                on_progress=lambda c, t, m: self.signals.progress.emit(c, t, m),
                cancel_check=worker.is_cancelled,
            )
            return {"mp3": str(result)}

        self._worker = AsyncWorker(job, self.signals)
        self.pool.start(self._worker)


class HealthController:
    def __init__(self) -> None:
        self.pool = QThreadPool.globalInstance()
        self.signals = WorkerSignals()

    def start(self) -> None:
        async def job(worker: AsyncWorker):
            import httpx

            status: dict[str, str] = {}
            # Internet
            try:
                async with httpx.AsyncClient(timeout=8.0) as client:
                    r = await client.get("https://www.msftconnecttest.com/connecttest.txt")
                    status["internet"] = "ONLINE" if r.status_code < 500 else "OFFLINE"
            except Exception:
                status["internet"] = "OFFLINE"

            # FFmpeg
            ok, msg = FFmpegService().health_check()
            status["ffmpeg"] = msg if ok else msg

            # Edge
            try:
                edge = get_provider("edge")
                ok, msg = await edge.health_check()
                status["edge"] = "AVAILABLE" if ok else f"UNAVAILABLE"
            except Exception:
                status["edge"] = "UNAVAILABLE"

            # Piper
            try:
                piper = get_provider("piper")
                ok, msg = await piper.health_check()
                status["piper"] = msg
            except Exception as exc:
                status["piper"] = f"ERROR ({exc})"

            return status

        worker = AsyncWorker(job, self.signals)
        self.pool.start(worker)
