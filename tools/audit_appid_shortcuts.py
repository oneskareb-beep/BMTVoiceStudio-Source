"""Audit AppUserModelID registration and shortcuts. Read-only."""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "qa_outputs" / "taskbar_diag"
APP_IDS = (
    "BelieversBusinessmenNetwork.BMTVoiceStudio",
    "BelieversBusinessmenNetwork.BMTVoiceStudio.App",
)


def _reg_appids() -> list[dict]:
    import winreg

    found = []
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\AppUserModelId")
    except OSError:
        return found
    i = 0
    while True:
        try:
            name = winreg.EnumKey(root, i)
        except OSError:
            break
        i += 1
        rec = {"id": name, "values": {}}
        try:
            key = winreg.OpenKey(root, name)
            j = 0
            while True:
                try:
                    vn, vv, _vt = winreg.EnumValue(key, j)
                except OSError:
                    break
                rec["values"][vn] = vv
                j += 1
            winreg.CloseKey(key)
        except OSError:
            pass
        if "BMT" in name.upper() or "Believers" in name or name in APP_IDS:
            found.append(rec)
    winreg.CloseKey(root)
    return found


def _iter_lnks() -> list[Path]:
    homes = [
        Path.home() / "Desktop",
        Path.home() / "OneDrive" / "Desktop",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Internet Explorer" / "Quick Launch" / "User Pinned" / "TaskBar",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    hits: list[Path] = []
    for root in homes:
        if not root.is_dir():
            continue
        hits.extend(root.rglob("*.lnk"))
    return hits


def _lnk_info(path: Path) -> dict | None:
    try:
        import win32com.client  # type: ignore
    except Exception:
        win32com = None
    rec = {"path": str(path), "name": path.name}
    if win32com is not None:
        shell = win32com.client.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(str(path))
        rec["target"] = str(sc.TargetPath or "")
        rec["icon"] = str(sc.IconLocation or "")
    else:
        rec["target"] = ""
        rec["icon"] = ""
        rec["note"] = "pywin32 not available; name-only scan"
    blob = path.read_bytes()
    rec["mentions_bmt"] = b"BMT" in blob or b"BMTVoice" in blob or "BMT" in path.name.upper()
    rec["mentions_appid"] = any(aid.encode("utf-16le") in blob or aid.encode() in blob for aid in APP_IDS)
    if rec["mentions_bmt"] or rec["mentions_appid"] or "BMT" in path.name.upper() or "Voice Studio" in path.name:
        return rec
    return None


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    lnks = []
    for path in _iter_lnks():
        info = _lnk_info(path)
        if info:
            lnks.append(info)
    report = {
        "app_ids_in_source": list(APP_IDS),
        "registry_appuser_model_ids": _reg_appids(),
        "matching_shortcuts": lnks,
    }
    (OUT / "appid_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
