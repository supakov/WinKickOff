"""core/i18n.py: English is the source; translations are files, complete and consistent; the window switches language.

The English source text is the key. Every tr()/N_() string of the package must have a Russian and a
Ukrainian translation with the same {placeholders}; stale translations are not allowed. Languages are found
from the files, so an added file adds a language, and anything missing falls back to English.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
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
TRANSLATIONS = ("ru", "uk")


def source_strings() -> list[str]:
    found: list[str] = []
    for path in sorted((ROOT / "winkickoff").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_")
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                found.append(node.args[0].value)
    return list(dict.fromkeys(found))


def load_table(lang: str) -> dict[str, str]:
    data = json.loads((ROOT / "resources" / f"strings.{lang}.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


class TranslationFilesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sources = source_strings()
        cls.files = {lang: load_table(lang) for lang in TRANSLATIONS}

    def test_source_strings_are_english(self) -> None:
        self.assertEqual([s for s in self.sources if CYRILLIC.search(s)], [])
        self.assertFalse((ROOT / "resources" / "strings.en.json").exists())

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

    def test_style_and_language_names(self) -> None:
        for lang, table in self.files.items():
            for text in table.values():
                self.assertFalse(any(chr(c) in text for c in (0x2013, 0x2014)), text)
        self.assertEqual([t for t in self.files["uk"].values() if RUSSIAN_ONLY.search(t)], [])
        names = i18n.available_languages(ROOT / "resources", ROOT / "rules")
        self.assertEqual(names, {"en": "English", "ru": "Русский", "uk": "Українська"})


class TranslatorTest(unittest.TestCase):
    def tearDown(self) -> None:
        i18n.set_language("en")

    def test_switch_and_fallback(self) -> None:
        i18n.set_language("uk", ROOT / "resources", ROOT / "rules")
        self.assertEqual(i18n.language(), "uk")
        self.assertNotEqual(i18n.tr("Save"), "Save")
        self.assertEqual(i18n.tr("a string without a translation {0}", 1), "a string without a translation 1")
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        rule = catalog.rules["defender.pua"]
        self.assertNotEqual(i18n.catalog_texts().rule(rule, "title"), rule.title)
        i18n.set_language("xx", ROOT / "resources", ROOT / "rules")
        self.assertEqual(i18n.language(), "en")
        self.assertEqual(i18n.tr("Save"), "Save")
        self.assertEqual(i18n.catalog_texts().rule(rule, "title"), rule.title)

    def test_an_added_file_adds_a_language_and_gaps_fall_back_to_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            resources, rules = Path(tmp) / "resources", Path(tmp) / "rules"
            (rules / "lang").mkdir(parents=True)
            resources.mkdir()
            (resources / "strings.de.json").write_text(json.dumps({"_language": "Deutsch", "Save": "Speichern"}), encoding="utf-8")
            (rules / "lang" / "de.toml").write_text('["defender.pua"]\ntitle = "PUA blockiert"\n', encoding="utf-8")
            shutil.copy(ROOT / "rules" / "lang" / "uk.toml", rules / "lang" / "uk.toml")  # a catalog file alone is enough
            self.assertEqual(i18n.available_languages(resources, rules), {"en": "English", "de": "Deutsch", "uk": "Українська"})
            i18n.set_language("de", resources, rules)
            self.assertEqual(i18n.tr("Save"), "Speichern")
            self.assertEqual(i18n.tr("Close"), "Close")  # missing string: English
            catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
            texts = i18n.catalog_texts()
            self.assertEqual(texts.rule(catalog.rules["defender.pua"], "title"), "PUA blockiert")
            self.assertEqual(texts.rule(catalog.rules["defender.pua"], "summary"), catalog.rules["defender.pua"].summary)
            self.assertEqual(texts.rule(catalog.rules["uac.baseline"], "title"), catalog.rules["uac.baseline"].title)

    def test_empty_choice_follows_windows(self) -> None:
        code = i18n.resolve_language("", ROOT / "resources", ROOT / "rules")
        self.assertIn(code, i18n.available_languages(ROOT / "resources", ROOT / "rules"))


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
        i18n.set_language("en")

    def test_window_in_russian_and_switch_back_keeps_the_profile(self) -> None:
        from winkickoff.core.settings import Settings
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
            i18n.set_language("ru", paths.resources, paths.rules)
            win = MainWindow(paths, catalog, profile, resources, Settings(language="ru"))
            try:
                win.withdraw()
                self.assertEqual(win.tree.item(WORKFLOW_NODE, "text").strip(), i18n.tr("Workflow"))
                self.assertTrue(CYRILLIC.search(win.tree.item(WORKFLOW_NODE, "text")))
                self.assertEqual(win.tree.item("r:defender.pua", "text").strip(),
                                 i18n.catalog_texts().rule(catalog.rules["defender.pua"], "title"))
                win.toggle_item("r:defender.pua")  # an unsaved change must survive the switch
                win.change_language("en")
                state = win.restart_state
            finally:
                try:
                    win.destroy()
                except tk.TclError:
                    pass
            self.assertIsNotNone(state)
            self.assertEqual(json.loads((base / "settings.json").read_text(encoding="utf-8"))["language"], "en")
            i18n.set_language("en", paths.resources, paths.rules)
            again = MainWindow(paths, catalog, state["profile"], resources, Settings(language="en"))
            try:
                again.withdraw()
                again.restore_state(state)
                self.assertTrue(again.dirty)
                self.assertFalse(again.profile.is_enabled("defender.pua"))
                self.assertEqual(again.tree.item(WORKFLOW_NODE, "text").strip(), "Workflow")
            finally:
                again.destroy()


if __name__ == "__main__":
    unittest.main()
