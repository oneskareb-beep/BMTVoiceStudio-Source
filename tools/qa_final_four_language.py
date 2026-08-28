"""Final four-language production validation for BMT Voice Studio 1.3.0-RC2.

Validation only — no redesign, no FINAL packaging, no TTS regeneration.
Uses the user's chosen active data root and real Daily Audio + real media.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Force the user's real library (do not inherit polluted QA env).
os.environ["LOCALAPPDATA"] = str(Path.home() / "AppData" / "Local")
os.environ["BMT_DATA_ROOT"] = str(Path.home() / "Documents" / "BMT Voice Studio")
for key in ("BMT_DOCUMENTS_DIR", "BMT_PHYSICAL_DOCUMENTS_DIR", "BMT_SKIP_LIBRARY_DIALOG"):
    os.environ.pop(key, None)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("BMT_SKIP_LIBRARY_DIALOG", "1")

DAY = date(2026, 8, 14)
SHOTS = ROOT / "qa_screenshots" / "final_four_language"
REPORT = ROOT / "qa_outputs" / "final_four_language" / "FINAL_FOUR_LANGUAGE_REPORT.json"
EXPECTED_RC2 = "4aae46472270b7dec4571e3f19f9ce1be98c9019402f7bbfe9488416b7221cb9"
EXPECTED_VOICES = {
    "english": {"en-NG-AbeoNeural", "en-NG-EzinneNeural"},
    "french": {"fr-FR-HenriNeural", "fr-FR-DeniseNeural"},
    "swahili": {"sw-KE-RafikiNeural", "sw-KE-ZuriNeural"},
    "portuguese": {"pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"},
}
CONTAMINATION_MARKERS = {
    "en": [],
    "fr": ["Kingdom Priorities", "Seek first the kingdom", "Living With Eternal"],
    "sw": ["Kingdom Priorities", "Seek first the kingdom", "Les priorités", "Prioridades do Reino"],
    "pt": ["Kingdom Priorities", "Seek first the kingdom", "Les priorités", "Vipaumbele"],
}


def ffmpeg() -> str:
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService

    return FFmpegService().find()


def probe_mp4(path: Path) -> dict:
    result = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    blob = (result.stderr or "") + (result.stdout or "")
    from bmt_voice_studio.video.media_probe import parse_ffmpeg_duration, parse_ffmpeg_video_size

    w, h = parse_ffmpeg_video_size(blob)
    fps = 0.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", blob)
    if m:
        fps = float(m.group(1))
    pix = ""
    pm = re.search(r"yuv\w+", blob)
    if pm:
        pix = pm.group(0)
    audio_streams = len(re.findall(r"Stream #.*Audio:", blob, flags=re.IGNORECASE))
    video_streams = len(re.findall(r"Stream #.*Video:", blob, flags=re.IGNORECASE))
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "size_mb": round(path.stat().st_size / (1024 * 1024), 2) if path.is_file() else 0.0,
        "width": w,
        "height": h,
        "fps": fps,
        "duration": parse_ffmpeg_duration(blob),
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "h264": "h264" in blob.lower() or "avc" in blob.lower(),
        "yuv420p": "yuv420p" in blob.lower(),
        "aac": "aac" in blob.lower(),
        "sample_rate_48000": "48000" in blob,
        "pixel_format": pix,
    }


def extract_frame(video: Path, dest: Path, when: float) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg(), "-y", "-ss", f"{when:.2f}", "-i", str(video), "-frames:v", "1", "-update", "1", str(dest)],
        check=True,
        capture_output=True,
    )


def pick_media() -> list[Path]:
    downloads = Path.home() / "Downloads"
    candidates = [
        downloads / "ARABICA AA.png",
        downloads / "ARABICA AB.png",
        downloads / "ARABICA NATURAL.png",
        downloads / "mixkit-meadow-covered-with-grass-and-trees-in-the-blazing-sun-40657-hd-ready.mp4",
        downloads / "100176-video-720.mp4",
        downloads / "100177-video-720.mp4",
    ]
    found = [p for p in candidates if p.is_file()]
    if len([p for p in found if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]) < 3:
        raise SystemExit(f"Need >=3 real photos, found {found}")
    if len([p for p in found if p.suffix.lower() in {".mp4", ".mov", ".m4v"}]) < 3:
        raise SystemExit(f"Need >=3 real videos, found {found}")
    # Keep real photo content, but cap huge stills so Ken Burns stays within realistic encode time.
    prepared_dir = ROOT / "qa_outputs" / "final_four_language" / "media"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    from PIL import Image

    for path in found:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            dest = prepared_dir / f"{path.stem}_1080.jpg"
            if not dest.is_file() or dest.stat().st_mtime < path.stat().st_mtime:
                im = Image.open(path).convert("RGB")
                im.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                im.save(dest, "JPEG", quality=92)
            out.append(dest)
        else:
            out.append(path)
    return out


def contamination_hits(language: str, texts: list[str]) -> list[str]:
    hits: list[str] = []
    blob = "\n".join(texts)
    for marker in CONTAMINATION_MARKERS.get(language, []):
        if marker and marker in blob:
            hits.append(marker)
    # Cross-check language-specific expected markers presence
    return hits


def main() -> int:
    from bmt_voice_studio.release_scan import STABLE_12_SHA256, STABLE_12_ZIP_NAME, sha256_file
    from bmt_voice_studio.config.paths import user_data_root, default_exports_dir, settings_file
    from bmt_voice_studio.daily.layout import daily_project_dir
    from bmt_voice_studio.resources import logo_path
    from bmt_voice_studio.video.batch import projects_for_batch
    from bmt_voice_studio.video.captions import captions_for_language
    from bmt_voice_studio.video.composition import (
        _intro_outro_for_audio,
        build_composition_plan,
        overlay_windows,
        ranges_overlap,
        window_is_active,
    )
    from bmt_voice_studio.video.discovery import language_tracks_for_day
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.history import load_video_history, upsert_video_entry
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import (
        TEMPLATE_BMT_NATURE,
        BrandingToggles,
        VideoProject,
        output_profile_for,
    )
    from bmt_voice_studio.video.paths import new_job_id, video_output_path, video_render_temp_dir
    from bmt_voice_studio.video.project_store import load_project, save_project
    from bmt_voice_studio.video.title_cards import render_intro_card, render_outro_card, render_verse_card

    report: dict = {"checks": [], "languages": {}, "recommendation": "NOT READY"}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    # SHA integrity
    zip12 = ROOT / "release" / STABLE_12_ZIP_NAME
    digest12 = sha256_file(zip12)
    check("stable_12_sha", digest12 == STABLE_12_SHA256, digest12)
    if digest12 != STABLE_12_SHA256:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print("STOP: stable 1.2 SHA changed")
        return 2
    rc_zip = ROOT / "release-candidate" / "BMTVoiceStudio-1.3.0-RC2-Windows-x64-Portable.zip"
    digest_rc = sha256_file(rc_zip)
    check("rc2_sha", digest_rc == EXPECTED_RC2, digest_rc)
    report["active_data_root"] = str(user_data_root())
    report["exports"] = str(default_exports_dir())
    report["settings"] = str(settings_file())
    check("active_data_root", Path(report["active_data_root"]).is_dir(), report["active_data_root"])

    # Daily discovery
    tracks = language_tracks_for_day(DAY)
    ready = [t for t in tracks if t.ready]
    check("four_languages_ready", len(ready) == 4, str([(t.language, round(t.audio_duration, 1)) for t in ready]))
    if len(ready) != 4:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    prod_path = daily_project_dir(DAY) / "REPORTS" / "production.json"
    prod = json.loads(prod_path.read_text(encoding="utf-8"))
    piper = 0
    voice_ok = True
    found_by_lang: dict[str, list[str]] = {}
    for key, expected in EXPECTED_VOICES.items():
        block = prod.get(key) or {}
        segs = block.get("segments") or []
        found = {
            str(s.get("voice") or "")
            for s in segs
            if isinstance(s, dict) and str(s.get("voice") or "").strip()
        }
        for field in ("male_voice", "female_voice", "configured_male_voice", "configured_female_voice"):
            val = str(block.get(field) or "").strip()
            if val:
                found.add(val)
        found_by_lang[key] = sorted(found)
        if not expected.issubset(found):
            voice_ok = False
        try:
            piper += int(block.get("piper_invocations") or 0)
        except (TypeError, ValueError):
            piper += 0
    check("production_voices", voice_ok, json.dumps(found_by_lang))
    check("piper_invocations_zero", piper == 0, str(piper))
    report["daily_sources"] = {t.language: t.audio_path for t in ready}
    report["production_json"] = str(prod_path)

    # Shared visual project
    media_paths = pick_media()
    items = []
    for i, path in enumerate(media_paths):
        item = probe_media(str(path))
        item.order = i
        item.crop_x = 0.06 if i % 2 == 0 else -0.04
        item.crop_y = 0.03 if i % 3 == 0 else -0.02
        item.zoom = 1.08 if item.media_type == "image" else 1.05
        if item.media_type == "video":
            item.trim_start = 0.5
            item.trim_end = min(float(item.duration or 10.0), 9.0)
            item.animation_mode = "static"
        else:
            item.animation_mode = "zoom_in" if i % 2 == 0 else "pan_lr"
        items.append(item)
    logo = logo_path()
    project = VideoProject(
        devotional_date=DAY.isoformat(),
        language=ready[0].language,
        audio_path=ready[0].audio_path,
        audio_duration=ready[0].audio_duration,
        topic=ready[0].topic,
        week_focus=ready[0].week_focus,
        month_theme=ready[0].month_theme,
        title=ready[0].title,
        memory_verse=ready[0].memory_verse,
        logo_path=str(logo or ""),
        media_items=items,
        template_id=TEMPLATE_BMT_NATURE,
        languages=list(tracks),
        selected_languages=[t.language for t in ready],
        show_captions=True,
        skip_caption_header=True,
        caption_content="body_verse",
        render_speed="standard",
        output_profile=output_profile_for("standard_1080p"),
        branding=BrandingToggles(captions=True),
    )
    save_project(project)
    report["media"] = [str(p) for p in media_paths]
    report["template"] = TEMPLATE_BMT_NATURE
    report["caption_mode"] = "body_verse"

    clones = projects_for_batch(project, [t.language for t in ready])
    check("batch_clones", len(clones) == 4, str([c.language for c in clones]))
    renderer = VideoRenderer()
    contamination_total = 0
    lang_results: dict = {}
    resume = (os.environ.get("BMT_FOUR_LANG_RESUME") or "1").strip().lower() not in {"0", "false", "no"}

    for clone in clones:
        lang = clone.language
        label = {"en": "EN", "fr": "FR", "sw": "SW", "pt": "PT"}[lang]
        expected_out = video_output_path(DAY, lang, profile_id=clone.output_profile.id)
        # Prefer newest unique sibling if a prior run already wrote VIDEO_2 etc.
        candidates = []
        for cand in expected_out.parent.glob(expected_out.stem + "*.mp4"):
            name = cand.name.upper()
            if "PREPOLISH" in name or "PREVIEW" in name:
                continue
            # Accept VIDEO.mp4 or VIDEO_2.mp4 style only.
            if not re.match(rf"^{re.escape(expected_out.stem)}(_\d+)?\.MP4$", name, flags=re.IGNORECASE):
                continue
            candidates.append(cand)
        candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
        existing = None
        for cand in candidates:
            probe_existing = probe_mp4(cand)
            if (
                resume
                and probe_existing.get("exists")
                and abs(float(probe_existing.get("duration") or 0.0) - float(clone.audio_duration or 0.0)) <= 0.75
                and probe_existing.get("width") == 1080
                and probe_existing.get("h264")
            ):
                existing = cand
                break
        print("RENDER", label, clone.audio_path, "dur", clone.audio_duration, "resume" if existing else "fresh")
        intro, outro = _intro_outro_for_audio(clone.audio_duration, clone.intro_duration, clone.outro_duration)
        windows = overlay_windows(
            intro,
            clone.audio_duration,
            outro,
            has_verse=bool((clone.memory_verse or "").strip() or (clone.week_focus or "").strip()),
        )
        collisions = {
            "verse_vs_lower": ranges_overlap(windows["verse_card"], windows["lower_third"]),
            "verse_vs_outro": ranges_overlap(windows["verse_card"], windows["outro"]),
            "lower_vs_outro": ranges_overlap(windows["lower_third"], windows["outro"]),
        }
        cues = captions_for_language(
            DAY,
            lang,
            audio_duration=clone.audio_duration,
            skip_header=True,
            caption_mode="body_verse",
        )
        cue_text = [c.text for c in cues]
        hits = contamination_hits(lang, [clone.topic, clone.week_focus, clone.month_theme, clone.memory_verse, *cue_text])
        contamination_total += len(hits)

        still_dir = SHOTS / label
        still_dir.mkdir(parents=True, exist_ok=True)
        render_intro_card(clone, still_dir / "intro_still.png")
        render_verse_card(clone, still_dir / "verse_still.png")
        render_outro_card(clone, still_dir / "outro_still.png")

        if existing is not None:
            rendered = existing
            elapsed = 0.0
            metrics = {"resumed": True, "wall_elapsed": 0.0, "video_duration": probe_mp4(existing).get("duration")}
        else:
            job = new_job_id()
            out = expected_out
            temp = video_render_temp_dir(job)
            plan = build_composition_plan(clone, output_path=out, temp_dir=temp, job_id=job)
            started = time.time()
            rendered = renderer.render(clone, plan, keep_temp_on_success=False)
            elapsed = time.time() - started
            metrics = dict(renderer.last_metrics or {})
            metrics["wall_elapsed"] = round(elapsed, 2)
        probe = probe_mp4(Path(rendered))
        master = float(clone.audio_duration or 0.0)
        delta = abs(float(probe.get("duration") or 0.0) - master)

        # Representative frames
        frames = {
            "intro": max(0.8, intro * 0.45),
            "verse": (windows["verse_card"][0] + windows["verse_card"][1]) / 2 if window_is_active(windows["verse_card"]) else intro + 2,
            "main_caption": min(master - 8.0, max(intro + 20.0, windows["lower_third"][0] + 1.0 if window_is_active(windows["lower_third"]) else intro + 20)),
            "outro": (windows["outro"][0] + windows["outro"][1]) / 2 if window_is_active(windows["outro"]) else master - 1.2,
        }
        extracted = {}
        for name, t in frames.items():
            dest = still_dir / f"frame_{name}.png"
            try:
                extract_frame(Path(rendered), dest, float(t))
                extracted[name] = str(dest)
            except Exception as exc:
                extracted[name] = f"ERR:{exc}"

        upsert_video_entry(
            {
                "date": DAY.isoformat(),
                "language": lang,
                "template": "BMT Nature",
                "quality": "Standard 1080p",
                "duration": f"{probe.get('duration') or 0:.1f}s",
                "size": f"{probe.get('size_mb')} MB",
                "status": "complete",
                "output": str(rendered),
                "elapsed_sec": metrics.get("elapsed_sec") or metrics.get("wall_elapsed"),
                "speed": metrics.get("speed"),
            }
        )

        lang_results[lang] = {
            "label": label,
            "audio": clone.audio_path,
            "master_duration": master,
            "video": str(rendered),
            "probe": probe,
            "duration_delta": round(delta, 3),
            "metrics": metrics,
            "windows": {k: [round(a, 3), round(b, 3)] for k, (a, b) in windows.items()},
            "collisions": collisions,
            "topic": clone.topic,
            "week_focus": clone.week_focus,
            "month_theme": clone.month_theme,
            "memory_verse": clone.memory_verse,
            "caption_cues": len(cues),
            "caption_sample": " | ".join(cue_text[:4]),
            "contamination_hits": hits,
            "frames": extracted,
            "codec_ok": bool(
                probe.get("h264")
                and (probe.get("yuv420p") or str(probe.get("pixel_format") or "").startswith("yuvj420"))
                and probe.get("width") == 1080
                and probe.get("height") == 1920
                and probe.get("fps", 0) >= 29
                and probe.get("aac")
                and probe.get("sample_rate_48000")
                and probe.get("video_streams") == 1
                and probe.get("audio_streams") == 1
            ),
            "sync_ok": delta <= 0.75,
            "collision_ok": not any(collisions.values()),
        }
        check(f"{label}_codec", lang_results[lang]["codec_ok"], json.dumps(probe))
        check(f"{label}_sync", lang_results[lang]["sync_ok"], f"delta={delta}")
        check(f"{label}_collisions", lang_results[lang]["collision_ok"], str(collisions))
        check(f"{label}_contamination", not hits, str(hits))
        print("DONE", label, rendered, "MB", probe.get("size_mb"), "delta", delta)

    report["languages"] = lang_results
    report["contamination_count"] = contamination_total
    check("contamination_total_zero", contamination_total == 0, str(contamination_total))

    # Project restore
    loaded = load_project()
    restore_ok = (
        loaded.template_id == TEMPLATE_BMT_NATURE
        and loaded.caption_content == "body_verse"
        and loaded.show_captions is True
        and loaded.render_speed == "standard"
        and loaded.selected_languages == ["en", "fr", "sw", "pt"]
        and len(loaded.media_items) == 6
        and loaded.media_items[0].zoom == items[0].zoom
        and loaded.media_items[3].trim_start == items[3].trim_start
    )
    history = load_video_history()
    hist_langs = {str(e.get("language") or "").lower() for e in history if str(e.get("date") or "") == DAY.isoformat()}
    history_ok = {"en", "fr", "sw", "pt"}.issubset(hist_langs)
    check("project_restore", restore_ok, f"template={loaded.template_id} captions={loaded.caption_content} langs={loaded.selected_languages}")
    check("video_history_four", history_ok, str(sorted(hist_langs)))

    # Packaged EXE identity smoke against same data root (no rebuild)
    exe = ROOT / "dist" / "BMTVoiceStudio-1.3.0-RC2" / "BMTVoiceStudio.exe"
    if exe.is_file():
        env = os.environ.copy()
        env["LOCALAPPDATA"] = str(Path.home() / "AppData" / "Local")
        env["BMT_DATA_ROOT"] = str(user_data_root())
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
        smoke = subprocess.run(
            [str(exe), "--video-maker-smoke"],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(exe.parent),
        )
        check("packaged_video_maker_smoke", smoke.returncode == 0, (smoke.stdout or smoke.stderr or "")[-300:])

    # Final SHA re-check
    check("stable_12_sha_after", sha256_file(zip12) == STABLE_12_SHA256, sha256_file(zip12))
    check("rc2_sha_after", sha256_file(rc_zip) == EXPECTED_RC2, sha256_file(rc_zip))

    failed = [c for c in report["checks"] if not c["ok"]]
    report["failed_checks"] = [c["name"] for c in failed]
    report["recommendation"] = "READY FOR 1.3.0 FINAL" if not failed else "NOT READY"
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", REPORT)
    print("RECOMMENDATION", report["recommendation"])
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
