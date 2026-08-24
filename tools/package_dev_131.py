"""Build BMT Voice Studio 1.3.1-dev onedir for UI review. Never create FINAL ZIP. Never touch 1.3.0."""

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

DIST_NAME = "BMTVoiceStudio-1.3.1-dev"


def _verify_stable(when: str) -> None:
    zip12 = ROOT / "release" / STABLE_12_ZIP_NAME
    zip130 = ROOT / "release" / STABLE_130_ZIP_NAME
    if not zip12.is_file():
        raise SystemExit(f"STOP: missing 1.2 zip {when}")
    if not zip130.is_file():
        raise SystemExit(f"STOP: missing 1.3.0 FINAL zip {when}")
    d12 = sha256_file(zip12)
    d130 = sha256_file(zip130)
    if d12 != STABLE_12_SHA256:
        raise SystemExit(f"STOP: 1.2 SHA changed {when}")
    if d130 != STABLE_130_SHA256:
        raise SystemExit(f"STOP: 1.3.0 FINAL SHA changed {when}\nexpected {STABLE_130_SHA256}\nactual {d130}")
    print("STABLE_OK", when, "1.2", d12[:12], "1.3.0", d130[:12])


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
    if version != "1.3.1-dev":
        raise SystemExit(f"STOP: VERSION must be 1.3.1-dev, got {version!r}")

    stamp = subprocess.run([str(py), str(ROOT / "tools" / "stamp_build.py")], cwd=ROOT)
    if stamp.returncode != 0:
        return stamp.returncode

    dist_target = ROOT / "dist" / DIST_NAME
    if dist_target.exists():
        shutil.rmtree(dist_target, ignore_errors=True)

    # Free space: remove prior non-FINAL onedir builds if needed (keep 1.3.0 dist optional)
    for stale in ("BMTVoiceStudio-1.3.0",):
        # Keep 1.3.0 dist if present for comparison; only remove if disk is critical
        pass

    spec = ROOT / "BMTVoiceStudio-1.3.1-dev.spec"
    build = subprocess.run(
        [str(py), "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)],
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
    # Explicitly do NOT write release/ FINAL zip
    print("DEV_EXE", exe)
    print("DEV_DIST", dist)
    print("NOTE: no FINAL portable ZIP created for 1.3.1-dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
