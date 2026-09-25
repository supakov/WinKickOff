"""Reference data shipped with the application: keyboard layouts and time zones."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PAIR_RE = re.compile(r"^[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}$")


def _load_list(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{path.name}: a JSON list of objects is expected")
    return data


def find_keyboard(keyboards: list[dict[str, Any]], item: str) -> dict[str, Any] | None:
    """Input-language entry for a profile item.

    A profile item is either a language tag (the first entry with that tag is used, for example
    uk-UA gives the Enhanced layout) or an explicit "LCID:KLID" pair (a specific layout).
    """
    if PAIR_RE.match(item):
        lcid, klid = item.upper().split(":")
        for entry in keyboards:
            if str(entry.get("lcid") or "").upper() == lcid and str(entry.get("klid") or "").upper() == klid:
                return entry
        return {"tag": None, "lcid": lcid, "klid": klid, "title": item, "transient": False}
    for entry in keyboards:
        if entry.get("tag") == item:
            return entry
    return None


def keyboard_item_id(keyboards: list[dict[str, Any]], entry: dict[str, Any]) -> str:
    """How an entry is stored in a profile: its tag when it is the first entry for that tag,
    otherwise the explicit LCID:KLID pair."""
    first = find_keyboard(keyboards, str(entry.get("tag")))
    if first is entry or entry.get("lcid") is None:
        return str(entry["tag"])
    return f"{entry['lcid']}:{entry['klid']}"


@dataclass(frozen=True)
class Resources:
    keyboards: list[dict[str, Any]]
    timezones: list[dict[str, Any]]

    @classmethod
    def load(cls, folder: Path) -> Resources:
        return cls(
            keyboards=_load_list(folder / "keyboards.json"),
            timezones=_load_list(folder / "timezones.json"),
        )
