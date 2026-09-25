"""core/i18n.py: interface translations are complete and consistent; the window switches language.

The Russian source text is the key. Every tr()/N_() string of the package must have a Ukrainian and an
English translation with the same {placeholders}; stale translations are not allowed.
"""

from __future__ import annotations

import ast
import json
import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from winkickoff.core import i18n
from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources

ROOT = Path(__file__).resolve().parents[1]
FIELD = re.compile(r"\{[^{}]*\}")
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")
RUSSIAN_ONLY = re.compile("[ыЫэЭъЪёЁ]")


def source_strings() -> list[str]:
    found: list[str] = []
    for path in sorted((ROOT / "winkickoff").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
    return list(dict.fromkeys(found))


class TranslationFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = source_strings()
        cls.files = {lang: json.loads((ROOT / "resources" / f"strings.{lang}.json").read_text(encoding="utf-8")) for lang in ("uk", "en")}

    def test_every_string_is_translated_and_nothing_is_stale(self) -> None:
        for lang, table in self.files.items():
            with self.subTest(language=lang):
                self.assertEqual([s for s in self.sources if not table.get(s)], [])
                self.assertEqual(sorted(set(table) - set(self.sources)), [])

    def test_placeholders_and_line_breaks_match(self) -> None:
        for lang, table in self.files.items():
            for source, text in table.items():
                with self.subTest(language=lang, source=source[:40]):
                    self.assertEqual(Counter(FIELD.findall(text)), Counter(FIELD.findall(source)))
                    self.assertEqual(text.count("\n"), source.count("\n"))

    def test_style(self) -> None:
        for lang, table in self.files.items():
            for text in table.values():
                self.assertFalse(any(chr(c) in text for c in (0x2013, 0x2014)), text)
        self.assertEqual([t for t in self.files["en"].values() if CYRILLIC.search(t)], [])
        self.assertEqual([t for t in self.files["uk"].values() if RUSSIAN_ONLY.search(t)], [])


class TranslatorTest(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("ru")

    def test_switch_and_fallback(self) -> None:
        i18n.set_language("uk", ROOT / "resources", ROOT / "rules")
        self.assertEqual(i18n.language(), "uk")
        self.assertNotEqual(i18n.tr("Сохранить"), "Сохранить")
        self.assertEqual(i18n.tr("строка, которой нет в переводах {0}", 1), "строка, которой нет в переводах 1")
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        rule = catalog.rules["defender.pua"]
        self.assertNotEqual(i18n.catalog_texts().rule(rule, "title"), rule.title)
        i18n.set_language("xx", ROOT / "resources", ROOT / "rules")
        self.assertEqual(i18n.language(), "ru")
        self.assertEqual(i18n.tr("Сохранить"), "Сохранить")


try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk is not available")
class WindowLanguageTest(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("ru")

    def test_window_in_english_and_switch_back_keeps_the_profile(self) -> None:
        from winkickoff.ui.main_window import WORKFLOW_NODE, MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                             output=base / "output", logs=base / "logs")
            for folder in (paths.profiles, paths.output, paths.logs):
                folder.mkdir()
            catalog = load_catalog(paths.rules, docs_root=paths.docs_root)
            resources = Resources.load(paths.resources)
            profile, _ = Profile.load(ROOT / "profiles" / "preset-office.json", catalog)
            i18n.set_language("en", paths.resources, paths.rules)
            win = MainWindow(paths, catalog, profile, resources)
            try:
                win.withdraw()
                self.assertEqual(win.tree.item(WORKFLOW_NODE, "text").strip(), i18n.tr("Порядок работы"))
                self.assertFalse(CYRILLIC.search(win.tree.item(WORKFLOW_NODE, "text")))
                self.assertEqual(win.tree.item("r:defender.pua", "text").strip(),
                                 i18n.catalog_texts().rule(catalog.rules["defender.pua"], "title"))
                win.toggle_item("r:defender.pua")  # an unsaved change must survive the switch
                win.change_language("ru")
                state = win.restart_state
            finally:
                try:
                    win.destroy()
                except tk.TclError:
                    pass
            self.assertIsNotNone(state)
            self.assertEqual(json.loads((base / "settings.json").read_text(encoding="utf-8"))["language"], "ru")
            i18n.set_language("ru", paths.resources, paths.rules)
            again = MainWindow(paths, catalog, state["profile"], resources)
            try:
                again.withdraw()
                again.restore_state(state)
                self.assertTrue(again.dirty)
                self.assertFalse(again.profile.is_enabled("defender.pua"))
                self.assertEqual(again.tree.item(WORKFLOW_NODE, "text").strip(), "Порядок работы")
            finally:
                again.destroy()


if __name__ == "__main__":
    unittest.main()
