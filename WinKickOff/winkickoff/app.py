"""Application start-up: paths, logging, catalog, profile, main window."""

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

log = logging.getLogger(__name__)


def _enable_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness before Tk creates its first window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - older Windows builds lack shcore; nothing to do
        pass


def load_catalog_or_die(paths: AppPaths) -> Catalog:
    """Load the rules catalog; on error show the reason and exit with code 2."""
    try:
        return load_catalog(paths.data / "rules", docs_root=paths.docs_root)
    except CatalogError as exc:
        log.error("catalog error: %s", exc)
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, f"Каталог правил не загружен.\n\n{exc}")
        root.destroy()
        sys.exit(2)


def initial_profile(paths: AppPaths, catalog: Catalog) -> Profile:
    """The office preset if it exists next to the app, otherwise catalog defaults."""
    preset = paths.data / "profiles" / "preset-office.json"
    if preset.exists():
        profile, warnings = Profile.load(preset, catalog)
        for w in warnings:
            log.warning("preset-office.json: %s", w)
        profile.path = None
        return profile
    return Profile.from_catalog(catalog, name="Офис")


def create_app(*, withdraw: bool = False) -> tk.Tk:
    """Build the Tk application; withdraw=True keeps the window hidden (tests)."""
    _enable_dpi_awareness()
    paths = app_paths()
    setup_logging(paths)
    log.info("%s %s starting; root=%s data=%s", APP_NAME, APP_VERSION, paths.root, paths.data)
    catalog = load_catalog_or_die(paths)
    profile = initial_profile(paths, catalog)

    from winkickoff.ui.main_window import MainWindow  # imported late: tkinter only when needed

    root = MainWindow(paths, catalog, profile)
    if withdraw:
        root.withdraw()
    return root


def run() -> None:
    root = create_app()
    root.mainloop()
