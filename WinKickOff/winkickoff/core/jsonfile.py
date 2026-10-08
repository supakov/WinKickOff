"""JSON files of the rule catalog and of catalog packages: strict reading, transparent decompression, canonical writing.

- Strict: a duplicate key, NaN, Infinity or a number too large for a float, a null value, a lone surrogate escape
  ("\\ud800" without its pair) or nesting deeper than MAX_DEPTH is an error. The standard json module keeps the last of
  two equal keys without a word, which could hide a second "path" of an action. A catalog package allows null
  (nulls=True): the policy records of core/admx.py use it, and core/admx.py checks every field.
- Bounded: a file is refused when it holds more than MAX_ITEMS values (counted before parsing: every value after the
  first of a container follows a comma), so a small file never becomes gigabytes of Python objects; the texts of
  errors quote at most a few dozen characters of the file.
- Compressed: gzip (1f 8b) and xz (fd 37 7a 58 5a 00) are recognised by their first bytes and unpacked with a size
  limit (and xz with a memory limit), so a small file never expands into gigabytes; one stream only, nothing may follow
  it. Anything else is read as plain JSON.
- Canonical: two spaces of indent; an object or an array is written on one line when it fits in WIDTH columns. The
  catalog files are written by this function only (tools/format_catalog.py, the generators, export), so a change of one
  rule changes only its own lines. Keys must be strings and numbers finite.
"""

from __future__ import annotations

import json
import lzma
import math
import re
import zlib
from pathlib import Path
from typing import Any

GZIP_MAGIC = b"\x1f\x8b"
XZ_MAGIC = b"\xfd7zXZ\x00"
MAX_DEPTH = 32
MAX_ITEMS = 1_000_000  # values in one file, counted as commas and brackets: all the templates of Windows 11 give 190 000
WIDTH = 120
MAX_FILE_BYTES = 64 * 1024 * 1024  # a file as it is stored
MAX_JSON_BYTES = 64 * 1024 * 1024  # the JSON text after unpacking; all the templates of Windows 11 take about 13 MB
MAX_XZ_MEMORY = 128 * 1024 * 1024  # what the xz decoder may allocate; the presets up to 9 need at most 65 MB
SUFFIXES = (".json", ".json.gz", ".json.xz")  # what a catalog package file may be called
_SURROGATE = re.compile("[" + chr(0xD800) + "-" + chr(0xDFFF) + "]")


class JsonFileError(ValueError):
    """A file that is not the strict JSON this program writes."""


def _size(limit: int) -> str:
    return f"{limit // (1024 * 1024)} MB" if limit >= 1024 * 1024 else f"{limit} bytes"


def short(value: Any, limit: int = 60) -> str:
    """repr() of a value read from a file, cut so that a message stays readable whatever the file holds."""
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def has_surrogate(value: str) -> bool:
    """A lone surrogate: half of a character of two halves (an emoji), which UTF-8 cannot encode. A Tk entry leaves one
    when such a character is deleted in part; loads() refuses it."""
    return bool(_SURROGATE.search(value))


def without_surrogates(text: str) -> str:
    """The text with every lone surrogate replaced by U+FFFD, so that it can be encoded and read back."""
    return _SURROGATE.sub(chr(0xFFFD), text)


def _text(value: str) -> str:
    if _SURROGATE.search(value):
        raise JsonFileError(f"a lone surrogate escape in {short(value)}")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise JsonFileError(f"the key {short(key)} appears twice")
        if value is None:
            raise JsonFileError(f"the value of {short(key)} is null")
        out[_text(key)] = value
    return out


def _pairs_with_nulls(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise JsonFileError(f"the key {short(key)} appears twice")
        out[_text(key)] = value
    return out


def _constant(name: str) -> Any:
    raise JsonFileError(f"{name} is not a number this program accepts")


def _float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise JsonFileError(f"the number {short(text)} is too large")
    return value


def _check_values(value: Any, nulls: bool, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise JsonFileError(f"nested deeper than {MAX_DEPTH} levels")
    if isinstance(value, str):
        _text(value)
    elif isinstance(value, dict):
        for item in value.values():
            _check_values(item, nulls, depth + 1)
    elif isinstance(value, list):
        for item in value:
            if item is None and not nulls:
                raise JsonFileError("a list holds null")
            _check_values(item, nulls, depth + 1)


def check_depth(value: Any, depth: int = 0) -> None:
    """JsonFileError when a value read some other way (a profile in memory) nests deeper than MAX_DEPTH. Only the depth:
    a lone surrogate that a Tk entry leaves after a Backspace must not stop a rebuild of the window."""
    if depth > MAX_DEPTH:
        raise JsonFileError(f"nested deeper than {MAX_DEPTH} levels")
    if isinstance(value, dict):
        for item in value.values():
            check_depth(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            check_depth(item, depth + 1)


def loads(text: str, *, nulls: bool = False, max_items: int = MAX_ITEMS) -> Any:
    """Strict JSON text (see the module text)."""
    if text.count(",") + text.count("[") + text.count("{") >= max_items:
        raise JsonFileError(f"more than {max_items} values")
    try:
        value = json.loads(text, object_pairs_hook=_pairs_with_nulls if nulls else _pairs, parse_constant=_constant,
                           parse_float=_float)
    except RecursionError as exc:
        raise JsonFileError(f"nested deeper than {MAX_DEPTH} levels") from exc
    except MemoryError as exc:
        raise JsonFileError("not enough memory to read the file") from exc
    except json.JSONDecodeError as exc:
        raise JsonFileError(f"JSON syntax: {exc.msg} at line {exc.lineno} column {exc.colno}") from exc
    except JsonFileError:
        raise
    except ValueError as exc:  # an integer with too many digits
        raise JsonFileError(str(exc)[:200]) from exc
    if value is None:
        raise JsonFileError("the file holds null")
    _check_values(value, nulls)
    return value


def unpack(data: bytes, limit: int = MAX_JSON_BYTES) -> bytes:
    """The bytes of a gzip or xz file unpacked (at most limit bytes), or the bytes themselves."""
    try:
        if data.startswith(GZIP_MAGIC):
            gz = zlib.decompressobj(wbits=31)
            try:
                out = gz.decompress(data, limit + 1)
            except zlib.error as exc:
                raise JsonFileError(f"the gzip data is damaged: {exc}") from exc
            if len(out) > limit or gz.unconsumed_tail:
                raise JsonFileError(f"larger than {_size(limit)} when unpacked")
            if not gz.eof:
                raise JsonFileError("the gzip data is cut off")
            if gz.unused_data:
                raise JsonFileError("data follows the gzip stream")
            return out
        if data.startswith(XZ_MAGIC):
            xz = lzma.LZMADecompressor(format=lzma.FORMAT_XZ, memlimit=MAX_XZ_MEMORY)
            try:
                out = xz.decompress(data, limit + 1)
            except lzma.LZMAError as exc:
                if "memory" in str(exc).lower():
                    raise JsonFileError(f"the xz data needs more than {_size(MAX_XZ_MEMORY)} of memory to unpack") from exc
                raise JsonFileError(f"the xz data is damaged: {exc}") from exc
            if len(out) > limit or (not xz.eof and not xz.needs_input):
                raise JsonFileError(f"larger than {_size(limit)} when unpacked")
            if not xz.eof:
                raise JsonFileError("the xz data is cut off")
            if xz.unused_data:
                raise JsonFileError("data follows the xz stream")
            return out
    except MemoryError as exc:
        raise JsonFileError("not enough memory to unpack the file") from exc
    if len(data) > limit:
        raise JsonFileError(f"larger than {_size(limit)}")
    return data


def decode(data: bytes, limit: int = MAX_JSON_BYTES, *, nulls: bool = False) -> Any:
    """The strict JSON value of the bytes of a file, plain or compressed."""
    try:
        text = unpack(data, limit).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JsonFileError(f"not UTF-8 text: {exc.reason} at byte {exc.start}") from exc
    if text.startswith(chr(0xFEFF)):
        raise JsonFileError("starts with a byte order mark")
    return loads(text, nulls=nulls)


def read(path: Path, *, file_limit: int = MAX_FILE_BYTES, json_limit: int = MAX_JSON_BYTES, nulls: bool = False) -> Any:
    """A JSON file of the catalog or a package, plain or compressed with gzip or xz, read strictly."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise JsonFileError(f"cannot read the file: {exc}") from exc
    if size > file_limit:
        raise JsonFileError(f"larger than {_size(file_limit)}")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise JsonFileError(f"cannot read the file: {exc}") from exc
    return decode(data, json_limit, nulls=nulls)


def _dump(value: Any, column: int, indent: int) -> str:
    if isinstance(value, dict) and not all(isinstance(key, str) for key in value):
        raise JsonFileError("the keys of a JSON object must be strings")
    try:
        flat = json.dumps(value, ensure_ascii=False, separators=(", ", ": "), allow_nan=False)
    except ValueError as exc:
        raise JsonFileError(str(exc)[:200]) from exc
    if not isinstance(value, (dict, list)) or not value or column + len(flat) + 1 <= WIDTH:
        return flat
    inner = indent + 2
    pad = " " * inner
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            head = json.dumps(key, ensure_ascii=False) + ": "
            lines.append(pad + head + _dump(item, inner + len(head), inner))
    else:
        lines = [pad + _dump(item, inner, inner) for item in value]
    opening, closing = ("{", "}") if isinstance(value, dict) else ("[", "]")
    return opening + "\n" + ",\n".join(lines) + "\n" + " " * indent + closing


def _check_keys(value: Any, depth: int = 0) -> None:
    """Every key at every level is a string: json.dumps would turn 1 into "1" on the one-line form only."""
    if depth > MAX_DEPTH:
        raise JsonFileError(f"nested deeper than {MAX_DEPTH} levels")
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise JsonFileError("the keys of a JSON object must be strings")
        for item in value.values():
            _check_keys(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _check_keys(item, depth + 1)


def dumps(value: Any) -> str:
    """Canonical text: two spaces of indent, short objects and arrays on one line, a final line break (LF). Only what
    loads() reads back: string keys at every level, finite numbers."""
    _check_keys(value)
    return _dump(value, 0, 0) + "\n"


def write(path: Path, value: Any) -> None:
    """Canonical JSON with CRLF line endings, UTF-8 without a byte order mark (the files of the repository)."""
    path.write_bytes(dumps(value).replace("\n", "\r\n").encode("utf-8"))
