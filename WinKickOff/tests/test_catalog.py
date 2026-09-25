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
        self.assertEqual(self.catalog.version, "0.3")

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
        self.assertEqual(sum(1 for r in asr if r.default), 17)

    def test_removable_apps_count(self) -> None:
        apps = self.catalog.rules_in_group("apps.remove")
        self.assertEqual(len(apps), 33)

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

    def test_missing_doc_file(self) -> None:
        self._expect(RULE_OK.replace('doc = "README.md"', 'doc = "nope.md"'), "doc file not found")

    def test_no_actions(self) -> None:
        self._expect(RULE_OK.split("[[rule.actions]]")[0], "no actions")


if __name__ == "__main__":
    unittest.main()
