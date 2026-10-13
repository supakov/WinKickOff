"""Constants, limits and the error of the policy templates, and the XML helpers: strict reading (no DTD, size
limits) and the safe characters of keys, value names and values, which end up in PowerShell strings and CDATA
sections."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from winkickoff.core.i18n import N_



FORMAT_VERSION = 2  # 2: list and multiText elements (1.1.0-rc.2); imports of format 1 still load
READ_FORMATS = (1, 2)
LEGACY_SKIPS = ("list", "multitext")  # reasons of format 1 for elements that are converted now
META_FILE = "import.json"
DATA_FILE = "policies.json"
SOURCE_CULTURE = "en-US"
MAX_FILES = 3000
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_DWORD = 0x7FFFFFFF  # larger values do not fit the signed DWORD that PowerShell writes
MAX_QWORD = 0x7FFFFFFFFFFFFFFF
IMPORT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_REF_RE = re.compile(r"^\$\((string|presentation)\.([^)]+)\)$")
_DECLARATION_RE = re.compile(r"^\s*<\?xml[^>]*\?>")
_TYPOGRAPHIC_QUOTES = "".join(chr(c) for c in (0x2018, 0x2019, 0x201A, 0x201B, 0x201C, 0x201D, 0x201E))
_CONTROL = "".join(chr(c) for c in range(32)) + chr(127)
_NOT_XML = "".join(chr(c) for c in range(0x80, 0xA0)) + chr(0xFFFE) + chr(0xFFFF)  # C1 controls, non-characters
_UNSAFE_NAME = set(_CONTROL + '"`$' + _TYPOGRAPHIC_QUOTES + _NOT_XML)
_UNSAFE_VALUE = set(_CONTROL + _TYPOGRAPHIC_QUOTES + _NOT_XML)

# why a policy was not imported; shown translated in the import summary
SKIP_REASONS: dict[str, str] = {
    "valuelist": N_("an option or a check box that writes several values"),
    "unsafe": N_("characters that are not safe in a script"),
    "range": N_("a number outside the range Windows PowerShell writes"),
    "novalue": N_("nothing to write (no value name)"),
    "broken": N_("a template error"),
}
SIDE_TITLES = {"machine": N_("Computer policies (HKLM, written during installation)"),
               "user": N_("User policies (default user profile)")}
NO_CATEGORY = N_("Without a category")
IMPORTED_RISK = N_("Imported from a policy template; WinKickOff has not reviewed this policy. Check its effect in "
                   "a virtual machine before using it on work computers.")
STATE_TITLE = N_("Policy state")
STATE_ENABLED = N_("Enabled")
STATE_DISABLED = N_("Disabled")
TITLE_ENABLED = N_("{0} (Enabled)")
TITLE_DISABLED = N_("{0} (Disabled)")
ON, OFF = N_("On"), N_("Off")
VALUE = N_("Value")
NO_EXPLAIN = N_("The template has no description of this policy.")


class AdmxError(ValueError):
    """A folder or file that cannot be imported."""


_CULTURE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{1,8}){0,4}$")

# --------------------------------------------------------------------------- XML helpers


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _kids(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [child for child in element if _local(child.tag) == name] if element is not None else []


def _kid(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _kids(element, name)
    return found[0] if found else None


def read_xml(path: Path) -> ET.Element:
    """Parse one template file; refuse big files and documents with a DTD or entities. Messages name the file only,
    never its folder: they are kept in the records and may travel in an exported catalog file."""
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise AdmxError(f"{path.name}: {size} bytes, more than {MAX_FILE_BYTES}")
        data = path.read_bytes()
    except OSError as exc:
        raise AdmxError(f"{path.name}: {exc.strerror or type(exc).__name__}") from None
    try:
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = data.decode("utf-16")
        elif data[:3] == b"\xef\xbb\xbf":
            text = data[3:].decode("utf-8")
        elif data[1:2] == b"\x00":
            text = data.decode("utf-16-le")
        else:
            text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc
    upper = text.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        raise AdmxError(f"{path.name}: DTDs and entities are not allowed")
    # the file is decoded here; some templates declare encodings the parser does not know ("unicode")
    text = _DECLARATION_RE.sub("", text, count=1)
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise AdmxError(f"{path.name}: {exc}") from exc


def safe_name(text: str) -> bool:
    """A registry key or value name that can go into a PowerShell string of the generated scripts."""
    return bool(text) and not (set(text) & _UNSAFE_NAME) and "]]>" not in text and len(text) <= 512


def safe_key(text: str) -> bool:
    """A registry key: a safe name whose segments are never empty, "." or ".." (PowerShell resolves ".." even with
    -LiteralPath, so a key "..\\.DEFAULT" of a user policy would leave the default user profile)."""
    if not safe_name(text):
        return False
    segments = re.split(r"[\\/]", text.strip("\\"))
    return all(segment not in ("", ".", "..") for segment in segments)


def safe_value(text: str) -> bool:
    return not (set(text) & _UNSAFE_VALUE) and "]]>" not in text and len(text) <= 4096
