"""Colour themes of the window: resources/themes/<id>.json.

A theme file is plain JSON, so users add or change themes without touching the code:

    {
      "name": "Dark",          English name; shown through the interface translations when one exists
      "base": "clam",          ttk theme to build on: "native" keeps the Windows look, "clam" takes every colour
      "dark": true,            dark window title bar on Windows 10 20H1 and later
      "font": "",              optional font family for the whole window
      "colors": { "background": "#202020", ... }
    }

Every colour not given in a file comes from the built-in light palette below; an empty string keeps the
native colour of the widget. The theme id "" follows Windows: the "dark" theme when apps use dark mode
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize AppsUseLightTheme = 0, read only),
otherwise "light". A missing or broken file falls back to the built-in light theme.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)
LIGHT = "light"
DARK = "dark"
_ID = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_COLOR = re.compile(r"^(#[0-9A-Fa-f]{3}|#[0-9A-Fa-f]{6}|)$")

# The built-in light palette: the look of the program before themes existed. "" keeps the native colour.
LIGHT_COLORS: dict[str, str] = {
    "background": "",  # window, frames, labels
    "foreground": "",
    "field": "",  # tree, text, entry and list backgrounds
    "field_foreground": "",
    "select": "",  # selected rows and text
    "select_foreground": "",
    "border": "",
    "button": "",
    "button_foreground": "",
    "button_active": "",
    "heading": "",  # table headings
    "disabled": "#7a7a7a",  # rules that are off in the tree
    "muted": "#666666",  # notes, hints, secondary text
    "link": "#1a5fb4",
    "changed": "#1f4e79",  # changed values and informational messages
    "error": "#b00020",
    "warning": "#8a5a00",
    "risky": "#a33333",
    "check_border": "#5b5b5b",  # rule check boxes
    "check_on": "#2463c7",
    "check_off": "#ffffff",
    "check_mark": "#ffffff",
}


@dataclass
class Theme:
    id: str
    name: str
    base: str = "native"
    dark: bool = False
    font: str = ""
    colors: dict[str, str] = field(default_factory=lambda: dict(LIGHT_COLORS))

    def color(self, key: str, fallback: str = "") -> str:
        return self.colors.get(key) or fallback


BUILTIN_LIGHT = Theme(LIGHT, "Light")


def load_theme(path: Path) -> Theme:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("a theme must be a JSON object")
    colors = dict(LIGHT_COLORS)
    for key, value in (data.get("colors") or {}).items():
        if key in LIGHT_COLORS and isinstance(value, str) and _COLOR.match(value):
            colors[key] = value
        else:
            log.warning("%s: colour %s=%r ignored", path.name, key, value)
    base = str(data.get("base", "native"))
    return Theme(
        id=path.stem,
        name=str(data.get("name") or path.stem),
        base=base if base in ("native", "clam", "alt", "default") else "native",
        dark=data.get("dark") is True,
        font=str(data.get("font") or ""),
        colors=colors,
    )


def available_themes(resources_dir: Path) -> dict[str, Theme]:
    """Theme id -> theme, light first, then dark, then the others by name; always has the light theme."""
    themes: dict[str, Theme] = {}
    for path in sorted((resources_dir / "themes").glob("*.json")):
        if not _ID.match(path.stem):
            continue
        try:
            themes[path.stem] = load_theme(path)
        except (OSError, ValueError) as exc:
            log.warning("theme %s ignored: %s", path.name, exc)
    themes.setdefault(LIGHT, BUILTIN_LIGHT)
    order = sorted(themes, key=lambda t: (t != LIGHT, t != DARK, themes[t].name.lower()))
    return {t: themes[t] for t in order}


def windows_uses_dark_mode() -> bool:
    """True when Windows apps use dark mode; reads the registry only."""
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except (OSError, ValueError):
        return False


def resolve_theme(wanted: str, resources_dir: Path) -> Theme:
    """The theme to use: the wanted one if its file exists; "" follows Windows light or dark mode."""
    themes = available_themes(resources_dir)
    if wanted in themes:
        return themes[wanted]
    automatic = DARK if windows_uses_dark_mode() else LIGHT
    return themes.get(automatic, themes[LIGHT])
