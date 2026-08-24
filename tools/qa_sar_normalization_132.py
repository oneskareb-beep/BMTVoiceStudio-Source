"""Retry the failed Portuguese WhatsApp render and short Standard/WhatsApp QA."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.composition import build_composition_plan
from bmt_voice_studio.video.ffmpeg_renderer import VideoRenderer
from bmt_voice_studio.video.media_probe import probe_audio_duration
from bmt_voice_studio.video.models import (
    PROFILE_STANDARD,
    PROFILE_WHATSAPP,
    MediaItem,
    MediaType,
    VideoProject,
    output_profile_for,
)
from bmt_voice_studio.video.paths import video_output_path


DESKTOP = Path.home() / "OneDrive" / "Desktop"
DOWNLOADS = Path.home() / "Downloads"
PT_AUDIO = (
    Path.home()
    / "Documents"
    / "BMT Voice Studio"
    / "Exports"
    / "Daily"
    / "2026"
    / "08"
    / "BMT_2026_08_15"
    / "PORTUGUESE"
    / "BMT_15_AUG_2026_PORTUGUESE_FINAL.mp3"
)
DAILY = Path.home() / "Documents" / "BMT Voice Studio" / "Exports" / "Daily" / "2026" / "08" / "BMT_2026_08_15"

FAILED_MEDIA = [
    (DESKTOP / "b5418dcc2ab6efa7fe51d8bffd385343.jpg", MediaType.IMAGE.value),
    (DESKTOP / "imagesY.jpg", MediaType.IMAGE.value),
    (DESKTOP / "SEEE.jpg", MediaType.IMAGE.value),
    (DESKTOP / "wp4937436.jpg", MediaType.IMAGE.value),
    (DOWNLOADS / "100177-video-720.mp4", MediaType.VIDEO.value),
    (DOWNLOADS / "100176-video-720.mp4", MediaType.VIDEO.value),
    (
        DOWNLOADS / "mixkit-meadow-covered-with-grass-and-trees-in-the-blazing-sun-40657-hd-ready.mp4",
        MediaType.VIDEO.value,
    ),
]


def _probe(path: Path) -> str:
    r = FFmpegService().run(["-hide_banner", "-i", str(path)], check=False)
    return (r.stderr or "") + (r.stdout or "")


def _duration(text: str) -> float:
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _audio_streams(text: str) -> int:
    return len(re.findall(r"Stream #\d+:\d+.*Audio:", text))


def _verify_geometry(path: Path, *, expect_dur: float | None = None) -> dict:
    text = _probe(path)
    assert path.is_file() and path.stat().st_size > 1024, f"empty {path}"
    assert "1080x1920" in text, text[-800:]
    assert "SAR 1:1" in text, text[-800:]
    assert "DAR 9:16" in text or "DAR 9:16" in text.replace(" ", "")
    assert "yuv420p" in text
    assert "yuvj420p" not in text
    assert "h264" in text.lower() or "H.264" in text or "avc1" in text
    streams = _audio_streams(text)
    assert streams == 1, f"audio streams={streams}\n{text[-800:]}"
    assert "48000 Hz" in text
    dur = _duration(text)
    if expect_dur is not None:
        assert abs(dur - expect_dur) < 1.2, f"duration {dur} expected {expect_dur}"
    return {"path": str(path), "size": path.stat().st_size, "duration": round(dur, 3), "audio_streams": streams, "probe": "ok"}


def _items(paths: list[tuple[Path, str]]) -> list[MediaItem]:
    out: list[MediaItem] = []
    for i, (path, kind) in enumerate(paths):
        if not path.is_file():
            raise SystemExit(f"missing media: {path}")
        out.append(MediaItem(path=str(path), media_type=kind, order=i))
    return out


def _render(project: VideoProject, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    plan = build_composition_plan(project, output_path=dest, temp_dir=dest.parent / f"tmp_{dest.stem}", job_id=dest.stem[:12])
    renderer = VideoRenderer()
    return renderer.render(project, plan, keep_temp_on_success=False)


def portuguese_whatsapp() -> dict:
    audio = PT_AUDIO
    if not audio.is_file():
        raise SystemExit(f"missing Portuguese master: {audio}")
    master_dur = probe_audio_duration(audio)
    project = VideoProject(
        devotional_date="2026-08-15",
        language="pt",
        topic="Confiar em Deus em Todas as Estações",
        audio_path=str(audio),
        audio_duration=master_dur,
        media_items=_items(FAILED_MEDIA),
        output_profile=output_profile_for(PROFILE_WHATSAPP),
        intro_enabled=True,
        outro_enabled=True,
        intro_duration=10.0,
        outro_duration=10.0,
        show_captions=True,
        skip_caption_header=True,
    )
    dest = video_output_path("2026-08-15", "pt", profile_id=PROFILE_WHATSAPP)
    out = _render(project, dest)
    info = _verify_geometry(out, expect_dur=master_dur + 20.0)
    info["master_duration"] = round(master_dur, 3)
    info["intro"] = 10.0
    info["outro"] = 10.0
    info["name"] = out.name
    return info


def short_qa() -> list[dict]:
    from PIL import Image

    qa = ROOT / "qa_outputs" / "sar_fix_132"
    qa.mkdir(parents=True, exist_ok=True)
    jpeg = qa / "odd.jpg"
    Image.new("RGB", (736, 1308), (30, 70, 110)).save(jpeg, quality=88)
    photo = qa / "portrait.png"
    Image.new("RGB", (1080, 1920), (12, 24, 40)).save(photo)
    land = qa / "land.mp4"
    ff = FFmpegService().find()
    import subprocess

    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "color=c=teal:s=1920x1080:d=2", "-pix_fmt", "yuv420p", str(land)],
        check=True,
        capture_output=True,
    )
    tone = qa / "tone6.m4a"
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "aac", "-ar", "48000", "-ac", "2", str(tone)],
        check=True,
        capture_output=True,
    )
    media = [
        MediaItem(path=str(jpeg), media_type="image", order=0),
        MediaItem(path=str(photo), media_type="image", order=1),
        MediaItem(path=str(land), media_type="video", order=2, duration=2.0),
    ]
    rows = []
    for lang, profile in (
        ("en", PROFILE_STANDARD),
        ("fr", PROFILE_STANDARD),
        ("sw", PROFILE_STANDARD),
        ("pt", PROFILE_STANDARD),
        ("en", PROFILE_WHATSAPP),
        ("fr", PROFILE_WHATSAPP),
        ("sw", PROFILE_WHATSAPP),
        ("pt", PROFILE_WHATSAPP),
    ):
        label = "WHATSAPP" if profile == PROFILE_WHATSAPP else "STANDARD"
        dest = qa / f"qa_{lang}_{label}.mp4"
        project = VideoProject(
            devotional_date="2026-08-15",
            language=lang,
            topic="QA",
            audio_path=str(tone),
            audio_duration=6.0,
            media_items=media,
            output_profile=output_profile_for(profile),
            intro_enabled=True,
            outro_enabled=True,
            intro_duration=10.0,
            outro_duration=10.0,
            show_captions=False,
        )
        out = _render(project, dest)
        info = _verify_geometry(out, expect_dur=26.0)
        info["lang"] = lang
        info["profile"] = label
        rows.append(info)
        print("QA_OK", lang, label, info["duration"], info["size"])
    return rows


def main() -> int:
    print("PORTUGUESE_WHATSAPP starting")
    pt = portuguese_whatsapp()
    print("PORTUGUESE_WHATSAPP", json.dumps({k: v for k, v in pt.items() if k != "probe"}, indent=2))
    print("SHORT_QA starting")
    qa = short_qa()
    report = {"portuguese_whatsapp": pt, "qa": qa}
    dest = ROOT / "qa_outputs" / "sar_fix_132" / "report.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
