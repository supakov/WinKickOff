"""agents/: the instructions of the WinKickOff assistant for any AI agent (customer request of 10.10.2026), the
universal sibling of pi-agent/AGENTS.md.

- the folder holds AGENTS.md and README.md only, and no information about the project (the markers of
  test_pi_agent.py: an agent that reads about the source starts exploring it);
- nothing in it is tied to pi: no codemode scripts, no pi folders or commands;
- AGENTS.md agrees with the server as the pi instructions do: every tool named and none invented, every error kind in
  the error table, existing rule and group ids and resources, the mode titles and the window labels of the program.
"""

from __future__ import annotations

import re
import unittest

import test_pi_agent as pi

AGENTS_DIR = pi.REPO / "agents"
AGENTS = AGENTS_DIR / "AGENTS.md"
README = AGENTS_DIR / "README.md"
STATUS_FIELDS = {"read_pc"}  # fields of get_status that look like tool names
PI_SPECIFIC = re.compile(r"\bpi\b|codemode|~/\.pi|tools\.mcp__|/reload\b|/mcp reconnect", re.IGNORECASE)
MARKERS = {**{what: pattern for what, pattern in pi.MARKERS.items() if what != "the folder in the source tree"},
           "the folder in the source tree": re.compile(r"(?<![\w-])agents/|pi-agent")}


class UniversalFolderTest(unittest.TestCase):
    def test_the_folder_holds_only_the_two_files(self) -> None:
        self.assertEqual(sorted(p.name for p in AGENTS_DIR.iterdir()), ["AGENTS.md", "README.md"])

    def test_no_project_markers_and_nothing_of_pi(self) -> None:
        for path in (AGENTS, README):
            text = path.read_text(encoding="utf-8")
            for what, pattern in {**MARKERS, "pi": PI_SPECIFIC}.items():
                with self.subTest(file=path.name, marker=what):
                    self.assertEqual([m.group(0) for m in pattern.finditer(text)], [], f"{path.name} mentions {what}")

    def test_no_dashes(self) -> None:
        for path in (AGENTS, README):
            with self.subTest(file=path.name):
                self.assertFalse(any(d in path.read_text(encoding="utf-8") for d in pi.DASHES))


class UniversalAgreesWithTheServerTest(pi.AgentsAgreesWithTheServerTest):
    """The checks of the pi instructions on agents/AGENTS.md, without the parts that belong to pi."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.text = AGENTS.read_text(encoding="utf-8")
        cls.ticked = pi.TICKS.findall(cls.text)

    def test_script_calls_name_real_tools(self) -> None:
        self.assertEqual(pi.SCRIPT_TOOL.findall(self.text), [])  # no scripts: the tools are called directly

    def test_every_tool_is_named_and_none_is_invented(self) -> None:
        self.assertEqual(len(self.tools), 19)
        named = {token.split("__")[-1] if token.startswith("mcp__") else token.split(".")[-1] for token in self.ticked}
        self.assertEqual(sorted(self.tools - named), [])
        for token in named:
            if pi.TOOL_LIKE.match(token) and token not in self.kinds and token not in STATUS_FIELDS:
                with self.subTest(token=token):
                    self.assertIn(token, self.tools)

    def test_mode_titles_are_the_window_titles(self) -> None:
        source = (pi.ROOT / "winkickoff" / "ui" / "main_window.py").read_text(encoding="utf-8")
        line = next(line for line in source.splitlines() if line.startswith("MODE_TITLES = "))
        for path in (AGENTS, README):
            for title in re.findall(r'N_\("([^"]+)"\)', line):
                with self.subTest(file=path.name, title=title):
                    self.assertIn(f'"{title}"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
