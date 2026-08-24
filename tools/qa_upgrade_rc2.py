"""Simulated upgrade QA: USE EXISTING LIBRARY and MOVE LIBRARY TO DEFAULT LOCATION."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bmt_voice_studio.config.data_root import decide_startup_root, persist_active_root
from bmt_voice_studio.config.migrate_library import migrate_library
from bmt_voice_studio.config.paths import EXPORT_DIR_NAME, user_data_root


def _populate(root: Path, stamp: str) -> Path:
    daily = root / "Exports" / "Daily" / "BMT_2026_08_14"
    daily.mkdir(parents=True, exist_ok=True)
    (daily / f"{stamp}_FINAL.mp3").write_bytes(b"mp3")
    (daily / "production.json").write_text("{}", encoding="utf-8")
    hist = root / "History"
    hist.mkdir(parents=True, exist_ok=True)
    (hist / "daily.json").write_text(
        json.dumps([{"date": "2026-08-14", "status": "COMPLETE", "language": stamp.lower()}]),
        encoding="utf-8",
    )
    video = root / "Exports" / "Video" / "BMT_2026_08_14"
    video.mkdir(parents=True, exist_ok=True)
    (video / f"{stamp}.mp4").write_bytes(b"mp4")
    return root


def _env(la: Path, docs: Path, phys: Path) -> None:
    os.environ["LOCALAPPDATA"] = str(la)
    os.environ["BMT_DOCUMENTS_DIR"] = str(docs)
    os.environ["BMT_PHYSICAL_DOCUMENTS_DIR"] = str(phys)
    os.environ.pop("BMT_DATA_ROOT", None)
    os.environ.pop("BMT_SKIP_LIBRARY_DIALOG", None)
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None


def main() -> int:
    report: dict = {"checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    parent = Path(tempfile.mkdtemp(prefix="bmt_rc2_upgrade_"))
    # --- USE EXISTING ---
    la1 = parent / "use_la"
    docs1 = parent / "use_onedrive" / "Documents"
    phys1 = parent / "use_documents"
    legacy1 = _populate(phys1 / EXPORT_DIR_NAME, "EN")
    _populate(docs1 / EXPORT_DIR_NAME, "FR")
    _env(la1, docs1, phys1)
    decision = decide_startup_root(allow_prompt=True)
    check("multi_library_prompt", decision.needs_prompt, decision.reason)
    persist_active_root(legacy1, mode="custom")
    from bmt_voice_studio.config import settings as settings_mod

    settings_mod._settings = None
    active = user_data_root()
    check("use_existing_active", active == legacy1, str(active))
    check("use_existing_no_copy", (legacy1 / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file())
    check(
        "use_existing_canonical_untouched_en",
        not (docs1 / EXPORT_DIR_NAME / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").exists(),
    )

    # --- MOVE ---
    la2 = parent / "move_la"
    docs2 = parent / "move_onedrive" / "Documents"
    phys2 = parent / "move_documents"
    legacy2 = _populate(phys2 / EXPORT_DIR_NAME, "EN")
    dest2 = docs2 / EXPORT_DIR_NAME
    dest2.mkdir(parents=True)
    _env(la2, docs2, phys2)
    result = migrate_library(legacy2, dest2)
    check("migrate_ok", bool(result.get("ok")), json.dumps({k: result.get(k) for k in ("ok", "errors", "files_copied")}))
    settings_mod._settings = None
    check("migrate_activated", user_data_root() == dest2, str(user_data_root()))
    check("migrate_source_kept", (legacy2 / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file())
    check("migrate_dest_has_en", (dest2 / "Exports" / "Daily" / "BMT_2026_08_14" / "EN_FINAL.mp3").is_file())
    check("migrate_report", Path(str(result.get("report_path") or "")).is_file(), str(result.get("report_path")))

    out = ROOT / "qa_outputs" / "rc2" / "upgrade_deploy.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("WROTE", out)
    failed = [c for c in report["checks"] if not c["ok"]]
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
