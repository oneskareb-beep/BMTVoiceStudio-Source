"""Legacy gradient placeholder generator (deprecated).

Bundled defaults now use free Mixkit stock footage:
  python tools/download_bundled_media.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE

OUT_ROOT = ROOT / "bmt_voice_studio" / "resources" / "default_media"
WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION = 12.0

# (label, base hex, accent hex, motion style)
CLASSIC_CLIPS = [
    ("classic_01_skyline", "0x0f141c", "0xd4a017", "pan_lr"),
    ("classic_02_warm", "0x1a2438", "0xc47620", "zoom_in"),
    ("classic_03_gold", "0x141820", "0xe8b040", "pan_rl"),
    ("classic_04_navy", "0x0a1428", "0x8a7040", "zoom_out"),
    ("classic_05_dawn", "0x182030", "0xf0c060", "pan_lr"),
]

NATURE_CLIPS = [
    ("nature_01_forest", "0x0e1c16", "0x3a7850", "zoom_in"),
    ("nature_02_water", "0x0a1820", "0x2a6888", "pan_lr"),
    ("nature_03_meadow", "0x142818", "0x5a9848", "pan_rl"),
    ("nature_04_sunset", "0x201810", "0xc87830", "zoom_out"),
    ("nature_05_mist", "0x101820", "0x487060", "zoom_in"),
]

MINIMAL_CLIPS = [
    ("minimal_01_stone", "0x080a0e", "0xc8c8c4", "zoom_in"),
    ("minimal_02_slate", "0x101418", "0xb0b4b8", "pan_lr"),
    ("minimal_03_ash", "0x0c0e12", "0xd0d0cc", "pan_rl"),
    ("minimal_04_pearl", "0x141618", "0xe0e0dc", "zoom_out"),
    ("minimal_05_charcoal", "0x06080c", "0xa8a8a4", "zoom_in"),
]

TEMPLATES = {
    TEMPLATE_BMT_CLASSIC: CLASSIC_CLIPS,
    TEMPLATE_BMT_NATURE: NATURE_CLIPS,
    TEMPLATE_BMT_MINIMAL: MINIMAL_CLIPS,
}


def _motion_filter(style: str, frames: int) -> str:
    if style == "zoom_in":
        return (
            f"zoompan=z='min(zoom+0.0008,1.18)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    if style == "zoom_out":
        return (
            f"zoompan=z='if(lte(zoom,1.0),1.18,max(1.0,zoom-0.0008))':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    if style == "pan_rl":
        return (
            f"zoompan=z='1.08':d={frames}:"
            f"x='max(0,(iw-iw/zoom)*(1-on/{frames}))':y='ih/4-(ih/zoom/4)':s={WIDTH}x{HEIGHT}:fps={FPS}"
        )
    return (
        f"zoompan=z='1.08':d={frames}:"
        f"x='min(iw-iw/zoom,(iw-iw/zoom)*on/{frames})':y='ih/4-(ih/zoom/4)':s={WIDTH}x{HEIGHT}:fps={FPS}"
    )


def _gradient_source(base: str, accent: str, frames: int) -> str:
    # Animated vertical gradient between two brand tones.
    return (
        f"gradients=s={WIDTH}x{HEIGHT}:c0={base}:c1={accent}:"
        f"x0=0:y0=0:x1=0:y1={HEIGHT}:duration={DURATION}:speed=0.15:seed=42,"
        f"format=rgb24,fps={FPS},trim=duration={DURATION},"
        f"{_motion_filter('pan_lr', frames)}"
    )


def render_clip(dest: Path, base: str, accent: str, motion: str, ffmpeg: FFmpegService) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(round(DURATION * FPS)))
    vf = _gradient_source(base, accent, frames)
    if motion != "pan_lr":
        vf = vf.replace(_motion_filter("pan_lr", frames), _motion_filter(motion, frames))
    cmd = [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-t",
        str(DURATION),
        str(dest),
    ]
    ffmpeg.run(cmd, check=True, timeout=120)


def main() -> int:
    ffmpeg = FFmpegService()
    for template_id, clips in TEMPLATES.items():
        folder = OUT_ROOT / template_id
        folder.mkdir(parents=True, exist_ok=True)
        for idx, (name, base, accent, motion) in enumerate(clips, start=1):
            dest = folder / f"clip_{idx:02d}.mp4"
            print(f"Generating {template_id}/{dest.name} ({name})…")
            render_clip(dest, base, accent, motion, ffmpeg)
            if not dest.is_file() or dest.stat().st_size < 10_000:
                print(f"FAILED: {dest}", file=sys.stderr)
                return 1
    print(f"Done — {len(TEMPLATES) * 5} clips in {OUT_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
