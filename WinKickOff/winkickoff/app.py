"""Application start-up: paths, logging, catalog, reference data, profile, main window."""

from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from tkinter import messagebox

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.catalog import Catalog, CatalogError, load_catalog
from winkickoff.core.log import setup_logging
from winkickoff.core.paths import AppPaths, app_paths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources

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
        _fatal(f"Каталог правил не загружен.\n\n{exc}")
        raise  # unreachable, keeps type checkers calm


def initial_profile(paths: AppPaths, catalog: Catalog) -> Profile:
    """The office preset if it ships with the application, otherwise catalog defaults."""
    preset = paths.data / "profiles" / DEFAULT_PRESET
    if preset.exists():
        try:
            profile, warnings = Profile.load(preset, catalog)
            for warning in warnings:
                log.warning("%s: %s", DEFAULT_PRESET, warning)
            return profile
        except (OSError, ValueError) as exc:
            log.error("%s not loaded: %s", DEFAULT_PRESET, exc)
    return Profile.from_catalog(catalog, name="Офис")


def create_app(*, withdraw: bool = False) -> tk.Tk:
    """Build the Tk application; withdraw=True keeps the window hidden (tests)."""
    _enable_dpi_awareness()
    paths = app_paths()
    setup_logging(paths)
    log.info("%s %s starting; root=%s data=%s", APP_NAME, APP_VERSION, paths.root, paths.data)
    catalog = load_catalog_or_die(paths)
    try:
        resources = Resources.load(paths.resources)
    except (OSError, ValueError) as exc:
        _fatal(f"Справочники не загружены.\n\n{exc}")
        raise
    profile = initial_profile(paths, catalog)

    from winkickoff.ui.main_window import MainWindow  # imported late: tkinter window only when needed

    root = MainWindow(paths, catalog, profile, resources)
    if withdraw:
        root.withdraw()
    return root


def run() -> None:
    root = create_app()
    root.mainloop()
