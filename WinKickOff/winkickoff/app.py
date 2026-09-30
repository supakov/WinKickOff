"""Application start-up: paths, logging, catalog, reference data, profile, main window."""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from tkinter import messagebox

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Catalog, CatalogError, load_catalog
from winkickoff.core.admx import with_imports
from winkickoff.core.i18n import language, set_language, tr
from winkickoff.core.log import setup_logging
from winkickoff.core.paths import AppPaths, app_paths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings

log = logging.getLogger(__name__)
DEFAULT_PRESET = "preset-office.json"


def _enable_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness before Tk creates its first window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - older Windows builds lack shcore; nothing to do
        pass


def _fatal(message: str) -> None:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(APP_NAME, message)
    root.destroy()
    sys.exit(2)


def load_catalog_or_die(paths: AppPaths) -> Catalog:
    """Load the rules catalog; on error show the reason and exit with code 2."""
    try:
        return load_catalog(paths.rules, docs_root=paths.docs_root)
    except CatalogError as exc:
        log.error("catalog error: %s", exc)
        _fatal(tr("The rule catalog was not loaded.\n\n{0}", exc))
        raise  # unreachable, keeps type checkers calm


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


def create_app(*, withdraw: bool = False, state: dict[str, object] | None = None) -> tk.Tk:
    """Build the Tk application; withdraw=True keeps the window hidden (tests).
    state carries the open profile across a restart of the window (language, theme or templates changed)."""
    _enable_dpi_awareness()
    paths = app_paths()
    setup_logging(paths)
    log.info("%s %s starting; root=%s data=%s", APP_NAME, APP_VERSION, paths.root, paths.data)
    catalog = load_catalog_or_die(paths)
    try:
        resources = Resources.load(paths.resources)
    except (OSError, ValueError) as exc:
        _fatal(tr("Reference data was not loaded.\n\n{0}", exc))
        raise
    settings = Settings.load(paths.settings_file)
    set_language(settings.language, paths.resources, paths.rules)
    catalog, problems = with_imports(catalog, paths.admx, settings.admx, language())  # texts from ADML, in this language
    for problem in problems:
        log.warning("%s", problem)
    if state:
        profile, warnings = state["profile"].rebind(catalog)  # type: ignore[attr-defined]
        for warning in warnings:
            log.info("profile after a restart: %s", warning)
    else:
        profile = initial_profile(paths, catalog, settings)

    from winkickoff.ui.main_window import MainWindow  # imported late: tkinter window only when needed

    root = MainWindow(paths, catalog, profile, resources, settings)  # type: ignore[arg-type]
    if state:
        root.restore_state(state)
    if problems:
        root.show_problems(problems)
    if withdraw:
        root.withdraw()
    return root


def run() -> None:
    """Run the window; a change of the language, theme or loaded templates closes it and a new one opens with the
    same profile."""
    state = None
    while True:
        root = create_app(state=state)
        root.mainloop()
        state = getattr(root, "restart_state", None)
        if not state:
            break
