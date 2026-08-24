"""Safe copy-based BMT library migration. Never deletes the source automatically."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _file_digest(path: Path, limit: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = limit
        while remaining > 0:
            chunk = fh.read(min(65536, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return h.hexdigest()


def preflight_migration(source: Path, destination: Path) -> dict[str, Any]:
    src = Path(source)
    dest = Path(destination)
    report: dict[str, Any] = {
        "ok": True,
        "errors": [],
        "source_root": str(src),
        "destination_root": str(dest),
        "files_found": 0,
        "bytes_found": 0,
        "destination_writable": False,
        "free_bytes": 0,
        "enough_space": False,
    }
    if not src.is_dir():
        report["ok"] = False
        report["errors"].append("The existing library folder was not found.")
        return report
    files = [p for p in src.rglob("*") if p.is_file()]
    report["files_found"] = len(files)
    report["bytes_found"] = sum(p.stat().st_size for p in files)
    dest.mkdir(parents=True, exist_ok=True)
    probe = dest / ".bmt_write_probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        report["destination_writable"] = True
    except Exception as exc:
        report["ok"] = False
        report["errors"].append(f"The destination folder is not writable: {exc}")
        return report
    try:
        free = shutil.disk_usage(dest).free
    except Exception:
        free = 0
    report["free_bytes"] = int(free)
    needed = int(report["bytes_found"] * 1.1) + 50_000_000
    report["enough_space"] = free >= needed
    if not report["enough_space"]:
        report["ok"] = False
        report["errors"].append("There is not enough free disk space to copy the library.")
    return report


def _conflict_name(dest: Path) -> Path:
    stem = dest.stem
    suffix = dest.suffix
    n = 1
    while True:
        candidate = dest.with_name(f"{stem}__from_other_library_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def copy_library(source: Path, destination: Path) -> dict[str, Any]:
    src = Path(source)
    dest = Path(destination)
    copied = 0
    skipped = 0
    conflicts: list[dict[str, str]] = []
    errors: list[str] = []
    dest.mkdir(parents=True, exist_ok=True)
    for file in src.rglob("*"):
        if not file.is_file():
            continue
        rel = file.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.exists():
                same = False
                try:
                    if target.stat().st_size == file.stat().st_size:
                        same = _file_digest(file) == _file_digest(target)
                except Exception:
                    same = False
                if same:
                    skipped += 1
                    continue
                alt = _conflict_name(target)
                shutil.copy2(file, alt)
                copied += 1
                conflicts.append({"source": str(file), "kept_as": str(alt)})
                continue
            shutil.copy2(file, target)
            copied += 1
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
    return {
        "files_copied": copied,
        "files_skipped": skipped,
        "conflicts": conflicts,
        "errors": errors,
    }


def verify_copy(source: Path, destination: Path) -> dict[str, Any]:
    src = Path(source)
    dest = Path(destination)
    missing: list[str] = []
    src_files = [p for p in src.rglob("*") if p.is_file()]
    for file in src_files:
        rel = file.relative_to(src)
        target = dest / rel
        if target.is_file():
            continue
        stem_hits = list(target.parent.glob(f"{target.stem}__from_other_library_*{target.suffix}"))
        if not stem_hits:
            missing.append(str(rel))
    indexes = []
    for rel in ("History/daily.json", "History/video.json", "Projects/autosave.json"):
        if (src / rel).is_file() and not (dest / rel).is_file():
            indexes.append(rel)
    ok = not missing and not indexes
    return {
        "ok": ok,
        "missing_count": len(missing),
        "missing_sample": missing[:20],
        "missing_indexes": indexes,
        "source_files": len(src_files),
    }


def write_migration_report(destination: Path, payload: dict[str, Any]) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = Path(destination) / "Reports" / "DataMigration" / ts
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "migration_report.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def migrate_library(source: Path, destination: Path) -> dict[str, Any]:
    pre = preflight_migration(source, destination)
    payload: dict[str, Any] = {
        "source_root": str(source),
        "destination_root": str(destination),
        "files_found": pre.get("files_found", 0),
        "files_copied": 0,
        "files_skipped": 0,
        "conflicts": [],
        "errors": list(pre.get("errors") or []),
        "verification_result": {},
        "activated_root": "",
        "ok": False,
    }
    if not pre.get("ok"):
        try:
            payload["report_path"] = str(write_migration_report(destination, payload))
        except Exception:
            pass
        return payload
    copied = copy_library(source, destination)
    payload["files_copied"] = copied["files_copied"]
    payload["files_skipped"] = copied["files_skipped"]
    payload["conflicts"] = copied["conflicts"]
    payload["errors"].extend(copied["errors"])
    verify = verify_copy(source, destination)
    payload["verification_result"] = verify
    payload["ok"] = bool(verify.get("ok")) and not copied["errors"]
    if payload["ok"]:
        from bmt_voice_studio.config.data_root import canonical_documents_location, persist_active_root
        from bmt_voice_studio.config.paths import EXPORT_DIR_NAME

        canonical = canonical_documents_location() / EXPORT_DIR_NAME
        mode = "default" if Path(destination).resolve() == canonical.resolve() else "custom"
        persist_active_root(destination, mode=mode)
        payload["activated_root"] = str(destination)
    payload["report_path"] = str(write_migration_report(destination, payload))
    return payload
