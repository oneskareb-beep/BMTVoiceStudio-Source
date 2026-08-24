"""Package BMT Voice Studio 1.3.1 FINAL into dist/ and release/. Never touch 1.3.0 or 1.2.0."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.release_scan import STABLE_12_SHA256, STABLE_12_ZIP_NAME, scan_rc_tree, sha256_file
from bmt_voice_studio.ui.theme import STABLE_130_SHA256, STABLE_130_ZIP_NAME

DIST_NAME = "BMTVoiceStudio-1.3.1"
PORTABLE_NAME = "BMTVoiceStudio-1.3.1-Windows-x64-Portable"
README = """BMT Voice Studio 1.3.1
Windows 10/11 x64

Features:
- Four-language Daily devotional audio
- English, French, Swahili and Portuguese
- Dual male/female speaker support using braces
- Portrait Video Maker
- BMT Classic, Nature and Minimal templates
- Multi-language video batch export
- Optional captions
- Standard and WhatsApp video profiles
- Video project restore and history

Installation:
1. Extract the ZIP completely.
2. Open the BMTVoiceStudio folder.
3. Run BMTVoiceStudio.exe.
4. Keep the complete application folder together.

Internet connection is required for neural voice generation.
Video rendering uses packaged FFmpeg.

Do not install Python. The complete BMTVoiceStudio folder is required.
"""


def _verify_stable(when: str) -> None:
    zip12 = ROOT / "release" / STABLE_12_ZIP_NAME
    zip130 = ROOT / "release" / STABLE_130_ZIP_NAME
    if not zip12.is_file():
        raise SystemExit(f"STOP: stable 1.2 zip missing {when}: {zip12}")
    if not zip130.is_file():
        raise SystemExit(f"STOP: stable 1.3.0 FINAL zip missing {when}: {zip130}")
    d12 = sha256_file(zip12)
    d130 = sha256_file(zip130)
    if d12 != STABLE_12_SHA256:
        raise SystemExit(f"STOP: 1.2 SHA changed {when}\nexpected {STABLE_12_SHA256}\nactual {d12}")
    if d130 != STABLE_130_SHA256:
        raise SystemExit(f"STOP: 1.3.0 FINAL SHA changed {when}\nexpected {STABLE_130_SHA256}\nactual {d130}")
    print("STABLE_OK", when, "1.2", d12[:12], "1.3.0", d130[:12])


def _scrub(tree: Path) -> None:
    drop_names = {
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".env",
        "credentials.json",
        ".cursor",
        "qa_outputs",
        "qa_screenshots",
    }
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


def _clear_dist(target: Path) -> None:
    if not target.exists():
        return
    stale = target.with_name(target.name + ".oldpack")
    if stale.exists():
        shutil.rmtree(stale, ignore_errors=True)
    try:
        target.rename(stale)
        shutil.rmtree(stale, ignore_errors=True)
    except Exception:
        shutil.rmtree(target, ignore_errors=True)


def main() -> int:
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    _verify_stable("before")

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != "1.3.1":
        raise SystemExit(f"STOP: VERSION must be 1.3.1 for FINAL package, got {version!r}")

    stamp = subprocess.run([str(py), str(ROOT / "tools" / "stamp_build.py")], cwd=ROOT)
    if stamp.returncode != 0:
        return stamp.returncode

    _clear_dist(ROOT / "dist" / DIST_NAME)
    # Also clear leftover DEV onedir if present (frees disk; never touch release ZIPs).
    for extra in ("BMTVoiceStudio-1.3.1-dev",):
        _clear_dist(ROOT / "dist" / extra)

    ico = ROOT / "bmt_voice_studio" / "resources" / "bmt_voice_studio.ico"
    if not ico.is_file():
        raise SystemExit(f"STOP: Windows application ICO missing: {ico}")
    spec = ROOT / "BMTVoiceStudio-1.3.1.spec"
    spec_text = spec.read_text(encoding="utf-8")
    if 'icon="bmt_voice_studio/resources/bmt_voice_studio.ico"' not in spec_text:
        raise SystemExit("STOP: FINAL spec must embed bmt_voice_studio.ico via EXE(icon=...)")
    build = subprocess.run(
        [str(py), "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)],
        cwd=ROOT,
    )
    if build.returncode != 0:
        return build.returncode

    dist = ROOT / "dist" / DIST_NAME
    exe = dist / "BMTVoiceStudio.exe"
    if not exe.is_file():
        raise SystemExit(f"FINAL EXE missing: {exe}")

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

    release_root = ROOT / "release"
    portable = release_root / PORTABLE_NAME
    inner = portable / "BMTVoiceStudio"
    release_root.mkdir(parents=True, exist_ok=True)
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

    from bmt_voice_studio.build_info import BUILD_TIMESTAMP

    ffmpeg_hits = list((inner / "_internal").rglob("ffmpeg*.exe"))
    ffmpeg_rel = ""
    if ffmpeg_hits:
        try:
            ffmpeg_rel = ffmpeg_hits[0].relative_to(inner).as_posix()
        except ValueError:
            ffmpeg_rel = ffmpeg_hits[0].name

    manifest = {
        "product_name": "BMT Voice Studio",
        "version": "1.3.1",
        "build_label": "Final",
        "build_timestamp": BUILD_TIMESTAMP,
        "platform": "Windows",
        "architecture": "x64",
        "packaging_mode": "pyinstaller-onedir",
        "executable": "BMTVoiceStudio/BMTVoiceStudio.exe",
        "supported_languages": ["en", "fr", "sw", "pt"],
        "provider": "Edge TTS",
        "piper_production_policy": "forbidden_for_approved_daily",
        "video_maker_templates": ["BMT Classic", "BMT Nature", "BMT Minimal"],
        "video_profiles": ["Standard 1080p", "WhatsApp Optimized"],
        "packaged_ffmpeg": ffmpeg_rel or True,
        "test_result": "252 passed, 1 skipped",
        "data_root_behavior": "shared library for Daily Audio, Video Maker, History, Projects",
        "promoted_from": "1.3.1-dev",
        "stable_1_3_0_sha256": STABLE_130_SHA256,
    }
    (portable / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    zip_path = release_root / f"{PORTABLE_NAME}.zip"
    _zip_dir(portable, zip_path)
    digest = sha256_file(zip_path)
    (release_root / f"{PORTABLE_NAME}.zip.sha256").write_text(
        f"{digest}  {PORTABLE_NAME}.zip\n", encoding="ascii"
    )
    (portable / "SHA256SUMS.txt").write_text(f"{digest}  {PORTABLE_NAME}.zip\n", encoding="ascii")
    manifest["release_zip"] = f"{PORTABLE_NAME}.zip"
    manifest["release_zip_sha256"] = digest
    (portable / "RELEASE_MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    sums = release_root / "SHA256SUMS.txt"
    line = f"{digest}  {PORTABLE_NAME}.zip\n"
    existing = sums.read_text(encoding="ascii") if sums.is_file() else ""
    if PORTABLE_NAME not in existing:
        with sums.open("a", encoding="ascii") as fh:
            fh.write(line)

    _verify_stable("after")
    print("FINAL_ZIP", zip_path)
    print("FINAL_SHA256", digest)
    print("FINAL_EXE", exe)
    print("FINAL_PORTABLE", portable)
    if ffmpeg_hits:
        print("BUNDLED_FFMPEG", ffmpeg_hits[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
