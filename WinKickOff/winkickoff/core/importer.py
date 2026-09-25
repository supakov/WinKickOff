"""Import a profile from an answer file built by WinKickOff (the profile is embedded in
Extensions/Profile). Import of the hand-written v0.2 file by matching actions is task T08."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from winkickoff.core.catalog import Catalog
from winkickoff.core.profile import Profile

EXT = "{urn:workgroup-unattend}"


class ImportFailed(ValueError):
    pass


def import_xml(text: str, catalog: Catalog) -> tuple[Profile, list[str]]:
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise ImportFailed(f"файл не является корректным XML: {exc}") from exc
    element = root.find(f"{EXT}Extensions/{EXT}Profile")
    if element is None or not (element.text or "").strip():
        raise ImportFailed(
            "в файле нет встроенного профиля WinKickOff. Открыть можно только файл, собранный этой программой; "
            "импорт написанного вручную файла v0.2 появится позже (задача T08)."
        )
    try:
        data = json.loads(element.text or "")
    except json.JSONDecodeError as exc:
        raise ImportFailed(f"встроенный профиль повреждён: {exc}") from exc
    if not isinstance(data, dict):
        raise ImportFailed("встроенный профиль должен быть объектом JSON")
    profile, warnings = Profile.from_dict(data, catalog)
    profile.path = None
    return profile, warnings
