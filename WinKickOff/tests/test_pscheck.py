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
