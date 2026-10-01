"""The request journal shown by the monitor: memory only, bounded, no bodies, no headers, no token.

Argument values are rendered by the tools as whitelisted scalars (rule ids, names, booleans, integers, enumeration
values); free text appears as "<text, N chars>", so nothing an agent wrote reaches the user's screen as text.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import Any

MAX_ENTRIES = 1000
FREE_TEXT_KEYS = frozenset({"comment", "author", "name", "query", "value", "title"})


@dataclass(frozen=True)
class Entry:
    seq: int
    time: str  # HH:MM:SS
    transport: str  # stdio | http
    client: str  # client name and version from initialize, cleaned
    method: str  # JSON-RPC method
    tool: str  # tool name or resource uri, or ""
    args: str  # whitelisted rendering of the arguments
    ok: bool
    ms: int
    note: str  # the program's short note: mode_required, window_busy, completed after timeout, ...


class Journal:
    def __init__(self, maxlen: int = MAX_ENTRIES) -> None:
        self._entries: deque[Entry] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0
        self.last_time = ""

    def append(self, transport: str, client: str, method: str, tool: str, args: str, ok: bool, ms: int, note: str = "") -> int:
        with self._lock:
            self._seq += 1
            entry = Entry(self._seq, time.strftime("%H:%M:%S"), transport, client, method, tool, args, ok, ms, note)
            self._entries.append(entry)
            self.last_time = entry.time
            return entry.seq

    def annotate(self, seq: int, note: str) -> None:
        """Add a note to an entry that already exists (a write that completed after the client gave up)."""
        with self._lock:
            for index, entry in enumerate(self._entries):
                if entry.seq == seq:
                    self._entries[index] = replace(entry, note=(entry.note + "; " if entry.note else "") + note)
                    return

    def since(self, seq: int) -> list[Entry]:
        with self._lock:
            return [entry for entry in self._entries if entry.seq > seq]

    def entries(self) -> list[Entry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return self._seq


_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
_SCALAR_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,60}$")
_URI_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,200}$")
_CLIENT_RE = re.compile(r"^[A-Za-z0-9 ._/()-]{1,60}$")


def render_args(arguments: dict[str, Any] | None, allowed: set[str] | None = None) -> str:
    """Whitelisted scalars of the arguments for the journal: identifier keys and values (ids, enumeration names,
    booleans, integers); free text, unknown keys and everything else only by kind and size, never as text."""
    if not arguments:
        return ""
    parts: list[str] = []
    for key, value in arguments.items():
        if not isinstance(key, str) or not _KEY_RE.match(key) or (allowed is not None and key not in allowed):
            parts.append(f"<unknown key, {len(str(key))} chars>")
            continue
        if isinstance(value, bool):
            parts.append(f"{key}={'true' if value else 'false'}")
        elif isinstance(value, int):
            parts.append(f"{key}={value}")
        elif isinstance(value, str):
            if key in FREE_TEXT_KEYS or not _SCALAR_RE.match(value):
                parts.append(f"{key}=<text, {len(value)} chars>")
            else:
                parts.append(f"{key}={value}")
        elif isinstance(value, list):
            parts.append(f"{key}=<list, {len(value)} items>")
        elif isinstance(value, dict):
            parts.append(f"{key}=<object>")
        else:
            parts.append(f"{key}=<{type(value).__name__}>")
        if len(parts) >= 20:
            parts.append("...")
            break
    return " ".join(parts)


def render_uri(uri: Any) -> str:
    """A resource URI for the journal: as it is when it is made of safe characters, else by size only."""
    return uri if isinstance(uri, str) and _URI_RE.match(uri) else f"<uri, {len(str(uri))} chars>"


def render_client(name: str, version: str) -> str:
    """The client name and version for the journal: identifier-like text only."""
    text = " ".join(part for part in (name, version) if part)
    return text if _CLIENT_RE.match(text) else (f"<client, {len(text)} chars>" if text else "")
