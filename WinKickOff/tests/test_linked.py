"""core/linked.py and the window: imported policies follow the built-in rules that set the same values (T21)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from winkickoff.core import admx, i18n, linked
from winkickoff.core.catalog import load_catalog
from winkickoff.core.paths import AppPaths
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.settings import Settings

ROOT = Path(__file__).resolve().parents[1]

ADMX = r"""<?xml version="1.0" encoding="utf-8"?>
<policyDefinitions xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <policyNamespaces><target prefix="lk" namespace="WinKickOff.Linked"/></policyNamespaces>
  <resources minRequiredRevision="1.0"/>
  <policies>
    <policy name="PuaLike" class="Machine" displayName="$(string.PuaLike)" key="Software\Policies\Microsoft\Windows Defender" valueName="PUAProtection">
      <enabledValue><decimal value="1"/></enabledValue>
      <disabledValue><decimal value="0"/></disabledValue>
    </policy>
    <policy name="WithOption" class="Machine" displayName="$(string.WithOption)" key="Software\Policies\Microsoft\Windows Defender">
      <elements>
        <enum id="Mode" valueName="PUAProtection">
          <item displayName="$(string.Off)"><value><decimal value="0"/></value></item>
          <item displayName="$(string.Block)"><value><decimal value="1"/></value></item>
          <item displayName="$(string.Audit)"><value><decimal value="2"/></value></item>
        </enum>
      </elements>
    </policy>
    <policy name="CloudSearch" class="Machine" displayName="$(string.CloudSearch)" key="Software\Policies\Microsoft\Windows\Windows Search" valueName="AllowCloudSearch">
      <enabledValue><decimal value="0"/></enabledValue>
      <disabledValue><decimal value="1"/></disabledValue>
    </policy>
  </policies>
</policyDefinitions>
"""

ADML = """<?xml version="1.0" encoding="utf-8"?>
<policyDefinitionResources xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <displayName/><description/>
  <resources><stringTable>
    <string id="PuaLike">Block PUA (template)</string>
    <string id="WithOption">PUA mode (template)</string>
    <string id="Off">Off</string>
    <string id="Block">Block</string>
    <string id="Audit">Audit</string>
    <string id="CloudSearch">No cloud search (template)</string>
  </stringTable></resources>
</policyDefinitionResources>
"""

PUA = "admx.winkickoff.linked.pualike"
OPTION = "admx.winkickoff.linked.withoption"
CLOUD = "admx.winkickoff.linked.cloudsearch"


class LinkedTestCase(unittest.TestCase):
    def setUp(self) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        folder = self.tmp / "templates"
        (folder / "en-US").mkdir(parents=True)
        (folder / "linked.admx").write_text(ADMX, encoding="utf-8")
        (folder / "en-US" / "linked.adml").write_text(ADML, encoding="utf-8")
        self.store = self.tmp / "app" / "admx"
        data = admx.read_templates(folder, ["en"])
        self.info = admx.save_import(self.store, folder, data, system=False, now=datetime(2026, 9, 30, 12, 0, 0))
        base = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        self.catalog, _ = admx.with_imports(base, self.store, [self.info.id], "en")
        self.profile = Profile.from_catalog(self.catalog)
        self.assertTrue(self.profile.is_enabled("defender.pua") and self.profile.is_enabled("search.cloud-off"))

    def tearDown(self) -> None:
        self._tmp.cleanup()
        i18n.set_language("en")


class LinkTest(LinkedTestCase):
    def test_equal_covered_and_option_links(self) -> None:
        self.assertEqual(linked.link(self.catalog, self.profile, PUA), linked.Link("defender.pua", True, {"state": 1}))
        option = linked.link(self.catalog, self.profile, OPTION)
        self.assertEqual((option.rule, option.equal, option.params), ("defender.pua", True, {"mode": 1}))  # not the current Off
        cloud = linked.link(self.catalog, self.profile, CLOUD)
        self.assertEqual((cloud.rule, cloud.equal), ("search.cloud-off", False))  # one of its three values
        self.assertIsNone(linked.link(self.catalog, self.profile, "defender.pua"))  # links go from imported policies

    def test_covering_follows_the_built_in_rule(self) -> None:
        self.assertIsNotNone(linked.covering(self.catalog, self.profile, PUA))
        self.profile.rules["defender.pua"].enabled = False
        self.assertIsNone(linked.covering(self.catalog, self.profile, PUA))

    def test_redundant_policies(self) -> None:
        self.assertEqual(linked.redundant(self.catalog, self.profile), [])
        self.profile.rules[PUA].enabled = True
        self.assertEqual(linked.redundant(self.catalog, self.profile), [(PUA, "defender.pua")])
        self.profile.set_param(PUA, "state", 0)  # Disabled writes 0: not what the built-in rule writes
        self.assertEqual(linked.redundant(self.catalog, self.profile), [])

    def test_only_registry_rules_compare(self) -> None:
        other = next(r for r in self.catalog.rules.values() if any(a.type not in ("reg", "reg-remove") for a in r.actions))
        self.assertIsNone(linked.registry_writes(other, {n: p.default for n, p in other.params.items()}))


try:
    import tkinter as tk

    _root = tk.Tk()
    _root.destroy()
    TK_OK = True
except Exception:  # noqa: BLE001
    TK_OK = False


@unittest.skipUnless(TK_OK, "Tk is not available")
class WindowTest(LinkedTestCase):
    def setUp(self) -> None:
        super().setUp()
        from winkickoff.ui.main_window import MainWindow

        base = self.tmp / "app"
        paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                         output=base / "output", logs=base / "logs")
        for folder in (paths.profiles, paths.output, paths.logs):
            folder.mkdir(parents=True)
        self.win = MainWindow(paths, self.catalog, self.profile, Resources.load(paths.resources),
                              Settings(language="en", theme="light", admx=[self.info.id]))
        self.win.withdraw()

    def tearDown(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        super().tearDown()

    def image(self, rule_id: str) -> str:
        on = str(self.win.images["on"])
        return "on" if str(self.win.tree.item("r:" + rule_id, "image")[0]) == on else "off"

    def test_a_covered_policy_is_shown_on_and_follows_the_rule(self) -> None:
        win = self.win
        self.assertEqual((self.image(PUA), win.profile.is_enabled(PUA)), ("on", False))  # shown on, not written twice
        self.assertIn("linked", win.tree.item("r:" + PUA, "tags"))
        win.show_item("r:" + PUA)
        self.assertIn("Set by the built-in rule", win.detail.get("1.0", "end"))
        win.show_item("r:" + OPTION)
        texts = [str(w.cget("text")) for w in win.params_frame.winfo_children()]
        self.assertTrue(any("come from the built-in rule" in text for text in texts))
        win.toggle_item("r:" + PUA)  # the same setting: the built-in rule goes off with it
        self.assertFalse(win.profile.is_enabled("defender.pua"))
        self.assertEqual((self.image(PUA), self.image(OPTION)), ("off", "off"))
        win.toggle_item("r:" + PUA)  # and on again: the reviewed built-in rule is used
        self.assertTrue(win.profile.is_enabled("defender.pua"))
        self.assertFalse(win.profile.is_enabled(PUA))
        self.assertEqual(self.image(PUA), "on")

    def test_a_partly_covered_policy_asks_before_the_whole_rule_goes_off(self) -> None:
        from winkickoff.ui import main_window as mw

        win = self.win
        with mock.patch.object(mw.messagebox, "askyesno", return_value=False) as ask:
            self.assertEqual(win.toggle_item("r:" + CLOUD), [])
        ask.assert_called_once()
        self.assertTrue(win.profile.is_enabled("search.cloud-off"))
        with mock.patch.object(mw.messagebox, "askyesno", return_value=True):
            win.toggle_item("r:" + CLOUD)
        self.assertFalse(win.profile.is_enabled("search.cloud-off"))
        win.toggle_item("r:" + CLOUD)  # not the same setting: the policy itself goes on
        self.assertTrue(win.profile.is_enabled(CLOUD))
        changes = win.toggle_item("r:search.cloud-off")  # the built-in rule now writes the value: the policy steps back
        self.assertFalse(win.profile.is_enabled(CLOUD))
        self.assertIn(CLOUD, [c.rule_id for c in changes if c.reason.startswith("covered by")])
        self.assertEqual(self.image(CLOUD), "on")

    def test_group_counts_include_covered_policies(self) -> None:
        on, total = self.win._group_counts("admx." + self.info.id)
        self.assertEqual((on, total), (3, 3))
        self.assertEqual(self.win.toggle_item("g:admx." + self.info.id), [])  # none is on by itself


if __name__ == "__main__":
    unittest.main()
