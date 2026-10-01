"""JSON-RPC 2.0 messages as MCP uses them: one object per message, string or integer ids, no batches."""

from __future__ import annotations

import json
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002


class JsonRpcError(Exception):
    """An error response to build: code, message, optional data, and the id of the request when known.
    silent marks a malformed notification: JSON-RPC forbids answering a notification, so transports drop it."""

    def __init__(self, code: int, message: str, data: Any = None, request_id: Any = None, silent: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data
        self.request_id = request_id
        self.silent = silent

    def response(self) -> dict[str, Any]:
        return error_response(self.request_id, self.code, self.message, self.data)


def parse_message(raw: bytes | str) -> dict[str, Any]:
    """One JSON-RPC message (request, notification or response) from text or UTF-8 bytes.

    Raises JsonRpcError: PARSE_ERROR for bad UTF-8 or JSON, INVALID_REQUEST for an array (batches were removed in
    MCP 2025-06-18), a non-object, a wrong "jsonrpc" value, a null, boolean or fractional id, or a non-string method;
    INVALID_PARAMS when params is present and not an object.
    """
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        message = json.loads(text, parse_constant=_refuse_constant)  # NaN and Infinity are not JSON
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise JsonRpcError(PARSE_ERROR, "parse error: " + type(exc).__name__) from exc
    if isinstance(message, list):
        raise JsonRpcError(INVALID_REQUEST, "batches are not supported")
    if not isinstance(message, dict):
        raise JsonRpcError(INVALID_REQUEST, "a JSON-RPC message must be an object")
    request_id = message.get("id")
    if "id" in message and not valid_id(request_id):
        raise JsonRpcError(INVALID_REQUEST, "id must be a string or an integer")
    if message.get("jsonrpc") != "2.0":
        raise JsonRpcError(INVALID_REQUEST, 'jsonrpc must be "2.0"', request_id=request_id if valid_id(request_id) else None)
    if "method" in message and not isinstance(message["method"], str):
        raise JsonRpcError(INVALID_REQUEST, "method must be a string", request_id=request_id)
    if "method" not in message and "result" not in message and "error" not in message:
        raise JsonRpcError(INVALID_REQUEST, "a message needs a method, a result or an error", request_id=request_id)
    if "params" in message and not isinstance(message["params"], dict):
        raise JsonRpcError(INVALID_PARAMS, "params must be an object", request_id=request_id, silent="id" not in message)
    return message


def _refuse_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def valid_id(value: Any) -> bool:
    return isinstance(value, str) or (isinstance(value, int) and not isinstance(value, bool))


def is_request(message: dict[str, Any]) -> bool:
    return "method" in message and "id" in message


def is_notification(message: dict[str, Any]) -> bool:
    return "method" in message and "id" not in message


def response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def dumps(obj: Any) -> bytes:
    """Compact UTF-8 JSON on one line (no indent, so json never emits a raw newline)."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    assert "\n" not in text and "\r" not in text
    return text.encode("utf-8")
