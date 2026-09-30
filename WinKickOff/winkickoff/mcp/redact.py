"""What leaves the server as text: secrets removed, control characters stripped, file names checked.

Passwords and product keys never reach a client. A profile is redacted field by field (redact_profile); a build for
preview is made from a copy without secrets (redacted_copy) and then checked structurally (assert_redacted_build):
a substring search for the secret values would refuse the starter profiles, whose passwords are short or common.
"""

from __future__ import annotations

import copy
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from winkickoff.core.profile import Profile
from winkickoff.core.render import BuildResult
from winkickoff.mcp.errors import RedactionError, ToolError

TITLE = 200
SUMMARY = 400
EFFECT = 2000
EXPLAIN = 4000
OTHER = 400
MAX_NAME = 80
KEY_PLACEHOLDER = "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"  # keeps the answer file well-formed where a custom key would be
HIDDEN = "<hidden>"
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}
_STRIP = "".join(chr(c) for c in list(range(0, 9)) + [11, 12] + list(range(14, 32)) + list(range(127, 160))
                 + list(range(0x200B, 0x2010)) + list(range(0x202A, 0x202F)) + list(range(0x2060, 0x2065))
                 + list(range(0x2066, 0x206A)) + [0xFEFF])
_STRIP_RE = re.compile("[" + re.escape(_STRIP) + "]")
_KEEP = {"\n", "\t", "\r"}


def clean_text(text: Any, limit: int = OTHER) -> str:
    """Text without control and invisible formatting characters (newlines and tabs stay), cut at limit."""
    value = _STRIP_RE.sub("", str(text) if text is not None else "").replace("\r\n", "\n").replace("\r", "\n")
    if len(value) > limit:
        value = value[:limit].rstrip() + " [truncated]"
    return value


def clean_json(value: Any, limit: int = EXPLAIN) -> Any:
    """clean_text applied to every string of a JSON-like structure."""
    if isinstance(value, str):
        return clean_text(value, limit)
    if isinstance(value, list):
        return [clean_json(item, limit) for item in value]
    if isinstance(value, dict):
        return {str(key): clean_json(item, limit) for key, item in value.items()}
    return value


def _scrub(value: Any) -> Any:
    """Secret fields of any JSON-like structure replaced by booleans; free text keys renamed to *_text."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key == "password":
                out["has_password"] = bool(item)
            elif key == "product_key":
                out["has_product_key"] = bool(item)
            elif key in ("comment", "author", "description"):
                out[key + "_text"] = clean_text(item, EFFECT)
            else:
                out[key] = _scrub(item)
        return out
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return clean_text(value, EFFECT)
    return value


def redact_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Profile.to_dict() without secrets: accounts[].password becomes has_password, install.product_key becomes
    has_product_key; comment and author become comment_text and author_text."""
    return _scrub(data)


def redact_differences(differences: list[Any]) -> list[dict[str, Any]]:
    """Difference rows as dicts; the product key and passwords are shown as <hidden>."""
    rows: list[dict[str, Any]] = []
    for item in differences:
        before, after = item.before, item.after
        if item.kind == "install" and item.key == "product_key":
            before, after = HIDDEN, HIDDEN
        rows.append({"kind": item.kind, "key": item.key, "before": _scrub(before), "after": _scrub(after)})
    return rows


def redacted_copy(profile: Profile) -> Profile:
    """A deep copy for the preview build: passwords blank, a custom product key replaced by a placeholder."""
    copied = copy.deepcopy(profile)
    for account in copied.accounts:
        account.password = ""
    if copied.install.get("product_key"):
        copied.install["product_key"] = KEY_PLACEHOLDER
    return copied


def _local(tag: Any) -> str:
    return str(tag).rsplit("}", 1)[-1]


def assert_redacted_build(result: BuildResult) -> None:
    """Structural check of a build made from redacted_copy: every Password/Value is empty, every ProductKey/Key is
    empty or the placeholder, and the embedded profile JSON holds no password and no real key."""
    try:
        root = ET.fromstring(result.xml)
    except ET.ParseError as exc:
        raise RedactionError(f"the build is not well-formed XML: {exc}") from exc
    for element in root.iter():
        name = _local(element.tag)
        if name == "Password":
            for child in element:
                if _local(child.tag) == "Value" and (child.text or "").strip():
                    raise RedactionError("a password value is present in the build")
        elif name == "ProductKey":
            for child in element:
                if _local(child.tag) == "Key" and (child.text or "").strip() not in public_keys():
                    raise RedactionError("a product key is present in the build")
        elif name == "Profile" and (element.text or "").strip():
            try:
                embedded = json.loads(element.text or "")
            except ValueError as exc:
                raise RedactionError("the embedded profile is not JSON") from exc
            for account in embedded.get("accounts", []):
                if account.get("password"):
                    raise RedactionError("a password is present in the embedded profile")
            if embedded.get("install", {}).get("product_key") not in public_keys() | {None}:
                raise RedactionError("a product key is present in the embedded profile")


def public_keys() -> set[str]:
    """Values a ProductKey/Key may hold in a redacted build: empty, the placeholder, or a generic key of an
    edition (public values published by Microsoft, not secrets)."""
    from winkickoff.core.render import EDITION_KEYS

    return {"", KEY_PLACEHOLDER, *EDITION_KEYS.values()}


def check_name(name: Any) -> str | None:
    """Why a profile or answer file name is refused, or None. Unicode letters and digits (str.isalnum), space,
    underscore, dot and hyphen; 1 to 80 code points after NFC; no leading or trailing space or dot; no ".."; no
    reserved device name."""
    if not isinstance(name, str):
        return "the name must be text"
    value = unicodedata.normalize("NFC", name)
    if not value or len(value) > MAX_NAME:
        return f"the name must have 1 to {MAX_NAME} characters"
    if "/" in value or "\\" in value:
        return "the name must not contain path separators"
    for ch in value:
        if not (ch.isalnum() or ch in " _.-"):
            return f"the character {ch!r} is not allowed in a name"
    if not value[0].isalnum():
        return "the name must start with a letter or a digit"
    if value[-1] in " .":
        return "the name must not end with a space or a dot"
    if ".." in value:
        return 'the name must not contain ".."'
    if value.split(".", 1)[0].upper() in _RESERVED:
        return "the name is a reserved device name"
    return None


def safe_child(folder: Path, name: str, suffix: str) -> Path:
    """folder/<name><suffix> after check_name; refuses preset names, anything that resolves outside the folder, and
    symlinks or reparse points on the folder or the file."""
    reason = check_name(name)
    if reason:
        raise ToolError("name_refused", reason, {"name": name})
    normalised = unicodedata.normalize("NFC", name)
    if normalised.lower().startswith("preset-"):
        raise ToolError("name_refused", "the names preset-* are reserved for presets", {"name": name})
    base = folder.resolve()
    if folder.is_symlink() or _is_reparse_point(folder):
        raise ToolError("name_refused", "the target folder is a link", {"name": name})
    target = folder / (normalised + suffix)  # in the caller's form of the folder path (resolve() may shorten names)
    if target.resolve().parent != base:
        raise ToolError("name_refused", "the name leaves the folder", {"name": name})
    if target.is_symlink() or _is_reparse_point(target):
        raise ToolError("name_refused", "the target is a link", {"name": name})
    return target


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = path.lstat().st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
