"""Application start-up: paths, logging, catalog, reference data, profile, main window, the MCP service."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
import tkinter as tk
from tkinter import messagebox

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.admx import with_imports
from winkickoff.core.catalog import Catalog, CatalogError, load_catalog
from winkickoff.core.i18n import language, set_language, tr
from winkickoff.core.log import setup_logging
from winkickoff.core.paths import AppPaths, app_paths
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings
from winkickoff.core.startup import DEFAULT_PRESET, initial_profile  # noqa: F401 - re-exported for the tests
from winkickoff.mcp.service import McpService

log = logging.getLogger(__name__)


def _enable_dpi_awareness() -> None:
    """Ask Windows for per-monitor DPI awareness before Tk creates its first window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001 - older Windows builds lack shcore; nothing to do
        pass


def fatal(message: str) -> None:
    """Show a message in a box (a windowed process has no console) and exit with code 2."""
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(APP_NAME, message)
    root.destroy()
    sys.exit(2)


_fatal = fatal  # the former name, kept for the tests


def load_catalog_or_die(paths: AppPaths) -> Catalog:
    """Load the rules catalog; on error show the reason and exit with code 2."""
    try:
        return load_catalog(paths.rules, docs_root=paths.docs_root)
    except CatalogError as exc:
        log.error("catalog error: %s", exc)
        fatal(tr("The rule catalog was not loaded.\n\n{0}", exc))
        raise  # unreachable, keeps type checkers calm


def create_app(*, withdraw: bool = False, state: dict[str, object] | None = None,
               service: McpService | None = None) -> tk.Tk:
    """Build the Tk application; withdraw=True keeps the window hidden (tests).
    state carries the open profile across a restart of the window (language, theme or templates changed).
    service is the MCP service of the process; without it the window is inert for MCP (tests)."""
    _enable_dpi_awareness()
    paths = app_paths()
    setup_logging(paths)
    log.info("%s %s starting; root=%s data=%s", APP_NAME, APP_VERSION, paths.root, paths.data)
    catalog = load_catalog_or_die(paths)
    try:
        resources = Resources.load(paths.resources)
    except (OSError, ValueError) as exc:
        fatal(tr("Reference data was not loaded.\n\n{0}", exc))
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

    if service is not None:
        service.configure(paths, settings)
    root = MainWindow(paths, catalog, profile, resources, settings, service=service)  # type: ignore[arg-type]
    if service is not None:
        service.on_save = root.save_settings  # the window's settings object is the only writer of settings.json
        if settings.mcp_autostart and not service.running:
            service.set_mode("read")
            try:
                service.start_http()
            except OSError as exc:
                problems.append(tr("The MCP server did not start: port {0} is used by another program. Clients configured for this "
                                   "port may already have sent the access token to that program. Choose another port in the "
                                   "monitor and generate a new access token (MCP menu).", settings.mcp_port))
                log.error("mcp autostart failed: %s", exc)
        root.refresh_mcp_status()
    if state:
        root.restore_state(state)
    if problems:
        root.show_problems(problems)
    if withdraw:
        root.withdraw()
    return root


def run(args: argparse.Namespace | None = None, extras: list[str] | None = None) -> None:
    """Run the window; a change of the language, theme or loaded templates closes it and a new one opens with the
    same profile. The MCP service outlives every window and stops when the last one closes."""
    if args is None:  # the console script entry of pyproject.toml: parse here, headless flags included
        from winkickoff.mcp.cli import parse_args, run_headless

        args, extras = parse_args(sys.argv[1:])
        if args.mcp or args.mcp_config or args.version:
            sys.exit(run_headless(args))
    if extras:
        log.info("ignored arguments: %s", extras)
    service = McpService()
    state = None
    try:
        while True:
            root = create_app(state=state, service=service)
            root.mainloop()
            state = getattr(root, "restart_state", None)
            if not state:
                break
    finally:
        service.stop(join_timeout=3.0)
