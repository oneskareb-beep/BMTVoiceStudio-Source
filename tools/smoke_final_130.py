"""Packaged smoke for BMT Voice Studio 1.3.0 Final (isolated profile)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / "dist" / "BMTVoiceStudio-1.3.0" / "BMTVoiceStudio.exe"


def main() -> int:
    report: dict = {"checks": [], "exe": str(EXE)}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail[-500:]})
        print(("PASS" if ok else "FAIL"), name, detail[-300:])

    if not EXE.is_file():
        check("dist_exe", False, str(EXE))
        return 1
    check("dist_exe", True, str(EXE))
    check("version_file", (EXE.parent / "VERSION").read_text(encoding="utf-8").strip() == "1.3.0")
    ffmpeg = list((EXE.parent / "_internal").rglob("ffmpeg*.exe"))
    check("bundled_ffmpeg", bool(ffmpeg), str(ffmpeg[0] if ffmpeg else ""))

    fresh_la = Path(tempfile.mkdtemp(prefix="bmt_f_la_"))
    fresh_docs = Path(tempfile.mkdtemp(prefix="bmt_f_docs_"))
    fresh_phys = Path(tempfile.mkdtemp(prefix="bmt_f_phys_"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fresh_la)
    env["BMT_DOCUMENTS_DIR"] = str(fresh_docs)
    env["BMT_PHYSICAL_DOCUMENTS_DIR"] = str(fresh_phys)
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    for key in ("FFMPEG_BINARY", "IMAGEIO_FFMPEG_EXE", "BMT_DATA_ROOT"):
        env.pop(key, None)
    env["PATH"] = str(EXE.parent / "_internal") + os.pathsep + env.get("PATH", "")

    for flag, timeout in (
        ("--video-maker-smoke", 90),
        ("--video-maker-render-smoke", 300),
        ("--project-restore-smoke", 180),
    ):
        proc = subprocess.run(
            [str(EXE), flag],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(EXE.parent),
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        check(flag.lstrip("-"), proc.returncode == 0, f"code={proc.returncode}\n{out}")

    out_path = ROOT / "qa_outputs" / "final_130" / "clean_deploy_smoke.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out_path)
    return 0 if all(c["ok"] for c in report["checks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
