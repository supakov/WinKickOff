"""Documentation of the repository: languages, structure, generated rule lists, links, dashes.

- docs/technical is English: Cyrillic only inside «quoted names» (Windows labels, data), inline code and fenced code;
- docs/user/{ru,uk,en} have the same files with the same headings structure;
- docs/user/<lang>/rules.md equals what tools/make_rule_docs.py generates now;
- the catalog translations rules/lang/{ru,uk}.toml are complete (English is the source);
- every relative Markdown link resolves, including #anchors;
- no em or en dash anywhere in our texts;
- every text file of the repository uses CRLF line endings (an editor or an agent on Linux writes LF).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import unittest
from pathlib import Path

from winkickoff import APP_VERSION
from winkickoff.core.catalog import heading_anchors, load_catalog
from winkickoff.core.i18n import CatalogTexts

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
USER = REPO / "docs" / "user"
CYRILLIC = re.compile("[" + chr(0x0400) + "-" + chr(0x04FF) + "]")
RUSSIAN_ONLY = re.compile(r"[ыЫэЭъЪёЁ]")
DASHES = (chr(0x2013), chr(0x2014))
LANGUAGES = ("ru", "uk", "en")  # the languages of docs/user
# .claude holds worktrees of agent sessions (copies of other branches); .venv, venv and node_modules hold third-party
# files; build and dist are left by tools/build.ps1 (dist holds copies of the documentation without the appendices);
# none of them is part of the repository
SKIP_PARTS = {".git", "__pycache__", "A-unattendedwinstall", "output", "logs", ".claude", ".venv", "venv", "node_modules",
              "build", "dist"}
FROZEN = "docs/appendices/"  # the originals there keep their own bytes, line endings included
CRLF_FIX = ("python3 -c \"import pathlib,sys; [pathlib.Path(p).write_bytes(pathlib.Path(p).read_bytes()"
            ".replace(b'\\r\\n', b'\\n').replace(b'\\n', b'\\r\\n')) for p in sys.argv[1:]]\" FILE...")


def markdown_files() -> list[Path]:
    return [p for p in REPO.rglob("*.md") if not SKIP_PARTS & set(p.relative_to(REPO).parts)]


def prose_lines(text: str) -> list[str]:
    """Lines outside fenced code, with inline code and «quoted names» removed."""
    out: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            out.append(re.sub(r"«[^»]*»", "", re.sub(r"`[^`]*`", "", line)))
    return out


def headings(text: str) -> list[int]:
    levels: list[int] = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
        elif not in_code:
            m = re.match(r"^(#{1,6})\s", line)
            if m:
                levels.append(len(m.group(1)))
    return levels


class DocsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=REPO)

    def test_no_dashes(self) -> None:
        files = markdown_files() + list((ROOT / "rules" / "lang").glob("*.toml"))
        bad = [str(p.relative_to(REPO)) for p in files if any(d in p.read_text(encoding="utf-8") for d in DASHES)]
        self.assertEqual(bad, [])

    def test_text_files_use_crlf(self) -> None:
        """Tracked files and new files that git does not ignore: a bare LF means a file written on Linux and not
        converted; .gitattributes stores files as they are, so it would reach the repository like that."""
        try:
            listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=REPO,
                                    capture_output=True, check=True, timeout=60).stdout
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git is not available or this is not a clone")
        bad: list[str] = []
        for name in listed.decode("utf-8").split("\0"):
            path = REPO / name
            if not name or name.startswith(FROZEN) or SKIP_PARTS & set(name.split("/")) or not path.is_file():
                continue
            data = path.read_bytes()
            if b"\0" not in data and b"\n" in data.replace(b"\r\n", b""):  # binary files contain zero bytes
                bad.append(name)
        self.assertEqual(bad, [], f"convert to CRLF: {CRLF_FIX}")

    def test_release_notes_of_this_version_exist(self) -> None:
        # .github/workflows/build.yml publishes a tag v<APP_VERSION> with these notes
        notes = REPO / "docs" / "releases" / f"v{APP_VERSION}.md"
        self.assertTrue(notes.exists(), notes)
        text = notes.read_text(encoding="utf-8")
        for heading in ("## Русский", "## Українська", "## English"):
            self.assertIn(heading, text)

    def test_technical_docs_are_english(self) -> None:
        bad = []
        for path in sorted((REPO / "docs" / "technical").rglob("*.md")):
            for line in prose_lines(path.read_text(encoding="utf-8")):
                if CYRILLIC.search(line):
                    bad.append(f"{path.relative_to(REPO)}: {line.strip()[:80]}")
        self.assertEqual(bad, [])

    def test_user_docs_have_the_same_structure_in_every_language(self) -> None:
        names = {lang: sorted(p.name for p in (USER / lang).glob("*.md")) for lang in LANGUAGES}
        self.assertEqual(names["uk"], names["ru"])
        self.assertEqual(names["en"], names["ru"])
        self.assertIn("rules.md", names["ru"])
        for name in names["ru"]:
            source = headings((USER / "ru" / name).read_text(encoding="utf-8"))
            for lang in ("uk", "en"):
                with self.subTest(file=f"{lang}/{name}"):
                    self.assertEqual(headings((USER / lang / name).read_text(encoding="utf-8")), source)

    def test_english_user_docs_have_no_russian_prose(self) -> None:
        for path in sorted((USER / "en").glob("*.md")):
            with self.subTest(file=path.name):
                lines = [line for line in prose_lines(path.read_text(encoding="utf-8")) if CYRILLIC.search(line)]
                self.assertEqual(lines, [])

    def test_ukrainian_user_docs_have_no_russian_letters(self) -> None:
        for path in sorted((USER / "uk").glob("*.md")):
            with self.subTest(file=path.name):
                lines = [line for line in prose_lines(path.read_text(encoding="utf-8")) if RUSSIAN_ONLY.search(line)]
                self.assertEqual(lines, [])

    def test_rule_lists_are_up_to_date(self) -> None:
        spec = importlib.util.spec_from_file_location("make_rule_docs", ROOT / "tools" / "make_rule_docs.py")
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        for lang in LANGUAGES:
            with self.subTest(language=lang):
                on_disk = (USER / lang / "rules.md").read_text(encoding="utf-8").replace("\r\n", "\n")
                self.assertEqual(on_disk, module.expected(self.catalog, lang), "run python tools/make_rule_docs.py")

    def test_catalog_translations_are_complete(self) -> None:
        for lang in ("ru", "uk"):  # the catalog source is English
            with self.subTest(language=lang):
                texts = CatalogTexts.load(ROOT / "rules", lang)
                self.assertEqual(texts.missing(self.catalog), [])
                self.assertEqual(texts.unknown(self.catalog), [])
        self.assertFalse((ROOT / "rules" / "lang" / "en.toml").exists(), "English is the source, not a translation")
        ukrainian = (ROOT / "rules" / "lang" / "uk.toml").read_text(encoding="utf-8")
        self.assertEqual([l for l in ukrainian.splitlines() if RUSSIAN_ONLY.search(l)], [])

    def test_every_path_named_in_agents_md_exists(self) -> None:
        """Paths in backticks that start at the repository root (docs/, WinKickOff/, tools/) exist.
        Patterns with <placeholders> or wildcards and the program's working folders are skipped."""
        text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
        working = ("WinKickOff/output", "WinKickOff/logs", "WinKickOff/settings.json")
        missing = []
        for token in re.findall(r"`([^`\s]+)`", text):
            token = token.replace("\\", "/").rstrip("/")
            if not token.startswith(("docs/", "WinKickOff/", "tools/")) or any(c in token for c in "<*{"):
                continue
            if token.startswith(working):
                continue
            if not (REPO / token).exists():
                missing.append(token)
        self.assertEqual(missing, [])

    def test_relative_links_resolve(self) -> None:
        bad = []
        for path in markdown_files():
            for m in re.finditer(r"\]\(([^)\s]+)\)", path.read_text(encoding="utf-8")):
                target = m.group(1)
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                file_part, _, anchor = target.partition("#")
                dest = (path.parent / file_part).resolve() if file_part else path
                if not dest.exists():
                    bad.append(f"{path.relative_to(REPO)} -> {target}")
                elif anchor and dest.suffix == ".md" and anchor not in heading_anchors(dest.read_text(encoding="utf-8")):
                    bad.append(f"{path.relative_to(REPO)} -> {target} (no heading)")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
