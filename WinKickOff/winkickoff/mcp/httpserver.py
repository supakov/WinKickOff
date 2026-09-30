"""The Streamable HTTP transport on 127.0.0.1: one endpoint, JSON answers, bearer token, strict sessions.

This is the only module of the package that imports http.server and names from socket: a loopback listener, off by
default and started by the user (task T22). Every response carries Content-Length and Connection: close, so a
handler thread lives for one request and shutdown() returns within the poll interval.
"""

from __future__ import annotations

import hmac
import logging
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socket import SOL_SOCKET
from typing import Any

from winkickoff.mcp import DRAIN_LIMIT, ENDPOINT, HEADER_VERSIONS, MAX_CONCURRENT, MAX_MESSAGE_BYTES, MAX_SESSIONS
from winkickoff.mcp.jsonrpc import INVALID_REQUEST, JsonRpcError, dumps, error_response, is_request, parse_message
from winkickoff.mcp.protocol import McpServer, Session

log = logging.getLogger("winkickoff.mcp.http")
HOST = "127.0.0.1"
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
SESSION_HEADER = "Mcp-Session-Id"


class McpHttpServer(ThreadingHTTPServer):
    allow_reuse_address = False
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, port: int, token: str, server: McpServer) -> None:
        self.token = token
        self.mcp = server
        self.sessions: dict[str, Session] = {}
        self.sessions_lock = threading.Lock()
        self.slots = threading.BoundedSemaphore(MAX_CONCURRENT)
        self.serving = threading.Event()  # set by the serving thread before serve_forever
        super().__init__((HOST, port), McpHandler)

    def server_bind(self) -> None:
        if sys.platform == "win32":
            from socket import SO_EXCLUSIVEADDRUSE  # keeps another process of the same user from taking the port

            self.socket.setsockopt(SOL_SOCKET, SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    def new_session(self) -> Session:
        session = Session(secrets.token_urlsafe(24), "http")
        with self.sessions_lock:
            while len(self.sessions) >= MAX_SESSIONS:
                oldest = min(self.sessions.values(), key=lambda s: s.last_seen)
                del self.sessions[oldest.id]
            self.sessions[session.id] = session
        return session

    def session(self, session_id: str) -> Session | None:
        with self.sessions_lock:
            return self.sessions.get(session_id)

    def end_session(self, session_id: str) -> bool:
        with self.sessions_lock:
            return self.sessions.pop(session_id, None) is not None


class McpHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "WinKickOff"
    sys_version = ""
    timeout = 30
    server: McpHttpServer  # type: ignore[assignment]

    # ----------------------------------------------------------------- logging

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the signature of the base class
        log.debug("%s %s", self.address_string(), format % args)

    def log_error(self, format: str, *args: Any) -> None:  # noqa: A002
        log.debug("%s %s", self.address_string(), format % args)

    # ----------------------------------------------------------------- responses

    def version_string(self) -> str:
        return self.server_version

    def _drain(self) -> None:
        """Read and discard an unread request body before an early answer: closing a socket with unread bytes makes
        Windows send a reset and the client loses the status code."""
        if getattr(self, "_consumed", False) or self.command not in ("POST", "PUT", "PATCH"):
            return
        self._consumed = True
        try:
            remaining = min(int(self.headers.get("Content-Length") or 0), DRAIN_LIMIT)
        except ValueError:
            return
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _reply(self, status: int, body: bytes = b"", content_type: str | None = None, extra: dict[str, str] | None = None) -> None:
        self._drain()
        self.close_connection = True
        self.send_response(status)
        if body:
            self.send_header("Content-Type", content_type or "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, obj: dict[str, Any], extra: dict[str, str] | None = None) -> None:
        self._reply(status, dumps(obj), "application/json; charset=utf-8", extra)

    # ----------------------------------------------------------------- checks

    def _checks(self) -> bool:
        """Host, Origin, token, path, protocol version; a failing check answers and returns False."""
        port = self.server.port
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in {f"{name}:{port}" for name in ALLOWED_HOSTS}:
            self._reply(421)
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin.strip().lower() not in {f"http://{name}:{port}" for name in ALLOWED_HOSTS}:
            self._reply(403)
            return False
        auth = self.headers.get("Authorization") or ""
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(token.strip().encode(), self.server.token.encode()):
            self._reply(401)
            return False
        if self.path != ENDPOINT:
            self._reply(404)
            return False
        version = self.headers.get("MCP-Protocol-Version")
        if version is not None and version.strip() not in HEADER_VERSIONS:
            self._reply(400)
            return False
        return True

    def _body(self) -> bytes | None:
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length") is None:
            self._reply(411)
            return None
        try:
            length = int(self.headers["Content-Length"])
        except ValueError:
            self._reply(400)
            return None
        if length > MAX_MESSAGE_BYTES:
            self._reply(413)  # _reply drains up to DRAIN_LIMIT first, so the client sees the status, not a reset
            return None
        content_type = (self.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("application/json"):
            self._reply(415)
            return None
        accept = (self.headers.get("Accept") or "*/*").lower()
        if "application/json" not in accept and "*/*" not in accept:
            self._reply(406)
            return None
        self._consumed = True
        return self.rfile.read(length)

    # ----------------------------------------------------------------- methods

    def do_POST(self) -> None:  # noqa: N802 - the naming of the base class
        if not self._checks():
            return
        if not self.server.slots.acquire(blocking=False):
            self._reply(503, extra={"Retry-After": "1"})
            return
        try:
            body = self._body()
            if body is None:
                return
            try:
                message = parse_message(body)
            except JsonRpcError as exc:
                self._json(400, exc.response())
                return
            self._dispatch(message)
        finally:
            self.server.slots.release()

    def _dispatch(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        session_id = (self.headers.get(SESSION_HEADER) or "").strip()
        extra: dict[str, str] = {}
        if is_request(message) and method == "initialize":
            session = self.server.new_session()
            extra[SESSION_HEADER] = session.id
        elif is_request(message) and method == "ping" and not session_id:
            session = Session("", "http")
        else:
            if not session_id:
                self._json(400, error_response(message.get("id"), INVALID_REQUEST, "Mcp-Session-Id header required"))
                return
            found = self.server.session(session_id)
            if found is None:
                self._reply(404)
                return
            session = found
        reply = self.server.mcp.handle(message, session)
        if reply is None:
            self._reply(202, extra=extra)
        else:
            self._json(200, reply, extra)

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._checks():
            return
        session_id = (self.headers.get(SESSION_HEADER) or "").strip()
        if session_id and self.server.end_session(session_id):
            self._reply(204)
        else:
            self._reply(404)

    def do_GET(self) -> None:  # noqa: N802
        if self._checks():
            self._reply(405, extra={"Allow": "POST, DELETE"})

    def do_HEAD(self) -> None:  # noqa: N802
        if self._checks():
            self._reply(405, extra={"Allow": "POST, DELETE"})

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._checks():
            self._reply(405, extra={"Allow": "POST, DELETE"})

    do_PUT = do_PATCH = do_OPTIONS


def start_http(port: int, token: str, server: McpServer) -> McpHttpServer:
    """Bind ("127.0.0.1", port); port 0 takes any free port, read back from httpd.port. Raises OSError."""
    return McpHttpServer(port, token, server)


def serve(httpd: McpHttpServer) -> None:
    """The body of the serving thread."""
    httpd.serving.set()
    try:
        httpd.serve_forever(poll_interval=0.5)
    finally:
        httpd.serving.clear()
