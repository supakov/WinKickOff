"""Logging into logs/winkickoff.log next to the executable (1 MB, three files).

A headless MCP process logs into its own file (logs/mcp-stdio-<pid>.log), because two processes writing one
RotatingFileHandler target lose records on Windows when the rollover renames a file another process holds open.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from winkickoff.core.paths import AppPaths

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(paths: AppPaths, level: int = logging.INFO, filename: str = "winkickoff.log", *, delay: bool = False) -> None:
    """One rotating file handler on the root logger; delay=True opens the file at the first record."""
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    root.setLevel(level)
    handler = RotatingFileHandler(
        paths.logs / filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8", delay=delay
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root.addHandler(handler)
