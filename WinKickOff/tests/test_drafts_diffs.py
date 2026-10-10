"""1.4.0-rc.2: the draft of the open profile, diff profiles and their merge, the comparison as a tree with the apply of
the changes only, and the read of this PC as administrator. Nothing runs PowerShell or asks for elevation here: the
UAC call, the audit and the dialogs are replaced."""

from __future__ import annotations

import quiet_tk  # noqa: F401 - first: every window of these tests stays invisible
import json
import logging
import tempfile
import time
import tkinter as tk
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from winkickoff.core import apply as apply_module
from winkickoff.core import i18n
from winkickoff.core.catalog import load_catalog
from winkickoff.core.diffprofile import is_empty, load_diff, make_diff, merge_diff, save_diff
from winkickoff.core.draft import draft_path, load_draft, save_draft
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings

from test_capture import fake_report

ROOT = Path(__file__).resolve().parents[1]
OFFICE = ROOT / "profiles" / "preset-office.json"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)

    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        base = self.tmp / "app"
        self.paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                              output=base / "output", logs=base / "logs")
        for folder in (self.paths.profiles, self.paths.output, self.paths.logs):
            folder.mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        i18n.set_language("en")

    def office(self) -> Profile:
        return Profile.load(OFFICE, self.catalog)[0]

    def changed(self) -> Profile:
        profile = self.office()
        profile.rules["network.netbios-off"].enabled = True
        profile.set_param("accounts.inactivity-lock", "seconds", 600)
        profile.install["time_zone"] = "UTC"
        return profile

    def window(self, profile: Profile | None = None):  # type: ignore[no-untyped-def]
        from winkickoff.ui.main_window import MainWindow

        win = MainWindow(self.paths, self.catalog, profile or self.office(), Resources.load(self.paths.resources),
                         Settings(language="en", theme="light"))
        win.withdraw()

        def close() -> None:
            try:
                win.destroy()
            except tk.TclError:
                pass

        self.addCleanup(close)
        return win


class DraftTest(Base):
    def test_a_draft_comes_back_with_its_path(self) -> None:
        profile = self.changed()
        profile.path = self.paths.profiles / "mine.json"
        save_draft(self.paths.root, profile, self.catalog)
        self.assertEqual([p.name for p in self.paths.root.iterdir() if p.is_file()], ["draft.json"])
        loaded, _ = load_draft(self.paths.root, self.catalog)
        self.assertEqual(loaded.path, profile.path)
        self.assertEqual(loaded.diff(profile, self.catalog), [])
        draft_path(self.paths.root).write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_draft(self.paths.root, self.catalog)

    def test_closing_with_unsaved_changes_writes_the_draft_and_asks_nothing(self) -> None:
        win = self.window()
        win.toggle_item("r:network.netbios-off")
        self.assertTrue(win.dirty)
        with mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
            win.on_close()
        boxes.askyesnocancel.assert_not_called()
        loaded, _ = load_draft(self.paths.root, self.catalog)
        self.assertTrue(loaded.is_enabled("network.netbios-off"))

    def test_saving_or_dropping_the_changes_deletes_the_draft(self) -> None:
        win = self.window()
        win.toggle_item("r:network.netbios-off")
        self.assertTrue(win.write_draft())
        self.assertTrue(draft_path(self.paths.root).exists())
        win.save_profile_to(self.paths.profiles / "mine.json")
        self.assertFalse(draft_path(self.paths.root).exists())
        win.toggle_item("r:network.netbios-off")
        win.write_draft()
        with mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
            boxes.askyesnocancel.return_value = False  # "No": drop the changes
            self.assertTrue(win.confirm_discard())
        self.assertFalse(draft_path(self.paths.root).exists())

    def test_the_next_start_opens_the_draft_unsaved(self) -> None:
        from winkickoff import app

        save_draft(self.paths.root, self.changed(), self.catalog)
        Settings(language="en", theme="light").save(self.paths.settings_file)
        with mock.patch.object(app, "app_paths", return_value=self.paths), mock.patch.object(app, "_enable_dpi_awareness"):
            win = app.create_app(withdraw=True)
        try:
            self.assertTrue(win.dirty)
            self.assertTrue(win.profile.is_enabled("network.netbios-off"))
            messages = [win.messages.item(i, "values")[2] for i in win.messages.get_children()]
            self.assertTrue(any("restored from the draft" in m for m in messages), messages)
        finally:
            try:
                win.destroy()
            except tk.TclError:
                pass
            for handler in list(logging.getLogger().handlers):
                if isinstance(handler, RotatingFileHandler) and Path(handler.baseFilename).is_relative_to(self.paths.root):
                    logging.getLogger().removeHandler(handler)
                    handler.close()


class DiffProfileTest(Base):
    def test_a_diff_holds_only_the_differences_and_merges_back(self) -> None:
        mine, base = self.changed(), self.office()
        diff = make_diff(mine, base, self.catalog)
        self.assertEqual(diff["rules"], {"network.netbios-off": {"enabled": True},
                                         "accounts.inactivity-lock": {"params": {"seconds": 600}}})
        self.assertEqual(diff["install"], {"time_zone": "UTC"})
        self.assertEqual((diff["languages"], "accounts" in diff), ({}, False))
        self.assertTrue(is_empty(make_diff(base, self.office(), self.catalog)))
        path = self.tmp / "changes.wkdiff"
        save_diff(path, diff)
        target = self.office()
        changed, warnings = merge_diff(target, load_diff(path), self.catalog)
        self.assertEqual((changed, warnings), (3, []))
        self.assertEqual(target.diff(mine, self.catalog), [])

    def test_what_a_merge_cannot_take_is_a_warning(self) -> None:
        diff = {"format": "winkickoff-diff", "rules": {"no.such-rule": {"enabled": True},
                                                       "accounts.inactivity-lock": {"params": {"seconds": 5}}},
                "install": {"colour": "red"}, "languages": {}}
        target = self.office()
        changed, warnings = merge_diff(target, diff, self.catalog)
        self.assertEqual(changed, 0)
        self.assertEqual(len(warnings), 3)
        for text in ("[]", json.dumps({"format": "winkickoff-diff", "rules": []})):
            path = self.tmp / "bad.wkdiff"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValueError):
                load_diff(path)


class ComparisonWindowTest(Base):
    def test_the_tree_shows_groups_rules_and_descriptions_and_applies_only_the_changes(self) -> None:
        win = self.window(self.changed())
        window = win.open_comparison(self.office(), "saved")
        tree = window.comparison_tree
        tops = list(tree.get_children(""))
        self.assertIn("gdata", tops)  # the time zone
        rule_nodes = [n for top in tops for n in tree.get_children(top) if n.startswith("n")]
        self.assertIn("nnetwork.netbios-off", rule_nodes)
        self.assertIn("naccounts.inactivity-lock", rule_nodes)
        tree.selection_set("nnetwork.netbios-off")
        window.update()
        self.assertIn("network.netbios-off", window.comparison_detail.get("1.0", tk.END))
        self.assertEqual(window.changed_rules, ["r:accounts.inactivity-lock", "r:network.netbios-off"])
        with mock.patch("winkickoff.ui.main_window.plan_apply", wraps=apply_module.plan_apply) as plan, \
                mock.patch.object(win, "_ensure_apply_allowed", return_value=True), \
                mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
            boxes.askyesno.return_value = False  # the person declines: nothing starts
            self.assertFalse(win.apply_now(window.changed_rules))
        self.assertEqual(plan.call_args[0][2], ["r:accounts.inactivity-lock", "r:network.netbios-off"])

    def test_merge_from_the_menu_marks_the_profile_changed(self) -> None:
        path = self.tmp / "changes.wkdiff"
        save_diff(path, make_diff(self.changed(), self.office(), self.catalog))
        win = self.window()
        self.assertEqual(win.merge_diff_file(path), 3)
        self.assertTrue(win.dirty)
        self.assertTrue(win.profile.is_enabled("network.netbios-off"))


class ElevatedReadTest(Base):
    def test_a_declined_prompt_is_a_clear_error(self) -> None:
        fake = SimpleNamespace(shell32=SimpleNamespace(ShellExecuteExW=lambda _info: 0),
                               kernel32=SimpleNamespace(GetLastError=lambda: apply_module.ERROR_CANCELLED))
        with mock.patch.object(apply_module.ctypes, "windll", fake, create=True), \
                mock.patch.object(apply_module.sys, "platform", "win32"):
            with self.assertRaisesRegex(RuntimeError, "Administrator rights were not given"):
                apply_module.run_audit_elevated("exit 0", self.paths.logs)

    def test_the_menu_reads_as_administrator(self) -> None:
        win = self.window()
        with mock.patch.object(apply_module, "run_audit_elevated", return_value=fake_report(self.catalog)) as elevated, \
                mock.patch("winkickoff.ui.main_window.run_audit") as plain, \
                mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
            boxes.askokcancel.return_value = True
            win.read_this_pc(elevated=True)
            deadline = time.monotonic() + 30
            while (win._busy or win.profile.name == "Office") and time.monotonic() < deadline:
                win.update()
                time.sleep(0.05)
        plain.assert_not_called()
        self.assertEqual(elevated.call_count, 1)
        self.assertIn("As administrator", boxes.askokcancel.call_args[0][1])
        self.assertEqual(win.profile.name, "Settings of REF-PC")


if __name__ == "__main__":
    unittest.main()
