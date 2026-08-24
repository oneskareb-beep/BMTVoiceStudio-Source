"""BMT Voice Studio application entrypoint."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from bmt_voice_studio.config.settings import get_settings
from bmt_voice_studio.logging_setup import setup_logging
from bmt_voice_studio.resources import (
    apply_win32_hwnd_icon,
    load_app_icon,
    prepare_windows_taskbar_identity,
)
from bmt_voice_studio.ui.main_window import MainWindow
from bmt_voice_studio.ui.theme import apply_theme
# Ensure production/smoke modules are bundled by PyInstaller
import bmt_voice_studio.production_batch  # noqa: F401
import bmt_voice_studio.release_smoke  # noqa: F401
import bmt_voice_studio.daily.pipeline  # noqa: F401
import bmt_voice_studio.video.ffmpeg_renderer  # noqa: F401
import bmt_voice_studio.video.captions  # noqa: F401


def main(argv: list[str] | None = None) -> int:
    from bmt_voice_studio.net import install_ipv4_preference

    install_ipv4_preference()
    argv = list(argv if argv is not None else sys.argv)
    # Headless packaged/clean-machine gate (no GUI)
    if "--release-smoke" in argv:
        from pathlib import Path

        from bmt_voice_studio.release_smoke import run_release_smoke

        report = None
        if "--report" in argv:
            i = argv.index("--report")
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith("-"):
                report = Path(argv[i + 1])
        setup_logging()
        return run_release_smoke(report)

    if "--project-restore-smoke" in argv:
        from pathlib import Path

        from bmt_voice_studio.video.packaged_smoke import run_project_restore_gui_smoke

        report = None
        if "--report" in argv:
            i = argv.index("--report")
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith("-"):
                report = Path(argv[i + 1])
        setup_logging()
        return run_project_restore_gui_smoke(report)

    if "--video-maker-smoke" in argv:
        from pathlib import Path

        from bmt_voice_studio.video.packaged_smoke import run_video_maker_smoke

        report = None
        if "--report" in argv:
            i = argv.index("--report")
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith("-"):
                report = Path(argv[i + 1])
        setup_logging()
        return run_video_maker_smoke(report)

    if "--video-maker-render-smoke" in argv:
        from pathlib import Path

        from bmt_voice_studio.video.packaged_smoke import run_video_maker_render_smoke

        report = None
        if "--report" in argv:
            i = argv.index("--report")
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith("-"):
                report = Path(argv[i + 1])
        setup_logging()
        return run_video_maker_render_smoke(report)

    if "--production-batch" in argv:
        setup_logging()
        from bmt_voice_studio.production_batch import run_production_batch

        return run_production_batch(argv)

    if "--daily-batch" in argv:
        setup_logging()
        from datetime import date
        from pathlib import Path

        from bmt_voice_studio.daily.pipeline import DailyJob, run_daily_job

        async def _run():
            i = argv.index("--daily-batch")
            inp = Path(argv[i + 1])
            out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else None
            d = date.fromisoformat(argv[argv.index("--date") + 1]) if "--date" in argv else date(2026, 8, 13)
            en = (inp / "BMT_13_AUG_2026_EN_TTS_READY.txt").read_text(encoding="utf-8")
            fr = (inp / "BMT_13_AUG_2026_FR_TTS_READY.txt").read_text(encoding="utf-8")
            job = DailyJob(
                date=d,
                english_text=en,
                french_text=fr,
                base_exports=out,
            )
            res = await run_daily_job(job)
            summary = {
                "status": res.status,
                "ok": res.ok,
                "folder": res.folder,
                "errors": res.errors,
                "english": res.english,
                "french": res.french,
                "report_md": res.report_md,
                "report_json": res.report_json,
            }
            report_path = (out or Path(res.folder or ".")) / "DAILY_BATCH_RESULT.json"
            if out:
                out.mkdir(parents=True, exist_ok=True)
            report_path.write_text(__import__("json").dumps(summary, indent=2, default=str), encoding="utf-8")
            print("DAILY_STATUS", res.status, res.folder)
            print("EN", bool(res.english and res.english.get("ok")), (res.english or {}).get("mp3_probe"))
            print("FR", bool(res.french and res.french.get("ok")), (res.french or {}).get("mp3_probe"))
            print("REPORT", report_path)
            return 0 if res.ok else 1

        import asyncio

        return asyncio.run(_run())

    setup_logging()
    # Registry IconResource + AppUserModelID must exist before any HWND.
    prepare_windows_taskbar_identity()
    # High-DPI is default on Qt6
    app = QApplication(argv)
    app.setApplicationName("BMT Voice Studio")
    app.setOrganizationName("BBNet")
    app.setOrganizationDomain("bbnet")
    from bmt_voice_studio import __version__ as _app_version

    app.setApplicationVersion(_app_version)
    icon = load_app_icon()
    if not icon.isNull():
        QApplication.setWindowIcon(icon)
        app.setWindowIcon(icon)
    settings = get_settings()
    apply_theme(app, settings.theme)
    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    apply_win32_hwnd_icon(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
