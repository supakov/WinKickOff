"""The WinKickOff assistant of pi-agent/: an image of the pi agent that works only through the WinKickOff MCP tools.

The customer decided that the folder pi-agent/ holds no information about the project itself: an agent that reads about
source files, tests or rule files starts exploring them. pi-agent/AGENTS.md is the system prompt of the agent and
pi-agent/README.md is read by the person who runs the container; the Dockerfile copies only AGENTS.md into the image.
These tests keep it so:

- AGENTS.md, README.md and the Dockerfile contain none of the project-internal markers of MARKERS. Each marker is a
  word or a path that legitimate text about the assistant never needs: a path into the source tree ("WinKickOff/",
  "rules/", "tests/", ".toml"), the old bind mount ("/projects"), test runs ("unittest"), version control ("git" as a
  word, which leaves "GitHub" and "digit" alone; "commit"), line endings ("CRLF", "line ending"), the source code as
  something to read ("source code", "source files", "repository"), Python (the image has none), the folder name
  "pi-agent/" and the removed in-container check script. The program's own folders the person sees ("profiles",
  "output") and file names such as "rules.md" or "autounattend.xml" stay allowed;
- the Dockerfile mounts nothing (only the named volume pi-winkickoff appears in run commands), copies only AGENTS.md,
  starts pi in /work, names neither Python nor git among the packages it installs and takes Node.js from the checked
  release archive, not from NodeSource's package, which depends on python3 (a test of the Dockerfile cannot see the
  dependencies apt pulls in: the CI check runs "command -v python3" in the built image), and its pi wrapper switches
  pi's own tools off, pins the system prompt and allows exactly the tools of the server (the 18 WinKickOff tools as
  mcp__winkickoff__<tool> and pi's three resource tools), so a new tool fails here until the wrapper names it;
- every tool, rule id, group id and winkickoff:// resource named in AGENTS.md exists in the server, all 18 tools are
  named, the mode titles are the window's, and every Russian or Ukrainian window label is a translation of the program.
"""

from __future__ import annotations

import dataclasses
import json
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
REPO = ROOT.parent
PI_AGENT = REPO / "pi-agent"
AGENTS = PI_AGENT / "AGENTS.md"
README = PI_AGENT / "README.md"
DOCKERFILE = PI_AGENT / "Dockerfile"
CI_SCRIPT = REPO / ".github" / "scripts" / "check_pi_agent.py"
MARKERS = {
    # "rules/" after a slash is the resource winkickoff://catalog/rules/<id>, not a folder
    "a path into the source tree": re.compile(r"WinKickOff/|(?<![/\w])(rules|tests?)/|\.toml\b"),
    "the old bind mount": re.compile(r"/projects\b"),
    "test runs": re.compile(r"\bunittest\b"),
    "version control": re.compile(r"\bgit\b|\bcommit", re.IGNORECASE),
    "line endings": re.compile(r"\bCRLF\b|line ending", re.IGNORECASE),
    "the source code": re.compile(r"\bsource (code|files?|tree)\b|\brepository\b", re.IGNORECASE),
    "Python": re.compile(r"\bpython", re.IGNORECASE),
    "the folder in the source tree": re.compile(r"pi-agent/"),
    "the removed check script": re.compile(r"check_container|Validate-Unattend"),
}
TICKS = re.compile(r"`([^`\n]+)`")
TOOL_LIKE = re.compile(r"^(get|list|set|check|preview|diff|load|show|save|write|read)_[a-z_]+$")
CLIENT_TOOLS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}  # pi's own resource tools
DOTTED = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z0-9-]+)+$")
FILE_SUFFIXES = (".md", ".json", ".xml", ".ps1")
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")
QUOTED = re.compile(r'"([^"]+)"')
WRAPPER_FLAGS = ("--no-extensions", "-e builtin:mcp", "--no-builtin-tools",
                 "--exclude-tools read,bash,edit,write,grep,find,ls,powershell,codemode,tool_search", "--no-skills",
                 "--no-context-files", "--no-prompt-templates", "--system-prompt /work/AGENTS.md",
                 "--append-system-prompt /dev/null")
SERVER = "winkickoff"
NOT_INSTALLED = {"python3", "python3-pip", "python3-venv", "python-is-python3", "git", "file"}
DASHES = (chr(0x2013), chr(0x2014))


def instructions(dockerfile: str) -> list[str]:
    """The instructions of a Dockerfile, continuation lines joined, comment lines dropped."""
    out: list[str] = []
    current = ""
    for line in dockerfile.splitlines():
        if line.lstrip().startswith("#") or not line.strip():
            continue
        current += " " + line.strip()
        if current.endswith("\\"):
            current = current[:-1]
            continue
        out.append(current.strip())
        current = ""
    if current.strip():
        out.append(current.strip())
    return out


class NoProjectInformationTest(unittest.TestCase):
    def test_no_project_markers(self) -> None:
        for path in (AGENTS, README, DOCKERFILE):
            text = path.read_text(encoding="utf-8")
            for what, pattern in MARKERS.items():
                with self.subTest(file=path.name, marker=what):
                    found = [m.group(0) for m in pattern.finditer(text)]
                    self.assertEqual(found, [], f"{path.name} mentions {what}")

    def test_the_folder_holds_only_the_three_files(self) -> None:
        self.assertEqual(sorted(p.name for p in PI_AGENT.iterdir()), ["AGENTS.md", "Dockerfile", "README.md"])
        self.assertTrue(CI_SCRIPT.is_file(), "the CI check of the image lives outside pi-agent/")

    def test_no_dashes(self) -> None:
        for path in (DOCKERFILE, CI_SCRIPT, REPO / ".github" / "workflows" / "build.yml"):
            with self.subTest(file=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertFalse(any(d in text for d in DASHES))


class DockerfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = DOCKERFILE.read_text(encoding="utf-8")
        cls.instructions = instructions(cls.text)

    def test_copies_only_the_instructions_and_mounts_nothing(self) -> None:
        copies = [i for i in self.instructions if i.split()[0].upper() in ("COPY", "ADD")]
        self.assertEqual(copies, ["COPY AGENTS.md /work/AGENTS.md"])
        self.assertFalse([i for i in self.instructions if i.split()[0].upper() == "VOLUME"])
        self.assertNotIn("--mount", self.text)
        for path in (DOCKERFILE, README):
            with self.subTest(file=path.name):
                runs = [line for line in path.read_text(encoding="utf-8").splitlines() if "podman run" in line]
                mounts = [m for line in runs for m in re.findall(r"\s-v\s+(\S+)", line)]
                self.assertNotIn("--volume", "\n".join(runs))
                self.assertTrue(mounts)
                self.assertEqual(set(mounts), {"pi-winkickoff:/home/pi/.pi"}, "only the named volume of pi's settings")

    def test_starts_pi_in_work(self) -> None:
        self.assertIn("WORKDIR /work", self.instructions)
        self.assertEqual(self.instructions[-1], 'CMD ["pi"]')

    def test_names_neither_python_nor_git_and_takes_node_from_the_checked_archive(self) -> None:
        packages: set[str] = set()
        for instruction in self.instructions:
            for part in instruction.split("&&"):
                words = part.split()
                if "apt-get" in words and "install" in words:
                    packages.update(w for w in words[words.index("install") + 1:] if not w.startswith("-"))
        self.assertTrue(packages)
        self.assertEqual(sorted(packages & (NOT_INSTALLED | {"nodejs", "npm"})), [])
        self.assertNotIn("deb.nodesource.com", self.text)
        node = next(i for i in self.instructions if "nodejs.org/dist/" in i)
        self.assertIn("sha256sum -c", node)
        self.assertIn("ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/node/bin",
                      self.instructions, "npm's own pi link must come after the wrapper in PATH")

    def test_the_wrapper_switches_pi_tools_off(self) -> None:
        wrapper = next(i for i in self.instructions if "/usr/local/bin/pi" in i and "printf" in i)
        for flag in WRAPPER_FLAGS:
            with self.subTest(flag=flag):
                self.assertIn(flag, wrapper)
        self.assertIn('test "$(command -v pi)" = /usr/local/bin/pi', wrapper)
        self.assertIn('test "$real" != /usr/local/bin/pi', wrapper, "the wrapper must not write through npm's link")
        self.assertIn('/dev/null "$@"', wrapper, "the arguments of the person come last, after the image's flags")


class AgentsAgreesWithTheServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        paths = AppPaths(root=ROOT, data=ROOT, docs_root=REPO, profiles=base / "profiles", output=base / "output",
                         logs=base / "logs")
        languages = tuple(available_languages(ROOT / "resources", ROOT / "rules"))
        cls.tools = set(ToolRegistry(dataclasses.replace(paths, root=base), languages).specs)
        registry = ResourceRegistry(paths, languages)  # root = WinKickOff/: the skill folder is served too
        cls.uris = {item["uri"] for item in registry.listing()}
        cls.templates = [item["uriTemplate"] for item in registry.templates()]
        catalog = load_catalog(ROOT / "rules", docs_root=REPO)
        cls.ids = set(catalog.rules) | set(catalog.groups)
        cls.prefixes = {item.split(".", 1)[0] for item in cls.ids}
        cls.text = AGENTS.read_text(encoding="utf-8")
        cls.ticked = TICKS.findall(cls.text)
        sources = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "winkickoff").rglob("*.py"))
        cls.kinds = (set(re.findall(r'ToolError\(\s*"([a-z_]+)"', sources))
                     | set(re.findall(r'super\(\)\.__init__\(\s*"([a-z_]+)"', sources))
                     | set(re.findall(r'"error": "([a-z_]+)"', sources)))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_error_table_names_every_kind_of_the_server(self) -> None:
        """The agent sees only the text of a refusal, which starts with the kind: every kind needs a row."""
        errors = self.text.split("## 5. Errors", 1)[1].split("\n## ", 1)[0]
        named = {kind for row in errors.splitlines() if row.startswith("| `")
                 for kind in TICKS.findall(row.split("|")[1])}
        self.assertEqual(sorted(self.kinds - named), [])
        self.assertEqual(sorted(named - self.kinds), [])

    def test_the_wrapper_allows_exactly_the_tools_of_the_server(self) -> None:
        wrapper = next(i for i in instructions(DOCKERFILE.read_text(encoding="utf-8"))
                       if "/usr/local/bin/pi" in i and "printf" in i)
        allowed = re.findall(r"--tools (\S+)", wrapper)
        self.assertEqual(len(allowed), 1)
        expected = {f"mcp__{SERVER}__{name}" for name in self.tools} | CLIENT_TOOLS
        self.assertEqual(sorted(allowed[0].split(",")), sorted(expected))

    def test_every_tool_is_named_and_none_is_invented(self) -> None:
        self.assertEqual(len(self.tools), 18)
        named = {token.split("__")[-1] if token.startswith("mcp__") else token for token in self.ticked}
        self.assertEqual(sorted(self.tools - named), [])
        self.assertEqual(sorted(CLIENT_TOOLS - named), [])
        for token in named:
            if TOOL_LIKE.match(token) and token not in CLIENT_TOOLS and token not in self.kinds:  # load_failed is a kind
                with self.subTest(token=token):
                    self.assertIn(token, self.tools)

    def test_rule_and_group_ids_exist(self) -> None:
        for token in self.ticked:
            if not DOTTED.match(token) or token.endswith(FILE_SUFFIXES) or token.split(".", 1)[0] not in self.prefixes:
                continue
            with self.subTest(token=token):
                self.assertIn(token, self.ids)

    def test_resources_exist(self) -> None:
        self.assertIn("winkickoff://skill/SKILL.md", self.uris)
        patterns = [re.compile("^" + re.sub(r"\\\{[a-z]+\\\}", "[^/]+", re.escape(t)) + "$") for t in self.templates]
        uris = re.findall(r"winkickoff://[^`\s)\"]+", self.text)
        self.assertIn("winkickoff://skill/SKILL.md", uris)
        for uri in uris:
            uri = re.sub(r"<[a-z]+>", "x", uri.rstrip(".,;:"))
            with self.subTest(uri=uri):
                self.assertTrue(uri in self.uris or any(p.match(uri) for p in patterns), uri)

    def test_mode_titles_are_the_window_titles(self) -> None:
        source = (ROOT / "winkickoff" / "ui" / "main_window.py").read_text(encoding="utf-8")
        line = next(line for line in source.splitlines() if line.startswith("MODE_TITLES = "))
        titles = re.findall(r'N_\("([^"]+)"\)', line)
        self.assertEqual(len(titles), 3)
        for path in (AGENTS, README):
            for title in titles:
                with self.subTest(file=path.name, title=title):
                    self.assertIn(f'"{title}"', path.read_text(encoding="utf-8"))

    def test_window_labels_are_the_program_translations(self) -> None:
        strings = {code: json.loads((ROOT / "resources" / f"strings.{code}.json").read_text(encoding="utf-8"))
                   for code in ("ru", "uk")}
        rows = [line for line in self.text.splitlines() if line.startswith("|") and CYRILLIC.search(line)]
        self.assertGreaterEqual(len(rows), 10)
        for row in rows:
            quoted = QUOTED.findall(row)
            english, translated = quoted[0], [q for q in quoted if CYRILLIC.search(q)]
            with self.subTest(label=english):
                self.assertIn(english, strings["ru"])
                self.assertEqual(translated, [strings["ru"][english], strings["uk"][english]])


if __name__ == "__main__":
    unittest.main()
