"""Logging into logs/winkickoff.log next to the executable (1 MB, three files)."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from winkickoff.core.paths import AppPaths

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(paths: AppPaths, level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(level)
    handler = RotatingFileHandler(
        paths.logs / "winkickoff.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
