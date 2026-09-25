"""Semantic golden: every action of the v0.2 answer file is present in the catalog (office preset)."""

from __future__ import annotations

import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import Profile

from v02_actions import catalog_actions, extract_script, parse_v02_actions

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT.parent / "autounattend.xml"

# Key strings of v0.2 ps fragments that must appear verbatim in some catalog ps action.
PS_KEY_STRINGS = (
    "/FeatureName:NetFx3",
    "Set-Service -Name Spooler -StartupType Automatic",
    "'wuauserv','UsoSvc','BITS','DoSvc','WaaSMedicSvc'",
    "NetBT\\Parameters\\Interfaces",
    "Set-WinUILanguageOverride",
    "Set-WinUserLanguageList -LanguageList $list -Force",
    "-PasswordNeverExpires $true",
    "-match '-50[01]$'",
    "C:\\Windows\\Temp\\ua.err",
    "unattend-original.xml",
)


@unittest.skipUnless(V02.exists(), "v0.2 answer file not found next to WinKickOff")
class CoverageV02Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.profile = Profile.from_catalog(cls.catalog)
        cls.v02 = parse_v02_actions(V02)
        cls.mine = catalog_actions(cls.catalog, cls.profile)

    def test_parser_found_a_plausible_number_of_actions(self) -> None:
        regs = [a for a in self.v02 if a[0] == "reg"]
        self.assertGreater(len(regs), 120, f"only {len(regs)} registry actions parsed from v0.2")
        self.assertTrue(any(a[0] == "service" for a in self.v02))
        self.assertTrue(any(a[0] == "exe" for a in self.v02))

    def test_every_v02_action_is_in_the_catalog(self) -> None:
        missing = sorted(self.v02 - self.mine, key=str)
        self.assertEqual(missing, [], "actions of v0.2 missing from the catalog:\n" + "\n".join(map(str, missing)))

    def test_catalog_extras_are_known(self) -> None:
        # Extras are allowed (new rules, per-GUID auditpol calls, feature actions) but listed for awareness.
        extras = sorted(self.mine - self.v02, key=str)
        unexpected = [a for a in extras if not (a[0] == "exe" and a[1] == "auditpol.exe")]
        self.assertEqual(unexpected, [], "catalog actions not present in v0.2 (add them consciously):\n" + "\n".join(map(str, unexpected)))

    def test_ps_fragments_keep_key_strings(self) -> None:
        scripts = "\n".join(
            str(a.fields["script"]) for rule in self.catalog.rules.values() for a in rule.actions if a.type == "ps"
        )
        for key in PS_KEY_STRINGS:
            self.assertIn(key, scripts, key)

    def test_v02_scripts_still_parse(self) -> None:
        text = V02.read_text(encoding="utf-8")
        for name in ("Setup-System.ps1", "Setup-User.ps1", "Post-OOBE.ps1"):
            self.assertTrue(extract_script(text, name).strip())


if __name__ == "__main__":
    unittest.main()
