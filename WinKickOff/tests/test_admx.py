"""core/admx.py: policy templates (ADMX, ADML) become rules of a subtree; import, store, build, apply, window.

The templates of the tests are written into a temporary folder; the real PolicyDefinitions folder of this
Windows is only read.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from winkickoff.core import admx, i18n
from winkickoff.core.apply import plan_apply, plan_revert, render_apply, render_audit, render_audit_block, render_revert, render_undo
from winkickoff.core.catalog import CatalogError, load_catalog, merge
from winkickoff.core.importer import import_xml
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.pscheck import check_scripts, powershell_path
from winkickoff.core.render import Renderer, render_action, ps_quote
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings
from winkickoff.core.validate import validate_profile, validate_xml
from winkickoff.core.verify import rollback_steps, verify_steps

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
# what a read-only audit must never contain (as in test_apply.py, plus the .NET writes of the list functions)
MUTATING = re.compile(r"\b(Set-ItemProperty|New-Item|Remove-Item|Remove-ItemProperty|Set-Reg|Set-RegList|Remove-Reg|"
                      r"SetValue|DeleteValue|CreateSubKey|reg\.exe)\b")
NS = "http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"

ADMX = r"""<?xml version="1.0" encoding="utf-8"?>
<policyDefinitions xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <policyNamespaces>
    <target prefix="wk" namespace="WinKickOff.Test"/>
  </policyNamespaces>
  <resources minRequiredRevision="1.0"/>
  <supportedOn><definitions><definition name="SUPPORTED_Test" displayName="$(string.SUPPORTED_Test)"/></definitions></supportedOn>
  <categories>
    <category name="Root" displayName="$(string.Root)"/>
    <category name="Child" displayName="$(string.Child)"><parentCategory ref="Root"/></category>
  </categories>
  <policies>
    <policy name="SimpleToggle" class="Machine" displayName="$(string.SimpleToggle)" explainText="$(string.SimpleToggle_Explain)" key="Software\Policies\WKTest" valueName="Toggle">
      <parentCategory ref="Child"/>
      <supportedOn ref="wk:SUPPORTED_Test"/>
      <enabledValue><decimal value="1"/></enabledValue>
      <disabledValue><decimal value="0"/></disabledValue>
    </policy>
    <policy name="With_Elements" class="User" displayName="$(string.WithElements)" explainText="$(string.WithElements_Explain)" key="Software\Policies\WKTest\User" valueName="Enabled" presentation="$(presentation.WithElements)">
      <parentCategory ref="Root"/>
      <elements>
        <decimal id="Seconds" valueName="Seconds" minValue="60" maxValue="600"/>
        <enum id="Mode" valueName="Mode">
          <item displayName="$(string.Mode_Block)"><value><decimal value="1"/></value></item>
          <item displayName="$(string.Mode_Audit)"><value><decimal value="2"/></value></item>
        </enum>
        <text id="Path" valueName="Path" expandable="true"/>
        <boolean id="Flag" valueName="Flag"/>
      </elements>
    </policy>
    <policy name="Pair" class="Both" displayName="$(string.Pair)" explainText="$(string.Pair_Explain)" key="Software\Policies\WKTest\Pair">
      <parentCategory ref="Child"/>
      <enabledList>
        <item valueName="A"><value><decimal value="1"/></value></item>
        <item key="Software\Policies\WKTest\Other" valueName="B"><value><string>on</string></value></item>
      </enabledList>
      <disabledList><item valueName="A"><value><decimal value="0"/></value></item></disabledList>
    </policy>
    <policy name="HasList" class="Machine" displayName="$(string.HasList)" key="Software\Policies\WKTest\List" valueName="On" presentation="$(presentation.HasList)">
      <enabledValue><decimal value="1"/></enabledValue>
      <disabledValue><decimal value="0"/></disabledValue>
      <elements><list id="Items" key="Software\Policies\WKTest\List\Items"/></elements>
    </policy>
    <policy name="Explicit" class="User" displayName="$(string.Explicit)" key="Software\Policies\WKTest\Pairs" presentation="$(presentation.Explicit)">
      <elements><list id="Zones" explicitValue="true" additive="true" expandable="true" valuePrefix="ignored"/></elements>
    </policy>
    <policy name="Numbered" class="Machine" displayName="$(string.Numbered)" key="Software\Policies\WKTest\Numbered">
      <elements>
        <list id="Urls" key="Software\Policies\WKTest\Numbered\Urls" valuePrefix=""/>
        <list id="Servers" key="Software\Policies\WKTest\Numbered\Servers" valuePrefix="Server" additive="true"/>
      </elements>
    </policy>
    <policy name="Lines" class="Machine" displayName="$(string.Lines)" key="Software\Policies\WKTest\Lines" presentation="$(presentation.Lines)">
      <elements><multiText id="Text" valueName="Text" required="true"/></elements>
    </policy>
    <policy name="DefenderList" class="Machine" displayName="$(string.DefenderList)" key="Software\Policies\WKTest">
      <elements><list id="All" key="Software\Policies\Microsoft\Windows Defender"/></elements>
    </policy>
    <policy name="BadList" class="Machine" displayName="$(string.BadList)" key="Software\Policies\WKTest">
      <elements><list id="Bad" key="Software\Policies\WKTest\$(Get-Date)"/></elements>
    </policy>
    <policy name="Unsafe" class="Machine" displayName="$(string.Unsafe)" key="Software\Policies\WKTest\$(Get-Date)" valueName="X"/>
    <policy name="SameAsBuiltin" class="Machine" displayName="$(string.Same)" key="Software\Policies\Microsoft\Windows Defender" valueName="PUAProtection">
      <enabledValue><decimal value="1"/></enabledValue>
      <disabledValue><decimal value="0"/></disabledValue>
    </policy>
  </policies>
</policyDefinitions>
"""

ADML_EN = """<?xml version="1.0" encoding="utf-8"?>
<policyDefinitionResources xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <displayName/><description/>
  <resources>
    <stringTable>
      <string id="SUPPORTED_Test">At least Windows 11</string>
      <string id="Root">Test root</string>
      <string id="Child">Test child</string>
      <string id="SimpleToggle">Turn on the toggle</string>
      <string id="SimpleToggle_Explain">First paragraph.

Second paragraph.</string>
      <string id="WithElements">Policy with elements</string>
      <string id="WithElements_Explain">Explains the elements.</string>
      <string id="Mode_Block">Block</string>
      <string id="Mode_Audit">Audit</string>
      <string id="Pair">Pair of lists</string>
      <string id="Pair_Explain">Lists.</string>
      <string id="HasList">Has a list</string>
      <string id="Explicit">Zones by name</string>
      <string id="Numbered">Numbered lists</string>
      <string id="Lines">Lines of text</string>
      <string id="DefenderList">A list in the key of a built-in rule</string>
      <string id="BadList">Unsafe list key</string>
      <string id="Unsafe">Unsafe key</string>
      <string id="Same">Same as built-in</string>
    </stringTable>
    <presentationTable>
      <presentation id="WithElements">
        <decimalTextBox refId="Seconds" defaultValue="120">Seconds</decimalTextBox>
        <dropdownList refId="Mode" defaultItem="1">Mode</dropdownList>
        <textBox refId="Path"><label>Folder</label><defaultValue>%TEMP%</defaultValue></textBox>
        <checkBox refId="Flag" defaultChecked="true">Flag it</checkBox>
      </presentation>
      <presentation id="HasList"><listBox refId="Items">Allowed sites</listBox></presentation>
      <presentation id="Explicit"><listBox refId="Zones">Zone of each site</listBox></presentation>
      <presentation id="Lines"><multiTextBox refId="Text">Text lines</multiTextBox></presentation>
    </presentationTable>
  </resources>
</policyDefinitionResources>
"""

ADML_RU = """<?xml version="1.0" encoding="utf-8"?>
<policyDefinitionResources xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <displayName/><description/>
  <resources>
    <stringTable>
      <string id="Root">Тестовый корень</string>
      <string id="SimpleToggle">Включить переключатель</string>
    </stringTable>
    <presentationTable>
      <presentation id="WithElements">
        <decimalTextBox refId="Seconds" defaultValue="120">Секунды</decimalTextBox>
      </presentation>
    </presentationTable>
  </resources>
</policyDefinitionResources>
"""

EVIL = """<?xml version="1.0"?>
<!DOCTYPE lol [<!ENTITY lol "lol">]>
<policyDefinitions xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions"/>
"""

GROUPS_TOML = """[[group]]
id = "g"
title = "G"
"""

RESERVED_RULE_TOML = r"""[[rule]]
id = "admx.x"
group = "g"
phase = "specialize"
title = "X"
level = "optional"
default = false
doc = "d"
summary = "s"
effect = "e"

[[rule.actions]]
type = "reg"
path = 'HKLM:\X'
name = "n"
kind = "DWord"
value = 1
"""

TOGGLE = "admx.winkickoff.test.simpletoggle"
ELEMENTS = "admx.winkickoff.test.with-elements"
PAIR = "admx.winkickoff.test.pair"
SAME = "admx.winkickoff.test.sameasbuiltin"
HASLIST = "admx.winkickoff.test.haslist"
EXPLICIT = "admx.winkickoff.test.explicit"
NUMBERED = "admx.winkickoff.test.numbered"
LINES = "admx.winkickoff.test.lines"
DEFLIST = "admx.winkickoff.test.defenderlist"
LIST_VALUES = {  # parameter values of the list policies used by the build, apply and window tests
    HASLIST: {"items": ["a.example", "https://*.example.com/it's"]},
    EXPLICIT: {"zones": ["Site=%TEMP%\\x", "Other = 2"]},
    NUMBERED: {"urls": ["one", "two"], "servers": ["srv"]},
    LINES: {"text": ["first line", "second line"]},
}


def write_templates(folder: Path) -> Path:
    (folder / "en-US").mkdir(parents=True)
    (folder / "ru-RU").mkdir()
    (folder / "de-DE").mkdir()  # a language the program has no translation for: not kept
    (folder / "wktest.admx").write_text(ADMX, encoding="utf-8")
    (folder / "en-US" / "wktest.adml").write_text(ADML_EN, encoding="utf-8")
    (folder / "ru-RU" / "wktest.adml").write_text(ADML_RU, encoding="utf-8")
    (folder / "de-DE" / "wktest.adml").write_text(ADML_EN, encoding="utf-8")
    (folder / "evil.admx").write_text(EVIL, encoding="utf-8")
    return folder


class AdmxTestCase(unittest.TestCase):
    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.templates = write_templates(self.tmp / "templates")
        self.store = self.tmp / "admx"
        self.base = load_catalog(ROOT / "rules", docs_root=ROOT.parent)

    def tearDown(self) -> None:
        self._tmp.cleanup()
        i18n.set_language("en")

    def imported(self, language: str = "en") -> tuple[admx.ImportInfo, object]:
        data = admx.read_templates(self.templates, ["en", "ru", "uk"])
        info = admx.save_import(self.store, self.templates, data, system=False, now=datetime(2026, 9, 30, 12, 0, 0))
        catalog, problems = admx.with_imports(self.base, self.store, [info.id], language)
        self.assertEqual(problems, [])
        return info, catalog


class ReadTemplatesTest(AdmxTestCase):
    def test_policies_skips_and_problems(self) -> None:
        data = admx.read_templates(self.templates, ["en", "ru", "uk"])
        self.assertEqual(data["cultures"], ["en-US", "ru-RU"])  # en-US first; de-DE is not a language of the program
        self.assertEqual([p["name"] for p in data["policies"]], ["SimpleToggle", "With_Elements", "Pair", "HasList", "Explicit",
                                                                "Numbered", "Lines", "DefenderList", "SameAsBuiltin"])
        self.assertEqual({(s["policy"], s["reason"]) for s in data["skipped"]}, {("BadList", "unsafe"), ("Unsafe", "unsafe")})
        self.assertEqual(len(data["problems"]), 1)
        self.assertIn("DTDs", data["problems"][0])
        self.assertEqual(set(data["categories"]), {"WinKickOff.Test:Root", "WinKickOff.Test:Child"})
        summary = dict(admx.skip_summary(data))
        self.assertEqual(summary[i18n.tr(admx.SKIP_REASONS["unsafe"])], 2)

    def test_a_folder_without_templates_is_refused(self) -> None:
        with self.assertRaises(admx.AdmxError):
            admx.read_templates(self.tmp, ["en"])

    def test_unsafe_text_is_refused(self) -> None:
        for good in ("Software\\Policies\\Microsoft\\Edge", "Name With Spaces", "a'b"):
            self.assertTrue(admx.safe_name(good), good)
        for bad in ("a$b", "a`b", 'a"b', "a" + chr(0x2019) + "b", "a\nb", ""):
            self.assertFalse(admx.safe_name(bad), repr(bad))
        self.assertFalse(admx.safe_value("x]]>y"))
        self.assertFalse(admx.safe_value("x" + chr(0x2018)))
        self.assertTrue(admx.safe_value("%TEMP%\\logs"))
        # quoting of the generated scripts doubles every quote PowerShell takes for a single quote
        self.assertEqual(ps_quote("a'b" + chr(0x2019) + "c"), "'a''b" + chr(0x2019) * 2 + "c'")


class CatalogPartTest(AdmxTestCase):
    def test_rules_groups_and_texts(self) -> None:
        info, catalog = self.imported("ru")
        root = "admx." + info.id
        self.assertIn(root, catalog.groups)
        self.assertEqual(catalog.groups[root].title, info.name)
        for group_id in catalog.groups:
            self.assertRegex(group_id, ID_RE)
        for rule_id in catalog.rules:
            self.assertRegex(rule_id, ID_RE)
        toggle = catalog.rules[TOGGLE]
        self.assertEqual(toggle.title, "Включить переключатель")  # from the ru-RU ADML
        self.assertEqual(toggle.summary, "First paragraph.")  # not translated in ru-RU: en-US
        self.assertIn("Second paragraph.", toggle.effect)
        self.assertEqual(toggle.versions, "At least Windows 11")
        self.assertEqual((toggle.phase, toggle.level, toggle.default, toggle.doc), ("specialize", "optional", False, ""))
        self.assertEqual([v for v, _ in toggle.params["state"].values], [1, 0])
        self.assertEqual(toggle.actions[0].fields, {"path": "HKLM:\\Software\\Policies\\WKTest", "name": "Toggle", "kind": "DWord", "value": "{state}"})
        # the category chain Root > Child under the computer side
        child = catalog.groups[toggle.group]
        self.assertEqual(child.title, "Test child")
        self.assertEqual(catalog.groups[child.parent].title, "Тестовый корень")
        self.assertEqual(catalog.groups[catalog.groups[child.parent].parent].id, root + ".machine")
        self.assertEqual(catalog.origins[TOGGLE].policy, "SimpleToggle")

    def test_elements_become_parameters_of_a_user_policy(self) -> None:
        _, catalog = self.imported("ru")
        rule = catalog.rules[ELEMENTS]
        self.assertEqual(rule.phase, "default-user")
        self.assertTrue(all(str(a.fields["path"]).startswith("DU:\\Software\\Policies\\WKTest\\User") for a in rule.actions))
        params = rule.params
        self.assertEqual((params["seconds"].type, params["seconds"].default, params["seconds"].min, params["seconds"].max), ("int", 120, 60, 600))
        self.assertEqual(params["seconds"].title, "Секунды")
        self.assertEqual(params["mode"].values, ((1, "Block"), (2, "Audit")))
        self.assertEqual(params["mode"].default, 2)  # defaultItem="1"
        self.assertEqual((params["path"].type, params["path"].default), ("string", "%TEMP%"))
        self.assertEqual((params["flag"].type, params["flag"].default), ("bool", True))
        kinds = {a.fields["name"]: a.fields["kind"] for a in rule.actions}
        self.assertEqual(kinds, {"Enabled": "DWord", "Seconds": "DWord", "Mode": "DWord", "Path": "ExpandString", "Flag": "DWord"})
        self.assertNotIn(ELEMENTS + ".off", catalog.rules)  # the Disabled state only removes values

    def test_a_policy_with_two_states_becomes_two_conflicting_rules(self) -> None:
        _, catalog = self.imported()
        on, off = catalog.rules[PAIR], catalog.rules[PAIR + ".off"]
        self.assertEqual((on.conflicts, off.conflicts), ((PAIR + ".off",), (PAIR,)))
        self.assertEqual(on.title, "Pair of lists (Enabled)")
        self.assertEqual([(a.type, a.fields["name"]) for a in on.actions], [("reg", "A"), ("reg", "B")])
        self.assertEqual([(a.type, a.fields["name"], a.fields.get("value")) for a in off.actions], [("reg", "A", 0)])
        self.assertEqual(on.phase, "specialize")  # class Both is written for the computer

    def test_same_registry_values_link_both_ways(self) -> None:
        _, catalog = self.imported()
        self.assertEqual(catalog.same_values(SAME), ["defender.pua"])
        self.assertIn(SAME, catalog.same_values("defender.pua"))
        self.assertEqual(catalog.same_values(TOGGLE), [])

    def test_a_second_import_of_the_same_templates_adds_no_duplicates(self) -> None:
        info, _ = self.imported()
        data = admx.read_templates(self.templates, ["en"])
        second = admx.save_import(self.store, self.templates, data, system=False, now=datetime(2026, 9, 30, 12, 0, 0))
        self.assertNotEqual(second.id, info.id)
        catalog, _ = admx.with_imports(self.base, self.store, [info.id, second.id], "en")
        self.assertEqual(sum(1 for r in catalog.rules if r == TOGGLE), 1)
        self.assertIn("already", catalog.groups["admx." + second.id].summary)


class StoreTest(AdmxTestCase):
    def test_save_list_load_delete(self) -> None:
        info, _ = self.imported()
        self.assertEqual(info.id, "folder-20260930-120000")
        self.assertEqual(info.name, "templates, 2026-09-30 12:00")
        self.assertEqual([i.id for i in admx.list_imports(self.store)], [info.id])
        meta = json.loads((self.store / info.id / admx.META_FILE).read_text(encoding="utf-8"))
        self.assertEqual((meta["format"], meta["policies"], meta["skipped"]), (2, 9, 2))
        with self.assertRaises(admx.AdmxError):
            admx.delete_import(self.store, "..")
        with self.assertRaises(admx.AdmxError):
            admx.load_import(self.store, "missing-1")
        catalog, problems = admx.with_imports(self.base, self.store, ["missing-1"], "en")
        self.assertIs(catalog, self.base)
        self.assertEqual(len(problems), 1)
        admx.delete_import(self.store, info.id)
        self.assertEqual(admx.list_imports(self.store), [])


class UseTest(AdmxTestCase):
    def test_build_writes_the_enabled_policies(self) -> None:
        _, catalog = self.imported()
        profile = Profile.from_catalog(catalog)
        for rule_id in (TOGGLE, ELEMENTS):
            profile.rules[rule_id].enabled = True
        profile.set_param(TOGGLE, "state", 0)
        resources = Resources.load(ROOT / "resources")
        result = Renderer(catalog, ROOT / "templates", resources.keyboards).build(profile, app_version="test")
        self.assertIn("Set-Reg -Path 'HKLM:\\Software\\Policies\\WKTest' -Name 'Toggle' -Type DWord -Value 0", result.xml)
        self.assertIn("Set-Reg -Path \"$du\\Software\\Policies\\WKTest\\User\" -Name 'Path' -Type ExpandString -Value '%TEMP%'", result.xml)
        self.assertIn(f"# [{ELEMENTS}]", result.xml)
        self.assertNotIn(PAIR, result.xml)

    def test_validation_warns_when_a_policy_repeats_an_enabled_built_in_rule(self) -> None:
        _, catalog = self.imported()
        profile = Profile.from_catalog(catalog)
        self.assertTrue(profile.is_enabled("defender.pua"))
        profile.rules[SAME].enabled = True
        warnings = [i for i in validate_profile(profile, catalog) if i.target == SAME]
        self.assertEqual(len(warnings), 1)
        self.assertIn("same registry value", warnings[0].message)

    def test_unchecked_policies_do_not_block_the_build(self) -> None:
        _, catalog = self.imported()
        profile, _ = Profile.load(ROOT / "profiles" / "preset-office.json", catalog)
        profile.set_param(ELEMENTS, "path", "")  # an empty value of an unchecked policy does not matter
        self.assertEqual([i for i in validate_profile(profile, catalog) if i.level == "error"], [])
        profile.rules[ELEMENTS].enabled = True  # optional text: empty is allowed
        self.assertEqual([i for i in validate_profile(profile, catalog) if i.level == "error"], [])
        profile.set_param(ELEMENTS, "path", "a]]>b")
        errors = [i for i in validate_profile(profile, catalog) if i.level == "error"]
        self.assertEqual([i.target for i in errors], [ELEMENTS])

    def test_the_prefix_is_reserved_for_templates(self) -> None:
        rules = self.tmp / "rules"
        rules.mkdir()
        (rules / "groups.toml").write_text(GROUPS_TOML, encoding="utf-8")
        (rules / "01-x.toml").write_text(RESERVED_RULE_TOML, encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "reserved"):
            load_catalog(rules)

    def test_profile_keeps_only_policies_in_use_and_restores_them(self) -> None:
        info, catalog = self.imported()
        profile = Profile.from_catalog(catalog)
        profile.rules[TOGGLE].enabled = True
        data = profile.to_dict(catalog)
        self.assertIn(TOGGLE, data["rules"])
        self.assertNotIn(ELEMENTS, data["rules"])  # off imported policies are "not configured": not written
        loaded, warnings = Profile.from_dict(data, catalog)
        self.assertEqual(warnings, [])  # an imported policy missing from the file is not a "new rule"
        self.assertTrue(loaded.is_enabled(TOGGLE))
        # without the templates the choice waits in "unknown" and comes back with them
        hidden, warnings = loaded.rebind(self.base)
        self.assertIn(TOGGLE, hidden.unknown)
        self.assertTrue(any("not loaded" in w for w in warnings))
        again, _ = Profile.from_dict(hidden.to_dict(self.base), catalog)
        self.assertTrue(again.is_enabled(TOGGLE))
        self.assertNotIn(TOGGLE, again.unknown)

    def test_apply_leaves_unchecked_policies_alone(self) -> None:
        info, catalog = self.imported()
        profile = Profile.from_catalog(catalog)
        profile.rules[TOGGLE].enabled = True
        plan = plan_apply(catalog, profile, ["g:admx." + info.id])
        self.assertEqual(plan.rule_ids, [TOGGLE])
        self.assertEqual(plan.reverts, [])  # nothing returned to defaults: unchecked means not configured
        self.assertEqual(plan.not_configured, len([r for r in catalog.rules if r.startswith("admx.")]) - 1)
        group_revert = plan_revert(catalog, ["g:admx." + info.id])
        self.assertEqual(group_revert.rules, [])
        self.assertGreater(group_revert.not_configured, 0)
        one = plan_revert(catalog, ["r:" + TOGGLE])
        self.assertEqual([p.rule.id for p in one.rules], [TOGGLE])
        self.assertIn("Remove-Reg", "\n".join(one.rules[0].lines))


class ListTest(AdmxTestCase):
    """List and multiText elements: parameters of type list, reg-list actions, build, apply, audit, import."""

    def profile_with_lists(self, catalog):  # type: ignore[no-untyped-def]
        profile = Profile.from_catalog(catalog)
        for rule_id, values in LIST_VALUES.items():
            profile.rules[rule_id].enabled = True
            for name, value in values.items():
                profile.set_param(rule_id, name, list(value))
        return profile

    def build(self, catalog, profile):  # type: ignore[no-untyped-def]
        resources = Resources.load(ROOT / "resources")
        return Renderer(catalog, TEMPLATES, resources.keyboards).build(profile, app_version="test")

    def test_list_elements_become_list_parameters(self) -> None:
        _, catalog = self.imported()
        rule = catalog.rules[HASLIST]
        items = rule.params["items"]
        self.assertEqual((items.type, items.default, items.required, items.pairs, items.title),
                         ("list", [], False, False, "Allowed sites"))
        # the list comes first: a list that is not additive deletes the other values of its key before they are written
        self.assertEqual([(a.type, a.fields) for a in rule.actions], [
            ("reg-list", {"path": "HKLM:\\Software\\Policies\\WKTest\\List\\Items", "kind": "String", "value": "{items}"}),
            ("reg", {"path": "HKLM:\\Software\\Policies\\WKTest\\List", "name": "On", "kind": "DWord", "value": 1})])
        off = catalog.rules[HASLIST + ".off"]  # the Disabled state leaves the key of the list without values
        self.assertEqual([(a.type, a.fields.get("value")) for a in off.actions], [("reg-list", []), ("reg", 0)])
        zones = catalog.rules[EXPLICIT]
        self.assertEqual((zones.phase, zones.params["zones"].pairs), ("default-user", True))
        self.assertEqual(zones.actions[0].fields, {"path": "DU:\\Software\\Policies\\WKTest\\Pairs", "kind": "ExpandString",
                                                   "value": "{zones}", "explicit": True, "additive": True})
        numbered = catalog.rules[NUMBERED]
        self.assertEqual([(a.fields.get("prefix"), a.fields.get("additive", False)) for a in numbered.actions],
                         [("", False), ("Server", True)])
        lines = catalog.rules[LINES]
        self.assertEqual((lines.params["text"].type, lines.params["text"].required), ("list", True))
        self.assertEqual(lines.actions[0].fields, {"path": "HKLM:\\Software\\Policies\\WKTest\\Lines", "name": "Text",
                                                   "kind": "MultiString", "value": "{text}"})

    def test_a_list_meets_every_value_of_its_key(self) -> None:
        _, catalog = self.imported()
        self.assertIn("defender.pua", catalog.same_values(DEFLIST))
        self.assertIn(DEFLIST, catalog.same_values("defender.pua"))
        self.assertEqual(catalog.same_values(NUMBERED), [])

    def test_build_writes_the_lists(self) -> None:
        _, catalog = self.imported()
        profile = self.profile_with_lists(catalog)
        self.assertEqual([i for i in validate_profile(profile, catalog) if i.level == "error"], [])
        result = self.build(catalog, profile)
        system = result.scripts["Setup-System.ps1"]
        self.assertIn("function Set-RegList", system)
        self.assertIn("Set-RegList -Path 'HKLM:\\Software\\Policies\\WKTest\\List\\Items' -Type String -Names "
                      "@('a.example','https://*.example.com/it''s') -Values @('a.example','https://*.example.com/it''s')", system)
        self.assertIn("Set-RegList -Path \"$du\\Software\\Policies\\WKTest\\Pairs\" -Type ExpandString "
                      "-Names @('Site','Other') -Values @('%TEMP%\\x','2') -Additive", system)
        self.assertIn("-Type String -Names @('1','2') -Values @('one','two')", system)
        self.assertIn("-Type String -Names @('Server1') -Values @('srv') -Additive", system)
        self.assertIn("-Name 'Text' -Type MultiString -Value @('first line','second line')", system)
        self.assertLess(system.index("-Names @('a.example'"), system.index("-Name 'On' -Type DWord -Value 1"))
        self.assertEqual([i for i in validate_xml(result.xml) if i.level == "error"], [])
        if powershell_path():
            with tempfile.TemporaryDirectory() as tmp:
                checked = check_scripts(result.scripts, Path(tmp))
            self.assertTrue(checked.ok, checked)

    def test_validation_of_list_parameters(self) -> None:
        _, catalog = self.imported()
        profile = self.profile_with_lists(catalog)

        def errors(rule_id: str, name: str, value: object) -> list[str]:
            profile.set_param(rule_id, name, value)
            found = [i.message for i in validate_profile(profile, catalog) if i.level == "error" and i.target == rule_id]
            profile.set_param(rule_id, name, list(LIST_VALUES[rule_id][name]))
            return found

        self.assertEqual(errors(LINES, "text", []), ["\"Lines of text\": 'Text lines' cannot be empty"])  # required
        self.assertEqual(errors(HASLIST, "items", []), [])  # an empty list is allowed: the key keeps no values
        for bad, fragment in ((["a", ""], "line 2 is empty"), (["a" + chr(9) + "b"], "line 1 is longer"),
                              (["x]]>y"], "line 1 is longer"), ("a", "list of lines"), ([1], "list of lines")):
            with self.subTest(value=bad):
                self.assertIn(fragment, errors(HASLIST, "items", bad)[0])
        for bad, fragment in ((["no equals sign"], "name=value"), (["=1"], "name=value"), (["$x=1"], "not allowed"),
                              (["a=1", "A = 2"], "used twice")):
            with self.subTest(value=bad):
                self.assertIn(fragment, errors(EXPLICIT, "zones", bad)[0])
        self.assertEqual(errors(EXPLICIT, "zones", ["a=", "b=c=d"]), [])  # an empty value and "=" inside a value are fine

    def test_apply_audit_and_revert(self) -> None:
        _, catalog = self.imported()
        profile = self.profile_with_lists(catalog)
        plan = plan_apply(catalog, profile, ["r:" + rule_id for rule_id in LIST_VALUES])
        self.assertEqual(sorted(plan.rule_ids), sorted(LIST_VALUES))
        self.assertEqual(plan.reverts, [])
        apply = render_apply(plan, profile, catalog, TEMPLATES, "test")
        self.assertIn("foreach ($n in @($present) + @($Names)) { Save-RegState", apply)  # every value touched is saved
        self.assertIn("-Names @('Site','Other')", apply)
        audit = render_audit(plan.rule_ids, profile, catalog, TEMPLATES, "test")
        self.assertIn(f"Test-RegList -Rule '{HASLIST}' -Path 'HKLM:\\Software\\Policies\\WKTest\\List\\Items' -Type String", audit)
        self.assertIn(f"Test-RegList -Rule '{EXPLICIT}' -Path 'HKCU:\\Software\\Policies\\WKTest\\Pairs'", audit)
        self.assertIn("-Additive -Note 'current user instead of the default profile'", audit)
        self.assertEqual(MUTATING.findall(audit), [])
        revert = plan_revert(catalog, ["r:" + HASLIST, "r:" + LINES])
        lines = {p.rule.id: p.lines for p in revert.rules}
        self.assertEqual(lines[HASLIST], ["Set-RegList -Path 'HKLM:\\Software\\Policies\\WKTest\\List\\Items' -Type String "
                                          "-Names @() -Values @()",
                                          "Remove-Reg -Path 'HKLM:\\Software\\Policies\\WKTest\\List' -Name 'On'"])
        self.assertEqual(lines[LINES], ["Remove-Reg -Path 'HKLM:\\Software\\Policies\\WKTest\\Lines' -Name 'Text'"])
        steps = verify_steps(catalog.rules[HASLIST], profile.params_for(catalog, HASLIST))
        self.assertIn("a.example = a.example; https://*.example.com/it's = https://*.example.com/it's and no other values", steps[0])
        if powershell_path():
            scripts = {"Apply.ps1": apply, "Audit.ps1": audit, "Undo-Apply.ps1": render_undo(TEMPLATES, profile, "test"),
                       "Revert.ps1": render_revert(revert, profile, TEMPLATES, "test")}
            with tempfile.TemporaryDirectory() as tmp:
                checked = check_scripts(scripts, Path(tmp))
            self.assertTrue(checked.ok, checked)

    def test_import_by_actions_reads_the_lists_back(self) -> None:
        _, catalog = self.imported()
        profile = self.profile_with_lists(catalog)
        xml = re.sub(r"<Profile .*?</Profile>", "", self.build(catalog, profile).xml, flags=re.S)  # a build without its profile
        restored, _ = import_xml(xml, catalog, Resources.load(ROOT / "resources").keyboards)
        for rule_id, values in LIST_VALUES.items():
            self.assertTrue(restored.is_enabled(rule_id), rule_id)
            expected = dict(values, zones=["Site=%TEMP%\\x", "Other=2"]) if rule_id == EXPLICIT else values
            self.assertEqual(restored.params_for(catalog, rule_id), expected)
        self.assertFalse(restored.is_enabled(HASLIST + ".off"))

    def test_imports_of_the_first_format_still_load(self) -> None:
        info, _ = self.imported()
        folder = self.store / info.id
        meta = json.loads((folder / admx.META_FILE).read_text(encoding="utf-8"))
        data = json.loads((folder / admx.DATA_FILE).read_text(encoding="utf-8"))
        data["skipped"].append({"file": "wktest.admx", "policy": "Old", "reason": "list"})  # skipped by 1.1.0-rc.1
        (folder / admx.DATA_FILE).write_text(json.dumps(data), encoding="utf-8")
        for fmt, loads in ((1, True), (3, False)):  # format 3 would come from a newer program
            with self.subTest(format=fmt):
                (folder / admx.META_FILE).write_text(json.dumps(dict(meta, format=fmt)), encoding="utf-8")
                self.assertEqual([i.id for i in admx.list_imports(self.store)], [info.id] if loads else [])
        (folder / admx.META_FILE).write_text(json.dumps(dict(meta, format=1)), encoding="utf-8")
        catalog, problems = admx.with_imports(self.base, self.store, [info.id], "en")
        self.assertEqual(problems, [])
        self.assertIn("1 policies with lists were skipped by an earlier version", catalog.groups["admx." + info.id].summary)


@unittest.skipUnless(admx.system_folder().is_dir(), "no PolicyDefinitions folder")
class SystemTemplatesTest(unittest.TestCase):
    """The templates of this Windows: read only, every policy converts and renders."""

    def test_every_imported_policy_renders(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        data = admx.read_templates(admx.system_folder(), ["en"])
        self.assertGreater(len(data["policies"]), 1000)
        self.assertEqual({s["reason"] for s in data["skipped"]} & set(admx.LEGACY_SKIPS), set())  # lists are converted
        info = admx.ImportInfo("system-test", "system", str(admx.system_folder()), "", "", tuple(data["cultures"]),
                               len(data["policies"]), len(data["skipped"]))
        base = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        part = admx.catalog_part(info, data, "en", set(base.rules))
        self.assertGreater(len(part.rules), len(data["policies"]))
        for rule in part.rules.values():
            self.assertRegex(rule.id, ID_RE)
            params = {name: p.default for name, p in rule.params.items()}
            for action in rule.actions:
                render_action(action, params)  # raises on a value the generator cannot write
            render_audit_block(rule, params)
            self.assertTrue(verify_steps(rule, params) and rollback_steps(rule, params), rule.id)
        for group_id in part.groups:
            self.assertRegex(group_id, ID_RE)
        lists = [r for r in part.rules.values() if not r.id.endswith(".off") and any(
            a.type == "reg-list" or a.fields.get("kind") == "MultiString" for a in r.actions)]
        self.assertGreater(len(lists), 150)
        # every list policy of this Windows with sample items: the generated scripts parse in Windows PowerShell
        catalog = merge(base, part.groups, part.rules, part.origins)
        profile = Profile.from_catalog(catalog)
        for rule in lists:
            profile.rules[rule.id].enabled = True
            for name, param in rule.params.items():
                if param.type == "list":
                    profile.set_param(rule.id, name, ["Name1=value 1", "Name2=%TEMP%"] if param.pairs else ["item 1", "https://*.example.com"])
        result = Renderer(catalog, TEMPLATES, Resources.load(ROOT / "resources").keyboards).build(profile, app_version="test")
        self.assertGreater(result.scripts["Setup-System.ps1"].count("Set-RegList -Path"), 100)
        if powershell_path():
            with tempfile.TemporaryDirectory() as tmp:
                checked = check_scripts(result.scripts, Path(tmp))
            self.assertTrue(checked.ok, checked)


try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk is not available")
class WindowTest(AdmxTestCase):
    def window(self):  # type: ignore[no-untyped-def]
        from winkickoff.ui.main_window import MainWindow

        base = self.tmp / "app"
        paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                         output=base / "output", logs=base / "logs")
        for folder in (paths.profiles, paths.output, paths.logs):
            folder.mkdir(parents=True)
        data = admx.read_templates(self.templates, ["en", "ru", "uk"])
        info = admx.save_import(paths.admx, self.templates, data, system=False, now=datetime(2026, 9, 30, 12, 0, 0))
        catalog, _ = admx.with_imports(self.base, paths.admx, [info.id], "en")
        profile = Profile.from_catalog(catalog)
        win = MainWindow(paths, catalog, profile, Resources.load(paths.resources),
                         Settings(language="en", theme="light", admx=[info.id]))
        win.withdraw()

        def close() -> None:
            try:
                win.destroy()
            except tk.TclError:
                pass  # already closed by a restart

        self.addCleanup(close)
        return win, info, paths

    def detail(self, win) -> str:  # type: ignore[no-untyped-def]
        return win.detail.get("1.0", "end")

    def test_subtree_links_and_group_check_box(self) -> None:
        win, info, _ = self.window()
        root = "g:admx." + info.id
        self.assertTrue(win.tree.exists(root))
        self.assertTrue(win.tree.exists("r:" + TOGGLE))
        win.show_item("r:" + SAME)
        text = self.detail(win)
        self.assertIn("Built into the catalog", text)
        self.assertIn(win.rule_title("defender.pua"), text)
        self.assertIn("Policy SameAsBuiltin of the template wktest.admx", text)
        win.show_item("r:defender.pua")
        self.assertIn("Also in imported templates", self.detail(win))
        self.assertEqual(win.toggle_item(root), [])  # the group never switches thousands of policies on
        self.assertFalse(any(win.profile.is_enabled(r) for r in win.catalog.rules if r.startswith("admx.")))
        win.toggle_item("r:" + PAIR)
        win.toggle_item("r:" + PAIR + ".off")  # conflicts: switching one state on switches the other off
        self.assertEqual((win.profile.is_enabled(PAIR), win.profile.is_enabled(PAIR + ".off")), (False, True))
        win.toggle_item(root)
        self.assertFalse(win.profile.is_enabled(PAIR + ".off"))
        menu = win.nametowidget(win.cget("menu"))
        labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "cascade"]
        self.assertIn("ADMX", labels)

    def test_import_and_hide_rebuild_the_window(self) -> None:
        win, info, paths = self.window()
        data = admx.read_templates(self.templates, ["en"])
        win.finish_import(self.templates, False, {"data": data})
        state = win.restart_state
        self.assertIsNotNone(state)
        new_ids = [i.id for i in admx.list_imports(paths.admx) if i.id != info.id]
        self.assertEqual(len(new_ids), 1)
        self.assertEqual(state["item"], "g:admx." + new_ids[0])
        self.assertEqual(win.settings.admx, [info.id, new_ids[0]])
        saved = json.loads(paths.settings_file.read_text(encoding="utf-8"))
        self.assertEqual(saved["admx"], [info.id, new_ids[0]])

    def test_list_parameter_box(self) -> None:
        win, _, _ = self.window()
        win.update()  # the selection events of the start would show another item and destroy the box
        win.show_item("r:" + HASLIST)
        box = win._param_boxes["items"]
        box.insert("1.0", " a.example \n\nhttps://*.example.com")  # spaces around items and empty lines are dropped
        win.update()
        self.assertEqual(win.profile.param(win.catalog, HASLIST, "items"), ["a.example", "https://*.example.com"])
        self.assertIn("-Names @('a.example','https://*.example.com')", self.detail(win))
        win.show_item("r:" + EXPLICIT)
        self.assertEqual(win._param_boxes["zones"].get("1.0", "end-1c"), "")
        win._param_boxes["zones"].insert("1.0", "no equals sign")
        win.update()
        self.assertIn("name=value", win.status_var.get())
        win.show_item("r:" + HASLIST)  # the box is filled from the profile again
        self.assertEqual(win._param_boxes["items"].get("1.0", "end-1c"), "a.example\nhttps://*.example.com")

    def test_hide_keeps_the_profile(self) -> None:
        win, info, _ = self.window()
        win.toggle_item("r:" + TOGGLE)
        win.show_templates(info.id, False)
        self.assertEqual(win.settings.admx, [])
        profile = win.restart_state["profile"]
        hidden, _ = profile.rebind(self.base)
        self.assertIn(TOGGLE, hidden.unknown)


if __name__ == "__main__":
    unittest.main()
