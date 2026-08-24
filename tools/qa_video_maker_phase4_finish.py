"""Finish Phase 4 full-length Nature render and write the combined QA report."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAY = date(2026, 8, 14)


def main() -> int:
    import importlib.util

    spec = importlib.util.spec_from_file_location("qa4", ROOT / "tools" / "qa_video_maker_phase4.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)

    from bmt_voice_studio.video.captions import captions_for_language
    from bmt_voice_studio.video.discovery import language_tracks_for_day
    from bmt_voice_studio.video.media_probe import probe_audio_duration
    from bmt_voice_studio.video.models import TEMPLATE_BMT_NATURE

    ffmpeg = mod._ffmpeg()
    qa_dir = ROOT / "qa_outputs" / "video_maker_phase4"
    assets = mod.ensure_assets(ffmpeg, qa_dir / "assets")
    tracks = language_tracks_for_day(DAY)
    for t in tracks:
        if t.ready and t.audio_path and t.audio_duration <= 0.4:
            t.audio_duration = probe_audio_duration(t.audio_path)

    clip = qa_dir / "clips" / "en_80s.mp3"
    if not clip.is_file():
        en = next(t for t in tracks if t.language == "en" and t.ready)
        clip = mod.clip_audio(ffmpeg, Path(en.audio_path), clip, mod.SHORT_SEC)

    short_en = None
    for t in tracks:
        if t.language == "en" and t.ready:
            short_en = type(t)(
                **{**t.__dict__, "audio_path": str(clip), "audio_duration": probe_audio_duration(clip)}
            )
            break
    assert short_en is not None
    bench_project = mod.build_shared(assets, [short_en], captions=False, speed="standard", template=TEMPLATE_BMT_NATURE)

    report = {
        "ffmpeg": ffmpeg,
        "assets": [str(p) for p in assets],
        "ready": [t.language for t in tracks if t.ready],
        "discovered": {
            t.language: {"ready": t.ready, "topic": t.topic, "audio": t.audio_path, "duration": t.audio_duration}
            for t in tracks
        },
        "captions": {},
        "short_batch": {},
        "benchmark": {},
        "full_nature": {},
        "probes": {},
    }
    for lang in ("en", "fr", "sw", "pt"):
        dest = qa_dir / f"short_{lang}_nature_captions.mp4"
        if dest.is_file():
            report["short_batch"][lang] = {"output": str(dest), "size": dest.stat().st_size}
            report["probes"][dest.name] = mod.probe_mp4(ffmpeg, dest)
        cues = captions_for_language(DAY, lang, audio_duration=80.0, skip_header=True)
        text = " ".join(c.text for c in cues[:10])
        report["captions"][lang] = {
            "cue_count": len(cues),
            "first_start": cues[0].start if cues else None,
            "sample": text[:300],
            "has_english_seek": "Seek first" in text,
            "encoding_ok": "Ã" not in text and "�" not in text,
        }
    for speed in ("standard", "faster"):
        proj = bench_project.bind_language("en")
        proj.render_speed = speed
        dest = qa_dir / f"bench_en_{speed}.mp4"
        result = mod.render_one(proj, dest)
        probe = mod.probe_mp4(ffmpeg, dest)
        elapsed = float(result["metrics"].get("wall_elapsed") or 0)
        dur = float(probe.get("duration") or mod.SHORT_SEC)
        report["benchmark"][speed] = {
            "render_time": elapsed,
            "speed_factor": round(dur / elapsed, 2) if elapsed else 0,
            "output_size": probe["size_bytes"],
            "video_bitrate": probe["bitrate"],
            "quality_profile": (
                "Standard (x264 medium, current CRF)"
                if speed == "standard"
                else "Faster (x264 veryfast, CRF +2)"
            ),
            "x264_preset": result["metrics"].get("x264_preset"),
            "probe": probe,
        }

    full = mod.build_shared(assets, tracks, captions=False, speed="faster", template=TEMPLATE_BMT_NATURE)
    full = full.bind_language("en")
    full.show_captions = False
    print("FULL_AUDIO", full.audio_path, full.audio_duration, flush=True)
    dest = qa_dir / "full_en_nature.mp4"
    result = mod.render_one(full, dest)
    report["full_nature"] = result
    report["probes"][dest.name] = mod.probe_mp4(ffmpeg, dest)

    out = qa_dir / "phase4_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("WROTE", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
