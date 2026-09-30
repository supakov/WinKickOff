"""The request journal shown by the monitor: memory only, bounded, no bodies, no headers, no token.

Argument values are rendered by the tools as whitelisted scalars (rule ids, names, booleans, integers, enumeration
values); free text appears as "<text, N chars>", so nothing an agent wrote reaches the user's screen as text.
"""

from __future__ import annotations

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


def render_args(arguments: dict[str, Any] | None) -> str:
    """Whitelisted scalars of the arguments for the journal: ids, names of enumerations, booleans, integers; free
    text and everything else only by kind and size."""
    if not arguments:
        return ""
    parts: list[str] = []
    for key, value in arguments.items():
        if isinstance(value, bool):
            parts.append(f"{key}={'true' if value else 'false'}")
        elif isinstance(value, int):
            parts.append(f"{key}={value}")
        elif isinstance(value, str):
            if key in FREE_TEXT_KEYS or len(value) > 60 or any(ch.isspace() for ch in value):
                parts.append(f"{key}=<text, {len(value)} chars>")
            else:
                parts.append(f"{key}={value}")
        elif isinstance(value, list):
            parts.append(f"{key}=<list, {len(value)} items>")
        elif isinstance(value, dict):
            parts.append(f"{key}=<object>")
        else:
            parts.append(f"{key}=<{type(value).__name__}>")
    return " ".join(parts)
