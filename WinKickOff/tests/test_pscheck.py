"""core/pscheck.py: syntax check of the generated scripts by Windows PowerShell 5.1 (parse only)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from winkickoff.core.pscheck import check_scripts, powershell_path


@unittest.skipUnless(powershell_path(), "powershell.exe not found")
class PsCheckTest(unittest.TestCase):
    def test_valid_and_broken_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = check_scripts(
                {
                    "Good.ps1": "$x = 'Київ'\nif ($x) { Write-Output $x }\nexit 0\n",
                    "Bad.ps1": "if ($x { Write-Output 1 }\nexit 0\n",
                },
                Path(tmp),
            )
            self.assertFalse(result.skipped)
            self.assertEqual(result.failure, "")
            self.assertTrue(any("Bad.ps1" in e for e in result.errors), result.errors)
            self.assertFalse(any("Good.ps1" in e for e in result.errors), result.errors)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], [], "work folder must be cleaned up")

    def test_a_name_template_and_account_texts_parse(self) -> None:
        from winkickoff.core.catalog import load_catalog
        from winkickoff.core.profile import Profile
        from winkickoff.core.render import Renderer
        from winkickoff.core.resources import Resources

        root = Path(__file__).resolve().parents[1]
        catalog = load_catalog(root / "rules", docs_root=root.parent)
        profile, _ = Profile.load(root / "profiles" / "preset-office.json", catalog)
        profile.install["computer_name_mode"], profile.install["computer_name"] = "template", "PC-{serial:4}{mac:2}{random}"
        profile.accounts[0].description = "\u041e\u043f\u0438\u0441 'x'"
        scripts = Renderer(catalog, root / "templates", Resources.load(root / "resources").keyboards).build(profile).scripts
        with tempfile.TemporaryDirectory() as tmp:
            result = check_scripts(scripts, Path(tmp))
        self.assertTrue(result.ok, result)

    def test_all_good(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = check_scripts({"Good.ps1": "exit 0\n"}, Path(tmp))
        self.assertTrue(result.ok, result)


class PsCheckSkipTest(unittest.TestCase):
    def test_nothing_to_check_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(check_scripts({}, Path(tmp)).skipped)


if __name__ == "__main__":
    unittest.main()
