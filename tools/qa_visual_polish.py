"""Render intro, verse, and a short sample video for the visual polish pass."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "qa_outputs" / "visual_polish"


def main() -> int:
    os.environ.setdefault("BMT_SKIP_LIBRARY_DIALOG", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    OUT = Path(os.environ.get("BMT_VISUAL_QA_DIR") or str(ROOT / "qa_outputs" / "visual_polish"))
    try:
        import shutil

        if shutil.disk_usage(str(OUT.anchor or "C:\\")).free < 500_000_000:
            OUT = Path(r"D:\BMT_RC2_QA\visual_polish")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("LOCALAPPDATA", str(OUT / "la"))
    os.environ.setdefault("BMT_DOCUMENTS_DIR", str(OUT / "docs"))
    os.environ.setdefault("BMT_PHYSICAL_DOCUMENTS_DIR", str(OUT / "phys"))
    from PIL import Image

    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
    from bmt_voice_studio.resources import logo_path
    from bmt_voice_studio.video.composition import build_composition_plan
    from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
    from bmt_voice_studio.video.media_probe import probe_audio_duration, probe_media
    from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, VideoProject, output_profile_for
    from bmt_voice_studio.video.title_cards import (
        render_intro_card,
        render_outro_card,
        render_verse_card,
    )

    logo = logo_path()
    project = VideoProject(
        devotional_date=date(2026, 8, 14).isoformat(),
        language="en",
        topic="Kingdom Priorities",
        week_focus="Walk in obedience today",
        month_theme="A season of harvest",
        memory_verse="Matthew 6:33 Seek first the kingdom of God and His righteousness.",
        template_id=TEMPLATE_BMT_CLASSIC,
        logo_path=str(logo or ""),
        output_profile=output_profile_for("standard_1080p"),
    )
    intro = OUT / "intro_screen.png"
    verse = OUT / "verse_screen.png"
    outro = OUT / "outro_screen.png"
    render_intro_card(project, intro)
    render_intro_card(project, OUT / "intro_logo_only.png", reveal="logo")
    render_intro_card(project, OUT / "intro_brand.png", reveal="brand")
    render_verse_card(project, verse)
    render_outro_card(project, outro)
    if logo:
        Image.open(logo).save(OUT / "logo_transparent.png")

    ffmpeg = FFmpegService().find()
    media = OUT / "bg.png"
    audio = OUT / "tone.wav"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x1E3A5F:s=1080x1920:d=1", "-frames:v", "1", str(media)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=12", "-ar", "48000", "-ac", "2", str(audio)],
        check=True,
        capture_output=True,
    )
    project.media_items = [probe_media(media)]
    project.audio_path = str(audio)
    project.audio_duration = probe_audio_duration(audio)
    sample = OUT / "sample_final.mp4"
    plan = build_composition_plan(
        project,
        output_path=sample,
        temp_dir=OUT / "temp",
        job_id="visual_polish",
    )
    renderer = VideoRenderer()
    out = renderer.render(project, plan, keep_temp_on_success=True)
    print("INTRO", intro)
    print("VERSE", verse)
    print("OUTRO", outro)
    print("SAMPLE", out)
    print("LOGO", logo)
    repo_shots = ROOT / "qa_outputs" / "visual_polish"
    repo_shots.mkdir(parents=True, exist_ok=True)
    import shutil

    for name in ("intro_screen.png", "verse_screen.png", "outro_screen.png", "intro_logo_only.png", "intro_brand.png", "logo_transparent.png"):
        src = OUT / name
        if src.is_file() and src.parent != repo_shots:
            shutil.copy2(src, repo_shots / name)
    return 0 if Path(out).is_file() else 1


if __name__ == "__main__":
    raise SystemExit(main())
