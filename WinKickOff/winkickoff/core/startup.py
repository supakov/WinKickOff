"""The profile a session starts with: the last profile of the window, else the Office preset, else catalog defaults.

Shared by the window (app.py) and the headless MCP processes (mcp/cli.py); imports no tkinter.
"""

from __future__ import annotations

import logging

from winkickoff.core.catalog import Catalog
from winkickoff.core.i18n import tr
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.settings import Settings

log = logging.getLogger(__name__)
DEFAULT_PRESET = "preset-office.json"


def initial_profile(paths: AppPaths, catalog: Catalog, settings: Settings | None = None) -> Profile:
    """The profile open at the last exit, else the office preset, else catalog defaults."""
    if settings is not None and settings.last_profile:
        last = Settings.resolve(settings.last_profile, paths.root)
        if last.exists():
            try:
                profile, warnings = Profile.load(last, catalog)
                for warning in warnings:
                    log.warning("%s: %s", last.name, warning)
                return profile
            except (OSError, ValueError) as exc:
                log.error("last profile %s not loaded: %s", last, exc)
    preset = paths.data / "profiles" / DEFAULT_PRESET
    if preset.exists():
        try:
            profile, warnings = Profile.load(preset, catalog)
            for warning in warnings:
                log.warning("%s: %s", DEFAULT_PRESET, warning)
            return profile
        except (OSError, ValueError) as exc:
            log.error("%s not loaded: %s", DEFAULT_PRESET, exc)
    return Profile.from_catalog(catalog, name=tr("Office"))
