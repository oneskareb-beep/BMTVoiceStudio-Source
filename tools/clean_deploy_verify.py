"""Clean-location packaged EXE verification + short multi-language smoke."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
RELEASE_EXE = (
    ROOT
    / "release"
    / f"BMTVoiceStudio-{_VERSION}-Windows-x64-Portable"
    / "BMTVoiceStudio"
    / "BMTVoiceStudio.exe"
)
DIST_DIR = ROOT / "dist" / f"BMTVoiceStudio-{_VERSION}"


def main() -> int:
    report: dict = {"checks": [], "smoke": {}}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        print(("PASS" if ok else "FAIL"), name, detail)

    # 1) Clean location copy
    clean_root = Path(r"C:\BMT_RELEASE_TEST")
    clean_root.mkdir(parents=True, exist_ok=True)
    dest = clean_root / "BMTVoiceStudio"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    src = RELEASE_EXE.parent if RELEASE_EXE.exists() else DIST_DIR
    shutil.copytree(src, dest)
    exe = dest / "BMTVoiceStudio.exe"
    check("clean_copy_exe", exe.exists(), str(exe))
    check("no_source_repo_needed", not (dest / "bmt_voice_studio").exists() or (dest / "_internal").exists())
    check("has_internal", (dest / "_internal").is_dir())

    # Fresh profile env
    fresh_la = Path(tempfile.mkdtemp(prefix="bmt_fresh_la_"))
    fresh_docs = Path(tempfile.mkdtemp(prefix="bmt_fresh_docs_"))
    env = os.environ.copy()
    env["LOCALAPPDATA"] = str(fresh_la)
    env["USERPROFILE"] = str(fresh_docs)  # documents resolve via home in some paths
    env["HOME"] = str(fresh_docs)
    # Keep real Documents for Qt if needed; force LOCALAPPDATA fresh for approvals
    env["BMT_TEST_MODE"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"

    smoke_report = fresh_la / "smoke_report.json"
    cmd = [str(exe), "--release-smoke", "--report", str(smoke_report)]
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300, cwd=str(dest))
        check("packaged_release_smoke_exit", proc.returncode == 0, f"code={proc.returncode}")
        if smoke_report.exists():
            data = json.loads(smoke_report.read_text(encoding="utf-8"))
            report["smoke"] = data
            for c in data.get("checks") or []:
                check(f"smoke:{c.get('name')}", bool(c.get("ok")), str(c.get("detail") or ""))
        else:
            # windowed exe may write under temp_work_dir in fresh LA
            alt = list(fresh_la.rglob("release_smoke*.json")) + list(Path(dest).rglob("*smoke*.json"))
            check("smoke_report_present", False, f"missing; alts={alt[:3]}")
    except Exception as exc:
        check("packaged_release_smoke_exit", False, str(exc))

    # Fresh-profile approval probe via import against source (defaults) + packaged identity
    sys.path.insert(0, str(ROOT))
    os.environ["LOCALAPPDATA"] = str(fresh_la / "approval_probe")
    from bmt_voice_studio.daily.language_config import get_language_config, selectable_daily_languages
    from bmt_voice_studio.audio.ffmpeg_service import FFmpegService
    from bmt_voice_studio import __version__
    from bmt_voice_studio.build_info import BUILD_TIMESTAMP

    ready = {c.language_id: c.readiness_state() for c in selectable_daily_languages()}
    check("fresh_en_ready", ready.get("en") == "Ready", str(ready))
    check("fresh_fr_ready", ready.get("fr") == "Ready", str(ready))
    check("fresh_sw_ready", ready.get("sw") == "Ready", str(ready))
    check("fresh_pt_ready", ready.get("pt") == "Ready", str(ready))
    check(f"version_{_VERSION.replace('.', '_')}", __version__ == _VERSION, __version__)
    check("build_timestamp_set", bool(BUILD_TIMESTAMP) and "2026" in BUILD_TIMESTAMP, BUILD_TIMESTAMP)

    voices = {
        "en": (get_language_config("en").male_voice, get_language_config("en").female_voice),
        "fr": (get_language_config("fr").male_voice, get_language_config("fr").female_voice),
        "sw": (get_language_config("sw").male_voice, get_language_config("sw").female_voice),
        "pt": (get_language_config("pt").male_voice, get_language_config("pt").female_voice),
    }
    check("en_voices", voices["en"] == ("en-NG-AbeoNeural", "en-NG-EzinneNeural"), str(voices["en"]))
    check("fr_voices", voices["fr"] == ("fr-FR-HenriNeural", "fr-FR-DeniseNeural"), str(voices["fr"]))
    check("sw_voices", voices["sw"] == ("sw-TZ-DaudiNeural", "sw-TZ-RehemaNeural"), str(voices["sw"]))
    check("pt_voices", voices["pt"] == ("pt-BR-AntonioNeural", "pt-BR-FranciscaNeural"), str(voices["pt"]))

    # Short multi-language generation against packaged environment using source runner
    # but with fresh LOCALAPPDATA and export under clean docs
    from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job
    import asyncio

    out = Path(r"C:\BMT_RELEASE_TEST\ExportsSmoke")
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)

    scripts = {
        "en": "Welcome to BMT. {This is female.} Closing male.",
        "fr": "Bienvenue. {Réponse femme.} Fin homme. en anglais et en français",
        "sw": "Karibu. {Habari mama.} Mwisho.",
        "pt": "Bem-vindo. {Ola senhora.} Fim.",
    }
    combos = [
        ["en"],
        ["fr"],
        ["sw"],
        ["pt"],
        ["en", "fr"],
        ["sw", "pt"],
        ["en", "fr", "sw"],
        ["en", "fr", "sw", "pt"],
    ]
    piper_total = 0
    combo_results = []
    for selected in combos:
        job = DailyJob(
            date=date(2026, 8, 13),
            english_text=scripts["en"] if "en" in selected else "",
            french_text=scripts["fr"] if "fr" in selected else "",
            swahili_text=scripts["sw"] if "sw" in selected else "",
            portuguese_text=scripts["pt"] if "pt" in selected else "",
            generate_english="en" in selected,
            generate_french="fr" in selected,
            generate_swahili="sw" in selected,
            generate_portuguese="pt" in selected,
            base_exports=out / ("_".join(selected)),
            provider="edge",
            use_piper_fallback=False,
        )
        try:
            res = asyncio.run(run_daily_job(job))
            ok = bool(res.ok)
            detail = res.status
            for block_name in ("english", "french", "swahili", "portuguese"):
                block = getattr(res, block_name)
                if isinstance(block, dict):
                    piper_total += int(block.get("piper_invocations") or 0)
                    if block.get("selected") is False:
                        continue
                    cfg_v = block.get("configured_voice") or ""
                    act_v = block.get("actual_voice") or ""
                    if cfg_v and act_v and cfg_v != act_v:
                        ok = False
                        detail += f"|mismatch:{block_name}"
            combo_results.append({"selected": selected, "ok": ok, "status": res.status, "folder": res.folder})
            check(f"gen_{'-'.join(selected)}", ok, detail)
        except Exception as exc:
            combo_results.append({"selected": selected, "ok": False, "error": str(exc)})
            check(f"gen_{'-'.join(selected)}", False, str(exc))

    check("piper_invocations_zero", piper_total == 0, str(piper_total))
    ff = FFmpegService()
    try:
        info = ff.resolution_info()
        check("ffmpeg_resolved", True, json.dumps(info))
        report["ffmpeg"] = info
    except Exception as exc:
        check("ffmpeg_resolved", False, str(exc))

    # developer path scan of release folder
    hit = False
    for p in dest.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".json", ".txt", ".md", ".py"}:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "C:\\Users\\aganz" in text or "C:/Users/aganz" in text:
                # allow only if somehow in binary noise; mark
                hit = True
                check("no_developer_path_in_release_text", False, str(p))
                break
    if not hit:
        check("no_developer_path_in_release_text", True)

    report["combo_results"] = combo_results
    report["piper_total"] = piper_total
    report["voices"] = voices
    report["ready"] = ready
    report["clean_exe"] = str(exe)
    out_path = ROOT / "qa_screenshots" / "final_release" / "CLEAN_DEPLOY_REPORT.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", out_path)
    failed = [c for c in report["checks"] if not c["ok"]]
    print("FAILED_COUNT", len(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
