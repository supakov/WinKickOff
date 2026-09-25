"""Project rules enforced on the sources: no cwd/APPDATA/registry access, no dashes, only stdlib."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "winkickoff"
FORBIDDEN = (
    re.compile(r"os\.getcwd\("),
    re.compile(r"APPDATA|PROGRAMDATA|LOCALAPPDATA"),
    re.compile(r"\bwinreg\b"),
    re.compile(r"\bimport (requests|urllib|http\.client|socket)\b"),
)
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")  # built from code points: the source must not contain them


def _text_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("winkickoff/**/*.py", "rules/**/*.toml", "resources/*.json", "tests/*.py", "*.md", "*.toml", "templates/*"):
        files.extend(p for p in ROOT.glob(pattern) if p.is_file())
    return files


class SourceRulesTest(unittest.TestCase):
    def test_no_forbidden_calls_in_package(self) -> None:
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN:
                self.assertIsNone(pattern.search(text), f"{path.name}: forbidden pattern {pattern.pattern}")

    def test_no_dashes_anywhere(self) -> None:
        offenders = [str(p.relative_to(ROOT)) for p in _text_files() if DASHES.search(p.read_text(encoding="utf-8", errors="replace"))]
        self.assertEqual(offenders, [], "files with em/en dashes")

    def test_only_stdlib_imports(self) -> None:
        stdlib = set(sys.stdlib_module_names)
        for path in PACKAGE.rglob("*.py"):
            for match in re.finditer(r"^(?:from|import)\s+([A-Za-z_][\w]*)", path.read_text(encoding="utf-8"), re.M):
                module = match.group(1)
                self.assertTrue(module in stdlib or module == "winkickoff", f"{path.name}: third-party import {module}")


if __name__ == "__main__":
    unittest.main()
