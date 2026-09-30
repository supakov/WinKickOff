"""MCP server (Model Context Protocol) of WinKickOff: constants shared by the transports, the protocol core and the UI.

The package imports nothing from winkickoff.ui and never imports tkinter (tests/test_sources.py checks it). Only
mcp/httpserver.py may import http.server, socketserver and names from socket: it is the loopback listener, off by
default and started by the user (task T22).
"""

from __future__ import annotations

PROTOCOL_VERSION = "2025-06-18"
SUPPORTED_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18")  # versions the server echoes in initialize
HEADER_VERSIONS = SUPPORTED_VERSIONS + ("2025-11-25",)  # accepted in the MCP-Protocol-Version header
SERVER_NAME = "winkickoff"
ENDPOINT = "/mcp"
DEFAULT_PORT = 47831

MODES = ("read", "edit", "files")  # ordered: every mode includes the previous one
MODE_READ, MODE_EDIT, MODE_FILES = MODES

MAX_MESSAGE_BYTES = 1_000_000  # one stdio line or one HTTP body
DRAIN_LIMIT = 4_000_000  # bytes of an oversized HTTP body read and discarded before the 413
BRIDGE_TIMEOUT = 5.0  # seconds a read call waits for the window
WRITE_TIMEOUT = 30.0  # seconds a write call waits for the window
MAX_RESULT_BYTES = 200_000  # a larger tool or resource result becomes result_too_large
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_CONCURRENT = 4  # HTTP requests handled at once; more get 503
MAX_SESSIONS = 16
MAX_DOC_BYTES = 65_536  # a documentation resource is cut at this size
TOKEN_RE_TEXT = r"^[A-Za-z0-9_-]{32,64}$"


def allows(current: str, required: str) -> bool:
    """Whether the current mode includes the required one."""
    return current in MODES and required in MODES and MODES.index(current) >= MODES.index(required)
