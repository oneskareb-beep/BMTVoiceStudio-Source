"""Apply a newer portable build over an existing BMT Voice Studio install."""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from bmt_voice_studio import __version__
from bmt_voice_studio.net import prefer_ipv4 as _prefer_ipv4
from bmt_voice_studio.update.channel import default_feed_url

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)")
_PORTABLE_ZIP = re.compile(r"BMTVoiceStudio-(\d+\.\d+\.\d+)-Windows-x64-Portable\.zip$", re.IGNORECASE)


def parse_version(text: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match((text or "").strip())
    if not m:
        return (0, 0, 0)
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def is_newer(candidate: str, current: str = __version__) -> bool:
    return parse_version(candidate) > parse_version(current)


def install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def sibling_update_zips(root: Path | None = None) -> list[Path]:
    here = (root or install_root()).parent
    found: list[Path] = []
    for folder in (here, here.parent, Path.home() / "Downloads"):
        try:
            for path in folder.glob("BMTVoiceStudio-*-Windows-x64-Portable.zip"):
                if path.is_file():
                    found.append(path)
        except OSError:
            continue
    unique = {p.resolve(): p for p in found}
    return sorted(unique.values(), key=lambda p: parse_version(_version_from_name(p.name)), reverse=True)


def _version_from_name(name: str) -> str:
    m = re.search(r"BMTVoiceStudio-(\d+\.\d+\.\d+)", name)
    return m.group(1) if m else "0.0.0"


def _version_from_tag(tag: str) -> str:
    text = (tag or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    m = _VERSION_RE.match(text)
    return m.group(0) if m else text


def normalize_feed(payload: dict) -> dict:
    """Accept either our latest.json or a GitHub Releases API document."""
    data = payload or {}
    version = str(data.get("version") or "").strip()
    zip_url = str(data.get("zip_url") or data.get("url") or "").strip()
    if version and zip_url:
        return {"version": version, "zip_url": zip_url, "name": str(data.get("name") or "")}

    tag = _version_from_tag(str(data.get("tag_name") or data.get("name") or ""))
    assets = data.get("assets") or []
    chosen = ""
    chosen_api = ""
    chosen_ver = tag
    for asset in assets:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        api_url = str(asset.get("url") or "")
        match = _PORTABLE_ZIP.match(name)
        if match and url:
            chosen = url
            chosen_api = api_url
            chosen_ver = match.group(1)
            break
    if not chosen:
        for asset in assets:
            name = str(asset.get("name") or "")
            url = str(asset.get("browser_download_url") or "")
            api_url = str(asset.get("url") or "")
            if name.lower().endswith(".zip") and "portable" in name.lower() and url:
                chosen = url
                chosen_api = api_url
                chosen_ver = _version_from_name(name) or tag
                break
    return {
        "version": chosen_ver,
        "zip_url": chosen,
        "asset_api_url": chosen_api,
        "name": str(data.get("name") or ""),
    }


def _ua_headers(**extra: str) -> dict[str, str]:
    headers = {
        "User-Agent": f"BMTVoiceStudio/{__version__}",
        "Accept": extra.pop("Accept", "*/*"),
    }
    headers.update(extra)
    return headers


def _urlopen_with_retry(req: Request, timeout: float, attempts: int = 4):
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            with _prefer_ipv4():
                return urlopen(req, timeout=timeout)  # noqa: S310
        except (URLError, TimeoutError, OSError) as exc:
            last = exc
            if i + 1 < attempts:
                time.sleep(0.6 * (i + 1))
    assert last is not None
    raise last


def fetch_feed(url: str, timeout: float = 20.0) -> dict:
    target = (url or "").strip() or default_feed_url()
    if not target:
        raise ValueError("No update feed URL is configured")
    req = Request(
        target,
        headers=_ua_headers(Accept="application/vnd.github+json, application/json"),
    )
    with _urlopen_with_retry(req, timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Update feed is not a JSON object")
    return normalize_feed(payload)


def download_update_zip(
    url: str,
    dest: Path,
    timeout: float = 90.0,
    *,
    asset_api_url: str = "",
    on_progress: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> Path:
    """Download a portable zip from the feed so the existing install can be replaced in place.

    Prefer the GitHub Releases *asset API* URL first. Many Windows PCs can reach
    api.github.com (same host as the feed) but fail DNS for github.com / CDN hosts.

    on_progress(received_bytes, total_bytes_or_0) is called while streaming.
    cancel_check() returning True aborts the current attempt.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    attempts: list[tuple[str, dict[str, str]]] = []
    api = str(asset_api_url or "").strip()
    browser = str(url or "").strip()
    # API first (api.github.com), then browser_download_url (github.com / objects CDN).
    if api:
        attempts.append((api, _ua_headers(Accept="application/octet-stream")))
    if browser and browser not in {u for u, _h in attempts}:
        attempts.append((browser, _ua_headers()))
    if not attempts:
        raise ValueError("Update URL must be http or https")
    last: Exception | None = None
    for candidate, headers in attempts:
        if cancel_check and cancel_check():
            raise InterruptedError("Update download cancelled")
        if not candidate.lower().startswith(("https://", "http://")):
            last = ValueError("Update URL must be http or https")
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            req = Request(candidate, headers=headers)
            # Fewer retries / shorter wait so a bad host fails over to the next URL quickly.
            with _urlopen_with_retry(req, timeout, attempts=3) as resp, tmp.open("wb") as handle:
                total = 0
                try:
                    hdrs = getattr(resp, "headers", None)
                    if hdrs is not None:
                        total = int(hdrs.get("Content-Length") or 0)
                except (TypeError, ValueError, AttributeError):
                    total = 0
                received = 0
                while True:
                    if cancel_check and cancel_check():
                        raise InterruptedError("Update download cancelled")
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    received += len(chunk)
                    if on_progress:
                        on_progress(received, total)
            tmp.replace(dest)
            if not zipfile.is_zipfile(dest):
                dest.unlink(missing_ok=True)
                raise ValueError("The download is not a zip package")
            if on_progress:
                on_progress(dest.stat().st_size, dest.stat().st_size)
            return dest
        except InterruptedError:
            tmp.unlink(missing_ok=True)
            raise
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            last = exc
            tmp.unlink(missing_ok=True)
            continue
    assert last is not None
    raise last


def write_updater_script(current_dir: Path, extracted_dir: Path, relaunch: Path) -> Path:
    """Write a .cmd that replaces files after this process exits, then relaunches."""
    script = current_dir / "_apply_update.cmd"
    src = str(extracted_dir)
    dst = str(current_dir)
    exe = str(relaunch)
    pid = os.getpid()
    # Use ping instead of timeout: clicking a console with Quick Edit can pause `timeout`
    # and leave users stuck mid-update. Keep the window minimized.
    script.write_text(
        "\r\n".join(
            [
                "@echo off",
                "setlocal",
                "if not \"%~1\"==\"__run\" (",
                "  start \"BMT Voice Studio Update\" /min cmd /c \"\"%~f0\" __run\"",
                "  exit /b 0",
                ")",
                f"set PID={pid}",
                "set /a waits=0",
                ":wait",
                "tasklist /FI \"PID eq %PID%\" | find \"%PID%\" >nul",
                "if not errorlevel 1 (",
                "  set /a waits+=1",
                "  if %waits% GEQ 120 goto copyfiles",
                "  ping -n 2 127.0.0.1 >nul",
                "  goto wait",
                ")",
                ":copyfiles",
                f'robocopy "{src}" "{dst}" /E /IS /IT /R:2 /W:1 /NFL /NDL /NJH /NJS /nc /ns /np',
                f'start "" "{exe}"',
                'rd /s /q "' + src + '"',
                'del "%~f0"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return script


def extract_portable_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)
    exe_hits = list(dest.rglob("BMTVoiceStudio.exe"))
    if not exe_hits:
        raise FileNotFoundError("The update zip does not contain BMTVoiceStudio.exe")
    return exe_hits[0].parent


def apply_zip_update(zip_path: Path) -> Path:
    """Extract a portable zip and return the updater script path. Caller should exit."""
    staging = Path(tempfile.mkdtemp(prefix="bmt_update_"))
    extracted = extract_portable_zip(Path(zip_path), staging)
    current = install_root()
    exe = current / "BMTVoiceStudio.exe"
    if not exe.is_file():
        exe = extracted / "BMTVoiceStudio.exe"
    return write_updater_script(current, extracted, exe)
