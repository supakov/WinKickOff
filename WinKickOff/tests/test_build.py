"""core/render.py Renderer.build: the office preset reproduces v0.2, disabled rules leave no trace."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.deps import Resolver
from winkickoff.core.profile import Profile
from winkickoff.core.render import EXTRACT_COMMAND, RUN_SYSTEM_COMMAND, Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.validate import has_errors, validate_xml

from v02_actions import extract_script, parse_script_actions, parse_script_actions_ordered, parse_v02_actions, rule_actions

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT.parent / "autounattend.xml"
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
class OfficeMatchesV02Test(BuildTestBase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.v02_text = V02.read_text(encoding="utf-8")

    def test_apply_order_follows_v02(self) -> None:
        """Rules are applied in the order of the v0.2 sections. ASR rules come from the $AsrRules table
        applied inside the Defender section; a rule may precede the previous one only inside one section
        (top-level group), where the actions are independent."""
        ordered = parse_script_actions_ordered(extract_script(self.v02_text, "Setup-System.ps1"))
        position = {action: index for index, action in enumerate(ordered)}

        def first_position(rule_id: str) -> float | None:
            found = [position[a] for a in rule_actions(self.catalog, self.office, self.catalog.rules[rule_id]) if a in position]
            return min(found) if found else None

        asr_anchor = first_position("defender.asr")
        self.assertIsNotNone(asr_anchor)
        last_value, last_rule = -1.0, ""
        checked = 0
        for rule_id in Resolver(self.catalog).apply_order(self.office):
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


if __name__ == "__main__":
    unittest.main()
