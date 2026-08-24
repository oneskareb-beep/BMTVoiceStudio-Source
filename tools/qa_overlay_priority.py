"""Render 12s overlay stress test and a ~50s realistic sample. Visual style unchanged."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DAY = date(2026, 8, 14)


def _ffmpeg(path: str, *args: str) -> None:
    subprocess.run([path, "-y", *args], check=True, capture_output=True)


def _extract(ffmpeg: str, video: Path, dest: Path, when: str) -> None:
    cmd = [ffmpeg, "-y"]
    if when.startswith("-"):
        cmd.extend(["-sseof", when, "-i", str(video)])
    else:
        cmd.extend(["-ss", when, "-i", str(video)])
    cmd.extend(["-frames:v", "1", "-update", "1", str(dest)])
    subprocess.run(cmd, check=True, capture_output=True)


def _write_captions_source(exports: Path) -> None:
    from bmt_voice_studio.daily.layout import ensure_daily_layout

    root = ensure_daily_layout(DAY, exports)
    report = root / "REPORTS" / "production.json"
    payload = {
        "english": {
            "ok": True,
            "pause_ms": 400,
            "segments": [
                {"index": 1, "spoken_text": "Believers Manna Today. Topic: Kingdom Priorities.", "probe": {"duration_sec": 5.5}},
                {
                    "index": 2,
                    "spoken_text": "Memory Verse. Matthew 6:33 Seek first the kingdom of God and His righteousness.",
                    "probe": {"duration_sec": 8.0},
                },
                {
                    "index": 3,
                    "spoken_text": "Devotional Insight. Seek first the kingdom of God, and every lesser worry finds its proper place.",
                    "probe": {"duration_sec": 22.0},
                },
                {
                    "index": 4,
                    "spoken_text": "Powerful Prayer. Lord, teach us to walk in obedience today.",
                    "probe": {"duration_sec": 10.0},
                },
            ],
        }
    }
    report.write_text(json.dumps(payload), encoding="utf-8")


def main() -> int:
    os.environ.setdefault("BMT_SKIP_LIBRARY_DIALOG", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    out = Path(os.environ.get("BMT_OVERLAY_QA_DIR") or str(ROOT / "qa_outputs" / "overlay_priority"))
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(out / "la"))
    os.environ.setdefault("BMT_DOCUMENTS_DIR", str(out / "docs"))
    os.environ.setdefault("BMT_PHYSICAL_DOCUMENTS_DIR", str(out / "phys"))
    os.environ.setdefault("BMT_DATA_ROOT", str(out / "data"))

    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
    from bmt_voice_studio.config.paths import default_exports_dir
    from bmt_voice_studio.resources import logo_path
    from bmt_voice_studio.video.composition import (
        _intro_outro_for_audio,
        build_composition_plan,
        overlay_windows,
        ranges_overlap,
        window_is_active,
    )
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, VideoProject, output_profile_for
    from bmt_voice_studio.video.title_cards import render_intro_card, render_outro_card, render_verse_card

    ffmpeg = FFmpegService().find()
    logo = logo_path()
    _write_captions_source(default_exports_dir())
    media = out / "bg.png"
    _ffmpeg(ffmpeg, "-f", "lavfi", "-i", "color=c=0x1E3A5F:s=1080x1920:d=1", "-frames:v", "1", str(media))

    renderer = VideoRenderer()
    report: dict = {"samples": {}}

    for name, seconds, captions in (("stress_12s", 12, False), ("realistic_50s", 50, True)):
        audio = out / f"{name}.wav"
        _ffmpeg(ffmpeg, "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-ar", "48000", "-ac", "2", str(audio))
        intro, outro = _intro_outro_for_audio(float(seconds), 5.5, 2.5)
        windows = overlay_windows(intro, float(seconds), outro, has_verse=True)
        collisions = {
            "verse_vs_lower": ranges_overlap(windows["verse_card"], windows["lower_third"]),
            "verse_vs_outro": ranges_overlap(windows["verse_card"], windows["outro"]),
            "lower_vs_outro": ranges_overlap(windows["lower_third"], windows["outro"]),
            "compact_vs_verse": ranges_overlap(windows["compact"], windows["verse_card"]),
            "compact_vs_outro": ranges_overlap(windows["compact"], windows["outro"]),
        }
        project = VideoProject(
            devotional_date=DAY.isoformat(),
            language="en",
            topic="Kingdom Priorities",
            week_focus="Walk in obedience today",
            month_theme="A season of harvest",
            memory_verse="Matthew 6:33 Seek first the kingdom of God and His righteousness.",
            template_id=TEMPLATE_BMT_CLASSIC,
            logo_path=str(logo or ""),
            output_profile=output_profile_for("standard_1080p"),
            show_captions=captions,
            skip_caption_header=True,
            caption_content="body_verse",
            render_speed="faster",
            audio_path=str(audio),
            audio_duration=probe_audio_duration(audio),
            media_items=[probe_media(media)],
        )
        still_dir = out / name
        still_dir.mkdir(parents=True, exist_ok=True)
        render_intro_card(project, still_dir / "intro_screen.png")
        render_verse_card(project, still_dir / "verse_screen.png")
        render_outro_card(project, still_dir / "outro_screen.png")
        sample = still_dir / f"{name}.mp4"
        plan = build_composition_plan(
            project,
            output_path=sample,
            temp_dir=still_dir / "temp",
            job_id=f"overlay_{name}",
        )
        rendered = renderer.render(project, plan, keep_temp_on_success=True)
        frames = {
            "intro": round(max(0.4, intro * 0.4), 2),
            "verse": round((windows["verse_card"][0] + windows["verse_card"][1]) / 2, 2),
            "lower": round((windows["lower_third"][0] + windows["lower_third"][1]) / 2, 2),
            "outro": round((windows["outro"][0] + windows["outro"][1]) / 2, 2),
        }
        if captions:
            frames["captions"] = 30.0
        extracted = {}
        for label, t in frames.items():
            dest = still_dir / f"frame_{label}.png"
            _extract(ffmpeg, Path(rendered), dest, f"{t:.2f}")
            extracted[label] = str(dest)
        report["samples"][name] = {
            "video": str(rendered),
            "intro": intro,
            "outro": outro,
            "windows": {k: [round(a, 3), round(b, 3)] for k, (a, b) in windows.items()},
            "active": {k: window_is_active(v) for k, v in windows.items()},
            "collisions": collisions,
            "frames": extracted,
        }
        print("SAMPLE", name, rendered)
        print("WINDOWS", json.dumps(report["samples"][name]["windows"]))
        print("COLLISIONS", collisions)

    report_path = out / "overlay_priority_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", report_path)
    bad = [
        f"{name}:{key}"
        for name, row in report["samples"].items()
        for key, hit in row["collisions"].items()
        if hit
    ]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
