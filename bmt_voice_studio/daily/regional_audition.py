"""Regional fallback voice auditions — Edge only, never auto-approved."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.audio.joining import join_segments
from bmt_voice_studio.audio.source_export import export_original_pipeline
from bmt_voice_studio.config.paths import default_exports_dir, local_appdata
from bmt_voice_studio.config.pipeline_config import PipelineSettings
from bmt_voice_studio.core.models import Segment, Speaker, SynthRequest, VoiceInfo
from bmt_voice_studio.core.parser import parse_speaker_script_source
from bmt_voice_studio.production_batch import _probe
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider
from bmt_voice_studio.providers.provider_guard import assert_provider_voice_compatible

# Shared sample scripts (male outside braces, female inside).
SWAHILI_SAMPLE_SCRIPT = (
    "Habari ndugu zangu. Leo tunakumbuka upendo wa Mungu katika maisha yetu ya kila siku. "
    "{Asante Bwana kwa neema yako na kwa neno lako.} "
    "Tuendelee kumtumaini Yesu Kristo kwa imani, na kuishi kwa amani na wengine."
)

PORTUGUESE_SAMPLE_SCRIPT = (
    "Bom dia, queridos irmãos. Hoje lembramos o amor de Deus em nossa caminhada diária. "
    "{Obrigada, Senhor, pela Tua graça e pela Tua palavra.} "
    "Continuemos a confiar em Jesus Cristo com fé, e a viver em paz uns com os outros."
)

AUDITION_RATE = "-10%"
AUDITION_PITCH = "-3Hz"
AUDITION_VOLUME = "+5%"
AUDITION_PAUSE_MS = 500
AUDITION_PIPELINE = PipelineSettings(
    pause_ms=500,
    lowpass_hz=7000,
    wav_channels=1,
    wav_sample_rate=44100,
    mp3_bitrate_kbps=192,
    export_wav=False,
    export_mp3=True,
    strict_source_mode=True,
    default_processing_mode="original",
    allow_piper_fallback=False,
    apply_bmt_mastering=False,
)

# Fixed Swahili candidate pairs (not Congo).
SW_KENYA = {
    "candidate_id": "sw_kenya",
    "language_id": "sw",
    "label": "KENYA",
    "fallback_locale": "sw-KE",
    "male_voice": "sw-KE-RafikiNeural",
    "female_voice": "sw-KE-ZuriNeural",
    "stem": "SWAHILI_KENYA_AUDITION",
    "banner": "Candidate fallback for Congo/DRC target",
}

SW_TANZANIA = {
    "candidate_id": "sw_tanzania",
    "language_id": "sw",
    "label": "TANZANIA",
    "fallback_locale": "sw-TZ",
    "male_voice": "sw-TZ-DaudiNeural",
    "female_voice": "sw-TZ-RehemaNeural",
    "stem": "SWAHILI_TANZANIA_AUDITION",
    "banner": "Candidate fallback for Congo/DRC target",
}

PT_PORTUGAL = {
    "candidate_id": "pt_portugal",
    "language_id": "pt",
    "label": "PORTUGAL",
    "fallback_locale": "pt-PT",
    "male_voice": "pt-PT-DuarteNeural",
    "female_voice": "pt-PT-RaquelNeural",
    "stem": "PORTUGUESE_PORTUGAL_AUDITION",
    "banner": "Candidate fallback for Angola target",
}


@dataclass
class AuditionResult:
    candidate_id: str
    language_id: str
    label: str
    fallback_locale: str
    banner: str
    male_voice: str
    female_voice: str
    male_sample_mp3: str = ""
    female_sample_mp3: str = ""
    combined_mp3: str = ""
    combined_wav: str = ""
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bitrate_kbps: float | None = None
    voice_audit: list[dict[str, Any]] = field(default_factory=list)
    provider: str = "edge"
    piper_invocations: int = 0
    ok: bool = False
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def auditions_dir() -> Path:
    path = default_exports_dir() / "Auditions" / "Regional"
    path.mkdir(parents=True, exist_ok=True)
    return path


def audition_manifest_path() -> Path:
    return local_appdata() / "regional_audition_manifest.json"


def save_manifest(results: list[AuditionResult]) -> Path:
    path = audition_manifest_path()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "auditions": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_manifest() -> dict[str, Any]:
    path = audition_manifest_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _gender_bucket(gender: str) -> str:
    g = (gender or "").lower()
    if "female" in g:
        return "female"
    if "male" in g:
        return "male"
    return "unknown"


def _is_disallowed_baseline_voice(voice_id: str) -> bool:
    low = (voice_id or "").lower()
    banned = ("mai", "flash", "child", "neuralhd", "dragonhd")
    return any(token in low for token in banned)


def select_brazil_pair(voices: list[VoiceInfo]) -> tuple[str, str]:
    """Pick one standard adult male + female pt-BR pair from live catalog."""
    br = [v for v in voices if (v.locale or "").lower() == "pt-br" or (v.id or "").lower().startswith("pt-br")]
    males = [
        v.id
        for v in br
        if _gender_bucket(v.gender) == "male" and not _is_disallowed_baseline_voice(v.id)
    ]
    females = [
        v.id
        for v in br
        if _gender_bucket(v.gender) == "female" and not _is_disallowed_baseline_voice(v.id)
    ]
    # Prefer classic Neural pair over Multilingual when both exist.
    preferred_male = "pt-BR-AntonioNeural"
    preferred_female = "pt-BR-FranciscaNeural"
    male = preferred_male if preferred_male in males else (males[0] if males else "")
    female = preferred_female if preferred_female in females else (females[0] if females else "")
    if not male or not female:
        raise RuntimeError(
            "No standard adult male+female pt-BR Neural pair found in live Edge catalog."
        )
    return male, female


def brazil_candidate_spec(voices: list[VoiceInfo]) -> dict[str, str]:
    male, female = select_brazil_pair(voices)
    return {
        "candidate_id": "pt_brazil",
        "language_id": "pt",
        "label": "BRAZIL",
        "fallback_locale": "pt-BR",
        "male_voice": male,
        "female_voice": female,
        "stem": "PORTUGUESE_BRAZIL_AUDITION",
        "banner": "Candidate fallback for Angola target",
    }


def all_candidate_specs(voices: list[VoiceInfo]) -> list[dict[str, str]]:
    return [dict(SW_KENYA), dict(SW_TANZANIA), dict(PT_PORTUGAL), brazil_candidate_spec(voices)]


async def _verify_voices_exist(voices: list[VoiceInfo], required: list[str]) -> list[str]:
    available = {(v.id or "") for v in voices}
    return [vid for vid in required if vid not in available]


async def generate_one_audition(
    spec: dict[str, str],
    *,
    voices: list[VoiceInfo] | None = None,
    script: str | None = None,
) -> AuditionResult:
    provider = EdgeTTSProvider()
    catalog = voices if voices is not None else await provider.list_voices()
    result = AuditionResult(
        candidate_id=spec["candidate_id"],
        language_id=spec["language_id"],
        label=spec["label"],
        fallback_locale=spec["fallback_locale"],
        banner=spec["banner"],
        male_voice=spec["male_voice"],
        female_voice=spec["female_voice"],
        provider="edge",
        piper_invocations=0,
    )

    missing = await _verify_voices_exist(
        catalog, [result.male_voice, result.female_voice]
    )
    if missing:
        result.errors.append("REQUIRED EDGE VOICE UNAVAILABLE: " + ", ".join(missing))
        return result

    for voice in (result.male_voice, result.female_voice):
        assert_provider_voice_compatible("edge", voice)

    text = script
    if text is None:
        text = SWAHILI_SAMPLE_SCRIPT if result.language_id == "sw" else PORTUGUESE_SAMPLE_SCRIPT

    parsed = parse_speaker_script_source(text)
    if not parsed.ok or not parsed.segments:
        result.errors = [e.message for e in parsed.errors] or ["No segments"]
        return result

    out_root = auditions_dir() / result.candidate_id
    seg_dir = out_root / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    male_only: Path | None = None
    female_only: Path | None = None

    for seg in parsed.segments:
        configured = result.male_voice if seg.speaker == Speaker.MALE else result.female_voice
        seg.voice = configured
        seg.rate = AUDITION_RATE
        seg.pitch = AUDITION_PITCH
        seg.volume = AUDITION_VOLUME
        seg.provider = "edge"
        out = seg_dir / f"{seg.index:03d}_{seg.speaker.value}.mp3"
        synth = await provider.synthesize(
            SynthRequest(
                text=seg.text,
                voice=configured,
                rate=AUDITION_RATE,
                pitch=AUDITION_PITCH,
                volume=AUDITION_VOLUME,
                output_path=str(out),
            )
        )
        if not synth.success:
            result.errors.append(synth.error or f"Segment {seg.index} failed")
            return result
        seg.audio_path = str(out)
        result.voice_audit.append(
            {
                "index": seg.index,
                "role": seg.speaker.value.upper(),
                "configured_voice": configured,
                "actual_voice": configured,
                "configured_provider": "Edge TTS",
                "actual_provider": "Edge TTS",
                "substituted": False,
            }
        )
        if seg.speaker == Speaker.MALE and male_only is None:
            male_only = out
        if seg.speaker == Speaker.FEMALE and female_only is None:
            female_only = out

    joined_raw = out_root / f"{spec['stem']}.__joined__.mp3"
    join_segments(
        parsed.segments,
        joined_raw,
        pause_ms=AUDITION_PAUSE_MS,
        bitrate_kbps=AUDITION_PIPELINE.mp3_bitrate_kbps or 192,
        also_wav=False,
    )

    mp3_path = auditions_dir() / f"{spec['stem']}.mp3"
    wav_path = auditions_dir() / f"{spec['stem']}.wav"
    export_original_pipeline(
        joined_raw,
        mp3_path,
        wav_path,
        AUDITION_PIPELINE,
        overwrite=True,
    )

    probe = _probe(mp3_path)
    result.combined_mp3 = str(mp3_path)
    result.combined_wav = str(wav_path) if wav_path.exists() else ""
    result.male_sample_mp3 = str(male_only) if male_only else ""
    result.female_sample_mp3 = str(female_only) if female_only else ""
    result.duration_sec = probe.get("duration_sec")
    result.sample_rate = probe.get("sample_rate")
    result.channels = probe.get("channels")
    result.bitrate_kbps = probe.get("bitrate_kbps")
    result.ok = bool(probe.get("duration_sec", 0) > 0) and mp3_path.exists()
    if not result.ok:
        result.errors.append("Audition export probe failed")
    return result


async def generate_all_regional_auditions() -> list[AuditionResult]:
    provider = EdgeTTSProvider()
    voices = await provider.list_voices()
    specs = all_candidate_specs(voices)
    missing_pt = await _verify_voices_exist(
        voices, [PT_PORTUGAL["male_voice"], PT_PORTUGAL["female_voice"]]
    )
    results: list[AuditionResult] = []
    for spec in specs:
        if spec["candidate_id"] == "pt_portugal" and missing_pt:
            bad = AuditionResult(
                candidate_id=spec["candidate_id"],
                language_id="pt",
                label=spec["label"],
                fallback_locale=spec["fallback_locale"],
                banner=spec["banner"],
                male_voice=spec["male_voice"],
                female_voice=spec["female_voice"],
                errors=["REQUIRED EDGE VOICE UNAVAILABLE: " + ", ".join(missing_pt)],
            )
            results.append(bad)
            continue
        results.append(await generate_one_audition(spec, voices=voices))
    save_manifest(results)
    return results


SWAHILI_MALE_REVIEW_SCRIPT = (
    "Ndugu zangu wapendwa, leo tunakumbuka kwamba Mungu anutupenda kwa neema yake. "
    "Ufalme wa Mungu unapaswa kuwa kipaumbele chetu cha kwanza katika maisha yetu ya kila siku. "
    "Yesu Kristo alituitia tuutafute Ufalme huo kwanza, kama ilivyoandikwa katika Mathayo. "
    "Roho Mtakatifu atusaidie kuishi kwa imani, kwa unyenyekevu, na kwa upendo kwa wengine. "
    "Tunamwomba Baba yetu wa mbinguni atupe hekima na nguvu za kuendelea katika safari yetu. "
    "Asante Mungu kwa Neno lako. Twakutumaini Yesu Kristo, sasa na siku zote. Amina."
)


async def generate_swahili_male_review_auditions() -> list[AuditionResult]:
    """Male-only comparison: Rafiki (KE) vs Daudi (TZ). Not Congo. Not production approval."""
    provider = EdgeTTSProvider()
    voices = await provider.list_voices()
    available = {(v.id or "") for v in voices}
    specs = [
        {
            "candidate_id": "sw_male_rafiki_ke",
            "language_id": "sw",
            "label": "RAFIKI — KENYA (male only)",
            "fallback_locale": "sw-KE",
            "male_voice": "sw-KE-RafikiNeural",
            "female_voice": "sw-KE-RafikiNeural",  # unused; male-only script
            "stem": "SWAHILI_MALE_RAFIKI_KE",
            "banner": "Male candidate comparison — not Congo; not approved",
            "rate": AUDITION_RATE,
            "pitch": AUDITION_PITCH,
        },
        {
            "candidate_id": "sw_male_daudi_tz",
            "language_id": "sw",
            "label": "DAUDI — TANZANIA (male only)",
            "fallback_locale": "sw-TZ",
            "male_voice": "sw-TZ-DaudiNeural",
            "female_voice": "sw-TZ-DaudiNeural",
            "stem": "SWAHILI_MALE_DAUDI_TZ",
            "banner": "Male candidate comparison — not Congo; not approved",
            "rate": AUDITION_RATE,
            "pitch": AUDITION_PITCH,
        },
        # Optional delivery variants (same voices, not different accents).
        {
            "candidate_id": "sw_male_rafiki_ke_variant_b",
            "language_id": "sw",
            "label": "RAFIKI — delivery variant B (-6% / -2Hz)",
            "fallback_locale": "sw-KE",
            "male_voice": "sw-KE-RafikiNeural",
            "female_voice": "sw-KE-RafikiNeural",
            "stem": "SWAHILI_MALE_RAFIKI_KE_VARIANT_B",
            "banner": "Delivery variant only — not a different regional accent",
            "rate": "-6%",
            "pitch": "-2Hz",
        },
        {
            "candidate_id": "sw_male_daudi_tz_variant_b",
            "language_id": "sw",
            "label": "DAUDI — delivery variant B (-6% / -2Hz)",
            "fallback_locale": "sw-TZ",
            "male_voice": "sw-TZ-DaudiNeural",
            "female_voice": "sw-TZ-DaudiNeural",
            "stem": "SWAHILI_MALE_DAUDI_TZ_VARIANT_B",
            "banner": "Delivery variant only — not a different regional accent",
            "rate": "-6%",
            "pitch": "-2Hz",
        },
    ]
    results: list[AuditionResult] = []
    for spec in specs:
        voice = spec["male_voice"]
        if voice not in available:
            results.append(
                AuditionResult(
                    candidate_id=spec["candidate_id"],
                    language_id="sw",
                    label=spec["label"],
                    fallback_locale=spec["fallback_locale"],
                    banner=spec["banner"],
                    male_voice=voice,
                    female_voice="",
                    errors=[f"REQUIRED EDGE VOICE UNAVAILABLE: {voice}"],
                )
            )
            continue
        results.append(
            await _generate_male_only_audition(
                spec,
                script=SWAHILI_MALE_REVIEW_SCRIPT,
                rate=spec.get("rate") or AUDITION_RATE,
                pitch=spec.get("pitch") or AUDITION_PITCH,
            )
        )
    # Merge into manifest without wiping Portuguese auditions.
    existing = load_manifest()
    by_id = {
        item.get("candidate_id"): item
        for item in (existing.get("auditions") or [])
        if item.get("candidate_id")
    }
    for r in results:
        by_id[r.candidate_id] = r.to_dict()
    path = audition_manifest_path()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "auditions": list(by_id.values()),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return results


def full_test_dir() -> Path:
    path = auditions_dir() / "Full_Test"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_swahili_full_test_script() -> str:
    """Prefer packaged sample; fall back to Daily SOURCE if a Swahili file appears later."""
    roots = [
        Path(__file__).resolve().parents[2] / "samples" / "swahili_full_test.txt",
        default_exports_dir() / "Daily",
    ]
    sample = roots[0]
    if sample.exists():
        return sample.read_text(encoding="utf-8")
    # Optional: newest swahili_source.txt under Daily exports
    daily = roots[1]
    if daily.exists():
        candidates = sorted(daily.rglob("swahili_source.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in candidates:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    raise FileNotFoundError("No Swahili full-test script found (samples/swahili_full_test.txt).")


async def generate_swahili_daudi_rehema_full_test() -> dict[str, Any]:
    """Full dual-voice Swahili trial — Daudi + Rehema. Not Daily History. Not approved."""
    from bmt_voice_studio.core.text_prepare import suppress_spoken_list_markers_counted
    from bmt_voice_studio.daily.regional_approval import (
        get_swahili_trial_pair,
        is_language_production_approved,
        set_swahili_trial_pair,
    )

    male_voice = "sw-TZ-DaudiNeural"
    female_voice = "sw-TZ-RehemaNeural"
    trial = set_swahili_trial_pair(
        male_voice=male_voice,
        female_voice=female_voice,
        trial_locale="sw-TZ",
        trial_pair="Daudi + Rehema",
    )

    provider = EdgeTTSProvider()
    catalog = await provider.list_voices()
    missing = await _verify_voices_exist(catalog, [male_voice, female_voice])
    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "trial_locale": "sw-TZ",
        "trial_pair": "Daudi + Rehema",
        "male_voice": male_voice,
        "female_voice": female_voice,
        "target_region": "Congo / DRC",
        "fallback_candidate": "Tanzania Swahili",
        "labeled_as_congo": False,
        "production_approved": False,
        "is_language_production_approved": is_language_production_approved("sw"),
        "written_to_daily_history": False,
        "provider": "edge",
        "piper_invocations": 0,
        "delivery": {
            "rate": AUDITION_RATE,
            "pitch": AUDITION_PITCH,
            "volume": AUDITION_VOLUME,
            "pause_ms": AUDITION_PAUSE_MS,
            "lowpass_hz": AUDITION_PIPELINE.lowpass_hz,
            "wav_sample_rate": AUDITION_PIPELINE.wav_sample_rate,
            "wav_channels": AUDITION_PIPELINE.wav_channels,
            "mp3_bitrate_kbps": AUDITION_PIPELINE.mp3_bitrate_kbps,
        },
        "trial_store": trial,
        "ok": False,
        "errors": [],
        "voice_audit": [],
    }
    if missing:
        report["errors"].append("REQUIRED EDGE VOICE UNAVAILABLE: " + ", ".join(missing))
        return report

    for voice in (male_voice, female_voice):
        assert_provider_voice_compatible("edge", voice)

    script = load_swahili_full_test_script()
    report["script_chars"] = len(script)
    parsed = parse_speaker_script_source(script)
    if not parsed.ok or not parsed.segments:
        report["errors"] = [e.message for e in parsed.errors] or ["No segments"]
        return report

    out_root = full_test_dir()
    seg_dir = out_root / "segments_daudi_rehema"
    seg_dir.mkdir(parents=True, exist_ok=True)

    male_count = 0
    female_count = 0
    for seg in parsed.segments:
        configured = male_voice if seg.speaker == Speaker.MALE else female_voice
        spoken, removed = suppress_spoken_list_markers_counted(seg.text, language="sw")
        seg.text = spoken
        seg.voice = configured
        seg.rate = AUDITION_RATE
        seg.pitch = AUDITION_PITCH
        seg.volume = AUDITION_VOLUME
        seg.provider = "edge"
        out = seg_dir / f"{seg.index:03d}_{seg.speaker.value}.mp3"
        synth = await provider.synthesize(
            SynthRequest(
                text=seg.text,
                voice=configured,
                rate=AUDITION_RATE,
                pitch=AUDITION_PITCH,
                volume=AUDITION_VOLUME,
                output_path=str(out),
            )
        )
        if not synth.success:
            report["errors"].append(synth.error or f"Segment {seg.index} failed")
            return report
        seg.audio_path = str(out)
        probe_seg = _probe(out)
        role = seg.speaker.value.upper()
        if seg.speaker == Speaker.MALE:
            male_count += 1
        else:
            female_count += 1
        report["voice_audit"].append(
            {
                "segment": seg.index,
                "speaker_role": role,
                "configured_voice": configured,
                "actual_voice": configured,
                "duration_sec": probe_seg.get("duration_sec"),
                "provider": "Edge TTS",
                "substitution": False,
                "spoken_list_markers_removed": removed,
            }
        )

    stem = "SWAHILI_DAUDI_REHEMA_FULL_TEST"
    joined_raw = out_root / f"{stem}.__joined__.mp3"
    join_segments(
        parsed.segments,
        joined_raw,
        pause_ms=AUDITION_PAUSE_MS,
        bitrate_kbps=AUDITION_PIPELINE.mp3_bitrate_kbps or 192,
        also_wav=False,
    )
    mp3_path = out_root / f"{stem}.mp3"
    wav_path = out_root / f"{stem}.wav"
    export_original_pipeline(joined_raw, mp3_path, wav_path, AUDITION_PIPELINE, overwrite=True)
    probe = _probe(mp3_path)

    report.update(
        {
            "ok": bool(probe.get("duration_sec", 0) > 0) and mp3_path.exists(),
            "mp3_path": str(mp3_path),
            "wav_path": str(wav_path) if wav_path.exists() else "",
            "duration_sec": probe.get("duration_sec"),
            "sample_rate": probe.get("sample_rate"),
            "channels": probe.get("channels"),
            "bitrate_kbps": probe.get("bitrate_kbps"),
            "segment_count": len(parsed.segments),
            "male_segment_count": male_count,
            "female_segment_count": female_count,
            "trial_snapshot": get_swahili_trial_pair(),
        }
    )
    if not report["ok"]:
        report["errors"].append("Full test export probe failed")

    report_path = out_root / f"{stem}_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


async def _generate_male_only_audition(
    spec: dict[str, str],
    *,
    script: str,
    rate: str,
    pitch: str,
) -> AuditionResult:
    provider = EdgeTTSProvider()
    result = AuditionResult(
        candidate_id=spec["candidate_id"],
        language_id=spec["language_id"],
        label=spec["label"],
        fallback_locale=spec["fallback_locale"],
        banner=spec["banner"],
        male_voice=spec["male_voice"],
        female_voice="",
        provider="edge",
        piper_invocations=0,
    )
    voice = spec["male_voice"]
    assert_provider_voice_compatible("edge", voice)

    out_root = auditions_dir() / result.candidate_id
    seg_dir = out_root / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    out = seg_dir / "001_male.mp3"
    synth = await provider.synthesize(
        SynthRequest(
            text=script,
            voice=voice,
            rate=rate,
            pitch=pitch,
            volume=AUDITION_VOLUME,
            output_path=str(out),
        )
    )
    if not synth.success:
        result.errors.append(synth.error or "Male audition synthesis failed")
        return result

    seg = Segment(
        index=1,
        speaker=Speaker.MALE,
        text=script,
        voice=voice,
        rate=rate,
        pitch=pitch,
        volume=AUDITION_VOLUME,
        provider="edge",
        audio_path=str(out),
    )
    result.voice_audit.append(
        {
            "index": 1,
            "role": "MALE",
            "configured_voice": voice,
            "actual_voice": voice,
            "configured_provider": "Edge TTS",
            "actual_provider": "Edge TTS",
            "substituted": False,
            "rate": rate,
            "pitch": pitch,
        }
    )

    joined_raw = out_root / f"{spec['stem']}.__joined__.mp3"
    join_segments(
        [seg],
        joined_raw,
        pause_ms=0,
        bitrate_kbps=AUDITION_PIPELINE.mp3_bitrate_kbps or 192,
        also_wav=False,
    )
    mp3_path = auditions_dir() / f"{spec['stem']}.mp3"
    wav_path = auditions_dir() / f"{spec['stem']}.wav"
    export_original_pipeline(joined_raw, mp3_path, wav_path, AUDITION_PIPELINE, overwrite=True)
    probe = _probe(mp3_path)
    result.male_sample_mp3 = str(out)
    result.combined_mp3 = str(mp3_path)
    result.combined_wav = str(wav_path) if wav_path.exists() else ""
    result.duration_sec = probe.get("duration_sec")
    result.sample_rate = probe.get("sample_rate")
    result.channels = probe.get("channels")
    result.bitrate_kbps = probe.get("bitrate_kbps")
    result.ok = bool(probe.get("duration_sec", 0) > 0) and mp3_path.exists()
    if not result.ok:
        result.errors.append("Male audition export probe failed")
    return result
