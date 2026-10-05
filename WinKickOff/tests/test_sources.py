"""Project rules enforced on the sources: no cwd/APPDATA access, no registry writes, no dashes, only stdlib,
English code comments."""

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
    re.compile(r"\bwinreg\.(SetValue|SetValueEx|CreateKey|CreateKeyEx|DeleteKey|DeleteKeyEx|DeleteValue|SaveKey|LoadKey)\b"),
    re.compile(r"\bimport (requests|urllib|http\.client|socket)\b"),
    # system-wide appearance: colours, parameters and hooks outside this program (themes stay inside the window)
    re.compile(r"\b(SetSysColors|SystemParametersInfo\w*|SetWindowsHookEx\w*|RegSetValue\w*|RegCreateKey\w*)\b"),
)
# the only module that may read the registry: themes.py reads the Windows light or dark mode, nothing else
REGISTRY_READERS = {"themes.py"}
# the only module that may listen on a socket: the MCP loopback listener, off by default, started by the user (T22)
NETWORK_MODULES = {"httpserver.py"}
LISTENER = re.compile(r"(?:from|import) (?:http\.server|socketserver)|from socket import")
MCP_PACKAGE = PACKAGE / "mcp"
WINREG = re.compile(r"\bwinreg\b")
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")
DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")  # built from code points: the source must not contain them


def _text_files() -> list[Path]:
    files: list[Path] = []
    for pattern in ("winkickoff/**/*.py", "rules/**/*.json", "resources/*.json", "tests/*.py", "tools/*.py", "*.md", "*.toml", "templates/*"):
        files.extend(p for p in ROOT.glob(pattern) if p.is_file())
    return files


class SourceRulesTest(unittest.TestCase):
    def test_no_forbidden_calls_in_package(self) -> None:
        for path in PACKAGE.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN:
                self.assertIsNone(pattern.search(text), f"{path.name}: forbidden pattern {pattern.pattern}")
            if path.name not in REGISTRY_READERS:
                self.assertIsNone(WINREG.search(text), f"{path.name}: registry access outside {REGISTRY_READERS}")
            if path.name not in NETWORK_MODULES:
                self.assertIsNone(LISTENER.search(text), f"{path.name}: a network listener outside {NETWORK_MODULES}")
            self.assertNotRegex(text, r"0\.0\.0\.0|bind\(\s*\(\s*\"\"", f"{path.name}: the MCP server binds 127.0.0.1 only")

    def test_mcp_server_stays_on_loopback_and_off_tkinter(self) -> None:
        """The listener binds the literal 127.0.0.1; the mcp package, the dispatcher and startup never import tkinter;
        only cli.py prints (stdout of a stdio server carries protocol messages)."""
        listener = (MCP_PACKAGE / "httpserver.py").read_text(encoding="utf-8")
        self.assertIn('HOST = "127.0.0.1"', listener)
        self.assertIn("super().__init__((HOST, port), McpHandler)", listener)
        headless = [*MCP_PACKAGE.glob("*.py"), PACKAGE / "core" / "startup.py", PACKAGE / "__main__.py", PACKAGE / "mcp_main.py"]
        for path in headless:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?:import|from) tkinter", f"{path.name}: tkinter in a headless module")
            if path.name != "cli.py":
                self.assertNotIn("print(", text, f"{path.name}: print outside cli.py")

    def test_every_dialog_of_the_window_is_counted(self) -> None:
        """Dialogs go through MainWindow._dialog(), which counts modal states for the MCP bridge (is_busy)."""
        for path in (PACKAGE / "ui").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"(?<![\w.])(messagebox|filedialog|simpledialog)\.\w+\(", text):
                line = text[:match.start()].rsplit("\n", 1)[-1] + match.group(0)
                self.assertIn("_dialog(", line, f"{path.name}: a dialog outside _dialog(): {line.strip()}")

    def test_code_and_comments_are_english(self) -> None:
        # 30.09.2026: English is the source language; Russian and Ukrainian live in the translation files
        import io
        import tokenize

        for path in list(PACKAGE.rglob("*.py")) + list((ROOT / "tools").glob("*.py")):
            if path.name == "make_rule_docs.py":  # holds the words of the generated user documentation per language
                continue
            source = path.read_text(encoding="utf-8")
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type in (tokenize.COMMENT, tokenize.STRING):
                    self.assertIsNone(CYRILLIC.search(token.string), f"{path.name}:{token.start[0]}: {token.string[:60]}")
        for path in sorted((ROOT / "rules").glob("*.json")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                self.assertFalse(CYRILLIC.search(line), f"{path.name}:{number}: the catalog source is English")

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
