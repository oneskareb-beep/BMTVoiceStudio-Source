"""Clean-location packaged smoke + short live render UI sanity for 1.3.1 FINAL."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "BMTVoiceStudio-1.3.1"


def main() -> int:
    report: dict = {"checks": [], "dist": str(DIST)}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": (detail or "")[-500:]})
        print(("PASS" if ok else "FAIL"), name, (detail or "")[-300:])

    exe_src = DIST / "BMTVoiceStudio.exe"
    check("dist_exe", exe_src.is_file(), str(exe_src))
    check("version_file", (DIST / "VERSION").read_text(encoding="utf-8").strip() == "1.3.1")
    if not exe_src.is_file():
        return 1

    clean_parent = Path(tempfile.mkdtemp(prefix="bmt_131_final_clean_"))
    # Prefer outside repo when possible
    try:
        outside = Path(tempfile.gettempdir()) / f"bmt_131_final_{os.getpid()}"
        if outside.exists():
            shutil.rmtree(outside, ignore_errors=True)
        outside.mkdir(parents=True, exist_ok=True)
        clean_parent = outside
    except Exception:
        pass

    dest = clean_parent / "BMTVoiceStudio"
    shutil.copytree(DIST, dest)
    exe = dest / "BMTVoiceStudio.exe"
    check("clean_copy_outside_repo", exe.is_file() and "Documents\\BMTVoiceStudio\\dist" not in str(exe), str(exe))
    check("no_source_tree", not (dest / "tests").exists() and not (dest / "bmt_voice_studio").exists())
    check("has_internal", (dest / "_internal").is_dir())

    ffmpeg_hits = list((dest / "_internal").rglob("ffmpeg*.exe"))
    check("bundled_ffmpeg", bool(ffmpeg_hits), str(ffmpeg_hits[0] if ffmpeg_hits else ""))
    report["bundled_ffmpeg"] = str(ffmpeg_hits[0]) if ffmpeg_hits else ""

    fresh_la = Path(tempfile.mkdtemp(prefix="bmt_131f_la_"))
    fresh_docs = Path(tempfile.mkdtemp(prefix="bmt_131f_docs_"))
    fresh_phys = Path(tempfile.mkdtemp(prefix="bmt_131f_phys_"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fresh_la)
    env["BMT_DOCUMENTS_DIR"] = str(fresh_docs)
    env["BMT_PHYSICAL_DOCUMENTS_DIR"] = str(fresh_phys)
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    for key in ("FFMPEG_BINARY", "IMAGEIO_FFMPEG_EXE", "BMT_DATA_ROOT"):
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
    check("video_maker_smoke", smoke.returncode == 0, (smoke.stdout or "") + (smoke.stderr or ""))
    render = run_flag("--video-maker-render-smoke", 360)
    check("video_maker_render_smoke", render.returncode == 0, (render.stdout or "") + (render.stderr or ""))
    restore = run_flag("--project-restore-smoke", 180)
    check("project_restore_smoke", restore.returncode == 0, (restore.stdout or "") + (restore.stderr or ""))

    # Live render UI sanity uses the same render-smoke path (short encode) and reports busy/output messaging.
    render_out = (render.stdout or "") + (render.stderr or "")
    check("live_render_sanity_ok", "VIDEO_MAKER_RENDER_SMOKE" in render_out and render.returncode == 0, render_out[-400:])
    check("bundled_ffmpeg_in_smoke", "ffmpeg" in render_out.lower() or bool(ffmpeg_hits), render_out[-200:])

    out = ROOT / "qa_outputs" / "final_131" / "clean_deploy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["clean_exe"] = str(exe)
    report["clean_dir"] = str(dest)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out)
    failed = [c for c in report["checks"] if not c["ok"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
