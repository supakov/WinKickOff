"""core/render.py Renderer.build: the v0.2 reference profile reproduces v0.2, the office preset builds cleanly,
disabled rules leave no trace."""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.computername import TEMPORARY_NAME
from winkickoff.core.deps import Resolver
from winkickoff.core.importer import import_xml
from winkickoff.core.profile import Profile
from winkickoff.core.render import EXTRACT_COMMAND, RUN_SYSTEM_COMMAND, Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.validate import has_errors, validate_xml

from v02_actions import V02
from v02_actions import extract_script, parse_script_actions, parse_script_actions_ordered, parse_v02_actions, reference_profile, rule_actions

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT.parent / "tools" / "Validate-Unattend.ps1"
U = "{urn:schemas-microsoft-com:unattend}"
ACTIVE_SETUP_GUID = "{7A6C3F5E-2B1D-4C8E-9F0A-5D3E6B7C8D91}"


def summary(xml_text: str) -> dict[str, object]:
    """The parts of an answer file that Setup acts on, per architecture, in document order."""
    root = ET.fromstring(xml_text)
    out: dict[str, object] = {}
    for settings in root.findall(f"{U}settings"):
        pass_name = settings.get("pass")
        for comp in settings.findall(f"{U}component"):
            key = f"{pass_name}/{comp.get('name')}/{comp.get('processorArchitecture')}"
            paths = [c.findtext(f"{U}Path") for c in comp.iter(f"{U}RunSynchronousCommand")]
            if paths:
                out[key + "/commands"] = paths
            if comp.get("name") == "Microsoft-Windows-International-Core":
                out[key + "/international"] = {
                    child.tag.replace(U, ""): (child.text or "").strip() for child in comp if len(child) == 0
                }
            if comp.get("name") == "Microsoft-Windows-Shell-Setup":
                oobe = comp.find(f"{U}OOBE")
                if oobe is not None:
                    out[key + "/oobe"] = {child.tag.replace(U, ""): (child.text or "").strip() for child in oobe}
                accounts = [
                    (a.findtext(f"{U}Name"), a.findtext(f"{U}Group")) for a in comp.iter(f"{U}LocalAccount")
                ]
                if accounts:
                    out[key + "/accounts"] = accounts
                if comp.findtext(f"{U}TimeZone"):
                    out[key + "/timezone"] = comp.findtext(f"{U}TimeZone")
            for key_node in comp.iter(f"{U}ProductKey"):
                out[key + "/product_key"] = (key_node.findtext(f"{U}Key"), key_node.findtext(f"{U}WillShowUI"))
    return out


class BuildTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.resources = Resources.load(ROOT / "resources")
        cls.renderer = Renderer(cls.catalog, ROOT / "templates", cls.resources.keyboards)
        cls.office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", cls.catalog)
        cls.result = cls.renderer.build(cls.office, app_version="test")

    def build_with_phase_disabled(self, phase: str):
        profile = self.office.copy()
        resolver = Resolver(self.catalog)
        for rule in self.catalog.rules.values():
            if rule.phase == phase and profile.is_enabled(rule.id):
                resolver.disable(profile, rule.id)
        return profile, self.renderer.build(profile, app_version="test")


class BuildBasicsTest(BuildTestBase):
    def test_output_is_deterministic(self) -> None:
        again = self.renderer.build(self.office.copy(), app_version="test")
        self.assertEqual(again.xml, self.result.xml)

    def test_output_is_ascii_with_crlf(self) -> None:
        self.assertTrue(self.result.xml.isascii())
        self.assertNotIn("\n", self.result.xml.replace("\r\n", ""))

    def test_output_passes_own_validation(self) -> None:
        issues = validate_xml(self.result.xml)
        self.assertFalse(has_errors(issues), [i.message for i in issues if i.level == "error"])

    def test_three_scripts_for_office(self) -> None:
        self.assertEqual(list(self.result.scripts), ["Setup-System.ps1", "Setup-User.ps1", "Post-OOBE.ps1"])
        for name, text in self.result.scripts.items():
            self.assertEqual(text.rstrip().splitlines()[-1].strip(), "exit 0", name)

    def test_every_enabled_rule_with_script_actions_is_marked(self) -> None:
        for rule_id in self.result.rule_ids:
            rule = self.catalog.rules[rule_id]
            if rule.phase in ("windowspe", "specialize-xml", "oobe-xml"):
                continue
            self.assertIn(f"# [{rule_id}]", self.result.xml, rule_id)

    def test_command_paths_stay_under_the_setup_limit(self) -> None:
        self.assertLessEqual(len(EXTRACT_COMMAND), 259)
        self.assertLessEqual(len(RUN_SYSTEM_COMMAND), 259)

    def test_profile_is_embedded(self) -> None:
        root = ET.fromstring(self.result.xml)
        profile = root.find("{urn:workgroup-unattend}Extensions/{urn:workgroup-unattend}Profile")
        self.assertIsNotNone(profile)


class DisabledRulesLeaveNoTraceTest(BuildTestBase):
    def test_disabled_rule_is_absent(self) -> None:
        self.assertFalse(self.office.is_enabled("network.netbios-off"))
        self.assertNotIn("# [network.netbios-off]", self.result.xml)
        strict, _ = Profile.load(ROOT / "profiles" / "preset-strict.json", self.catalog)
        self.assertIn("# [network.netbios-off]", self.renderer.build(strict, app_version="test").xml)

    def test_disabling_a_rule_removes_its_marker(self) -> None:
        rule_id = next(r for r in self.result.rule_ids if self.catalog.rules[r].phase == "specialize")
        profile = self.office.copy()
        Resolver(self.catalog).disable(profile, rule_id)
        self.assertNotIn(f"# [{rule_id}]", self.renderer.build(profile, app_version="test").xml)

    def test_no_user_logon_rules_means_no_user_script_and_no_active_setup(self) -> None:
        _, result = self.build_with_phase_disabled("user-first-logon")
        self.assertNotIn("Setup-User.ps1", result.scripts)
        self.assertNotIn(ACTIVE_SETUP_GUID, result.xml)
        self.assertFalse(has_errors(validate_xml(result.xml)))

    def test_no_post_oobe_rules_means_no_task(self) -> None:
        _, result = self.build_with_phase_disabled("post-oobe")
        self.assertNotIn("Post-OOBE.ps1", result.scripts)
        self.assertNotIn("taskXml", result.scripts["Setup-System.ps1"])
        self.assertNotIn("Post-OOBE", result.scripts["Setup-System.ps1"])
        self.assertFalse(has_errors(validate_xml(result.xml)))

    def test_no_default_user_rules_means_no_hive_load(self) -> None:
        _, result = self.build_with_phase_disabled("default-user")
        self.assertNotIn("reg.exe load", result.scripts["Setup-System.ps1"])


@unittest.skipUnless(V02.exists(), "v0.2 answer file not found next to WinKickOff")
class ReferenceMatchesV02Test(BuildTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.v02_text = V02.read_text(encoding="utf-8")
        cls.reference = reference_profile(cls.catalog)
        cls.result = cls.renderer.build(cls.reference, app_version="test")

    def test_apply_order_follows_v02(self) -> None:
        """Rules are applied in the order of the v0.2 sections. ASR rules come from the $AsrRules table
        applied inside the Defender section; a rule may precede the previous one only inside one section
        (top-level group), where the actions are independent."""
        ordered = parse_script_actions_ordered(extract_script(self.v02_text, "Setup-System.ps1"))
        position = {action: index for index, action in enumerate(ordered)}

        def first_position(rule_id: str) -> float | None:
            found = [position[a] for a in rule_actions(self.catalog, self.reference, self.catalog.rules[rule_id]) if a in position]
            return min(found) if found else None

        asr_anchor = first_position("defender.asr")
        self.assertIsNotNone(asr_anchor)
        last_value, last_rule = -1.0, ""
        checked = 0
        for rule_id in Resolver(self.catalog).apply_order(self.reference):
            rule = self.catalog.rules[rule_id]
            if rule.phase not in ("specialize", "default-user"):
                continue
            value = asr_anchor + 0.5 if rule_id.startswith("asr.") else first_position(rule_id)
            if value is None:
                continue
            checked += 1
            if value < last_value:  # allowed only inside one section (top-level group) of v0.2
                section = rule.group.split(".")[0]
                self.assertEqual(section, self.catalog.rules[last_rule].group.split(".")[0], f"{rule_id} runs after {last_rule}, v0.2 did it earlier")
            if value >= last_value:
                last_value, last_rule = value, rule_id
        self.assertGreater(checked, 60)

    def test_setup_actions_cover_v02(self) -> None:
        mine = parse_script_actions(self.result.scripts["Setup-System.ps1"])
        missing = sorted(parse_v02_actions(self.v02_text) - mine, key=str)
        self.assertEqual(missing, [], "v0.2 actions missing from the generated Setup-System.ps1:\n" + "\n".join(map(str, missing)))

    def test_generated_script_parses_like_the_embedded_one(self) -> None:
        embedded = extract_script(self.result.xml, "Setup-System.ps1").strip()
        self.assertEqual(embedded.replace("\r\n", "\n"), self.result.scripts["Setup-System.ps1"].strip())

    def test_setup_passes_match_v02(self) -> None:
        mine, v02 = summary(self.result.xml), summary(self.v02_text)
        for key in sorted(set(mine) | set(v02)):
            with self.subTest(key=key):
                self.assertEqual(mine.get(key), v02.get(key))


class AccountAndEditionModesTest(BuildTestBase):
    def test_account_asked_during_installation(self) -> None:
        profile = self.office.copy()
        profile.install["account_mode"] = "ask"
        result = self.renderer.build(profile, app_version="test")
        self.assertNotIn("<UserAccounts>", result.xml)
        self.assertNotIn("<LocalAccount ", result.xml)
        self.assertIn("<HideOnlineAccountScreens>true</HideOnlineAccountScreens>", result.xml)
        self.assertIn("Accounts: none in this file; Windows Setup asks", result.xml)
        self.assertIn("$accounts = @()", result.scripts["Post-OOBE.ps1"])
        self.assertIn("<UserAccounts>", self.result.xml)  # the preset itself still creates Admin and User

    def test_asked_account_keeps_the_passwords_of_the_form_out_of_the_file(self) -> None:
        profile = self.office.copy()
        profile.accounts[0].password = "Form-Secret-123"
        profile.install["account_mode"] = "ask"
        xml = self.renderer.build(profile, app_version="test").xml
        self.assertNotIn("Form-Secret-123", xml)  # neither in the XML nor in the embedded profile
        restored, _ = import_xml(xml, self.catalog)
        self.assertEqual(restored.install["account_mode"], "ask")
        self.assertEqual([a.name for a in restored.accounts], [a.name for a in profile.accounts])
        self.assertEqual({a.password for a in restored.accounts}, {""})
        profile.install["account_mode"] = "file"  # the accounts are created: the password is in the file, as before
        self.assertIn("Form-Secret-123", self.renderer.build(profile, app_version="test").xml)

    def computer_names(self, xml: str) -> list[str | None]:
        root = ET.fromstring(xml)
        return [c.findtext(f"{U}ComputerName") for c in
                root.findall(f"{U}settings[@pass='specialize']/{U}component[@name='Microsoft-Windows-Shell-Setup']")]

    def test_windows_chooses_the_computer_name_by_default(self) -> None:
        self.assertEqual(self.computer_names(self.result.xml), [None, None])
        self.assertNotIn("COMPUTER NAME FROM THE TEMPLATE", self.result.scripts["Setup-System.ps1"])

    def test_a_fixed_computer_name(self) -> None:
        profile = self.office.copy()
        profile.install["computer_name_mode"], profile.install["computer_name"] = "fixed", "BUH-01"
        result = self.renderer.build(profile, app_version="test")
        self.assertEqual(self.computer_names(result.xml), ["BUH-01", "BUH-01"])
        self.assertNotIn("COMPUTER NAME FROM THE TEMPLATE", result.scripts["Setup-System.ps1"])
        restored, _ = import_xml(result.xml, self.catalog)
        self.assertEqual((restored.install["computer_name_mode"], restored.install["computer_name"]), ("fixed", "BUH-01"))

    def test_a_computer_name_template(self) -> None:
        profile = self.office.copy()
        profile.install["computer_name_mode"], profile.install["computer_name"] = "template", "KANC-{serial:5}{random:2}"
        result = self.renderer.build(profile, app_version="test")
        self.assertEqual(self.computer_names(result.xml), [TEMPORARY_NAME, TEMPORARY_NAME])
        system = result.scripts["Setup-System.ps1"]
        self.assertIn("foreach ($part in @('text:KANC-','serial:5','random:2'))", system)
        self.assertLess(system.index("COMPUTER NAME FROM THE TEMPLATE"), system.index("# RULES"))  # the loop starts early
        self.assertIn("-WindowStyle Hidden", system)

    def test_account_texts_outside_ascii_are_set_after_oobe(self) -> None:
        profile, _ = self.build_with_phase_disabled("post-oobe")  # the texts alone need Post-OOBE.ps1 and its task
        account = profile.accounts[0]
        account.display_name = "\u0410\u0434\u043c\u0456\u043d\u0456\u0441\u0442\u0440\u0430\u0442\u043e\u0440"
        account.description = "\u041e\u0431\u043b\u0456\u043a\u043e\u0432\u0438\u0439 \u0437\u0430\u043f\u0438\u0441 \u00ab1\u00bb"
        result = self.renderer.build(profile, app_version="test")
        self.assertTrue(result.xml.isascii())  # the embedded profile is escaped, the scripts carry Base64
        written = next(a for a in ET.fromstring(result.xml).iter(f"{U}LocalAccount") if a.findtext(f"{U}Name") == account.name)
        self.assertEqual(written.findtext(f"{U}DisplayName"), account.name)
        self.assertIsNone(written.find(f"{U}Description"))
        line = next(line for line in result.scripts["Post-OOBE.ps1"].splitlines() if line.startswith("Set-AccountText"))
        texts = [base64.b64decode(text).decode("utf-8") for text in re.findall(r"ConvertFrom-Base64Text '([^']+)'", line)]
        self.assertEqual(texts, [account.display_name, account.description])
        self.assertIn("Unattend-PostOOBE", result.scripts["Setup-System.ps1"])  # the task that runs it
        restored, _ = import_xml(result.xml, self.catalog)
        self.assertEqual((restored.accounts[0].display_name, restored.accounts[0].description),
                         (account.display_name, account.description))
        self.assertNotIn("Set-AccountText -Name", self.result.scripts["Post-OOBE.ps1"])  # ASCII texts stay in the file

    def test_edition_chosen_during_installation(self) -> None:
        profile = self.office.copy()
        profile.install["product_key_mode"] = "ask"
        result = self.renderer.build(profile, app_version="test")
        self.assertIn("<Key>00000-00000-00000-00000-00000</Key>", result.xml)
        self.assertIn("<WillShowUI>Always</WillShowUI>", result.xml)
        self.assertIn("Edition: chosen during Setup", result.xml)


class NewRuleKindsTest(BuildTestBase):
    def test_a_first_sign_in_rule_writes_the_registry_of_the_user(self) -> None:
        profile = self.office.copy()
        profile.rules["nav.libraries"].enabled = True
        script = self.renderer.build(profile, app_version="test").scripts["Setup-User.ps1"]
        self.assertIn("function Set-Reg", script)
        self.assertIn("Set-Reg -Path 'HKCU:\\Software\\Classes\\CLSID\\{031E4825-7B94-4dc3-B131-E946B44C8DD5}' "
                      "-Name 'System.IsPinnedToNameSpaceTree' -Type DWord -Value 1", script)

    def test_switch_keys_reach_new_accounts_and_the_sign_in_screen(self) -> None:
        profile = self.office.copy()
        rule_id = "default-user.input-switch-keys"
        profile.rules[rule_id].enabled = True
        profile.set_param(rule_id, "language", "2")
        profile.set_param(rule_id, "layout", "1")
        system = self.renderer.build(profile, app_version="test").scripts["Setup-System.ps1"]
        self.assertIn("Set-Reg -Path ($du + '\\Keyboard Layout\\Toggle') -Name 'Language Hotkey' -Type String -Value '2'", system)
        self.assertIn("Set-Reg -Path 'HKU:\\.DEFAULT\\Keyboard Layout\\Toggle' -Name 'Layout Hotkey' -Type String -Value '1'",
                      system)
        # both parts are inside the mounted default profile block, which creates the HKU: drive first
        self.assertLess(system.index("New-PSDrive -Name HKU"), system.index("Keyboard Layout"))


@unittest.skipUnless(shutil.which("powershell.exe") and VALIDATOR.exists(), "Windows PowerShell or the validator not found")
class ExternalValidatorTest(BuildTestBase):
    def test_validator_accepts_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "autounattend.xml"
            target.write_bytes(self.result.xml.encode("utf-8"))
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(VALIDATOR), "-Path", str(target)],
                capture_output=True, text=True, timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-2000:])

    def test_validator_accepts_a_computer_name_and_account_texts(self) -> None:
        profile = self.office.copy()
        profile.install["computer_name_mode"], profile.install["computer_name"] = "fixed", "BUH-01"
        profile.accounts[0].description = "\u041e\u043f\u0438\u0441"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "autounattend.xml"
            target.write_bytes(self.renderer.build(profile, app_version="test").xml.encode("utf-8"))
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(VALIDATOR), "-Path", str(target)],
                capture_output=True, text=True, timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-2000:])
        self.assertIn("ComputerName valid (amd64)", proc.stdout)
        self.assertIn("LocalAccount texts in ASCII", proc.stdout)

    def test_validator_accepts_a_build_that_asks_for_the_account(self) -> None:
        profile = self.office.copy()
        profile.install["account_mode"] = "ask"
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "autounattend.xml"
            target.write_bytes(self.renderer.build(profile, app_version="test").xml.encode("utf-8"))
            proc = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(VALIDATOR), "-Path", str(target)],
                capture_output=True, text=True, timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-2000:])
        self.assertIn("none: OOBE asks", proc.stdout)


if __name__ == "__main__":
    unittest.main()
