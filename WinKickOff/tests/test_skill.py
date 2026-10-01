"""The Agent Skill in skills/winkickoff: a valid skill that agrees with the MCP server and the catalog.

The skill teaches AI agents that use WinKickOff over MCP; it goes stale silently when a tool, an error kind, a rule
or a resource changes. These tests tie it to the code:
- SKILL.md has the frontmatter of the Agent Skills format: name equal to the folder (lowercase letters, digits and
  hyphens, at most 64 characters, no reserved word), a description of at most 200 characters (the limit of uploads to
  Claude Desktop and claude.ai) and no angle brackets; its body stays under 500 lines;
- every tool of the server and every error kind of the code is named in SKILL.md, and nothing in the skill names a tool
  or an error kind the server does not have;
- every rule id, group id and winkickoff:// resource written in backticks exists; the mode titles are the window's.
Dashes, links and line endings of the skill files are checked by test_docs.py with every Markdown file.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.i18n import available_languages
from winkickoff.core.paths import AppPaths
from winkickoff.mcp.resources import ResourceRegistry
from winkickoff.mcp.tools import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "winkickoff"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TICKS = re.compile(r"`([^`\n]+)`")
TOOL_LIKE = re.compile(r"^(get|list|set|check|preview|diff|load|show|save|write)_[a-z_]+$")
CLIENT_TOOLS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}  # pi's own resource tools
DOTTED = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)+$")
FILE_SUFFIXES = (".md", ".json", ".xml", ".ps1", ".exe", ".toml", ".py", ".log", ".cmd", ".zip", ".txt", ".yml")
MODE_TITLES = ("Read only", "Read and change the open profile", "Change and create files")


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    """The top-level keys of the YAML frontmatter (single-line values; nested blocks are kept as raw text) and the body."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise AssertionError("SKILL.md must start with a frontmatter block between --- lines")
    end = lines.index("---", 1)
    fields: dict[str, str] = {}
    key = ""
    for line in lines[1:end]:
        if line and not line[0].isspace() and ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
        elif key:
            fields[key] += "\n" + line
    return fields, "\n".join(lines[end + 1:])


def skill_files() -> list[Path]:
    return sorted(SKILL.rglob("*.md"))


def ticked(path: Path) -> list[str]:
    return TICKS.findall(path.read_text(encoding="utf-8"))


class SkillFormatTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.fields, self.body = frontmatter(self.text)

    def test_name_matches_the_folder_and_the_rules_of_the_format(self) -> None:
        name = self.fields.get("name", "")
        self.assertEqual(name, SKILL.name)
        self.assertRegex(name, NAME_RE)
        self.assertLessEqual(len(name), 64)
        self.assertFalse({"anthropic", "claude"} & set(name.split("-")))

    def test_description_says_what_and_when_within_the_limits(self) -> None:
        description = self.fields.get("description", "")
        self.assertTrue(description)
        self.assertLessEqual(len(description), 200, "Claude Desktop and claude.ai refuse longer descriptions")
        self.assertIn("WinKickOff", description)
        self.assertNotRegex(self.text.split("---", 2)[1], r"[<>]")  # no XML-like tags in the frontmatter
        self.assertLessEqual(len(self.fields.get("compatibility", "")), 500)

    def test_body_is_short_and_points_to_the_references(self) -> None:
        self.assertLess(len(self.body.splitlines()), 500)
        for name in ("tools.md", "workflows.md", "concepts.md"):
            with self.subTest(reference=name):
                self.assertTrue((SKILL / "references" / name).is_file())
                self.assertIn(f"](references/{name}", self.body)


class SkillAgreesWithTheServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        paths = AppPaths(root=base, data=ROOT, docs_root=ROOT.parent, profiles=base / "profiles", output=base / "output",
                         logs=base / "logs")
        languages = tuple(available_languages(ROOT / "resources", ROOT / "rules"))
        cls.tools = set(ToolRegistry(paths, languages).specs)
        registry = ResourceRegistry(paths, languages)
        cls.uris = {item["uri"] for item in registry.listing()}
        cls.templates = [item["uriTemplate"] for item in registry.templates()]
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.ids = set(catalog.rules) | set(catalog.groups)
        cls.prefixes = {item.split(".", 1)[0] for item in cls.ids}
        sources = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "winkickoff").rglob("*.py"))
        # ToolError("kind", ...), subclasses that pass a kind to super().__init__, and the result_too_large result
        cls.kinds = (set(re.findall(r'ToolError\(\s*"([a-z_]+)"', sources))
                     | set(re.findall(r'super\(\)\.__init__\(\s*"([a-z_]+)"', sources))
                     | set(re.findall(r'"error": "([a-z_]+)"', sources)))
        cls.skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_every_tool_is_in_skill_md_and_no_other_is_named(self) -> None:
        self.assertEqual(len(self.tools), 18)
        named = set(TICKS.findall(self.skill_md))
        self.assertEqual(sorted(self.tools - named), [])
        for path in skill_files():
            for token in ticked(path):
                tool = token.split("__")[-1] if token.startswith("mcp__") else token
                if TOOL_LIKE.match(tool) and tool not in CLIENT_TOOLS and tool not in self.kinds:  # load_failed is a kind
                    with self.subTest(file=path.name, token=token):
                        self.assertIn(tool, self.tools)

    def test_every_error_kind_is_explained_and_none_is_invented(self) -> None:
        self.assertIn("mode_required", self.kinds)
        named = set(TICKS.findall(self.skill_md))
        self.assertEqual(sorted(self.kinds - named), [])
        errors = self.skill_md.split("## Errors", 1)[1].split("\n## ", 1)[0]
        for row in errors.splitlines():
            if row.startswith("| `"):
                for kind in TICKS.findall(row.split("|")[1]):
                    with self.subTest(kind=kind):
                        self.assertIn(kind, self.kinds)

    def test_rule_and_group_ids_exist(self) -> None:
        for path in skill_files():
            for token in ticked(path):
                ident = token[2:] if token[:2] in ("r:", "g:") else token
                if not DOTTED.match(ident) or ident.endswith(FILE_SUFFIXES) or ident.split(".", 1)[0] not in self.prefixes:
                    continue
                with self.subTest(file=path.name, token=token):
                    self.assertIn(ident, self.ids)

    def test_resources_exist(self) -> None:
        patterns = [re.compile("^" + re.sub(r"\\\{[a-z]+\\\}", "[^/]+", re.escape(t)) + "$") for t in self.templates]
        for path in skill_files():
            for uri in re.findall(r"winkickoff://[^`\s)\"]+", path.read_text(encoding="utf-8")):
                uri = re.sub(r"<[a-z]+>", "x", uri.rstrip(".,;:"))
                with self.subTest(file=path.name, uri=uri):
                    concrete = uri in self.uris or uri in self.templates
                    self.assertTrue(concrete or any(p.match(uri) for p in patterns), uri)
                    if uri.startswith("winkickoff://docs/") and "{" not in uri and "/x" not in uri:
                        relative = uri[len("winkickoff://docs/"):].replace("reference/", "technical/reference/", 1)
                        self.assertTrue((ROOT.parent / "docs" / relative).is_file(), relative)

    def test_mode_titles_are_the_window_titles(self) -> None:
        # read from the source: importing the window needs tkinter, which the Linux container of pi-agent/ lacks
        source = (ROOT / "winkickoff" / "ui" / "main_window.py").read_text(encoding="utf-8")
        line = next(line for line in source.splitlines() if line.startswith("MODE_TITLES = "))
        self.assertEqual(MODE_TITLES, tuple(re.findall(r'N_\("([^"]+)"\)', line)))
        for title in MODE_TITLES:
            with self.subTest(title=title):
                self.assertIn(f'"{title}"', self.skill_md)


if __name__ == "__main__":
    unittest.main()
