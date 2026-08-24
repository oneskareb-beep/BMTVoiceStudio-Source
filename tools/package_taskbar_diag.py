"""Build two taskbar diagnostic onedirs. Never touch 1.3.2 FINAL dist or zip."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.release_scan import sha256_file

FINAL_EXE = ROOT / "dist" / "BMTVoiceStudio-1.3.2" / "BMTVoiceStudio.exe"
FINAL_ZIP = ROOT / "release" / "BMTVoiceStudio-1.3.2-Windows-x64-Portable.zip"
ICO = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
STABLE_131 = "1abd8500897136120cd610049b81210c7eae2ac5e3526995954166b4428dc9a2"


def main() -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    if not ICO.is_file():
        raise SystemExit(f"STOP: ICO missing {ICO}")
    if not FINAL_EXE.is_file():
        raise SystemExit("STOP: 1.3.2 FINAL EXE missing; diagnosis needs it intact")
    before_exe = sha256_file(FINAL_EXE)
    before_zip = sha256_file(FINAL_ZIP) if FINAL_ZIP.is_file() else ""
    zip131 = ROOT / "release" / "BMTVoiceStudio-1.3.1-Windows-x64-Portable.zip"
    if zip131.is_file() and sha256_file(zip131) != STABLE_131:
        raise SystemExit("STOP: 1.3.1 FINAL hash changed")

    for spec_name, dest_name in (
        ("BMTVoiceStudio-TaskbarTest-NoAppID.spec", "BMTVoiceStudio-TaskbarTest-NoAppID"),
        ("BMTVoiceStudio-TaskbarTest-AppID.spec", "BMTVoiceStudio-TaskbarTest-AppID"),
    ):
        spec = ROOT / spec_name
        text = spec.read_text(encoding="utf-8")
        if "icon=ICO" not in text and "bmt_voice_studio.ico" not in text:
            raise SystemExit(f"STOP: {spec_name} missing ICO")
        dest = ROOT / "dist" / dest_name
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        print("BUILD", dest_name)
        run = subprocess.run(
            [str(py), "-m", "PyInstaller", "--noconfirm", str(spec)],
            cwd=ROOT,
        )
        exe = dest / "BMTVoiceStudio.exe"
        build_exe = ROOT / "build" / dest_name / "BMTVoiceStudio.exe"
        shared_internal = ROOT / "dist" / "BMTVoiceStudio-1.3.2" / "_internal"
        if not exe.is_file() and build_exe.is_file():
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(build_exe, exe)
            print("FALLBACK_EXE_FROM_BUILD", exe)
        if not exe.is_file():
            return run.returncode or 1
        internal = dest / "_internal"
        if internal.exists() and internal.resolve() != shared_internal.resolve():
            shutil.rmtree(internal, ignore_errors=True)
        if not internal.exists():
            link = subprocess.run(["cmd", "/c", "mklink", "/J", str(internal), str(shared_internal)])
            if link.returncode != 0:
                raise SystemExit(f"STOP: could not junction _internal for {dest_name}")
            print("JUNCTION", internal, "->", shared_internal)
        print("OK", exe)

    after_exe = sha256_file(FINAL_EXE)
    after_zip = sha256_file(FINAL_ZIP) if FINAL_ZIP.is_file() else ""
    if after_exe != before_exe:
        raise SystemExit("STOP: 1.3.2 FINAL EXE hash changed during diagnosis")
    if before_zip and after_zip != before_zip:
        raise SystemExit("STOP: 1.3.2 FINAL zip hash changed during diagnosis")
    print("FINAL_132_EXE_UNCHANGED", before_exe)
    if before_zip:
        print("FINAL_132_ZIP_UNCHANGED", before_zip[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
