"""Package BMT Voice Studio 1.3.0-RC1 into dist/ and release-candidate/. Never touch 1.2.0."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.release_scan import STABLE_12_SHA256, STABLE_12_ZIP_NAME, scan_rc_tree, sha256_file

DIST_NAME = "BMTVoiceStudio-1.3.0-RC1"
PORTABLE_NAME = "BMTVoiceStudio-1.3.0-RC1-Windows-x64-Portable"
README = """BMT Voice Studio 1.3.0 RC1

Windows 10/11 x64

Main features:

- Daily BMT neural audio generation
- English / French / Swahili / Portuguese
- Automatic portrait devotional video creation
- Multi-language video batch production
- BMT Classic / Nature / Minimal templates
- Optional captions
- Standard / WhatsApp output profiles

Internet connection required for neural voice generation.

Video rendering itself uses packaged FFmpeg.

How to use:
1. Extract this folder anywhere.
2. Open BMTVoiceStudio.exe inside the BMTVoiceStudio folder.
3. Do not move the EXE alone — keep the whole folder together.
"""


def _verify_stable_12(when: str) -> str:
    zip12 = ROOT / "release" / STABLE_12_ZIP_NAME
    if not zip12.is_file():
        raise SystemExit(f"STOP: stable 1.2 zip missing {when}: {zip12}")
    digest = sha256_file(zip12)
    if digest != STABLE_12_SHA256:
        raise SystemExit(
            f"STOP: stable 1.2 SHA changed {when}.\nexpected {STABLE_12_SHA256}\nactual   {digest}"
        )
    print("STABLE_1.2_SHA_OK", when, digest)
    return digest


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


def _zip_dir(src: Path, dest: Path) -> None:
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in src.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(src.parent).as_posix())


def main() -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    _verify_stable_12("before")

    stamp = subprocess.run([str(py), str(ROOT / "tools" / "stamp_build.py")], cwd=ROOT)
    if stamp.returncode != 0:
        return stamp.returncode

    spec = ROOT / "BMTVoiceStudio-1.3.0-RC1.spec"
    build = subprocess.run(
        [str(py), "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)],
        cwd=ROOT,
    )
    if build.returncode != 0:
        return build.returncode

    dist = ROOT / "dist" / DIST_NAME
    exe = dist / "BMTVoiceStudio.exe"
    if not exe.is_file():
        raise SystemExit(f"RC EXE missing: {exe}")

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

    rc_root = ROOT / "release-candidate"
    portable = rc_root / PORTABLE_NAME
    inner = portable / "BMTVoiceStudio"
    rc_root.mkdir(parents=True, exist_ok=True)
    if portable.exists():
        shutil.rmtree(portable)
    shutil.copytree(dist, inner)
    (portable / "README.txt").write_text(README, encoding="utf-8")
    _scrub(portable)
    hits = scan_rc_tree(inner)
    if hits:
        print("SECURITY_SCAN_FAIL portable")
        for hit in hits[:40]:
            print(" ", hit)
        return 1

    zip_path = rc_root / f"{PORTABLE_NAME}.zip"
    _zip_dir(portable, zip_path)
    digest = sha256_file(zip_path)
    (rc_root / f"{PORTABLE_NAME}.zip.sha256").write_text(
        f"{digest}  {PORTABLE_NAME}.zip\n", encoding="ascii"
    )
    (portable / "SHA256SUMS.txt").write_text(f"{digest}  {PORTABLE_NAME}.zip\n", encoding="ascii")
    print("RC_ZIP", zip_path)
    print("RC_SHA256", digest)

    forbidden_release = ROOT / "release" / f"{PORTABLE_NAME}.zip"
    if forbidden_release.exists():
        raise SystemExit("STOP: RC zip was written into production release/")

    _verify_stable_12("after")
    print("RC_EXE", exe)
    print("RC_PORTABLE", portable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
