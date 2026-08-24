"""Download free Mixkit stock clips and build bundled 16:9 defaults per template.

License: Mixkit Free License — commercial use allowed, no attribution required.
https://mixkit.co/license/

Run before packaging:
  python tools/download_bundled_media.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.models import TEMPLATE_BMT_CLASSIC, TEMPLATE_BMT_MINIMAL, TEMPLATE_BMT_NATURE

OUT_ROOT = ROOT / "bmt_voice_studio" / "resources" / "default_media"
ATTRIBUTION = OUT_ROOT / "ATTRIBUTION.json"
WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION = 12.0
MIXKIT_BASE = "https://assets.mixkit.co/videos"


@dataclass(frozen=True)
class ClipSpec:
    mixkit_id: int
    title: str
    start: float = 0.0
    grade: str = "soft"


# Curated soft, calm footage — Mixkit Free License
NATURE_CLIPS = [
    ClipSpec(40657, "Forest canopy path", start=2.0, grade="nature"),
    ClipSpec(5008, "Tranquil lake reflection", start=1.0, grade="nature"),
    ClipSpec(21577, "Green meadow", start=0.5, grade="nature"),
    ClipSpec(1780, "Golden sunset over hills", start=3.0, grade="nature"),
    ClipSpec(28341, "Misty forest morning", start=1.5, grade="nature"),
]

CLASSIC_CLIPS = [
    ClipSpec(4119, "Warm sunset sky", start=2.0, grade="classic"),
    ClipSpec(4396, "Mountain vista", start=1.0, grade="classic"),
    ClipSpec(4374, "Peaceful river", start=2.5, grade="classic"),
    ClipSpec(1187, "Golden hour clouds", start=0.0, grade="classic"),
    ClipSpec(5039, "Sunlit forest trail", start=1.0, grade="classic"),
]

MINIMAL_CLIPS = [
    ClipSpec(4070, "Soft drifting clouds", start=0.0, grade="minimal"),
    ClipSpec(4132, "Calm cloudscape", start=2.0, grade="minimal"),
    ClipSpec(1164, "Gentle water surface", start=1.0, grade="minimal"),
    ClipSpec(50944, "Soft fog over trees", start=1.5, grade="minimal"),
    ClipSpec(825, "Open field horizon", start=0.5, grade="minimal"),
]

TEMPLATES: dict[str, list[ClipSpec]] = {
    TEMPLATE_BMT_NATURE: NATURE_CLIPS,
    TEMPLATE_BMT_CLASSIC: CLASSIC_CLIPS,
    TEMPLATE_BMT_MINIMAL: MINIMAL_CLIPS,
}

GRADE_FILTERS = {
    "nature": "eq=saturation=0.82:contrast=0.94:brightness=0.02",
    "classic": "eq=saturation=0.88:contrast=0.96:brightness=0.03,colorbalance=rs=0.04:gs=0.02:bs=-0.03",
    "minimal": "eq=saturation=0.62:contrast=0.90:brightness=0.04",
    "soft": "eq=saturation=0.75:contrast=0.92:brightness=0.02",
}


def mixkit_url(video_id: int) -> str:
    return f"{MIXKIT_BASE}/{video_id}/{video_id}-1080.mp4"


def download_source(client: httpx.Client, video_id: int, dest: Path) -> None:
    url = mixkit_url(video_id)
    with client.stream("GET", url, follow_redirects=True, timeout=120.0) as resp:
        resp.raise_for_status()
        dest.write_bytes(resp.read())


def process_clip(src: Path, dest: Path, spec: ClipSpec, ffmpeg: FFmpegService) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    grade = GRADE_FILTERS.get(spec.grade, GRADE_FILTERS["soft"])
    vf = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"{grade},"
        f"fps={FPS},format=yuv420p"
    )
    cmd = [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(spec.start),
        "-i",
        str(src),
        "-t",
        str(DURATION),
        "-an",
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    ffmpeg.run(cmd, check=True, timeout=180)


def main() -> int:
    ffmpeg = FFmpegService()
    attribution: dict[str, list[dict[str, str | int]]] = {
        "license": "Mixkit Free License (https://mixkit.co/license/)",
        "note": "Free for commercial use; attribution appreciated but not required.",
        "templates": {},
    }

    with httpx.Client(headers={"User-Agent": "BMTVoiceStudio/1.3"}) as client:
        with tempfile.TemporaryDirectory(prefix="bmt_media_") as tmp:
            tmp_dir = Path(tmp)
            for template_id, clips in TEMPLATES.items():
                folder = OUT_ROOT / template_id
                folder.mkdir(parents=True, exist_ok=True)
                entries: list[dict[str, str | int]] = []
                for idx, spec in enumerate(clips, start=1):
                    dest = folder / f"clip_{idx:02d}.mp4"
                    raw = tmp_dir / f"{spec.mixkit_id}.mp4"
                    print(f"Downloading Mixkit {spec.mixkit_id} ({spec.title})…")
                    download_source(client, spec.mixkit_id, raw)
                    if raw.stat().st_size < 50_000:
                        print(f"FAILED download: {spec.mixkit_id}", file=sys.stderr)
                        return 1
                    print(f"Processing {template_id}/{dest.name}…")
                    process_clip(raw, dest, spec, ffmpeg)
                    if not dest.is_file() or dest.stat().st_size < 100_000:
                        print(f"FAILED encode: {dest}", file=sys.stderr)
                        return 1
                    entries.append(
                        {
                            "slot": idx,
                            "file": dest.name,
                            "mixkit_id": spec.mixkit_id,
                            "title": spec.title,
                            "source": mixkit_url(spec.mixkit_id),
                            "page": f"https://mixkit.co/free-stock-video/{spec.mixkit_id}/",
                        }
                    )
                attribution["templates"][template_id] = entries

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    ATTRIBUTION.write_text(json.dumps(attribution, indent=2), encoding="utf-8")
    print(f"Done — {sum(len(v) for v in TEMPLATES.values())} clips in {OUT_ROOT}")
    print(f"Attribution: {ATTRIBUTION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
