"""Errors of tool execution: they become tool results with isError true, never JSON-RPC errors."""

from __future__ import annotations

from typing import Any


class ToolError(Exception):
    """A refusal or failure of a tool, with a kind the client can act on and optional structured data."""

    def __init__(self, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.data = dict(data or {})

    def structured(self) -> dict[str, Any]:
        return {"error": self.kind, "message": self.message, **self.data}


class RedactionError(ToolError):
    """A build still holds a secret after redaction: the text is never returned."""

    def __init__(self, message: str) -> None:
        super().__init__("redaction_failed", message)
