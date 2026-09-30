"""core/themes.py and the window: colour themes are files; "" follows the Windows light or dark mode."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from winkickoff.core import i18n, themes
from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def _underline(value: object) -> int:
    """The underline option as a number: Tk 8.6 says -1 for none, Tk 9 (the CI build) an empty string."""
    text = str(value).strip()
    return int(text) if text.lstrip("-").isdigit() else -1


class ThemeFilesTest(unittest.TestCase):
    def test_bundled_themes(self) -> None:
        found = themes.available_themes(ROOT / "resources")
        self.assertEqual(list(found), ["light", "dark", "latte", "matrix"])
        self.assertFalse(found["latte"].dark)
        self.assertEqual(found["latte"].base, "clam")
        self.assertEqual(found["light"].base, "native")
        self.assertTrue(found["dark"].dark and found["matrix"].dark)
        self.assertEqual(found["matrix"].font, "Consolas")
        for theme in found.values():
            self.assertEqual(set(theme.colors), set(themes.LIGHT_COLORS))

    def test_a_user_theme_file_is_found_and_broken_ones_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources = Path(tmp)
            (resources / "themes").mkdir()
            shutil.copy(ROOT / "resources" / "themes" / "dark.json", resources / "themes" / "dark.json")
            (resources / "themes" / "sepia.json").write_text(json.dumps(
                {"name": "Sepia", "base": "clam", "colors": {"background": "#f4ecd8", "link": "not a colour"}}), encoding="utf-8")
            (resources / "themes" / "broken.json").write_text("{", encoding="utf-8")
            found = themes.available_themes(resources)
            self.assertEqual(list(found), ["light", "dark", "sepia"])  # the built-in light theme is always there
            self.assertEqual(found["sepia"].colors["background"], "#f4ecd8")
            self.assertEqual(found["sepia"].colors["link"], themes.LIGHT_COLORS["link"])  # a bad value keeps the default

    def test_empty_choice_follows_windows(self) -> None:
        with mock.patch.object(themes, "windows_uses_dark_mode", return_value=True):
            self.assertEqual(themes.resolve_theme("", ROOT / "resources").id, "dark")
        with mock.patch.object(themes, "windows_uses_dark_mode", return_value=False):
            self.assertEqual(themes.resolve_theme("", ROOT / "resources").id, "light")
        self.assertEqual(themes.resolve_theme("matrix", ROOT / "resources").id, "matrix")
        self.assertEqual(themes.resolve_theme("missing", ROOT / "resources").id in ("light", "dark"), True)


try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk is not available")
class WindowThemeTest(unittest.TestCase):
    def test_window_builds_in_every_theme(self) -> None:
        from winkickoff.ui.main_window import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                             output=base / "output", logs=base / "logs")
            for folder in (paths.profiles, paths.output, paths.logs):
                folder.mkdir()
            catalog = load_catalog(paths.rules, docs_root=paths.docs_root)
            resources = Resources.load(paths.resources)
            i18n.set_language("en", paths.resources, paths.rules)
            for theme_id in ("light", "dark", "latte", "matrix"):
                with self.subTest(theme=theme_id):
                    profile, _ = Profile.load(ROOT / "profiles" / "preset-office.json", catalog)
                    win = MainWindow(paths, catalog, profile, resources, Settings(language="en", theme=theme_id))
                    try:
                        win.withdraw()
                        self.assertEqual(win.theme.id, theme_id)
                        field = win.theme.colors["field"]
                        if field:
                            self.assertEqual(str(win.detail.cget("background")).lower(), field.lower())
                        self._check_menu_bar(win)
                        margins = win.menu_margins
                        win.change_theme("dark" if theme_id != "dark" else "light")
                        self.assertIsNotNone(win.restart_state)
                        self.assertFalse(margins.active)  # the menu hook ends with the window
                    finally:
                        try:
                            win.destroy()
                        except tk.TclError:
                            pass

    def _check_menu_bar(self, win: object) -> None:
        """Light keeps the Windows menu bar; a coloured theme draws its own, since Windows paints its menu bar in
        system colours only. Alt + an underlined letter opens a menu whatever the keyboard layout."""
        labels = ["File", "Build", "Language", "Theme", "This PC", "Help"]
        if win.theme.base == "native":  # type: ignore[attr-defined]
            bar = win.nametowidget(win.cget("menu"))  # type: ignore[attr-defined]
            cascades = [i for i in range(bar.index("end") + 1) if bar.type(i) == "cascade"]
            self.assertEqual([bar.entrycget(i, "label") for i in cascades], labels)
            self.assertEqual([_underline(bar.entrycget(i, "underline")) for i in cascades], [0, 0, 0, 0, 5, 0])
            self.assertEqual(win.menu_buttons, [])  # type: ignore[attr-defined]
            return
        self.assertEqual(win.cget("menu"), "")  # type: ignore[attr-defined]
        buttons = win.menu_buttons  # type: ignore[attr-defined]
        self.assertEqual([b.cget("text") for b in buttons], labels)
        colors = win.theme.colors  # type: ignore[attr-defined]
        for button in buttons:
            self.assertEqual(str(button.cget("background")).lower(), colors["background"].lower())
            self.assertEqual(str(button.cget("foreground")).lower(), colors["foreground"].lower())
            self.assertEqual(_underline(button.cget("underline")), -1)  # letters are underlined only while Alt is held
        win._show_access_keys(True)  # type: ignore[attr-defined]
        self.assertEqual([_underline(b.cget("underline")) for b in buttons], [0, 0, 0, 0, 5, 0])
        win._show_access_keys(False)  # type: ignore[attr-defined]
        self.assertEqual({_underline(b.cget("underline")) for b in buttons}, {-1})
        if sys.platform == "win32":
            self.assertTrue(win.menu_margins.active)  # type: ignore[attr-defined]
        with mock.patch.object(win, "_post_menu", return_value="break") as post:
            self.assertEqual(win._on_alt_key(SimpleNamespace(char="", keycode=0x48)), "break")  # type: ignore[attr-defined]
            post.assert_called_with(buttons[5])  # H: Help, by key code (another layout active)
            win._on_alt_key(SimpleNamespace(char="p", keycode=0x50))  # type: ignore[attr-defined]
            post.assert_called_with(buttons[4])  # P: This PC
            self.assertIsNone(win._on_alt_key(SimpleNamespace(char="q", keycode=0x51)))  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
