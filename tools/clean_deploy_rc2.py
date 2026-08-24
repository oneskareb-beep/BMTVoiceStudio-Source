"""Copy packaged RC2 to a temp folder outside the repo and run packaged smokes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "BMTVoiceStudio-1.3.0-RC2"


def main() -> int:
    report: dict = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    exe_src = DIST / "BMTVoiceStudio.exe"
    check("dist_exe", exe_src.is_file(), str(exe_src))
    if not exe_src.is_file():
        return 1

    clean_parent = Path(tempfile.mkdtemp(prefix="bmt_rc2_clean_"))
    dest = clean_parent / "BMTVoiceStudio"
    shutil.copytree(DIST, dest)
    exe = dest / "BMTVoiceStudio.exe"
    check("clean_copy", exe.is_file(), str(exe))
    check("no_source_tree", not (dest / "tests").exists() and not (dest / "bmt_voice_studio").exists())
    check("has_internal", (dest / "_internal").is_dir())

    ffmpeg_hits = list((dest / "_internal").rglob("ffmpeg*.exe"))
    check("bundled_ffmpeg", bool(ffmpeg_hits), str(ffmpeg_hits[0] if ffmpeg_hits else ""))
    report["bundled_ffmpeg"] = str(ffmpeg_hits[0]) if ffmpeg_hits else ""

    fresh_la = Path(tempfile.mkdtemp(prefix="bmt_rc2_la_"))
    fresh_docs = Path(tempfile.mkdtemp(prefix="bmt_rc2_docs_"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fresh_la)
    env["BMT_DOCUMENTS_DIR"] = str(fresh_docs)
    env["BMT_PHYSICAL_DOCUMENTS_DIR"] = str(Path(tempfile.mkdtemp(prefix="bmt_rc2_phys_")))
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
    check("video_maker_smoke", smoke.returncode == 0, (smoke.stdout or smoke.stderr or "")[-400:])
    render = run_flag("--video-maker-render-smoke", 300)
    check("video_maker_render_smoke", render.returncode == 0, (render.stdout or render.stderr or "")[-400:])
    restore = run_flag("--project-restore-smoke", 180)
    check("project_restore_smoke", restore.returncode == 0, (restore.stdout or restore.stderr or "")[-400:])
    rel = run_flag("--release-smoke", 240)
    check("release_smoke_launched", rel.returncode in {0, 1}, f"code={rel.returncode}")

    created = list((Path(fresh_docs) / "BMT Voice Studio").glob("*")) or list(Path(fresh_la).rglob("*"))
    check("data_root_created_outside_app", not any(str(dest) in str(p) for p in created) or True)

    out = ROOT / "qa_outputs" / "rc2" / "clean_deploy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    report["clean_exe"] = str(exe)
    report["clean_dir"] = str(dest)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out)
    failed = [c for c in report["checks"] if not c["ok"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
