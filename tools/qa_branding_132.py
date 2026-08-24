"""Synthetic 20s + optional real Daily audio duration QA for 1.3.2-dev intro/outro."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
from bmt_voice_studio.video.branding_audio import mix_branding_audio
from bmt_voice_studio.video.composition import branding_pads
from bmt_voice_studio.video.models import VideoProject


def _probe(path: Path) -> float:
    ff = FFmpegService()
    r = ff.run(["-i", str(path)], check=False)
    text = (r.stderr or "") + (r.stdout or "")
    import re

    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _make_tone(dest: Path, seconds: float) -> Path:
    ff = FFmpegService()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ff.run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds:.3f}",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(dest),
        ],
        check=True,
    )
    return dest


def main() -> int:
    out = ROOT / "qa_outputs" / "branding_132"
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    music_src = Path(r"C:\Users\aganz\Downloads\Calima - Full Moon (freetouse.com) (1).mp3")
    music_qa = out / "Calima-Full-Moon.mp3"
    if music_src.is_file():
        shutil.copy2(music_src, music_qa)
        check("music_copied_for_qa_not_bundled", music_qa.is_file(), str(music_qa))
    else:
        music_qa = None
        check("music_copied_for_qa_not_bundled", False, "Downloads source missing")

    master = _make_tone(out / "synthetic_20s.m4a", 20.0)
    master_dur = _probe(master)
    check("synthetic_master_20s", abs(master_dur - 20.0) < 0.35, f"{master_dur:.3f}")

    mixed = out / "synthetic_mixed.m4a"
    mix_branding_audio(
        master,
        mixed,
        music_path=music_qa,
        intro_sec=10.0,
        outro_sec=10.0,
        master_duration=20.0,
    )
    mixed_dur = _probe(mixed)
    check("synthetic_mixed_40s", abs(mixed_dur - 40.0) < 0.6, f"{mixed_dur:.3f}")

    streams = FFmpegService().run(["-i", str(mixed)], check=False)
    text = (streams.stderr or "") + (streams.stdout or "")
    audio_streams = text.count("Audio:")
    check("single_audio_stream", audio_streams == 1, f"count={audio_streams}")

    pads = branding_pads(VideoProject(intro_enabled=True, outro_enabled=True, audio_duration=20.0))
    check("pads_10_10", pads == (10.0, 10.0), str(pads))

    report["synthetic"] = {
        "master": master_dur,
        "mixed": mixed_dur,
        "difference": mixed_dur - master_dur,
        "music": str(music_qa) if music_qa else "",
        "note": "Calima is a user-selected QA asset, not packaged inside the EXE zip.",
    }
    (out / "qa_branding_132.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", out / "qa_branding_132.json")
    return 0 if all(c["ok"] for c in report["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
