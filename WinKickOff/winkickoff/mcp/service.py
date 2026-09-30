"""The MCP service of a process: the mode, the HTTP server and its thread, the bridge, the journal, the token.

One instance per process. The window's Settings object is the only writer of settings.json: the service holds a
reference to it and a save callback, generates the token through them on the main thread and never writes the file
itself. A headless process (mcp/cli.py) never calls configure with a save callback and never writes the token.
"""

from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from winkickoff import APP_VERSION
from winkickoff.core.i18n import available_languages
from winkickoff.core.paths import AppPaths
from winkickoff.core.settings import TOKEN_RE, Settings
from winkickoff.mcp import ENDPOINT, MODE_READ, MODES
from winkickoff.mcp.bridge import Bridge
from winkickoff.mcp.httpserver import HOST, McpHttpServer, serve, start_http
from winkickoff.mcp.journal import Journal
from winkickoff.mcp.protocol import McpServer
from winkickoff.mcp.resources import ResourceRegistry
from winkickoff.mcp.tools import ToolRegistry
from winkickoff.mcp.workspace import Workspace

log = logging.getLogger("winkickoff.mcp")
STDIO_EXE = "WinKickOff-mcp.exe"


@dataclass(frozen=True)
class ServiceStatus:
    running: bool
    port: int
    mode: str
    requests: int
    last_time: str
    sessions: int
    url: str


def new_token() -> str:
    return secrets.token_urlsafe(32)


class McpService:
    def __init__(self) -> None:
        self.mode = MODE_READ
        self.bridge = Bridge()
        self.journal = Journal()
        self.paths: AppPaths | None = None
        self.settings: Settings | None = None
        self.on_save: Callable[[], None] | None = None
        self.httpd: McpHttpServer | None = None
        self.thread: threading.Thread | None = None
        self.server: McpServer | None = None
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- configuration

    def configure(self, paths: AppPaths, settings: Settings, on_save: Callable[[], None] | None = None) -> None:
        """The live settings object of the window and its save method; called again after every window rebuild."""
        self.paths = paths
        self.settings = settings
        self.on_save = on_save

    def attach(self, workspace: Workspace) -> None:
        self.bridge.attach(workspace)

    def detach(self) -> None:
        self.bridge.detach()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(mode)
        self.mode = mode
        log.info("mcp mode: %s", mode)

    @property
    def running(self) -> bool:
        return self.httpd is not None and self.thread is not None and self.thread.is_alive()

    @property
    def token(self) -> str:
        return self.settings.mcp_token if self.settings is not None else ""

    def ensure_token(self) -> str:
        """The token of the settings, generated and saved through the window when missing (main thread only)."""
        if self.settings is None:
            raise RuntimeError("the service is not configured")
        if not TOKEN_RE.fullmatch(self.settings.mcp_token or ""):
            self.settings.mcp_token = new_token()
            if self.on_save is not None:
                self.on_save()
        return self.settings.mcp_token

    def rotate_token(self) -> str:
        """A new token; a running server stops, because its clients hold the old one."""
        if self.settings is None:
            raise RuntimeError("the service is not configured")
        self.stop()
        self.settings.mcp_token = new_token()
        if self.on_save is not None:
            self.on_save()
        return self.settings.mcp_token

    # ----------------------------------------------------------------- server

    def build_server(self, transport: str, has_window: bool) -> McpServer:
        if self.paths is None:
            raise RuntimeError("the service is not configured")
        languages = tuple(available_languages(self.paths.resources, self.paths.rules))
        tools = ToolRegistry(self.paths, languages)
        resources = ResourceRegistry(self.paths, languages)
        return McpServer(tools, resources, self.bridge, self.journal, transport=transport, mode=lambda: self.mode,
                         has_window=has_window)

    def start_http(self, port: int | None = None, *, has_window: bool = True) -> int:
        """Start the HTTP server on 127.0.0.1; returns the bound port. Raises OSError when the port is taken."""
        with self._lock:
            if self.running:
                return self.httpd.port  # type: ignore[union-attr]
            if self.settings is None or self.paths is None:
                raise RuntimeError("the service is not configured")
            token = self.ensure_token()
            self.server = self.build_server("http", has_window)
            httpd = start_http(self.settings.mcp_port if port is None else port, token, self.server)
            thread = threading.Thread(target=serve, args=(httpd,), name="mcp-http", daemon=True)
            self.httpd, self.thread = httpd, thread
            thread.start()
            log.info("mcp http server started on %s:%d, mode %s", HOST, httpd.port, self.mode)
            return httpd.port

    def stop(self, join_timeout: float = 3.0) -> None:
        with self._lock:
            httpd, thread = self.httpd, self.thread
            self.httpd, self.thread = None, None
        if httpd is None:
            return
        if thread is not None and thread.is_alive() and httpd.serving.is_set():
            httpd.shutdown()  # only when serve_forever runs: otherwise shutdown() would wait forever
        httpd.server_close()
        if thread is not None and thread.is_alive():
            thread.join(join_timeout)
        self.bridge.fail_all(RuntimeError("server stopped"))
        log.info("mcp http server stopped")

    def status(self) -> ServiceStatus:
        httpd = self.httpd
        running = self.running
        port = httpd.port if httpd is not None and running else (self.settings.mcp_port if self.settings else 0)
        sessions = len(httpd.sessions) if httpd is not None and running else 0
        url = f"http://{HOST}:{port}{ENDPOINT}" if running else ""
        return ServiceStatus(running, port, self.mode, self.journal.count, self.journal.last_time, sessions, url)

    # ----------------------------------------------------------------- client configuration

    def client_config(self, kind: str) -> str:
        if self.paths is None or self.settings is None:
            raise RuntimeError("the service is not configured")
        port = self.httpd.port if self.httpd is not None and self.running else self.settings.mcp_port
        return client_config(kind, paths=self.paths, port=port, token=self.token, mode=self.mode)


def client_config(kind: str, *, paths: AppPaths, port: int, token: str, mode: str = MODE_READ) -> str:
    """The mcpServers entry for Claude Code or Claude Desktop, as JSON text."""
    if kind == "http":
        entry = {"type": "http", "url": f"http://{HOST}:{port}{ENDPOINT}", "headers": {"Authorization": f"Bearer {token}"}}
    else:
        args = ["--mode", "edit"] if mode != MODE_READ else []
        if getattr(sys, "frozen", False):
            entry = {"command": str(Path(sys.executable).resolve().parent / STDIO_EXE), "args": args}
        else:
            python = Path(sys.executable)
            if python.name.lower() == "pythonw.exe":
                python = python.with_name("python.exe")
            entry = {"command": str(python), "args": ["-m", "winkickoff", "--mcp", "stdio", *args],
                     "env": {"PYTHONPATH": str(paths.root)}}
    return json.dumps({"mcpServers": {"winkickoff": entry}}, ensure_ascii=False, indent=2)
