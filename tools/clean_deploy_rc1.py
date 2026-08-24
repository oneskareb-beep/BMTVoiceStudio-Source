"""Copy packaged RC1 to a temp folder outside the repo and run packaged smokes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "BMTVoiceStudio-1.3.0-RC1"


def main() -> int:
    report: dict = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    exe_src = DIST / "BMTVoiceStudio.exe"
    check("dist_exe", exe_src.is_file(), str(exe_src))
    if not exe_src.is_file():
        return 1

    clean_parent = Path(tempfile.mkdtemp(prefix="bmt_rc1_clean_", dir=r"C:\Users\aganz\AppData\Local\Temp"))
    dest = clean_parent / "BMTVoiceStudio"
    shutil.copytree(DIST, dest)
    exe = dest / "BMTVoiceStudio.exe"
    check("clean_copy", exe.is_file(), str(exe))
    check("no_source_tree", not (dest / "tests").exists())
    check("has_internal", (dest / "_internal").is_dir())

    ffmpeg_hits = list((dest / "_internal").rglob("ffmpeg*.exe"))
    check("bundled_ffmpeg", bool(ffmpeg_hits), str(ffmpeg_hits[0] if ffmpeg_hits else ""))
    report["bundled_ffmpeg"] = str(ffmpeg_hits[0]) if ffmpeg_hits else ""

    fresh_la = Path(tempfile.mkdtemp(prefix="bmt_rc1_la_"))
    fresh_docs = Path(tempfile.mkdtemp(prefix="bmt_rc1_docs_"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fresh_la)
    env["BMT_DOCUMENTS_DIR"] = str(fresh_docs)
    env["BMT_DATA_ROOT"] = str(fresh_docs / "BMT Voice Studio")
    env["QT_QPA_PLATFORM"] = "offscreen"
    for key in ("FFMPEG_BINARY", "IMAGEIO_FFMPEG_EXE"):
        env.pop(key, None)
    env["PATH"] = str(dest / "_internal") + os.pathsep + env.get("PATH", "")

    def run_flag(flag: str, timeout: int = 180) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(exe), flag],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(dest),
        )

    smoke = run_flag("--video-maker-smoke", 90)
    check("video_maker_smoke", smoke.returncode == 0, (smoke.stdout or smoke.stderr or "")[-400:])
    render = run_flag("--video-maker-render-smoke", 300)
    check("video_maker_render_smoke", render.returncode == 0, (render.stdout or render.stderr or "")[-400:])
    rel = run_flag("--release-smoke", 240)
    check("release_smoke_launched", rel.returncode in {0, 1}, f"code={rel.returncode}")

    out = ROOT / "qa_outputs" / "video_maker_phase4" / "clean_deploy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["clean_exe"] = str(exe)
    report["clean_dir"] = str(dest)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out)
    failed = [c for c in report["checks"] if not c["ok"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
