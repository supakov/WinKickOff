"""core/catalog.py: the real catalog loads and is consistent; broken catalogs are rejected."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import PHASES, Catalog, CatalogError, load_catalog

ROOT = Path(__file__).resolve().parents[1]

GROUPS: list[dict[str, Any]] = [{"id": "a", "title": "A", "order": 1}]

RULE_OK: dict[str, Any] = {
    "id": "a.one", "group": "a", "phase": "specialize", "title": "One", "level": "baseline", "default": True,
    "doc": "README.md", "summary": "s", "effect": "e",
    "actions": [{"type": "reg", "path": "HKLM:\\SOFTWARE\\Test", "name": "X", "kind": "DWord", "value": 1}],
}

RULE_LIST: dict[str, Any] = {
    "id": "a.list", "group": "a", "phase": "specialize", "title": "List", "level": "optional", "default": False,
    "doc": "README.md", "summary": "s", "effect": "e",
    "params": {"sites": {"type": "list", "title": "Sites", "default": ["a=1"], "pairs": True, "required": True}},
    "actions": [{"type": "reg-list", "path": "HKLM:\\SOFTWARE\\Policies\\Test\\Sites", "kind": "String", "explicit": True,
                 "value": "{sites}"}],
}


def rule(base: dict[str, Any] = RULE_OK, *, action: dict[str, Any] | None = None, drop: tuple[str, ...] = (),
         drop_action: tuple[str, ...] = (), **changes: Any) -> dict[str, Any]:
    """A copy of base with changed rule fields, changed fields of its first action and removed keys."""
    out = copy.deepcopy(base)
    out.update(copy.deepcopy(changes))
    for key in drop:
        out.pop(key, None)
    if action or drop_action:
        first = out["actions"][0]
        first.update(copy.deepcopy(action or {}))
        for key in drop_action:
            first.pop(key, None)
    return out


def write_catalog(tmp: str, rules: list[dict[str, Any]] | str, groups: list[dict[str, Any]] | str = GROUPS) -> Path:
    """A catalog folder with groups.json and 10-test.json; a string is written as it is (a broken file)."""
    root = Path(tmp)
    (root / "rules").mkdir()
    for name, value, key in (("groups.json", groups, "groups"), ("10-test.json", rules, "rules")):
        text = value if isinstance(value, str) else json.dumps({"comment": ["test"], key: value}, indent=2)
        (root / "rules" / name).write_text(text, encoding="utf-8")
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

    def test_the_catalog_has_no_toml_left(self) -> None:
        self.assertEqual(sorted(p.name for p in (ROOT / "rules").rglob("*.toml")), [])
        self.assertTrue(all(rule.source.endswith(".json") for rule in self.catalog.rules.values()))

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

    def test_multi_line_scripts_are_lists_of_lines_in_the_file(self) -> None:
        script = self.catalog.rules["nav.removable-drives-once"].actions[0].fields["script"]
        self.assertTrue(script.startswith("foreach ($root in"))
        self.assertIn("\n", script)
        self.assertFalse(script.endswith("\n"))


class BrokenCatalogTest(unittest.TestCase):
    def _expect(self, rules: list[dict[str, Any]] | str, fragment: str, groups: list[dict[str, Any]] | str = GROUPS) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, rules, groups)
            with self.assertRaises(CatalogError) as ctx:
                load_catalog(root / "rules", docs_root=root)
            self.assertIn(fragment, str(ctx.exception))

    def _load(self, rules: list[dict[str, Any]]) -> Catalog:
        with tempfile.TemporaryDirectory() as tmp:
            root = write_catalog(tmp, rules)
            return load_catalog(root / "rules", docs_root=root)

    def test_good_catalog_loads(self) -> None:
        catalog = self._load([RULE_OK])
        self.assertIsInstance(catalog, Catalog)
        self.assertEqual(catalog.order, ["a.one"])
        self.assertEqual(catalog.rules["a.one"].source, "10-test.json")

    def test_duplicate_id(self) -> None:
        self._expect([RULE_OK, RULE_OK], "duplicate rule id")

    def test_unknown_group(self) -> None:
        self._expect([rule(group="zzz")], "unknown group")

    def test_unknown_requires(self) -> None:
        self._expect([rule(requires=["nope"])], "unknown rule")

    def test_cycle(self) -> None:
        self._expect([rule(requires=["a.two"]), rule(id="a.two", requires=["a.one"])], "dependency cycle")

    def test_missing_action_field(self) -> None:
        self._expect([rule(drop_action=("kind",))], "missing 'kind'")

    def test_unknown_action_type(self) -> None:
        self._expect([rule(action={"type": "magic"})], "unknown type")

    def test_bad_phase(self) -> None:
        self._expect([rule(phase="later")], "unknown phase")

    def test_du_path_outside_default_user_phase(self) -> None:
        self._expect([rule(action={"path": "DU:\\Software\\Test"})], "DU: paths")

    def test_placeholder_without_param(self) -> None:
        self._expect([rule(action={"value": "{n}"})], "undeclared params")

    def test_sign_in_screen_values_only_where_hku_is_mounted(self) -> None:
        sign_in = rule(action={"path": "HKU:\\.DEFAULT\\Test"})
        self.assertIsNotNone(self._load([sign_in]))  # phase specialize
        self._expect([rule(sign_in, phase="user-first-logon")], "HKU:")

    def test_first_sign_in_and_post_oobe_scripts_run_only_registry_and_ps(self) -> None:
        service = rule(actions=[{"type": "service", "name": "Spooler", "start": 4}])
        self.assertIsNotNone(self._load([service]))
        self._expect([rule(service, phase="post-oobe")], "cannot run action type")

    def test_two_enum_parameters_that_must_differ(self) -> None:
        def params(other: str, same: list[int]) -> dict[str, Any]:
            return {"a": {"type": "enum", "title": "A", "default": 1, "values": [{"value": 1}, {"value": 2}]},
                    "b": {"type": "enum", "title": "B", "default": 2, "values": [{"value": 1}, {"value": 2}],
                          "differs_from": other, "same_allowed": same}}
        self.assertIsNotNone(self._load([rule(params=params("a", [2]))]))
        self._expect([rule(params=params("c", []))], "not another enum")
        self._expect([rule(params=params("a", [3]))], "same_allowed")

    def test_placeholders_only_in_values(self) -> None:
        """A key or a value name is never filled in: a parameter must not become part of a path."""
        with_param = rule(params={"n": {"type": "string", "title": "N", "default": "x"}})
        self._expect([rule(with_param, action={"name": "{n}"})], "placeholders are filled in only in")
        self._expect([rule(with_param, action={"path": "HKLM:\\SOFTWARE\\{n}"})], "placeholders are filled in only in")

    def test_windows_default_must_fit_the_value(self) -> None:
        self._expect([rule(action={"default": "5"})], "must be an integer")
        self._expect([rule(action={"default": "none"})], "must be an integer")
        for good in (5, "absent", "unknown"):
            with self.subTest(default=good):
                self.assertIn("a.one", self._load([rule(action={"default": good})]).rules)

    def test_list_parameter_and_list_action(self) -> None:
        loaded = self._load([RULE_LIST]).rules["a.list"]
        param = loaded.params["sites"]
        self.assertEqual((param.type, param.default, param.pairs, param.required), ("list", ["a=1"], True, True))
        self.assertEqual(loaded.actions[0].fields["value"], "{sites}")
        sites = RULE_LIST["params"]["sites"]
        self._expect([rule(RULE_LIST, params={"sites": dict(sites, default=1)})], "list of strings")
        self._expect([rule(RULE_LIST, action={"kind": "DWord"})], "kind must be one of")
        self._expect([rule(RULE_LIST, action={"prefix": "n"})], "exclude each other")
        self._expect([rule(RULE_LIST, action={"value": [1, 2]})], "list of strings")
        self._expect([rule(RULE_LIST, action={"default": "none"})], "must be 'absent'")

    def test_missing_doc_file(self) -> None:
        self._expect([rule(doc="nope.md")], "doc file not found")

    def test_no_actions(self) -> None:
        self._expect([rule(actions=[])], "no actions")


class StrictFileTest(unittest.TestCase):
    """The catalog files are strict JSON with known keys only (since editor 1.3.0)."""

    _expect = BrokenCatalogTest._expect
    _load = BrokenCatalogTest._load

    def test_a_misspelt_field_is_an_error(self) -> None:
        self._expect([rule(requries=["a.two"])], "unknown fields ['requries']")
        self._expect([rule(params={"n": {"type": "string", "title": "N", "default": "x", "minimum": 1}})],
                     "unknown fields ['minimum']")
        self._expect([rule(params={"n": {"type": "enum", "title": "N", "default": 1,
                                         "values": [{"value": 1, "label": "One"}]}})], "unknown fields ['label']")
        self._expect([rule(action={"kinds": "DWord"})], "unknown fields ['kinds']")
        self._expect([RULE_OK], "unknown fields ['colour']", groups=[{"id": "a", "title": "A", "colour": "red"}])

    def test_only_the_list_and_a_comment_at_the_top(self) -> None:
        self._expect(json.dumps({"rules": [RULE_OK], "rule": []}), "unknown keys ['rule']")
        self._expect(json.dumps({"comment": "one line", "rules": [RULE_OK]}), "'comment' must be a list of strings")
        self._expect(json.dumps([RULE_OK]), "must hold a JSON object")
        self._expect(json.dumps({"rules": {"a.one": RULE_OK}}), "'rules' must be a list of objects")

    def test_json_that_python_would_accept_silently_is_refused(self) -> None:
        text = json.dumps({"rules": [RULE_OK]})
        self._expect(text.replace('"group": "a"', '"group": "a", "group": "a"'), "appears twice")
        self._expect(text.replace('"risk"', '"x"').replace('"effect": "e"', '"effect": "e", "risk": null'), "is null")
        self._expect(text.replace('"value": 1', '"value": NaN'), "NaN")
        self._expect(chr(0xFEFF) + text, "byte order mark")
        self._expect(text[:-5], "JSON syntax")

    def test_text_fields_must_be_strings(self) -> None:
        self._expect([rule(risk=5)], "'risk' must be a string")
        self._expect([rule(note=["x"])], "'note' must be a string")
        self._expect([rule(action={"path": 5})], "'path' must be a string")
        self._expect([RULE_OK], "'order' must be an integer", groups=[{"id": "a", "title": "A", "order": "1"}])

    def test_scripts_of_several_lines_and_notes(self) -> None:
        script = rule(note="A remark for the people who edit the catalog.",
                      actions=[{"type": "ps", "script": ["if ($true) {", "    Write-Log 'x'", "}"]}])
        loaded = self._load([script]).rules["a.one"]
        self.assertEqual(loaded.actions[0].fields["script"], "if ($true) {\n    Write-Log 'x'\n}")
        self._expect([rule(actions=[{"type": "ps", "script": ["a", 1]}])], "a ps script is a string or a list of lines")
        self._expect([rule(actions=[{"type": "ps", "script": ["a\nb"]}])], "a ps script is a string or a list of lines")

    def test_parameter_fields_by_type(self) -> None:
        def param(**fields):  # type: ignore[no-untyped-def]
            return rule(params={"n": fields})

        enum = {"type": "enum", "title": "N", "default": 1, "values": [{"value": 1}, {"value": 2}]}
        self._expect([param(**dict(enum, default=[1]))], "default not in values")
        self._expect([param(**dict(enum, values=[{"value": [1]}]))], "a 'value' (a string or an integer)")
        self._expect([param(**dict(enum, values=[{"value": True}], default=True))], "a 'value' (a string or an integer)")
        self._expect([param(**dict(enum, differs_from="m", same_allowed=[[1]]))], "same_allowed")
        self._expect([param(**dict(enum, min=1))], "do not apply to a parameter of type enum")
        integer = {"type": "int", "title": "N", "default": 5}
        self._expect([param(**dict(integer, min="0"))], "min and max must be integers")
        self._expect([param(**dict(integer, max=True))], "min and max must be integers")
        self._expect([param(**dict(integer, values=[{"value": 1}]))], "do not apply to a parameter of type int")
        self._expect([param(type="string", title="N", default=5)], "string default must be a string")
        self._expect([param(type="string", title="N", default="x", pairs=True)], "do not apply")
        self._expect([param(type="string", title="N", default="x", required="no")], "'required' must be true or false")
        self._expect([param(type="bool", title="N", default=True, required=False)], "do not apply")
        loaded = self._load([param(type="string", title="N", default="", required=False)]).rules["a.one"]
        self.assertFalse(loaded.params["n"].required)  # an optional text: the check accepts it empty

    def test_a_field_of_an_unexpected_type_names_the_file_and_the_rule(self) -> None:
        self._expect([rule(actions=[{"type": {"x": 1}}])], "[10-test.json] <a.one>")


if __name__ == "__main__":
    unittest.main()
