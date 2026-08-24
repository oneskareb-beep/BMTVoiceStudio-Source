"""Render sample locked covers for all production languages."""
from pathlib import Path

from bmt_voice_studio.video.locked_card import render_locked_intro_card
from bmt_voice_studio.video.models import VideoProject

out = Path("release/cover_samples")
out.mkdir(parents=True, exist_ok=True)

samples = [
    ("en", "Enduring in the Faith"),
    ("fr", "Persévérer dans la foi"),
    ("sw", "Kuvumilia katika Imani"),
    ("pt", "Perseverar na Fé"),
]

for lang, topic in samples:
    project = VideoProject(
        topic=topic,
        language=lang,
        devotional_date="2026-08-21",
        title=topic,
    )
    dest = out / f"cover_{lang}.png"
    render_locked_intro_card(project, dest, width=540, height=960)
    print(f"OK {lang} {dest.resolve()} bytes={dest.stat().st_size}")

print("DIR", out.resolve())
