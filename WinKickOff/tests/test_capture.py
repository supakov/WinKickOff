"""core/capture.py: the settings of a running Windows read into a profile (task T25). The audit never runs here: the
tests build its JSON report themselves, so nothing on this computer is read or changed."""

from __future__ import annotations

import quiet_tk  # noqa: F401 - first: the window test below stays invisible
import json
import tempfile
import time
import unittest
from datetime import datetime
from unittest import mock
from pathlib import Path
from typing import Any

from winkickoff.core import admx, i18n
from winkickoff.core.apply import _audit_path, render_audit
from winkickoff.core.capture import _evidence, capture_profile, capture_rules, read_rule, render_capture, summary_lines
from winkickoff.core.catalog import Action, Catalog, Rule, load_catalog
from winkickoff.core.profile import Profile
from winkickoff.core.pscheck import check_scripts, powershell_path
from winkickoff.core.resources import Resources
from winkickoff.core.validate import validate_profile

ROOT = Path(__file__).resolve().parents[1]
OFFICE = ROOT / "profiles" / "preset-office.json"
SYSTEM = {
    "computer_name": "REF-PC", "edition_id": "Professional", "build": "26200", "display_version": "25H2",
    "time_zone": "FLE Standard Time", "ui_language": "uk-UA", "system_locale": "uk-UA", "user_locale": "uk-UA",
    "input": [{"tag": "en-US", "tips": ["0409:00000409"]}, {"tag": "uk-UA", "tips": ["0422:00020422"]},
              {"tag": "ru-UA", "tips": ["2000:00000419"]}],
    "accounts": [{"name": "Boss", "full_name": "Бос", "description": "Owner", "group": "Administrators"},
                 {"name": "Clerk", "full_name": "", "description": "", "group": "Users"}],
}
# a policy on the value of a built-in rule (defender.pua writes PUAProtection 1) whose Enabled state writes the opposite
CAPTURE_ADMX = r"""<?xml version="1.0" encoding="utf-8"?>
<policyDefinitions xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <policyNamespaces><target prefix="wkc" namespace="WinKickOff.Capture"/></policyNamespaces>
  <resources minRequiredRevision="1.0"/>
  <categories><category name="Root" displayName="$(string.Root)"/></categories>
  <policies>
    <policy name="PuaOff" class="Machine" displayName="$(string.PuaOff)" key="Software\Policies\Microsoft\Windows Defender" valueName="PUAProtection">
      <parentCategory ref="Root"/>
      <enabledValue><decimal value="0"/></enabledValue>
      <disabledValue><decimal value="1"/></disabledValue>
    </policy>
  </policies>
</policyDefinitions>
"""
CAPTURE_ADML = """<?xml version="1.0" encoding="utf-8"?>
<policyDefinitionResources xmlns="http://schemas.microsoft.com/GroupPolicy/2006/07/PolicyDefinitions" revision="1.0" schemaVersion="1.0">
  <displayName/><description/>
  <resources><stringTable>
    <string id="Root">Capture root</string>
    <string id="PuaOff">PUA protection off</string>
  </stringTable></resources>
</policyDefinitionResources>
"""


def checks(rule: Rule, status: str = "ok", currents: dict[int, str] | None = None,
           statuses: dict[int, str] | None = None) -> list[dict[str, str]]:
    """The checks Audit.runtime.ps1 reports for a rule, one per action, with the check text it writes."""
    out = []
    for index, action in enumerate(rule.actions):
        fields = action.fields
        if action.type in ("reg", "reg-remove"):
            what = f"{_audit_path(str(fields['path']))[0]}\\{fields['name']}"
        elif action.type == "service":
            what = f"service {fields['name']}"
        else:
            what = action.type
        out.append({"rule": rule.id, "check": what, "status": (statuses or {}).get(index, status),
                    "current": (currents or {}).get(index, ""), "expected": str(fields.get("value", ""))})
    return out


def fake_report(catalog: Catalog, system: dict[str, Any] | None = None, admin: bool = True,
                extra: list[dict[str, str]] | None = None) -> str:
    """A report of a reference PC: Defender PUA and the screen lock (600 s) in effect, the telemetry level 0, NetBIOS
    not, UAC partly; every other rule absent from the report (not readable), unless extra holds its checks."""
    results = checks(catalog.rules["defender.pua"]) + list(extra or [])
    results += checks(catalog.rules["accounts.inactivity-lock"], "differs", {0: "600"})
    telemetry = catalog.rules["privacy.telemetry-minimal"]
    results += checks(telemetry, "ok", {0: "0"}, {0: "differs"})
    results += checks(catalog.rules["network.netbios-off"], "differs", {0: "2"})
    uac = catalog.rules["uac.baseline"]
    first = next(i for i, action in enumerate(uac.actions) if _evidence(action, {}))  # a value Windows does not have
    results += checks(uac, "differs", {first: "1"}, {first: "ok"})
    return json.dumps({"computer": "REF-PC", "admin": admin, "time": "2026-10-10T12:00:00",
                       "system": SYSTEM if system is None else system, "results": results})


class CaptureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.resources = Resources.load(ROOT / "resources")

    def office(self) -> Profile:
        return Profile.load(OFFICE, self.catalog)[0]

    def capture(self, report: str | None = None) -> tuple[Profile, Any]:
        return capture_profile(self.catalog, self.office(), report or fake_report(self.catalog), self.resources.keyboards)

    def test_the_script_reads_every_rule_a_running_windows_shows_and_the_forms(self) -> None:
        script = render_capture(self.catalog, self.office(), ROOT / "templates", "test")
        rule_ids, skipped = capture_rules(self.catalog)
        self.assertIn("# [defender.pua]", script)
        self.assertNotIn("# [install.bypass-tpm]", script)  # installation only: kept from the open profile
        self.assertIn("install.bypass-tpm", [rule.id for rule, _ in skipped])
        self.assertEqual(len(rule_ids) + len(skipped), len(self.catalog.rules))
        self.assertIn("DATA FORMS OF THE PROFILE", script)
        self.assertNotIn("Password", script.split("DATA FORMS OF THE PROFILE")[1].split("$out =")[0].replace(
            "Passwords and product keys are\n# never read", ""))
        plain = render_audit(rule_ids[:3], self.office(), self.catalog, ROOT / "templates", "test")
        self.assertNotIn("DATA FORMS OF THE PROFILE", plain)  # "Check the selection on this PC" reads no forms

    @unittest.skipUnless(powershell_path(), "powershell.exe not found")
    def test_the_script_parses_in_windows_powershell(self) -> None:
        script = render_capture(self.catalog, self.office(), ROOT / "templates", "test")
        with tempfile.TemporaryDirectory() as tmp:
            result = check_scripts({"Read-PC.ps1": script}, Path(tmp))  # parsed only, never run
        self.assertTrue(result.ok, result)

    def test_rules_take_the_state_of_the_computer(self) -> None:
        profile, summary = self.capture()
        office = self.office()
        self.assertTrue(profile.is_enabled("defender.pua"))
        self.assertEqual(profile.param(self.catalog, "accounts.inactivity-lock", "seconds"), 600)  # read, not 900
        self.assertTrue(profile.is_enabled("accounts.inactivity-lock"))
        self.assertEqual(profile.param(self.catalog, "privacy.telemetry-minimal", "level"), 0)
        self.assertFalse(profile.is_enabled("network.netbios-off"))
        self.assertFalse(profile.is_enabled("uac.baseline"))  # partly in effect: off, listed
        self.assertIn("uac.baseline", summary.partly)
        self.assertTrue(summary.differs["uac.baseline"])  # the checks that do not match, for the person
        self.assertIn(("accounts.inactivity-lock", "seconds", 600), summary.params)
        for rule_id in ("defender.realtime", "install.bypass-tpm"):  # not readable or not shown: as in the open profile
            self.assertEqual(profile.is_enabled(rule_id), office.is_enabled(rule_id), rule_id)
        self.assertIn("defender.realtime", summary.unknown)
        self.assertIn("install.bypass-tpm", summary.kept)
        self.assertEqual((profile.name, profile.path), ("Settings of REF-PC", None))
        self.assertIn("REF-PC", profile.comment)

    def test_a_value_outside_the_parameter_is_not_taken(self) -> None:
        rule = self.catalog.rules["accounts.inactivity-lock"]
        status, params, _ = read_rule(rule, checks(rule, "differs", {0: "5"}), {"seconds": 900})  # below the minimum
        self.assertEqual((status, params["seconds"]), ("not-applied", 900))
        status, params, _ = read_rule(rule, checks(rule, "differs", {0: "text"}), {"seconds": 900})
        self.assertEqual(status, "not-applied")
        status, _, _ = read_rule(rule, checks(rule, "unknown"), {"seconds": 900})
        self.assertEqual(status, "unknown")

    def test_what_a_clean_windows_already_has_is_no_evidence(self) -> None:
        # an imported policy with an empty list and a deleted value matches on every PC where nobody set it
        policy = type("Policy", (), {"actions": [
            Action("reg-list", {"path": r"HKLM:\SOFTWARE\Policies\X", "kind": "String", "value": "{items}"}, "admx.x"),
            Action("reg-remove", {"path": r"HKLM:\SOFTWARE\Policies\X", "name": "Y"}, "admx.x")], "params": {}})()
        checks_ok = [{"check": "a", "status": "ok", "current": ""}, {"check": "b", "status": "ok", "current": ""}]
        self.assertEqual(read_rule(policy, checks_ok, {"items": []})[0], "as-default")
        self.assertEqual(read_rule(policy, checks_ok, {"items": ["https://x"]})[0], "applied")  # a list that was set
        one_off = [checks_ok[0], {"check": "b", "status": "differs", "current": "1"}]
        self.assertEqual(read_rule(policy, one_off, {"items": []})[0], "not-applied")  # only the empty list matched
        rule = self.catalog.rules["defender.pua"]  # a policy value: present only when it was set
        self.assertEqual(read_rule(rule, checks(rule), {})[0], "applied")
        _, summary = self.capture()
        self.assertIn("as in Windows by default 0", summary_lines(summary, lambda r: r)[0][2])

    def test_as_in_windows_by_default_keeps_the_state_of_the_open_profile(self) -> None:
        # the read of 12.10.2026: "apps.remove.onedrive" only deletes a value and "logging.powershell-v2-off" disables a
        # feature that 24H2 and later do not ship; both matched, both were switched off in the copy and showed as
        # differences from the profile the PC was installed from, where they were on
        onedrive, ps2 = self.catalog.rules["apps.remove.onedrive"], self.catalog.rules["logging.powershell-v2-off"]
        self.assertFalse(_evidence(ps2.actions[0], {}, "absent"))  # "not present on this build": nothing was disabled
        self.assertTrue(_evidence(ps2.actions[0], {}, "Disabled"))
        extra = checks(onedrive) + checks(ps2, "ok", {0: "absent", 1: "absent"})
        for enabled in (True, False):
            base = self.office()
            base.rules["apps.remove.onedrive"].enabled = enabled
            base.rules["logging.powershell-v2-off"].enabled = enabled
            profile, summary = capture_profile(self.catalog, base, fake_report(self.catalog, extra=extra), self.resources.keyboards)
            self.assertEqual(profile.is_enabled("apps.remove.onedrive"), enabled)
            self.assertEqual(profile.is_enabled("logging.powershell-v2-off"), enabled)
            self.assertEqual(sorted(summary.as_default), ["apps.remove.onedrive", "logging.powershell-v2-off"])
            self.assertNotIn("apps.remove.onedrive", summary.in_effect + summary.not_in_effect)
        self.assertIn("as in Windows by default 2", summary_lines(summary, lambda r: r)[0][2])
        disabled = checks(ps2, "ok", {0: "Disabled", 1: "Disabled"})  # the feature is there and off: the rule acted
        profile, _ = capture_profile(self.catalog, self.office(), fake_report(self.catalog, extra=disabled), self.resources.keyboards)
        self.assertTrue(profile.is_enabled("logging.powershell-v2-off"))

    def test_a_policy_a_built_in_rule_covers_keeps_its_state_and_parameters(self) -> None:
        # the read of 12.10.2026: 55 Edge and Chrome policies of a profile differed after a read only in the parameter
        # "state", read as the Disabled state the built-in browser rules write, although every policy stayed off
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "templates"
            (folder / "en-US").mkdir(parents=True)
            (folder / "wkcapture.admx").write_text(CAPTURE_ADMX, encoding="utf-8")
            (folder / "en-US" / "wkcapture.adml").write_text(CAPTURE_ADML, encoding="utf-8")
            data = admx.read_templates(folder, ["en"])
            info = admx.save_import(Path(tmp) / "admx", folder, data, system=False, now=datetime(2026, 10, 12, 12, 0, 0))
            catalog, problems = admx.with_imports(self.catalog, Path(tmp) / "admx", [info.id], "en")
        self.assertEqual(problems, [])
        policy = "admx.winkickoff.capture.puaoff"
        rule = catalog.rules[policy]
        self.assertEqual((catalog.same_values(policy), rule.params["state"].default), (["defender.pua"], 0))
        base = Profile.load(OFFICE, catalog)[0]  # defender.pua on; the policy off, its state Enabled (0) by default
        extra = checks(rule, "ok", {0: "1"})  # PUAProtection is 1 on the PC: the Disabled state of the policy
        profile, summary = capture_profile(catalog, base, fake_report(catalog, extra=extra), self.resources.keyboards)
        self.assertTrue(profile.is_enabled("defender.pua"))
        self.assertEqual(summary.covered, [policy])
        self.assertEqual(profile.rules[policy], base.rules[policy])  # off, and not "Disabled" either
        self.assertEqual([d for d in profile.diff(base, catalog) if d.key.startswith(policy)], [])
        self.assertEqual([entry for entry in summary.params if entry[0] == policy], [])
        self.assertIn((policy, "As in the open profile: an enabled built-in rule writes the same values"),
                      [(target, text) for _level, target, text in summary_lines(summary, lambda r: r)])
        base.rules[policy].enabled = True  # chosen on by the person next to the built-in rule: also kept
        profile, summary = capture_profile(catalog, base, fake_report(catalog, extra=extra), self.resources.keyboards)
        self.assertEqual((profile.is_enabled(policy), summary.covered), (True, [policy]))

    def test_the_data_forms(self) -> None:
        profile, summary = self.capture()
        self.assertEqual(profile.install["edition"], "Pro")
        self.assertEqual(profile.install["time_zone"], "FLE Standard Time")
        self.assertEqual(profile.install["computer_name_mode"], "random")  # never the name of the reference PC
        self.assertEqual(profile.languages["input"], ["en-US", "uk-UA", "ru-UA"])  # Enhanced uk-UA is the tag itself
        self.assertEqual([(a.name, a.display_name, a.group, a.password) for a in profile.accounts],
                         [("Boss", "Бос", "Administrators", ""), ("Clerk", "Clerk", "Users", "")])
        self.assertIn("accounts", summary.forms)
        self.assertTrue(any("REF-PC" in note for note in summary.notes))
        self.assertEqual(summary.system["accounts"], [{"name": "Boss", "group": "Administrators"},
                                                      {"name": "Clerk", "group": "Users"}])

    def test_forms_that_cannot_be_used_stay(self) -> None:
        office = self.office()
        system = dict(SYSTEM, edition_id="Core", time_zone="", ui_language="x",
                      accounts=[{"name": "Clerk", "group": "Users"}], input=[{"tag": "uk-UA", "tips": ["0422:00000422"]}])
        profile, summary = self.capture(fake_report(self.catalog, system, admin=False))
        self.assertEqual(profile.install["edition"], office.install["edition"])  # Home has no generic key here
        self.assertEqual(profile.install["time_zone"], office.install["time_zone"])
        self.assertEqual(profile.languages["ui_language"], office.languages["ui_language"])
        self.assertEqual(profile.languages["input"], ["0422:00000422"])  # a layout that is not the first of its tag
        self.assertEqual([a.name for a in profile.accounts], [a.name for a in office.accounts])  # no administrator read
        self.assertTrue(any("administrator rights" in note for note in summary.notes))
        _, without = self.capture(fake_report(self.catalog, {}) .replace('"system": {}', '"system": null'))
        self.assertTrue(any("data forms were not read" in note for note in without.notes))

    def test_the_new_profile_checks_like_any_other(self) -> None:
        profile, summary = self.capture()
        issues = validate_profile(profile, self.catalog, self.resources.keyboards)
        self.assertEqual([i.message for i in issues if i.level == "error"], [])
        lines = summary_lines(summary, lambda rule_id: rule_id)
        self.assertIn("in effect 3, partly 1, not in effect 1, as in Windows by default 0", lines[0][2])
        self.assertTrue(any(target == "uac.baseline" and level == "warning" for level, target, _ in lines))

    def test_a_damaged_report_is_a_value_error(self) -> None:
        for text in ("", "[]", "{\"results\": 5}", "not json"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.capture(text or "null")



class ReadThisPcWindowTest(unittest.TestCase):
    """The menu command of the window, with the audit and the dialogs replaced: nothing on this computer is read."""

    def test_the_menu_reads_this_pc_into_a_new_profile(self) -> None:
        from winkickoff.core.paths import AppPaths
        from winkickoff.core.settings import Settings
        from winkickoff.ui.main_window import MainWindow

        i18n.set_language("en", ROOT / "resources", ROOT / "rules")
        self.addCleanup(i18n.set_language, "en")
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "app"
            paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles",
                             output=base / "output", logs=base / "logs")
            for folder in (paths.profiles, paths.output, paths.logs):
                folder.mkdir(parents=True)
            catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
            win = MainWindow(paths, catalog, Profile.load(OFFICE, catalog)[0], Resources.load(paths.resources),
                             Settings(language="en", theme="light"))
            win.withdraw()
            try:
                menu = win.pc_menu
                labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
                self.assertIn("Read the settings of this PC into a new profile...", labels)
                with mock.patch("winkickoff.ui.main_window.run_audit", return_value=fake_report(catalog)) as audit,                         mock.patch("winkickoff.ui.main_window.messagebox") as boxes:
                    boxes.askokcancel.return_value = True
                    win.read_this_pc()
                    deadline = time.monotonic() + 30
                    while (win._busy or win.profile.name == "Office") and time.monotonic() < deadline:
                        win.update()
                        time.sleep(0.05)
                self.assertIn("DATA FORMS OF THE PROFILE", audit.call_args[0][0])
                self.assertEqual((win.profile.name, win.dirty), ("Settings of REF-PC", True))
                self.assertEqual(win.profile.param(catalog, "accounts.inactivity-lock", "seconds"), 600)
                self.assertTrue(any("in effect 3" in issue.message for issue in win._issues))
            finally:
                win.destroy()


if __name__ == "__main__":
    unittest.main()
