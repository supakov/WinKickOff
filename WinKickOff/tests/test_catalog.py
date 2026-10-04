"""core/catalog.py: the real catalog loads and is consistent; broken catalogs are rejected."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from winkickoff.core.catalog import PHASES, Catalog, CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]

GROUPS = """
[[group]]
id = "a"
title = "A"
order = 1
"""

RULE_OK = """
[[rule]]
id = "a.one"
group = "a"
phase = "specialize"
title = "One"
level = "baseline"
default = true
doc = "README.md"
summary = "s"
effect = "e"
[[rule.actions]]
type = "reg"
path = 'HKLM:\\SOFTWARE\\Test'
name = "X"
kind = "DWord"
value = 1
"""


RULE_LIST = """
[[rule]]
id = "a.list"
group = "a"
phase = "specialize"
title = "List"
level = "optional"
default = false
doc = "README.md"
summary = "s"
effect = "e"
[rule.params.sites]
type = "list"
title = "Sites"
default = ["a=1"]
pairs = true
required = true
[[rule.actions]]
type = "reg-list"
path = 'HKLM:\\SOFTWARE\\Policies\\Test\\Sites'
kind = "String"
explicit = true
value = "{sites}"
"""


def write_catalog(tmp: str, rules: str, groups: str = GROUPS) -> Path:
    root = Path(tmp)
    (root / "rules").mkdir()
    (root / "rules" / "groups.toml").write_text(textwrap.dedent(groups), encoding="utf-8")
    (root / "rules" / "10-test.toml").write_text(textwrap.dedent(rules), encoding="utf-8")
    (root / "README.md").write_text("doc", encoding="utf-8")
    return root


class RealCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)

    def test_loads_with_rules_and_groups(self) -> None:
        self.assertGreater(len(self.catalog.rules), 60)
        self.assertGreater(len(self.catalog.groups), 15)
        self.assertEqual(self.catalog.version, "0.6")

    def test_every_rule_has_actions_and_docs(self) -> None:
        for rule in self.catalog.rules.values():
            self.assertTrue(rule.actions, rule.id)
            self.assertTrue(rule.summary and rule.effect and rule.doc, rule.id)
            self.assertIn(rule.phase, PHASES)

    def test_asr_rules_require_asr_master(self) -> None:
        asr = [r for r in self.catalog.rules.values() if r.id.startswith("asr.")]
        self.assertEqual(len(asr), 18)
        for rule in asr:
            self.assertIn("defender.asr", rule.requires, rule.id)
        # asr.lsass and, since 26.09.2026, asr.usb-untrusted are off by default
        self.assertEqual(sum(1 for r in asr if r.default), 16)

    def test_removable_apps_count(self) -> None:
        apps = self.catalog.rules_in_group("apps.remove")
        self.assertEqual(len(apps), 34)  # 33 of v0.2 and OneDrive

    def test_search_finds_by_registry_name_and_tag(self) -> None:
        self.assertIn("defender.pua", self.catalog.search("PUAProtection"))
        self.assertIn("network.llmnr-off", self.catalog.search("responder"))
        self.assertEqual(self.catalog.search(""), self.catalog.order)

    def test_required_by_index(self) -> None:
        self.assertIn("asr.ransomware", self.catalog.required_by("defender.cloud"))
        self.assertIn("default-user.autoplay-off", self.catalog.required_by("removable.autorun-off"))


class BrokenCatalogTest(unittest.TestCase):
    def _expect(self, rules: str, fragment: str, groups: str = GROUPS) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, rules, groups)
            with self.assertRaises(CatalogError) as ctx:
                load_catalog(root / "rules", docs_root=root)
            self.assertIn(fragment, str(ctx.exception))

    def test_good_catalog_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, RULE_OK)
            catalog = load_catalog(root / "rules", docs_root=root)
            self.assertIsInstance(catalog, Catalog)
            self.assertEqual(catalog.order, ["a.one"])

    def test_duplicate_id(self) -> None:
        self._expect(RULE_OK + RULE_OK, "duplicate rule id")

    def test_unknown_group(self) -> None:
        self._expect(RULE_OK.replace('group = "a"', 'group = "zzz"'), "unknown group")

    def test_unknown_requires(self) -> None:
        self._expect(RULE_OK.replace('default = true', 'default = true\nrequires = ["nope"]'), "unknown rule")

    def test_cycle(self) -> None:
        two = RULE_OK.replace("a.one", "a.two").replace('default = true', 'default = true\nrequires = ["a.one"]')
        one = RULE_OK.replace('default = true', 'default = true\nrequires = ["a.two"]')
        self._expect(one + two, "dependency cycle")

    def test_missing_action_field(self) -> None:
        self._expect(RULE_OK.replace('kind = "DWord"\n', ""), "missing 'kind'")

    def test_unknown_action_type(self) -> None:
        self._expect(RULE_OK.replace('type = "reg"', 'type = "magic"'), "unknown type")

    def test_bad_phase(self) -> None:
        self._expect(RULE_OK.replace('phase = "specialize"', 'phase = "later"'), "unknown phase")

    def test_du_path_outside_default_user_phase(self) -> None:
        self._expect(RULE_OK.replace("HKLM:\\SOFTWARE\\Test", "DU:\\Software\\Test"), "DU: paths")

    def test_placeholder_without_param(self) -> None:
        self._expect(RULE_OK.replace("value = 1", 'value = "{n}"'), "undeclared params")

    def _load(self, rules: str) -> Catalog:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, rules)
            return load_catalog(root / "rules", docs_root=root)

    def test_sign_in_screen_values_only_where_hku_is_mounted(self) -> None:
        sign_in = RULE_OK.replace("HKLM:\\SOFTWARE\\Test", "HKU:\\.DEFAULT\\Test")
        self.assertIsNotNone(self._load(sign_in))  # phase specialize
        self._expect(sign_in.replace('phase = "specialize"', 'phase = "user-first-logon"'), "HKU:")

    def test_first_sign_in_and_post_oobe_scripts_run_only_registry_and_ps(self) -> None:
        service = RULE_OK.replace('type = "reg"\npath', 'type = "service"\nstart = 4\npath').replace(
            "path = 'HKLM:\\SOFTWARE\\Test'\nname = \"X\"\nkind = \"DWord\"\nvalue = 1", 'name = "Spooler"')
        self.assertIsNotNone(self._load(service))
        self._expect(service.replace('phase = "specialize"', 'phase = "post-oobe"'), "cannot run action type")

    def test_two_enum_parameters_that_must_differ(self) -> None:
        params = ('[rule.params.a]\ntype = "enum"\ntitle = "A"\ndefault = 1\nvalues = [ { value = 1 }, { value = 2 } ]\n'
                  '[rule.params.b]\ntype = "enum"\ntitle = "B"\ndefault = 2\nvalues = [ { value = 1 }, { value = 2 } ]\n'
                  'differs_from = "{other}"\nsame_allowed = [{same}]\n[[rule.actions]]')
        good = RULE_OK.replace("[[rule.actions]]", params.replace("{other}", "a").replace("{same}", "2"), 1)
        self.assertIsNotNone(self._load(good))
        self._expect(RULE_OK.replace("[[rule.actions]]", params.replace("{other}", "c").replace("{same}", ""), 1),
                     "not another enum")
        self._expect(RULE_OK.replace("[[rule.actions]]", params.replace("{other}", "a").replace("{same}", "3"), 1),
                     "same_allowed")

    def test_placeholders_only_in_values(self) -> None:
        """A key or a value name is never filled in: a parameter must not become part of a path."""
        with_param = RULE_OK.replace("[[rule.actions]]", '[rule.params.n]\ntype = "string"\ntitle = "N"\ndefault = "x"\n'
                                                         "[[rule.actions]]")
        self._expect(with_param.replace('name = "X"', 'name = "{n}"'), "placeholders are filled in only in")
        self._expect(with_param.replace("SOFTWARE\\Test", "SOFTWARE\\{n}"), "placeholders are filled in only in")

    def test_windows_default_must_fit_the_value(self) -> None:
        self._expect(RULE_OK.replace("value = 1", 'value = 1\ndefault = "5"'), "must be an integer")
        self._expect(RULE_OK.replace("value = 1", 'value = 1\ndefault = "none"'), "must be an integer")
        for good in ("5", '"absent"', '"unknown"'):
            with self.subTest(default=good), tempfile.TemporaryDirectory() as tmp:
                root = write_catalog(tmp, RULE_OK.replace("value = 1", f"value = 1\ndefault = {good}"))
                self.assertIn("a.one", load_catalog(root / "rules", docs_root=root).rules)

    def test_list_parameter_and_list_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, RULE_LIST)
            rule = load_catalog(root / "rules", docs_root=root).rules["a.list"]
            param = rule.params["sites"]
            self.assertEqual((param.type, param.default, param.pairs, param.required), ("list", ["a=1"], True, True))
            self.assertEqual(rule.actions[0].fields["value"], "{sites}")
        self._expect(RULE_LIST.replace('default = ["a=1"]', "default = 1"), "list of strings")
        self._expect(RULE_LIST.replace('kind = "String"', 'kind = "DWord"'), "kind must be one of")
        self._expect(RULE_LIST.replace("explicit = true", 'explicit = true\nprefix = "n"'), "exclude each other")
        self._expect(RULE_LIST.replace('value = "{sites}"', "value = [1, 2]"), "list of strings")
        self._expect(RULE_LIST.replace('value = "{sites}"', 'value = "{sites}"\ndefault = "none"'), "must be 'absent'")

    def test_missing_doc_file(self) -> None:
        self._expect(RULE_OK.replace('doc = "README.md"', 'doc = "nope.md"'), "doc file not found")

    def test_no_actions(self) -> None:
        self._expect(RULE_OK.split("[[rule.actions]]")[0], "no actions")


if __name__ == "__main__":
    unittest.main()
