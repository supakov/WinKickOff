"""The command line of the MCP server: the headless stdio and HTTP servers, the client configuration, the version.

Imports nothing from winkickoff.app and nothing from tkinter, so `python -m winkickoff --mcp stdio` never loads Tk.
This is the only module of the package that prints (usage, --version, --mcp-config), through emit().
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from winkickoff import APP_NAME, APP_VERSION
from winkickoff.core.settings import TOKEN_RE, valid_port
from winkickoff.mcp import MODE_READ, MODES

log = logging.getLogger("winkickoff.mcp.cli")
HEADLESS_FLAGS = ("--mcp", "--mcp-config", "--version")
LOG_KEEP_DAYS = 7


def parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    """Parsed arguments and the unknown extras; extras are an error only with --mcp or --mcp-config."""
    parser = argparse.ArgumentParser(prog=APP_NAME, allow_abbrev=False, add_help=True,
                                     description="WinKickOff editor; with --mcp a headless MCP server")
    parser.add_argument("--mcp", choices=("stdio", "http"), help="run the MCP server without a window")
    parser.add_argument("--port", type=int, help="port for --mcp http (0 or 1024-65535; default: the settings)")
    parser.add_argument("--token", help="bearer token for --mcp http (default: the token saved by the window)")
    parser.add_argument("--mode", choices=MODES, default=MODE_READ, help="read (default), edit or files")
    parser.add_argument("--read-pc", action="store_true",
                        help="allow the tool read_this_pc to read the settings of this computer (read only)")
    parser.add_argument("--profile", help="a preset id (office, strict, laptop, home), a saved profile name or a path")
    parser.add_argument("--language", help="language of the texts (en, ru, uk); default: the settings, then Windows")
    parser.add_argument("--mcp-config", choices=("stdio", "http"), help="print the client configuration and exit")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    args, extras = parser.parse_known_args(argv)
    if extras and (args.mcp or args.mcp_config):
        parser.error("unrecognized arguments: " + " ".join(extras))
    if args.port is not None and not valid_port(args.port):
        parser.error("--port must be 0 or 1024-65535")
    if args.token is not None and not TOKEN_RE.fullmatch(args.token):
        parser.error("--token must be 32 to 64 characters of A-Z, a-z, 0-9, _ and -")
    return args, extras


def is_headless(argv: list[str]) -> bool:
    return any(item in HEADLESS_FLAGS or item.startswith("--mcp=") or item.startswith("--mcp-config=") for item in argv)


def emit(text: str) -> bool:
    """Print to stdout when there is one; a process without a console logs one line and returns False."""
    stdout = getattr(sys, "stdout", None)
    if stdout is None:
        log.error("no console: use python.exe or WinKickOff-mcp.exe for this flag")
        return False
    stdout.write(text + ("" if text.endswith("\n") else "\n"))
    stdout.flush()
    return True


def housekeep_logs(logs: Path, now: float | None = None) -> None:
    """Remove this program's headless log files older than LOG_KEEP_DAYS (mcp-*.log and their rollovers)."""
    now = time.time() if now is None else now
    try:
        candidates = list(logs.glob("mcp-*.log*"))
    except OSError:
        return
    for path in candidates:
        try:
            if now - path.stat().st_mtime > LOG_KEEP_DAYS * 86400:
                path.unlink()
        except OSError:
            continue


def run_headless(args: argparse.Namespace) -> int:
    """--version, --mcp-config, --mcp stdio or --mcp http; returns the exit code."""
    if args.version:
        return 0 if emit(f"{APP_NAME} {APP_VERSION}") else 3
    from winkickoff.core.paths import app_paths

    paths = app_paths()
    if args.mcp_config:
        from winkickoff.core.settings import Settings
        from winkickoff.mcp.service import client_config

        settings = Settings.load(paths.settings_file)
        text = client_config(args.mcp_config, paths=paths, port=args.port if args.port is not None else settings.mcp_port,
                             token=args.token or settings.mcp_token, mode=args.mode)
        return 0 if emit(text) else 3
    from winkickoff.core.log import setup_logging

    setup_logging(paths, filename=f"mcp-{args.mcp}-{os.getpid()}.log", delay=True)
    logging.captureWarnings(True)
    housekeep_logs(paths.logs)
    try:
        prepared = prepare(paths, args)
    except StartupError as exc:
        log.error("start-up failed: %s", exc)
        return 2
    if args.mcp == "stdio":
        return serve_stdio_process(prepared)
    return serve_http_process(prepared, args)


class StartupError(RuntimeError):
    pass


def prepare(paths: Any, args: argparse.Namespace) -> dict[str, Any]:
    """Catalog, imports, resources, profile and the server objects of a headless process (no tkinter)."""
    from winkickoff.core.admx import with_imports
    from winkickoff.core.catalog import CatalogError, load_catalog
    from winkickoff.core.i18n import language, set_language
    from winkickoff.core.profile import Profile
    from winkickoff.core.resources import Resources
    from winkickoff.core.settings import Settings
    from winkickoff.core.startup import initial_profile
    from winkickoff.mcp.bridge import InlineBridge
    from winkickoff.mcp.service import McpService
    from winkickoff.mcp.workspace import HeadlessWorkspace, profile_file

    settings = Settings.load(paths.settings_file)  # read only: a headless process never writes settings
    set_language(args.language or settings.language, paths.resources, paths.rules)
    try:
        catalog = load_catalog(paths.rules, docs_root=paths.docs_root)
    except CatalogError as exc:
        raise StartupError(f"catalog: {exc}") from exc
    catalog, problems = with_imports(catalog, paths.admx, settings.admx, language())
    for problem in problems:
        log.warning("%s", problem)
    try:
        resources = Resources.load(paths.resources)
    except (OSError, ValueError) as exc:
        raise StartupError(f"resources: {exc}") from exc
    if args.profile:
        wanted = str(args.profile)
        path = Path(wanted) if Path(wanted).is_absolute() else None
        if path is None:
            try:
                path = profile_file(paths, wanted)
            except Exception as exc:  # noqa: BLE001 - a refused name is a start-up error
                raise StartupError(f"profile name refused: {exc}") from exc
        try:
            profile, warnings = Profile.load(path, catalog)
        except (OSError, ValueError) as exc:
            raise StartupError(f"profile {wanted}: {type(exc).__name__}: {exc}") from exc
        for warning in warnings:
            log.warning("%s: %s", path.name, warning)
    else:
        profile = initial_profile(paths, catalog, settings)
    service = McpService()
    service.configure(paths, settings)  # no save callback: nothing is ever written
    service.set_mode(args.mode)
    service.set_read_pc(args.read_pc)
    workspace = HeadlessWorkspace(paths, catalog, profile, resources, APP_VERSION)
    service.bridge = InlineBridge(workspace)
    return {"paths": paths, "settings": settings, "service": service, "workspace": workspace}


def serve_stdio_process(prepared: dict[str, Any]) -> int:
    from winkickoff.mcp.protocol import Session
    from winkickoff.mcp.stdio import open_std_streams, serve_stdio

    streams = open_std_streams()
    if streams is None:
        log.error("no standard streams: start the stdio server from python.exe or WinKickOff-mcp.exe")
        return 3
    service = prepared["service"]
    server = service.build_server("stdio", has_window=False)
    log.info("mcp stdio server started, mode %s, profile %s", service.mode, prepared["workspace"].profile.name)
    reader, writer = streams
    return serve_stdio(reader, writer, server, Session("stdio", "stdio"))


def serve_http_process(prepared: dict[str, Any], args: argparse.Namespace) -> int:
    from winkickoff.mcp.httpserver import serve, start_http

    settings, service = prepared["settings"], prepared["service"]
    token = args.token or settings.mcp_token
    if not TOKEN_RE.fullmatch(token or ""):
        log.error("no access token: start the server once from the window or pass --token")
        emit("no access token: start the server once from the window or pass --token")
        return 2
    server = service.build_server("http", has_window=False)
    try:
        httpd = start_http(args.port if args.port is not None else settings.mcp_port, token, server)
    except OSError as exc:
        log.error("bind failed: %s", exc)
        emit(f"the port is not available: {exc}")
        return 2
    emit(f"MCP server on http://127.0.0.1:{httpd.port}/mcp, mode {service.mode}; Ctrl+C stops it")
    try:
        serve(httpd)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry of the console executable WinKickOff-mcp.exe: a stdio server unless another flag is given."""
    raw = sys.argv[1:] if argv is None else list(argv)
    if not is_headless(raw):
        raw = ["--mcp", "stdio", *raw]
    try:
        args, _extras = parse_args(raw)
    except SystemExit as exc:
        return int(exc.code or 0) if isinstance(exc.code, int) else 2
    return run_headless(args)
