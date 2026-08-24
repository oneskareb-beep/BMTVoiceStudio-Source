"""Gate 1 — Piper offline via Voice Manager code paths (no UI hacks)."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\aganz\Documents\BMTVoiceStudio")
sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.config.paths import models_dir, temp_work_dir
from bmt_voice_studio.config.settings import get_settings, save_settings
from bmt_voice_studio.core.models import SynthRequest
from bmt_voice_studio.providers import get_provider, reset_registry
from bmt_voice_studio.providers.edge_tts import EdgeTTSProvider
from bmt_voice_studio.providers.piper import PiperProvider, PiperVoiceManager


def probe_duration(path: Path) -> float:
    r = FFmpegService().run(["-i", str(path)], check=False)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", (r.stderr or ""))
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


async def main() -> int:
    report: dict = {"gate": "piper_offline", "checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": ok, "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    mgr = PiperVoiceManager()
    voice_id = "en_US-lessac-medium"  # medium quality, Voice Manager catalog entry

    print("=== Ensure Piper binary (Voice Manager path) ===")
    exe = await mgr.ensure_piper_binary(on_progress=print)
    check("piper_binary", exe.exists(), str(exe))

    print("=== Download model via Voice Manager download_voice ===")
    info = await mgr.download_voice(voice_id, on_progress=print)
    model_root = models_dir() / "voices" / voice_id
    check("download_ok", info.installed and info.id == voice_id, info.id)
    check("stored_under_models", model_root.exists(), str(model_root))
    check("onnx_present", (model_root / f"{voice_id}.onnx").exists())
    check("json_present", (model_root / f"{voice_id}.onnx.json").exists())
    meta = model_root / "voice_meta.json"
    check("metadata_detected", meta.exists(), meta.read_text(encoding="utf-8")[:200] if meta.exists() else "")
    card = mgr.get_model_card(voice_id)
    check("model_card", len(card) > 10, card[:120].replace("\n", " "))

    installed = mgr.installed_voices()
    check("installed_list", any(v.id == voice_id for v in installed), str([v.id for v in installed]))

    # Assign as male + female fallback (single model for gate; still valid assignment path)
    settings = get_settings()
    settings.piper_male_model = voice_id
    settings.piper_female_model = voice_id
    settings.auto_piper_fallback = True
    save_settings(settings)
    loaded = get_settings()
    check(
        "assign_fallback_voices",
        loaded.piper_male_model == voice_id and loaded.piper_female_model == voice_id,
        f"male={loaded.piper_male_model} female={loaded.piper_female_model}",
    )

    reset_registry()
    piper = get_provider("piper")

    # Preview (same as Voice Manager audition)
    preview_out = temp_work_dir() / "gate1_piper_preview.wav"
    if preview_out.exists():
        preview_out.unlink()
    prev = await piper.preview(voice_id, text="This is a Piper offline voice preview.", output_path=str(preview_out))
    check("preview", prev.success and preview_out.exists() and preview_out.stat().st_size > 1000, prev.error or str(preview_out))
    if prev.success:
        check("preview_duration", probe_duration(preview_out) > 0.3, f"{probe_duration(preview_out):.2f}s")

    # Direct Piper generation (provider=piper, no Edge)
    gen_out = temp_work_dir() / "gate1_piper_paragraph.mp3"
    if gen_out.exists():
        gen_out.unlink()
    edge_calls = {"n": 0}

    class CountingEdge(EdgeTTSProvider):
        async def synthesize(self, request, *, cancel_check=None, on_progress=None):
            edge_calls["n"] += 1
            return await super().synthesize(request, cancel_check=cancel_check, on_progress=on_progress)

    # Register counting edge but use piper provider explicitly
    from bmt_voice_studio.providers import register_provider

    register_provider(CountingEdge())
    result = await piper.synthesize(
        SynthRequest(
            text="Beloved, seek first the kingdom of God. This paragraph is generated offline with Piper.",
            voice=voice_id,
            output_path=str(gen_out),
        )
    )
    check("piper_generate", result.success, result.error or str(gen_out))
    check("piper_provider_tag", result.provider == "piper", result.provider)
    check("edge_not_called_when_piper_selected", edge_calls["n"] == 0, f"edge_calls={edge_calls['n']}")
    dur = probe_duration(gen_out) if gen_out.exists() else 0
    check("piper_audio_valid", gen_out.exists() and dur > 0.5 and gen_out.stat().st_size > 1000, f"dur={dur:.2f}s size={gen_out.stat().st_size if gen_out.exists() else 0}")
    report["piper_model"] = voice_id
    report["audio_output"] = str(gen_out)
    report["duration_sec"] = dur

    # Automatic fallback: Edge fails -> Piper succeeds
    class BoomEdge(EdgeTTSProvider):
        async def synthesize(self, request, *, cancel_check=None, on_progress=None):
            edge_calls["n"] += 1
            from bmt_voice_studio.core.models import SynthResult

            return SynthResult(
                success=False,
                error="Could not connect to Edge TTS. Your internet connection may be unavailable.",
                provider="edge",
            )

    reset_registry()
    register_provider(BoomEdge())
    register_provider(PiperProvider())
    settings = get_settings()
    settings.auto_piper_fallback = True
    settings.piper_male_model = voice_id
    settings.piper_female_model = voice_id
    save_settings(settings)

    # Simulate GenerationController auto-fallback path
    from bmt_voice_studio.core.models import Segment, Speaker
    from bmt_voice_studio.core.hashing import segment_cache_hash

    edge_calls["n"] = 0
    seg = Segment(
        index=1,
        speaker=Speaker.MALE,
        text="Automatic fallback test paragraph for Believers Manna Today.",
        voice="en-NG-AbeoNeural",
        rate="-10%",
        pitch="-3Hz",
        provider="edge",
    )
    out = temp_work_dir() / "gate1_auto_fallback.mp3"
    if out.exists():
        out.unlink()

    provider = get_provider("edge")
    result = await provider.synthesize(
        SynthRequest(text=seg.text, voice=seg.voice, rate=seg.rate, pitch=seg.pitch, output_path=str(out))
    )
    check("edge_simulated_fail", not result.success, result.error)

    if settings.auto_piper_fallback and not result.success:
        piper = get_provider("piper")
        seg.voice = settings.piper_male_model
        seg.provider = "piper"
        result = await piper.synthesize(
            SynthRequest(text=seg.text, voice=seg.voice, output_path=str(out))
        )
        check("auto_fallback_piper_success", result.success and result.provider == "piper", result.error or str(out))
        check("auto_fallback_audio", out.exists() and probe_duration(out) > 0.3, f"dur={probe_duration(out):.2f}s")
        report["auto_fallback_output"] = str(out)
        report["auto_fallback_duration"] = probe_duration(out)

    # Return to Edge TTS afterward
    reset_registry()
    edge = get_provider("edge")
    back = temp_work_dir() / "gate1_back_to_edge.mp3"
    if back.exists():
        back.unlink()
    er = await edge.synthesize(
        SynthRequest(
            text="Back to Edge TTS after Piper fallback.",
            voice="en-NG-AbeoNeural",
            rate="-10%",
            pitch="-3Hz",
            output_path=str(back),
        )
    )
    check("return_to_edge", er.success and er.provider == "edge", er.error or str(back))

    failed = sum(1 for c in report["checks"] if not c["ok"])
    report["passed"] = sum(1 for c in report["checks"] if c["ok"])
    report["failed"] = failed
    out_json = ROOT / "GATE1_PIPER_RESULTS.json"
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out_json)
    print("SUMMARY", report["passed"], "passed,", failed, "failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
