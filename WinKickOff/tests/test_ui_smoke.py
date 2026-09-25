"""ui/main_window.py smoke test: tree clicks, profile save and load, build to a file.

The window is shown fully transparent and outside the screen (Treeview computes row geometry
only for a mapped window); all files go to a temporary folder. Dialogs are replaced by mocks.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001 - no display or no Tk: the test is skipped
    TK_OK = False

from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(TK_OK, "Tk is not available")
class MainWindowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from winkickoff.ui.main_window import MainWindow

        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                             output=base / "output", logs=base / "logs")
        for folder in (cls.paths.profiles, cls.paths.output, cls.paths.logs):
            folder.mkdir(parents=True)
        cls.catalog = load_catalog(cls.paths.rules, docs_root=cls.paths.docs_root)
        cls.office_path = ROOT / "profiles" / "preset-office.json"
        profile, _ = Profile.load(cls.office_path, cls.catalog)
        cls.win = MainWindow(cls.paths, cls.catalog, profile, Resources.load(cls.paths.resources))
        cls.win.attributes("-alpha", 0.0)
        cls.win.geometry("1200x800+-4000+-4000")
        cls.win.update()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.win.destroy()
        cls.tmp.cleanup()

    def setUp(self) -> None:
        profile, _ = Profile.load(self.office_path, self.catalog)
        self.win.set_profile(profile, dirty=False)
        self.win.update()

    # ----------------------------------------------------------------- helpers

    def first_group(self) -> str:
        return next(i for i in self.win.tree.get_children("") if i.startswith("g:"))

    def point(self, item: str, element: str) -> tuple[int, int]:
        box = self.win.tree.bbox(item)
        if not box:
            self.skipTest("Treeview has no geometry in this session")
        y = box[1] + box[3] // 2
        for x in range(0, 120):
            if element in str(self.win.tree.identify_element(x, y)):
                return x, y
        self.fail(f"no '{element}' in row {item}")

    def click(self, x: int, y: int) -> None:
        self.win.tree.event_generate("<Button-1>", x=x, y=y, when="now")
        self.win.tree.event_generate("<ButtonRelease-1>", x=x, y=y, when="now")
        self.win.update()

    # ----------------------------------------------------------------- tests

    def test_tree_structure(self) -> None:
        from winkickoff.ui.main_window import WORKFLOW_NODE

        top = self.win.tree.get_children("")
        self.assertEqual(top[0], WORKFLOW_NODE)
        self.assertIn("data:install", top)
        rules = [i for i in self.win._all_items() if i.startswith("r:")]
        self.assertEqual(len(rules), len(self.catalog.rules))

    def test_plus_only_opens_the_branch(self) -> None:
        group = self.first_group()
        counts = self.win._group_counts(group[2:])
        was_open = bool(self.win.tree.item(group, "open"))
        self.click(*self.point(group, "indicator"))
        self.assertEqual(self.win._group_counts(group[2:]), counts)
        self.assertNotEqual(bool(self.win.tree.item(group, "open")), was_open)
        self.assertFalse(self.win.dirty)

    def test_check_box_toggles_the_group(self) -> None:
        group = self.first_group()
        on, total = self.win._group_counts(group[2:])
        x, y = self.point(group, "image")
        self.click(x, y)
        expected = 0 if on == total else total
        self.assertEqual(self.win._group_counts(group[2:])[0], expected)
        self.assertTrue(self.win.dirty)
        self.assertTrue(self.win.title().endswith("*"))

    def test_rule_toggle_with_cascade_is_listed(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if r.default and any(r.id in o.requires and o.default for o in self.catalog.rules.values()))
        changes = self.win.toggle_item("r:" + rule.id)
        self.assertFalse(self.win.profile.is_enabled(rule.id))
        dependents = [c for c in changes if c.rule_id != rule.id]
        self.assertTrue(dependents)
        rows = [self.win.messages.item(i, "values") for i in self.win.messages.get_children()]
        self.assertEqual(len(rows), len(dependents))
        self.assertIn("автоматически", self.win.status_var.get())

    def test_save_as_and_reopen(self) -> None:
        self.win.toggle_item("r:network.netbios-off")
        target = self.paths.profiles / "Бухгалтерия.json"
        with mock.patch("winkickoff.ui.main_window.filedialog.asksaveasfilename", return_value=str(target)):
            self.assertTrue(self.win.save_profile())  # a preset is never overwritten: Save turns into Save as
        self.assertTrue(target.exists())
        self.assertFalse(self.win.dirty)
        self.assertEqual(self.win.profile.name, "Бухгалтерия")
        self.assertIn("Бухгалтерия", self.win.profile_box.cget("values"))

        self.assertTrue(self.win.load_profile_file(self.office_path))
        self.assertFalse(self.win.profile.is_enabled("network.netbios-off"))
        self.assertTrue(self.win.load_profile_file(target))
        self.assertTrue(self.win.profile.is_enabled("network.netbios-off"))

    def test_preset_names_are_reserved(self) -> None:
        target = self.paths.profiles / "preset-mine.json"
        with mock.patch("winkickoff.ui.main_window.filedialog.asksaveasfilename", return_value=str(target)), \
             mock.patch("winkickoff.ui.main_window.messagebox.showerror") as error:
            self.assertFalse(self.win.save_profile_as())
        error.assert_called_once()
        self.assertFalse(target.exists())

    def test_int_parameter_goes_to_the_profile(self) -> None:
        rule, param = next(
            (r, p) for r in self.catalog.rules.values() for p in r.params.values()
            if p.type == "int" and p.min is not None and p.max is not None and p.max > p.default
        )
        self.win.show_item("r:" + rule.id)
        var = self.win._param_vars[list(rule.params).index(param.name)]
        var.set(str(param.default + 1))
        self.assertEqual(self.win.profile.param(self.catalog, rule.id, param.name), param.default + 1)
        self.assertTrue(self.win.dirty)
        var.set(str(param.max + 1))  # out of range: refused, the last valid value stays
        self.assertEqual(self.win.profile.param(self.catalog, rule.id, param.name), param.default + 1)
        var.set(str(param.default))  # back to the default: the override disappears from the profile
        self.assertNotIn(param.name, self.win.profile.rules[rule.id].params)

    def test_parameter_change_is_marked(self) -> None:
        rule, param = next(
            (r, p) for r in self.catalog.rules.values() for p in r.params.values()
            if p.type == "int" and p.max is not None and p.max > p.default
        )
        self.win.show_item("r:" + rule.id)
        mark = self.win._param_marks[param.name]
        self.assertEqual(str(mark.cget("text")), "")
        self.win._param_vars[list(rule.params).index(param.name)].set(str(param.default + 1))
        self.assertEqual(str(mark.cget("text")), "изменено")
        self.assertIn("changed", self.win.tree.item("r:" + rule.id, "tags"))

    def detail_links(self) -> dict[str, str]:
        """Text of every link in the description, by tag name."""
        out = {}
        for name in self.win._link_tags:
            ranges = self.win.detail.tag_ranges(name)
            out[name] = self.win.detail.get(ranges[0], ranges[1])
        return out

    def click_link(self, name: str) -> None:
        index = self.win.detail.tag_ranges(name)[0]
        self.win.detail.see(index)
        self.win.update()
        x, y, _w, h = self.win.detail.bbox(index)
        # Text tag bindings follow the "current" mark, which only mouse motion updates.
        self.win.detail.event_generate("<Motion>", x=x + 2, y=y + h // 2, when="now")
        self.win.detail.event_generate("<Button-1>", x=x + 2, y=y + h // 2, when="now")
        self.win.update()

    def test_dependency_link_opens_the_rule(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if r.requires)
        self.win.select_node("r:" + rule.id)
        self.win.update()
        target_title = self.catalog.rules[rule.requires[0]].title
        name = next(n for n, text in self.detail_links().items() if target_title in text)
        self.click_link(name)
        self.assertEqual(self.win.tree.selection(), ("r:" + rule.requires[0],))

    def test_reference_link_opens_the_card(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if "#" in r.doc)
        self.win.select_node("r:" + rule.id)
        self.win.update()
        name = next(n for n, text in self.detail_links().items() if rule.doc in text)
        with mock.patch("winkickoff.ui.main_window.os.startfile", create=True) as startfile:
            self.click_link(name)
        startfile.assert_called_once_with(self.paths.docs_root / rule.doc.split("#", 1)[0])

    def test_verify_and_rollback_are_always_shown(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if not r.verify and r.actions[0].type == "reg")
        self.win.show_item("r:" + rule.id)
        text = self.win.detail.get("1.0", "end")
        self.assertIn("Сформировано по действиям правила", text)
        self.assertIn("reg query", text)

    def test_check_catalog(self) -> None:
        issues = self.win.check_catalog()
        self.assertEqual([i.level for i in issues], ["info"])
        self.assertIn("ошибок 0", self.win.status_var.get())

    @unittest.skipUnless((ROOT.parent / "autounattend.xml").exists(), "v0.2 answer file not found")
    def test_import_hand_written_v02(self) -> None:
        self.assertTrue(self.win.import_file(ROOT.parent / "autounattend.xml"))
        self.assertEqual(self.win.profile.name, "Импорт autounattend")
        self.assertTrue(self.win.dirty)
        office, _ = Profile.load(self.office_path, self.catalog)
        self.assertEqual(self.win.profile.enabled_ids(), office.enabled_ids())
        rows = [self.win.messages.item(i, "values")[2] for i in self.win.messages.get_children()]
        self.assertTrue(any("по действиям" in r for r in rows), rows)

    def test_reserved_account_name_is_refused(self) -> None:
        self.win.show_item("data:accounts")
        form = self.win.forms["data:accounts"]
        form.tree.selection_set("1")
        self.win.update()
        form.name.set("Administrator")
        form._apply()
        self.assertEqual(self.win.profile.accounts[1].name, "User")
        self.assertIn("зарезервированное", form.error.get())
        form.name.set("Kasa")
        form._apply()
        self.assertEqual(self.win.profile.accounts[1].name, "Kasa")
        self.assertTrue(self.win.dirty)

    def test_check_and_build_to_file(self) -> None:
        issues = self.win.check()
        self.assertFalse(any(i.level == "error" for i in issues), [i.message for i in issues if i.level == "error"])
        result, issues = self.win.run_checks(with_powershell=False)
        self.assertIsNotNone(result)
        target = self.paths.output / "autounattend.xml"
        self.win.write_build(result, target)
        self.assertEqual(target.read_bytes(), result.xml.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
