"""Program settings in settings.json next to the executable: window geometry, last profile,
recently used files, language, colour theme and the imported templates shown. A missing or damaged file gives the defaults; nothing is written elsewhere."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.paths import display_path

log = logging.getLogger(__name__)
MAX_RECENT = 8
_CHOICE_RE = re.compile(r"^[A-Za-z0-9_.-]{0,32}$")  # a language code or a theme id; "" follows Windows
_IMPORT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")  # a folder name in admx/ (core/admx.py IMPORT_ID_RE)
MAX_IMPORTS = 16
_GEOMETRY_RE = re.compile(r"^\d{3,5}x\d{3,5}[+-]-?\d{1,5}[+-]-?\d{1,5}$|^\d{3,5}x\d{3,5}$")


@dataclass
class Settings:
    geometry: str = ""
    last_profile: str = ""  # relative to the program folder when inside it
    recent: list[str] = field(default_factory=list)  # profiles (.json) and answer files (.xml), newest first
    language: str = ""  # interface language code (en, ru, uk or any added file); "" follows Windows
    theme: str = ""  # colour theme id from resources/themes; "" follows the Windows light or dark mode
    allow_apply: bool = False  # "Apply the selection now" on this PC; off until the user allows it
    admx: list[str] = field(default_factory=list)  # imported templates shown in the tree (folders in admx/)

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning("settings %s ignored: %s", path, exc)
            return cls()
        if not isinstance(data, dict):
            log.warning("settings %s ignored: not a JSON object", path)
            return cls()
        geometry = str(data.get("geometry", ""))
        recent = data.get("recent")
        imports = data.get("admx")
        return cls(
            geometry=geometry if _GEOMETRY_RE.match(geometry) else "",
            last_profile=str(data.get("last_profile", "")),
            language=_choice(data.get("language")),
            theme=_choice(data.get("theme")),
            allow_apply=data.get("allow_apply") is True,
            recent=[str(item) for item in recent][:MAX_RECENT] if isinstance(recent, list) else [],
            admx=[i for i in dict.fromkeys(imports) if isinstance(i, str) and _IMPORT_RE.match(i)][:MAX_IMPORTS]
            if isinstance(imports, list) else [],
        )

    def save(self, path: Path) -> None:
        """Write through a temporary file in the same folder, so a crash never leaves half a file."""
        data: dict[str, Any] = {"geometry": self.geometry, "last_profile": self.last_profile, "recent": self.recent,
                                "language": self.language, "theme": self.theme, "allow_apply": self.allow_apply,
                                "admx": self.admx}
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        except OSError as exc:
            log.warning("settings %s not saved: %s", path, exc)

    def add_recent(self, path: Path, root: Path) -> None:
        item = display_path(path, root)
        self.recent = [item] + [r for r in self.recent if r.lower() != item.lower()]
        del self.recent[MAX_RECENT:]

    def forget(self, path: Path, root: Path) -> None:
        item = display_path(path, root).lower()
        self.recent = [r for r in self.recent if r.lower() != item]

    @staticmethod
    def resolve(item: str, root: Path) -> Path:
        path = Path(item)
        return path if path.is_absolute() else root / path


def _choice(value: object) -> str:
    text = str(value) if isinstance(value, str) else ""
    return text if _CHOICE_RE.match(text) else ""
