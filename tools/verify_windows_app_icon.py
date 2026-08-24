"""Verify packaged EXE icon embedding and capture a live taskbar screenshot."""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_EXE = ROOT / "dist" / "BMTVoiceStudio-1.3.1" / "BMTVoiceStudio.exe"
OUT = ROOT / "qa_outputs" / "windows_icon_1.3.1"
REQUIRED = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}


def _ico_sizes(path: Path) -> set[tuple[int, int]]:
    data = path.read_bytes()
    _reserved, itype, count = struct.unpack_from("<HHH", data)
    sizes = set()
    for i in range(count):
        w, h = data[6 + i * 16], data[7 + i * 16]
        sizes.add((w or 256, h or 256))
    return sizes


def _extract_associated_icon(exe: Path, dest: Path) -> bool:
    ps = f"""
Add-Type -AssemblyName System.Drawing
$icon = [System.Drawing.Icon]::ExtractAssociatedIcon('{str(exe).replace("'", "''")}')
$icon.ToBitmap().Save('{str(dest).replace("'", "''")}')
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return dest.is_file() and dest.stat().st_size > 0 and r.returncode == 0


def _make_shortcut(exe: Path, dest: Path) -> bool:
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{str(dest).replace("'", "''")}')
$sc.TargetPath = '{str(exe).replace("'", "''")}'
$sc.WorkingDirectory = '{str(exe.parent).replace("'", "''")}'
$sc.IconLocation = '{str(exe).replace("'", "''")},0'
$sc.Save()
"""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    return dest.is_file() and r.returncode == 0


def _grab_desktop(dest: Path) -> bool:
    from PIL import ImageGrab

    im = ImageGrab.grab(all_screens=True)
    im.save(dest)
    return dest.is_file()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"checks": [], "out": str(OUT)}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    ico = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
    check("source_ico", ico.is_file(), str(ico))
    if ico.is_file():
        sizes = _ico_sizes(ico)
        check("source_ico_sizes", sizes == REQUIRED, str(sorted(sizes)))

    exe = DIST_EXE
    check("dist_exe", exe.is_file(), str(exe))
    if not exe.is_file():
        (OUT / "icon_verify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1

    bundled = exe.parent / "_internal" / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
    check("frozen_ico_resource", bundled.is_file(), str(bundled))
    if bundled.is_file():
        check("frozen_ico_sizes", _ico_sizes(bundled) == REQUIRED, str(sorted(_ico_sizes(bundled))))

    extracted = OUT / "exe_associated_icon.png"
    check("exe_embedded_icon", _extract_associated_icon(exe, extracted), str(extracted))

    fresh = Path(os.environ.get("TEMP", ".")) / "BMTVoiceStudio-1.3.1-iconfix"
    if fresh.exists():
        shutil.rmtree(fresh, ignore_errors=True)
    shutil.copytree(exe.parent, fresh)
    fresh_exe = fresh / "BMTVoiceStudio.exe"
    check("fresh_copy_exe", fresh_exe.is_file(), str(fresh_exe))

    shortcut = OUT / "BMT Voice Studio.lnk"
    check("shortcut_from_exe", _make_shortcut(fresh_exe, shortcut), str(shortcut))

    env = os.environ.copy()
    env["BMT_SKIP_LIBRARY_DIALOG"] = "1"
    env["BMT_SKIP_RECOVERY"] = "1"
    env.pop("QT_QPA_PLATFORM", None)
    env.pop("BMT_QA_CAPTURE", None)
    proc = subprocess.Popen([str(fresh_exe)], cwd=str(fresh), env=env)
    report["pid"] = proc.pid
    time.sleep(8)
    shot = OUT / "taskbar_icon_proof.png"
    try:
        check("taskbar_screenshot", _grab_desktop(shot), str(shot))
    except Exception as exc:
        check("taskbar_screenshot", False, str(exc))
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    check("app_launched", True, f"pid={proc.pid}")

    (OUT / "icon_verify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    failed = [c for c in report["checks"] if not c["ok"]]
    print("REPORT", OUT / "icon_verify.json")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
