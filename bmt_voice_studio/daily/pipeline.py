"""Daily BMT dual-language generation — reuses v1.0 TTS/join/master/cache."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable

from bmt_voice_studio import __version__
from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.joining import join_segments
from bmt_voice_studio.audio.mastering import MasteringOptions, master_audio
from bmt_voice_studio.audio.source_export import export_original_pipeline
from bmt_voice_studio.config.french_tts import remap_french_preset
from bmt_voice_studio.config.pipeline_config import ProcessingMode
from bmt_voice_studio.config.presets import VoicePreset
from bmt_voice_studio.core.text_prepare import (
    FRENCH_SPOKEN_SANITIZE_TAG,
    SPOKEN_LIST_SUPPRESSION_TAG,
    count_system_english_contamination,
    prepare_tts_text,
    sanitize_french_spoken_for_tts,
    suppress_spoken_list_markers_counted,
)
from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.core.job_progress import language_work_total
from bmt_voice_studio.core.hashing import needs_regeneration, segment_cache_hash
from bmt_voice_studio.core.models import Speaker, SynthRequest
from bmt_voice_studio.core.parser import parse_speaker_script, parse_speaker_script_source
from bmt_voice_studio.daily.history import upsert_entry
from bmt_voice_studio.daily.language_config import (
    get_language_config,
    not_selected_language_block,
    unapproved_setup_message,
)
from bmt_voice_studio.daily.layout import ensure_daily_layout, final_paths, language_dir
from bmt_voice_studio.daily.naming import display_date, freeze_devotional_date, project_id
from bmt_voice_studio.daily.report import write_reports
from bmt_voice_studio.daily.validate import overall_status_selected, validate_daily_script
from bmt_voice_studio.m3u.parser import validate_audio_magic
from bmt_voice_studio.production_batch import _loudness, _probe
from bmt_voice_studio.providers import get_provider
from bmt_voice_studio.providers.base import TTSProviderError
from bmt_voice_studio.providers.provider_guard import assert_provider_voice_compatible
from bmt_voice_studio.providers.voice_verify import verify_required_voices

logger = logging.getLogger(__name__)

ProgressFn = Callable[[str, int, int, str], None]  # lang, current, total, message
CancelFn = Callable[[], bool]


@dataclass
class DailyJob:
    date: date
    english_text: str = ""
    french_text: str = ""
    swahili_text: str = ""
    portuguese_text: str = ""
    generate_english: bool = True
    generate_french: bool = True
    generate_swahili: bool = False
    generate_portuguese: bool = False
    pause_ms: int = 500
    target_lufs: float = -16.0
    mastering: bool = False
    export_mp3: bool = True
    export_wav: bool = False
    mp3_bitrate: int | None = 192
    provider: str = "edge"
    use_piper_fallback: bool = False
    base_exports: Path | None = None
    processing_mode: ProcessingMode = "original"
    strict_source_mode: bool = True
    product_mode: str = "bmt"
    kinyarwanda_text: str = ""
    english_caption_text: str = ""

    def selected_language_ids(self) -> list[str]:
        ids: list[str] = []
        if self.generate_english:
            ids.append("en")
        if self.generate_french:
            ids.append("fr")
        if self.generate_swahili:
            ids.append("sw")
        if self.generate_portuguese:
            ids.append("pt")
        return ids


@dataclass
class DailyResult:
    ok: bool
    status: str
    folder: str
    english: dict[str, Any] | None = None
    french: dict[str, Any] | None = None
    swahili: dict[str, Any] | None = None
    portuguese: dict[str, Any] | None = None
    report_md: str = ""
    report_json: str = ""
    errors: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


def preflight(job: DailyJob) -> list[str]:
    issues: list[str] = []
    selected = job.selected_language_ids()
    if not selected:
        issues.append("Select at least one language.")
        return issues

    for lang_id in selected:
        cfg = get_language_config(lang_id)
        if cfg is not None and not cfg.production_approved:
            issues.append(
                f"PRODUCTION_SETUP_REQUIRED:{lang_id}:{unapproved_setup_message(lang_id)}"
            )
            continue
        if cfg is not None:
            preset = cfg.resolved_preset()
            if not (preset.male_voice and preset.female_voice):
                issues.append(
                    f"PRODUCTION_SETUP_REQUIRED:{lang_id}:{unapproved_setup_message(lang_id)}"
                )

    script_checks = [
        ("en", job.generate_english, job.english_text, "ENGLISH"),
        ("fr", job.generate_french, job.french_text, "FRENCH"),
        ("sw", job.generate_swahili, job.swahili_text, "SWAHILI"),
        ("pt", job.generate_portuguese, job.portuguese_text, "PORTUGUESE"),
    ]
    for _lid, enabled, text, label in script_checks:
        if not enabled:
            continue
        v = validate_daily_script(text)
        if not v.ok:
            if v.status == "EMPTY":
                issues.append(f"{label} SCRIPT REQUIRED")
            else:
                issues.append(f"{label} SCRIPT INVALID: " + (v.errors[0] if v.errors else "invalid"))

    from bmt_voice_studio.config.product import is_hhr

    if is_hhr(job.product_mode) and job.generate_swahili and not (job.kinyarwanda_text or "").strip():
        issues.append("KINYARWANDA TRANSCRIPT REQUIRED")

    try:
        ok, msg = FFmpegService().health_check()
        if not ok:
            issues.append(f"FFmpeg not ready: {msg}")
    except Exception as exc:
        issues.append(f"FFmpeg not ready: {exc}")
    try:
        get_provider(job.provider or "edge")
    except Exception as exc:
        if job.use_piper_fallback:
            try:
                get_provider("piper")
            except Exception:
                issues.append(f"No TTS provider available: {exc}")
        else:
            issues.append(f"TTS provider not available: {exc}")
    return issues


def _cache_file(lang_dir: Path) -> Path:
    return lang_dir / "segments" / "cache.json"


def _load_cache(lang_dir: Path) -> dict[str, Any]:
    p = _cache_file(lang_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _load_word_timings(audio_path: Path) -> list[dict[str, Any]]:
    """Load Edge WordBoundary sidecar written next to a segment MP3."""
    side = Path(audio_path).with_suffix(".words.json")
    if not side.is_file():
        return []
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start + 0.05)
        except (TypeError, ValueError):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        out.append({"text": text, "start": start, "end": max(start + 0.02, end)})
    return out


def _save_cache(lang_dir: Path, segments: list) -> None:
    payload = {"segments": [s.to_dict() for s in segments]}
    _cache_file(lang_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def is_original_pipeline_job(job: DailyJob, preset: VoicePreset | None = None) -> bool:
    """True when Daily BMT must stay on Edge reference voices with no Piper."""
    if job.processing_mode == "original":
        return True
    if preset is not None and preset.is_reference_locked and not job.mastering:
        return True
    return False


def resolve_daily_provider(job: DailyJob, preset: VoicePreset) -> str:
    """Original Pipeline / BMT reference presets always use Edge TTS."""
    if is_original_pipeline_job(job, preset) or preset.is_reference_locked:
        return "edge"
    return (job.provider or "edge").strip().lower() or "edge"


def effective_job_config(job: DailyJob, preset: VoicePreset) -> dict[str, Any]:
    """Canonical effective settings actually passed into synthesis/export."""
    preset = remap_french_preset(preset)
    pause, bitrate, export_mp3, export_wav, use_mastering, allow_piper = _effective_pipeline(job, preset)
    provider = resolve_daily_provider(job, preset)
    return {
        "provider": provider,
        "male_voice": preset.male_voice,
        "female_voice": preset.female_voice,
        "rate": preset.rate,
        "pitch": preset.pitch,
        "volume": preset.volume,
        "pause_ms": pause,
        "mp3_bitrate": bitrate,
        "lowpass_hz": preset.pipeline.lowpass_hz if not use_mastering else preset.pipeline.lowpass_hz,
        "mastering": use_mastering,
        "export_mp3": export_mp3,
        "export_wav": export_wav,
        "allow_piper_fallback": allow_piper,
        "processing_mode": "original" if not use_mastering and is_original_pipeline_job(job, preset) else job.processing_mode,
        "strict_source_mode": bool(job.strict_source_mode and preset.pipeline.strict_source_mode),
    }


def _effective_pipeline(job: DailyJob, preset: VoicePreset) -> tuple[int, int | None, bool, bool, bool, bool]:
    """Resolve pause, bitrate, exports, mastering, and piper fallback for preset."""
    pipe = preset.pipeline
    use_original = is_original_pipeline_job(job, preset)
    if preset.is_reference_locked or use_original:
        pause = pipe.pause_ms
        bitrate = pipe.mp3_bitrate_kbps
        export_mp3 = pipe.export_mp3 if job.export_mp3 else False
        export_wav = False  # Daily delivers MP3 only
        # Original Pipeline never applies BMT mastering/LUFS chain.
        use_mastering = (
            (not use_original)
            and job.mastering
            and pipe.apply_bmt_mastering
            and job.processing_mode == "enhanced"
        )
        # Never silently fall back to Piper for BMT reference Original Pipeline.
        allow_piper = (
            (not use_original)
            and pipe.allow_piper_fallback
            and job.use_piper_fallback
        )
    else:
        pause = job.pause_ms
        bitrate = job.mp3_bitrate
        export_mp3 = job.export_mp3
        export_wav = False
        use_mastering = job.mastering
        allow_piper = job.use_piper_fallback
    if use_original:
        use_mastering = False
        allow_piper = False
    return pause, bitrate, export_mp3, export_wav, use_mastering, allow_piper


async def _synth_language(
    *,
    job: DailyJob,
    language: str,
    text: str,
    preset: VoicePreset,
    root: Path,
    on_progress: ProgressFn | None,
    cancel_check: CancelFn | None,
) -> dict[str, Any]:
    preset = remap_french_preset(preset)
    pause_ms, mp3_bitrate, export_mp3, export_wav, use_mastering, allow_piper = _effective_pipeline(
        job, preset
    )
    strict = job.strict_source_mode and preset.pipeline.strict_source_mode
    original_mode = is_original_pipeline_job(job, preset)
    provider_id = resolve_daily_provider(job, preset)
    eff = effective_job_config(job, preset)
    result: dict[str, Any] = {
        "ok": False,
        "errors": [],
        "segments": [],
        "voice_audit": [],
        "retry_count": 0,
        "fallback_events": 0,
        "piper_invocations": 0,
        "provider": provider_id,
        "configured_provider": "edge" if original_mode or preset.is_reference_locked else (job.provider or "edge"),
        "actual_provider": provider_id,
        "male_voice": preset.male_voice,
        "female_voice": preset.female_voice,
        "configured_male_voice": preset.male_voice,
        "configured_female_voice": preset.female_voice,
        "configured_voice": f"{preset.male_voice} / {preset.female_voice}",
        "actual_voice": "",
        "target_locale": preset.language,
        "rate": preset.rate,
        "pitch": preset.pitch,
        "volume": preset.volume,
        "pause_ms": pause_ms,
        "mp3_bitrate": mp3_bitrate,
        "lowpass_hz": preset.pipeline.lowpass_hz,
        "mastering": use_mastering,
        "processing_mode": job.processing_mode,
        "strict_source_mode": strict,
        "effective_config": eff,
        "segment_count": 0,
        "cached": 0,
        "regenerated": 0,
    }
    parse_fn = parse_speaker_script_source if strict else parse_speaker_script
    parsed = parse_fn(text)
    if not parsed.ok or not parsed.segments:
        result["errors"] = [e.message for e in parsed.errors] or ["No segments"]
        return result

    lang_dir = language_dir(root, language)
    seg_dir = lang_dir / "segments"
    cache = _load_cache(lang_dir)
    old_by_idx = {}
    for item in cache.get("segments") or []:
        try:
            from bmt_voice_studio.core.models import Segment as SegModel

            old_by_idx[int(item["index"])] = SegModel.from_dict(item)
        except Exception:
            continue

    settings = get_settings()
    provider = get_provider(provider_id)
    total = len(parsed.segments)
    work_total = language_work_total(total)
    result["segment_count"] = total
    result["spoken_list_marker_suppression"] = False
    result["spoken_list_markers_removed"] = 0
    result["french_spoken_sanitize"] = False
    result["french_spoken_sanitize_replacements"] = 0
    result["english_contamination_count"] = 0
    # Legacy French fields (backward compatible with prior reports).
    result["spoken_numbering_normalization"] = False
    result["french_numbering_replacements"] = 0
    lang_key = (preset.language or language or "").lower()
    is_french = lang_key.startswith("fr")
    is_english = lang_key.startswith("en")
    if is_french or is_english:
        result["spoken_list_marker_suppression"] = True
        result["language"] = "fr" if is_french else "en"
        if is_french:
            result["spoken_numbering_normalization"] = True
            result["french_spoken_sanitize"] = True

    # Hard guard: never hand Edge Neural voices to Piper.
    for voice in (preset.male_voice, preset.female_voice):
        try:
            assert_provider_voice_compatible(provider_id, voice)
        except TTSProviderError as exc:
            result["errors"].append(str(exc))
            return result

    if original_mode or preset.is_reference_locked:
        if provider_id != "edge":
            result["errors"].append(
                "PROVIDER CONFIGURATION ERROR: Original Pipeline requires EdgeTTSProvider."
            )
            return result
        required = {preset.male_voice, preset.female_voice}
        try:
            checks = await verify_required_voices(list(required))
        except Exception as exc:
            checks = []
            logger.warning("Voice catalog pre-check skipped for %s: %s", language, exc)
        missing = [
            c.configured
            for c in checks
            if not c.available and not getattr(c, "catalog_error", "")
        ]
        if missing:
            result["errors"].append(
                "REQUIRED BMT EDGE VOICE UNAVAILABLE: " + ", ".join(missing)
            )
            return result

    for seg in parsed.segments:
        if cancel_check and cancel_check():
            result["errors"].append("Cancelled.")
            result["cancelled"] = True
            _save_cache(lang_dir, parsed.segments)
            return result
        configured_voice = (
            preset.male_voice if seg.speaker == Speaker.MALE else preset.female_voice
        )
        seg.voice = configured_voice
        seg.rate = preset.rate
        seg.pitch = preset.pitch
        seg.volume = preset.volume
        seg.provider = provider_id
        tts_text = prepare_tts_text(
            seg.text,
            language=preset.language,
            strict_source_mode=strict,
            apply_spoken_list_suppression=False,
        )
        removed = 0
        if is_french or is_english:
            tts_text, removed = suppress_spoken_list_markers_counted(
                tts_text, language=preset.language
            )
            result["spoken_list_markers_removed"] = int(
                result.get("spoken_list_markers_removed") or 0
            ) + removed
            if is_french:
                result["french_numbering_replacements"] = int(
                    result.get("spoken_list_markers_removed") or 0
                )
        if is_french:
            tts_text, san = sanitize_french_spoken_for_tts(tts_text)
            result["french_spoken_sanitize_replacements"] = int(
                result.get("french_spoken_sanitize_replacements") or 0
            ) + san
            contam = count_system_english_contamination(tts_text)
            result["english_contamination_count"] = int(
                result.get("english_contamination_count") or 0
            ) + contam
        spoken_tag = None
        if is_french:
            spoken_tag = f"{SPOKEN_LIST_SUPPRESSION_TAG}+{FRENCH_SPOKEN_SANITIZE_TAG}"
        elif is_english:
            spoken_tag = SPOKEN_LIST_SUPPRESSION_TAG
        new_hash = segment_cache_hash(seg, spoken_text=tts_text, spoken_norm_tag=spoken_tag)
        out = seg_dir / f"{seg.index:03d}_{seg.speaker.value}.mp3"
        prev = old_by_idx.get(seg.index)
        cached_file = Path(prev.audio_path) if prev and prev.audio_path else out
        if not cached_file.exists() and out.exists():
            cached_file = out
        if (
            prev
            and cached_file.exists()
            and not needs_regeneration(prev, new_hash)
            and prev.text == seg.text
            and prev.speaker == seg.speaker
        ):
            seg.audio_path = str(cached_file)
            seg.cache_hash = prev.cache_hash or new_hash
            result["cached"] += 1
            if on_progress:
                on_progress(
                    language,
                    seg.index,
                    work_total,
                    f"{language} cached {seg.index}/{total}",
                )
            info = _probe(Path(seg.audio_path))
            word_timings = _load_word_timings(Path(seg.audio_path))
            audit = {
                "index": seg.index,
                "role": seg.speaker.value.upper(),
                "configured_voice": configured_voice,
                "actual_voice": seg.voice,
                "configured_provider": "Edge TTS",
                "actual_provider": "Edge TTS" if (prev.provider or provider_id) == "edge" else (prev.provider or provider_id),
                "substituted": seg.voice != configured_voice,
            }
            result["voice_audit"].append(audit)
            result["segments"].append(
                {
                    "index": seg.index,
                    "role": seg.speaker.value.upper(),
                    "voice": seg.voice,
                    "configured_voice": configured_voice,
                    "actual_voice": seg.voice,
                    "provider": prev.provider or provider_id,
                    "actual_provider": prev.provider or provider_id,
                    "path": seg.audio_path,
                    "cached": True,
                    "source_text": seg.text,
                    "spoken_text": tts_text,
                    "probe": info,
                    "valid": info["duration_sec"] > 0,
                    "word_timings": word_timings,
                }
            )
            continue

        if on_progress:
            on_progress(
                language,
                seg.index,
                work_total,
                f"Generating {language} segment {seg.index} of {total}…",
            )
        last_err = ""
        ok = False
        used_provider = provider
        used_voice = configured_voice
        synth_timings: list[dict[str, Any]] = []
        try:
            assert_provider_voice_compatible(used_provider.id, used_voice)
        except TTSProviderError as exc:
            result["errors"].append(str(exc))
            _save_cache(lang_dir, parsed.segments)
            return result

        for attempt in range(1, max(2, settings.retry_count) + 1):
            if cancel_check and cancel_check():
                result["errors"].append("Cancelled.")
                result["cancelled"] = True
                _save_cache(lang_dir, parsed.segments)
                return result
            if used_provider.id == "piper":
                result["piper_invocations"] = int(result.get("piper_invocations") or 0) + 1
            if original_mode or preset.is_reference_locked:
                if used_provider.id != "edge" or used_voice != configured_voice:
                    result["errors"].append(
                        f"Segment {seg.index}: REQUIRED BMT EDGE VOICE UNAVAILABLE "
                        "(provider/voice substitution blocked in Original Pipeline)"
                    )
                    _save_cache(lang_dir, parsed.segments)
                    return result
            r = await used_provider.synthesize(
                SynthRequest(
                    text=tts_text,
                    voice=used_voice,
                    rate=seg.rate,
                    pitch=seg.pitch,
                    volume=seg.volume,
                    output_path=str(out),
                )
            )
            synth_timings = list(getattr(r, "timings", None) or [])
            if r.success and out.exists() and out.stat().st_size > 64:
                magic_ok, kind = validate_audio_magic(out.read_bytes()[:256])
                if magic_ok:
                    ok = True
                    seg.provider = used_provider.id
                    seg.voice = used_voice
                    break
                last_err = f"invalid audio magic: {kind}"
                synth_timings = []
            else:
                last_err = r.error or "empty output"
                synth_timings = []
            result["retry_count"] += 1
            # Auto Piper fallback — NEVER for Original Pipeline / BMT reference presets.
            if original_mode or preset.is_reference_locked:
                last_err = (
                    f"EDGE TTS CONNECTION FAILED: {last_err}. "
                    "Original Pipeline does not use Piper. Retry when Edge TTS is available."
                )
                break
            if (
                allow_piper
                and settings.auto_piper_fallback
                and used_provider.id == "edge"
                and attempt == 1
            ):
                piper_voice = (
                    settings.piper_male_model
                    if seg.speaker == Speaker.MALE
                    else settings.piper_female_model
                )
                if piper_voice:
                    try:
                        assert_provider_voice_compatible("piper", piper_voice)
                        used_provider = get_provider("piper")
                        used_voice = piper_voice
                        result["fallback_events"] += 1
                        continue
                    except Exception:
                        pass
            await asyncio.sleep(min(1.2 * attempt, 4))
        if not ok:
            if original_mode or preset.is_reference_locked:
                result["errors"].append(
                    f"Segment {seg.index}: {last_err or 'EDGE TTS CONNECTION FAILED'}"
                )
            else:
                result["errors"].append(f"Segment {seg.index} failed: {last_err}")
            _save_cache(lang_dir, parsed.segments)
            return result
        seg.audio_path = str(out)
        seg.cache_hash = segment_cache_hash(
            seg, spoken_text=tts_text, spoken_norm_tag=spoken_tag
        )
        result["regenerated"] += 1
        info = _probe(out)
        audit = {
            "index": seg.index,
            "role": seg.speaker.value.upper(),
            "configured_voice": configured_voice,
            "actual_voice": used_voice,
            "configured_provider": "Edge TTS" if provider_id == "edge" else provider_id,
            "actual_provider": "Edge TTS" if used_provider.id == "edge" else used_provider.id,
            "substituted": used_voice != configured_voice or used_provider.id != provider_id,
        }
        result["voice_audit"].append(audit)
        result["segments"].append(
            {
                "index": seg.index,
                "role": seg.speaker.value.upper(),
                "voice": used_voice,
                "configured_voice": configured_voice,
                "actual_voice": used_voice,
                "provider": used_provider.id,
                "actual_provider": used_provider.id,
                "path": str(out),
                "cached": False,
                "source_text": seg.text,
                "spoken_text": tts_text,
                "probe": info,
                "valid": info["duration_sec"] > 0,
                "word_timings": synth_timings or _load_word_timings(out),
            }
        )

    if on_progress:
        on_progress(
            language,
            total + 1,
            work_total,
            f"Joining {language}…",
        )
    raw = lang_dir / "_raw_join.mp3"
    if raw.exists():
        raw.unlink()
    join_bitrate = mp3_bitrate or 128
    join_segments(
        parsed.segments,
        raw,
        pause_ms=pause_ms,
        bitrate_kbps=join_bitrate,
        also_wav=False,
    )
    mp3_path, wav_path = final_paths(root, job.date, language)
    export_label = "Mastering" if use_mastering else "Exporting"
    if on_progress:
        on_progress(
            language,
            total + 2,
            work_total,
            f"{export_label} {language}…",
        )
    if use_mastering:
        if on_progress:
            on_progress(
                language,
                total + 2,
                work_total,
                f"Mastering {language} (loudness + limits)…",
            )
        mastered = master_audio(
            raw,
            mp3_path,
            MasteringOptions(
                normalize_loudness=True,
                target_lufs=job.target_lufs,
                remove_silence=False,
                fade_in_ms=40,
                fade_out_ms=120,
                peak_limiter=True,
                bitrate_kbps=join_bitrate,
                lowpass_hz=preset.pipeline.lowpass_hz,
            ),
            overwrite=True,
        )
        if export_wav:
            if on_progress:
                on_progress(
                    language,
                    total + 2,
                    work_total,
                    f"Exporting {language} WAV…",
                )
            if wav_path.exists():
                wav_path.unlink()
            FFmpegService().convert(mastered, wav_path, bitrate_kbps=join_bitrate)
    else:
        if on_progress:
            on_progress(
                language,
                total + 2,
                work_total,
                f"Exporting {language} MP3…",
            )
        export_original_pipeline(
            raw,
            mp3_path if export_mp3 else None,
            wav_path if export_wav else None,
            preset.pipeline,
            overwrite=True,
        )
        mastered = mp3_path if export_mp3 and mp3_path.exists() else raw
    if on_progress:
        on_progress(
            language,
            total + 3,
            work_total,
            f"Finalizing {language}…",
        )
    if not export_mp3 and mastered.exists() and mastered.suffix.lower() == ".mp3":
        pass
    _save_cache(lang_dir, parsed.segments)
    result["final_mp3"] = str(mastered) if export_mp3 else ""
    result["final_wav"] = str(wav_path) if export_wav and wav_path.exists() else ""
    if export_mp3 and mastered and Path(mastered).is_file():
        if on_progress:
            on_progress(
                language,
                total + 3,
                work_total,
                f"Embedding artwork for {language}…",
            )
        _embed_locked_mp3_artwork(Path(mastered), job, language)
    result["mp3_probe"] = _probe(mastered)
    result["wav_probe"] = _probe(wav_path) if export_wav and wav_path.exists() else {}
    result["loudness"] = _loudness(mastered)
    if on_progress:
        on_progress(
            language,
            work_total,
            work_total,
            f"{language} export complete",
        )
    result["ok"] = all(s["valid"] for s in result["segments"]) and result["mp3_probe"].get("duration_sec", 0) > 0
    result["selected"] = True
    result["status"] = "COMPLETE" if result["ok"] else "FAILED"
    result["output_files"] = {
        "mp3": result["final_mp3"],
        "wav": result["final_wav"],
    }
    result["duration"] = (result["mp3_probe"] or {}).get("duration_sec", "")
    # Last used voices from audit (actual).
    if result.get("voice_audit"):
        result["actual_voice"] = " / ".join(
            sorted({a.get("actual_voice", "") for a in result["voice_audit"] if a.get("actual_voice")})
        )
    return result


def _embed_locked_mp3_artwork(mp3_path: Path, job: DailyJob, language: str) -> None:
    """WhatsApp / players show the locked 9:16 card, not a generated photo still."""
    try:
        from bmt_voice_studio.video.discovery import extract_metadata
        from bmt_voice_studio.video.locked_card import embed_locked_artwork, locked_card_jpeg_bytes
        from bmt_voice_studio.video.models import VideoProject

        texts = {
            "en": job.english_text,
            "fr": job.french_text,
            "sw": job.swahili_text,
            "pt": job.portuguese_text,
        }
        language_id = (language or "en").lower()
        source_text = texts.get(language_id, "")
        meta = extract_metadata(source_text)
        topic = str(meta.get("topic") or "").strip()
        # Do not brand a translated MP3 with an English or generic topic.
        # If the translated source lacks its explicit topic label, leave the
        # audio untouched and let Video Maker surface the validation error.
        if not topic:
            return
        from bmt_voice_studio.config.product import get_product

        profile = get_product(job.product_mode)
        project = VideoProject(
            topic=topic,
            title=meta.get("title") or topic,
            devotional_date=job.date.isoformat(),
            language=language_id,
            product_mode=job.product_mode or "bmt",
        )
        jpeg = locked_card_jpeg_bytes(project)
        embed_locked_artwork(
            mp3_path,
            jpeg,
            title=meta.get("topic") or profile.tagline,
            date_label=display_date(job.date),
            product=job.product_mode,
        )
    except Exception:
        return


async def run_daily_job(
    job: DailyJob,
    *,
    on_progress: ProgressFn | None = None,
    cancel_check: CancelFn | None = None,
) -> DailyResult:
    issues = preflight(job)
    if issues:
        return DailyResult(ok=False, status="FAILED", folder="", errors=issues)

    # Freeze the UI/devotional calendar date once — never re-derive from clock/UTC.
    # If the pasted message contains a date, that date wins over "today".
    from bmt_voice_studio.daily.message_date import detect_message_date

    found = detect_message_date(
        "\n".join(
            [
                job.english_text or "",
                job.french_text or "",
                job.swahili_text or "",
                job.portuguese_text or "",
                job.kinyarwanda_text or "",
                job.english_caption_text or "",
            ]
        )
    )
    job.date = freeze_devotional_date(found or job.date)

    root = ensure_daily_layout(job.date, job.base_exports)
    (root / "SOURCE" / "english_source.txt").write_text(job.english_text or "", encoding="utf-8")
    (root / "SOURCE" / "french_source.txt").write_text(job.french_text or "", encoding="utf-8")
    (root / "SOURCE" / "swahili_source.txt").write_text(job.swahili_text or "", encoding="utf-8")
    (root / "SOURCE" / "portuguese_source.txt").write_text(job.portuguese_text or "", encoding="utf-8")
    (root / "SOURCE" / "kinyarwanda_transcript.txt").write_text(job.kinyarwanda_text or "", encoding="utf-8")
    (root / "SOURCE" / "english_captions.txt").write_text(job.english_caption_text or "", encoding="utf-8")
    (root / "SOURCE" / "product_mode.txt").write_text((job.product_mode or "bmt").strip().lower(), encoding="utf-8")

    # Original Pipeline / BMT reference: force Edge TTS — never switch job.provider to Piper.
    job.provider = "edge" if (
        job.processing_mode == "original"
        or job.strict_source_mode
    ) else (job.provider or "edge")
    job.use_piper_fallback = False if (
        job.processing_mode == "original" or job.strict_source_mode
    ) else job.use_piper_fallback

    try:
        provider = get_provider(job.provider)
        ok, msg = await provider.health_check()
        original_locked = job.processing_mode == "original" or job.strict_source_mode
        if not ok:
            if original_locked:
                logger.warning("Edge catalog health check failed; trying generation anyway: %s", msg)
                if on_progress:
                    on_progress(
                        "OVERALL",
                        0,
                        1,
                        "Voice service check failed — generating anyway…",
                    )
            elif job.use_piper_fallback:
                piper = get_provider("piper")
                pok, pmsg = await piper.health_check()
                if pok:
                    job.provider = "piper"
                    if on_progress:
                        on_progress(
                            "OVERALL",
                            0,
                            14,
                            f"Edge TTS unavailable ({msg}) — Piper fallback "
                            "(PIPER DOES NOT MATCH BMT REFERENCE VOICES)",
                        )
                else:
                    return DailyResult(
                        ok=False,
                        status="FAILED",
                        folder=str(root),
                        errors=[
                            f"Edge TTS unavailable ({msg}); Piper not ready ({pmsg}). "
                            "Use Settings → Advanced → Troubleshooting → Export Cloud Fallback Package."
                        ],
                    )
            else:
                return DailyResult(
                    ok=False,
                    status="FAILED",
                    folder=str(root),
                    errors=[
                        f"EDGE TTS CONNECTION FAILED: {msg}. "
                        "Retry or use Settings → Advanced → Troubleshooting → Export Cloud Fallback Package."
                    ],
                )
    except Exception as exc:
        return DailyResult(
            ok=False,
            status="FAILED",
            folder=str(root),
            errors=[f"EDGE TTS CONNECTION FAILED: {exc}"],
        )

    english = None
    french = None
    swahili = None
    portuguese = None
    errors: list[str] = []
    cancelled = False
    selected = job.selected_language_ids()
    steps = max(1, len(selected))
    step = 0

    def _preset_for(lang_id: str) -> VoicePreset:
        cfg = get_language_config(lang_id)
        if cfg is None:
            raise RuntimeError(f"Unknown language: {lang_id}")
        return cfg.resolved_preset()

    if job.generate_english:
        step += 1
        if on_progress:
            on_progress("OVERALL", step, steps + 2, "Validating / generating English…")
            on_progress("ENGLISH", 0, 1, "Validating English…")
        english = await _synth_language(
            job=job,
            language="ENGLISH",
            text=job.english_text,
            preset=_preset_for("en"),
            root=root,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )
        if not english.get("ok"):
            errors.extend(english.get("errors") or ["English generation failed"])

    if cancel_check and cancel_check():
        cancelled = True

    if not cancelled and job.generate_french:
        step += 1
        if on_progress:
            on_progress("OVERALL", step, steps + 2, "Validating / generating French…")
            on_progress("FRENCH", 0, 1, "Validating French…")
        french = await _synth_language(
            job=job,
            language="FRENCH",
            text=job.french_text,
            preset=_preset_for("fr"),
            root=root,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )
        if not french.get("ok"):
            errors.extend(french.get("errors") or ["French generation failed"])

    if cancel_check and cancel_check():
        cancelled = True

    if not cancelled and job.generate_swahili:
        step += 1
        if on_progress:
            on_progress("OVERALL", step, steps + 2, "Validating / generating Swahili…")
            on_progress("SWAHILI", 0, 1, "Validating Swahili…")
        swahili = await _synth_language(
            job=job,
            language="SWAHILI",
            text=job.swahili_text,
            preset=_preset_for("sw"),
            root=root,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )
        if not swahili.get("ok"):
            errors.extend(swahili.get("errors") or ["Swahili generation failed"])

    if cancel_check and cancel_check():
        cancelled = True

    if not cancelled and job.generate_portuguese:
        step += 1
        if on_progress:
            on_progress("OVERALL", step, steps + 2, "Validating / generating Portuguese…")
            on_progress("PORTUGUESE", 0, 1, "Validating Portuguese…")
        portuguese = await _synth_language(
            job=job,
            language="PORTUGUESE",
            text=job.portuguese_text,
            preset=_preset_for("pt"),
            root=root,
            on_progress=on_progress,
            cancel_check=cancel_check,
        )
        if not portuguese.get("ok"):
            errors.extend(portuguese.get("errors") or ["Portuguese generation failed"])

    # Unselected languages: explicit NOT_SELECTED blocks for reports.
    if not job.generate_english:
        english = not_selected_language_block("en")
    if not job.generate_french:
        french = not_selected_language_block("fr")
    if not job.generate_swahili:
        swahili = not_selected_language_block("sw")
    if not job.generate_portuguese:
        portuguese = not_selected_language_block("pt")

    result_map = {
        "en": bool(english and english.get("ok")) if job.generate_english else None,
        "fr": bool(french and french.get("ok")) if job.generate_french else None,
        "sw": bool(swahili and swahili.get("ok")) if job.generate_swahili else None,
        "pt": bool(portuguese and portuguese.get("ok")) if job.generate_portuguese else None,
    }
    status = overall_status_selected(result_map, selected=selected)
    payload = {
        "date": job.date.isoformat(),
        "project_id": project_id(job.date),
        "display_date": display_date(job.date),
        "application_version": __version__,
        "selected_languages": selected,
        "pause_ms": job.pause_ms,
        "mp3_bitrate": job.mp3_bitrate,
        "target_lufs": job.target_lufs,
        "processing_mode": job.processing_mode,
        "provider": job.provider,
        "effective_english": effective_job_config(job, _preset_for("en")) if job.generate_english else None,
        "effective_french": effective_job_config(job, _preset_for("fr")) if job.generate_french else None,
        "effective_swahili": effective_job_config(job, _preset_for("sw")) if job.generate_swahili else None,
        "effective_portuguese": effective_job_config(job, _preset_for("pt")) if job.generate_portuguese else None,
        "folder": str(root),
        "status": status,
        "english": english,
        "french": french,
        "swahili": swahili,
        "portuguese": portuguese,
    }
    if on_progress:
        on_progress("OVERALL", steps + 1, steps + 2, "Output validation")
        on_progress("OVERALL", steps + 2, steps + 2, "Writing production report")
    md_path, json_path = write_reports(root, payload)
    upsert_entry(
        {
            "date": job.date.isoformat(),
            "project_id": project_id(job.date),
            "display_date": display_date(job.date),
            "selected_languages": selected,
            "english": bool(english and english.get("ok")) if job.generate_english else None,
            "french": bool(french and french.get("ok")) if job.generate_french else None,
            "swahili": bool(swahili and swahili.get("ok")) if job.generate_swahili else None,
            "portuguese": bool(portuguese and portuguese.get("ok")) if job.generate_portuguese else None,
            "status": status,
            "folder": str(root),
            "en_mp3": (english or {}).get("final_mp3", "") if job.generate_english else "",
            "fr_mp3": (french or {}).get("final_mp3", "") if job.generate_french else "",
            "sw_mp3": (swahili or {}).get("final_mp3", "") if job.generate_swahili else "",
            "pt_mp3": (portuguese or {}).get("final_mp3", "") if job.generate_portuguese else "",
            "en_duration": ((english or {}).get("mp3_probe") or {}).get("duration_sec") if job.generate_english else "",
            "fr_duration": ((french or {}).get("mp3_probe") or {}).get("duration_sec") if job.generate_french else "",
            "sw_duration": ((swahili or {}).get("mp3_probe") or {}).get("duration_sec") if job.generate_swahili else "",
            "pt_duration": ((portuguese or {}).get("mp3_probe") or {}).get("duration_sec") if job.generate_portuguese else "",
            "report": str(md_path),
        }
    )
    ok = status == "COMPLETE"
    return DailyResult(
        ok=ok,
        status=status,
        folder=str(root),
        english=english,
        french=french,
        swahili=swahili,
        portuguese=portuguese,
        report_md=str(md_path),
        report_json=str(json_path),
        errors=errors,
        payload=payload,
    )
