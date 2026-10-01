"""The stdio transport: one JSON-RPC message per line on stdin and stdout, logs into a file, nothing else on stdout."""

from __future__ import annotations

import logging
import os
import sys
from typing import BinaryIO

from winkickoff.mcp import MAX_MESSAGE_BYTES
from winkickoff.mcp.jsonrpc import PARSE_ERROR, JsonRpcError, dumps, error_response, parse_message
from winkickoff.mcp.protocol import McpServer, Session

log = logging.getLogger("winkickoff.mcp.stdio")


def serve_stdio(reader: BinaryIO, writer: BinaryIO, server: McpServer, session: Session) -> int:
    """Read lines until EOF; every answer is one line. Returns the exit code of the process (always 0)."""
    try:
        while True:
            line = reader.readline(MAX_MESSAGE_BYTES + 1)
            if not line:
                break
            if not line.endswith(b"\n") and len(line) > MAX_MESSAGE_BYTES:
                _drain(reader)  # the tail of an over-long line is never parsed as a message
                _write(writer, error_response(None, PARSE_ERROR, f"a message is longer than {MAX_MESSAGE_BYTES} bytes"))
                continue
            text = line.strip()
            if not text:
                continue
            try:
                message = parse_message(text)
            except JsonRpcError as exc:
                if not exc.silent:  # a malformed notification gets no answer, as JSON-RPC requires
                    _write(writer, exc.response())
                continue
            reply = server.handle(message, session)
            if reply is not None:
                _write(writer, reply)
    except (BrokenPipeError, KeyboardInterrupt):
        log.info("stdio transport closed")
    return 0


def _drain(reader: BinaryIO) -> None:
    while True:
        chunk = reader.readline(MAX_MESSAGE_BYTES + 1)
        if not chunk or chunk.endswith(b"\n"):
            return


def _write(writer: BinaryIO, obj: dict) -> None:
    writer.write(dumps(obj) + b"\n")
    writer.flush()


def open_std_streams() -> tuple[BinaryIO, BinaryIO] | None:
    """The binary standard streams, or the inherited descriptors 0 and 1 when Python made no stream objects
    (a process without a console), or None when neither exists."""
    stdin, stdout = getattr(sys, "stdin", None), getattr(sys, "stdout", None)
    if stdin is not None and stdout is not None and hasattr(stdin, "buffer") and hasattr(stdout, "buffer"):
        return stdin.buffer, stdout.buffer
    try:
        os.fstat(0)
        os.fstat(1)
        return os.fdopen(0, "rb", buffering=0), os.fdopen(1, "wb", buffering=0)
    except OSError:
        return None
