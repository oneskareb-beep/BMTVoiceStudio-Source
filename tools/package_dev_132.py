"""Build BMT Voice Studio 1.3.2-dev. Never overwrite 1.3.1 FINAL."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.release_scan import STABLE_12_SHA256, STABLE_12_ZIP_NAME, scan_rc_tree, sha256_file
from bmt_voice_studio.ui.theme import STABLE_130_SHA256, STABLE_130_ZIP_NAME

DIST_NAME = "BMTVoiceStudio-1.3.2-dev"
STABLE_131_ZIP = "BMTVoiceStudio-1.3.1-Windows-x64-Portable.zip"
STABLE_131_SHA256 = "1abd8500897136120cd610049b81210c7eae2ac5e3526995954166b4428dc9a2"


def _verify_stable(when: str) -> None:
    zip12 = ROOT / "release" / STABLE_12_ZIP_NAME
    zip130 = ROOT / "release" / STABLE_130_ZIP_NAME
    zip131 = ROOT / "release" / STABLE_131_ZIP
    for path, expected, label in (
        (zip12, STABLE_12_SHA256, "1.2"),
        (zip130, STABLE_130_SHA256, "1.3.0"),
        (zip131, STABLE_131_SHA256, "1.3.1"),
    ):
        if not path.is_file():
            raise SystemExit(f"STOP: missing {label} zip {when}: {path}")
        digest = sha256_file(path)
        if digest != expected:
            raise SystemExit(f"STOP: {label} SHA changed {when}\nexpected {expected}\nactual {digest}")
        print("STABLE_OK", when, label, digest[:12])


def _scrub(tree: Path) -> None:
    drop_names = {".git", ".pytest_cache", "__pycache__", ".env", "credentials.json", ".cursor"}
    for path in list(tree.rglob("*")):
        if not path.exists():
            continue
        if path.name in drop_names or path.suffix.lower() in {".pyc", ".pyo"}:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)


def main() -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    _verify_stable("before")
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != "1.3.2-dev":
        raise SystemExit(f"STOP: VERSION must be 1.3.2-dev, got {version!r}")

    ico = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
    if not ico.is_file():
        raise SystemExit(f"STOP: Windows ICO missing: {ico}")
    spec = ROOT / "BMTVoiceStudio-1.3.2-dev.spec"
    if 'icon="bmt_voice_studio/resources/bmt_voice_studio.ico"' not in spec.read_text(encoding="utf-8"):
        raise SystemExit("STOP: 1.3.2-dev spec must embed bmt_voice_studio.ico")

    stamp = subprocess.run([str(py), str(ROOT / "tools" / "stamp_build.py")], cwd=ROOT)
    if stamp.returncode != 0:
        return stamp.returncode

    dist_target = ROOT / "dist" / DIST_NAME
    if dist_target.exists():
        shutil.rmtree(dist_target, ignore_errors=True)

    build = subprocess.run(
        [str(py), "-m", "PyInstaller", "--noconfirm", str(spec)],
        cwd=ROOT,
    )
    if build.returncode != 0:
        return build.returncode

    dist = ROOT / "dist" / DIST_NAME
    exe = dist / "BMTVoiceStudio.exe"
    if not exe.is_file():
        raise SystemExit(f"DEV EXE missing: {exe}")
    for name in ("THIRD_PARTY_NOTICES.txt", "VERSION"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dist / name)
    _scrub(dist)
    hits = scan_rc_tree(dist)
    if hits:
        print("SECURITY_SCAN_FAIL")
        for hit in hits[:40]:
            print(" ", hit)
        return 1
    print("SECURITY_SCAN_OK", dist)
    _verify_stable("after")
    print("DEV_EXE", exe)
    print("DEV_DIST", dist)
    print("NOTE: 1.3.1 FINAL zip was not modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
