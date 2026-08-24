"""Application logging setup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from bmt_voice_studio.config.paths import logs_dir


def setup_logging() -> None:
    log_file = logs_dir() / "app.log"
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(fh)
    root.addHandler(sh)
