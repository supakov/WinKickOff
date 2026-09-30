"""Translations of the interface and of the rule catalog.

The source language is English: the code and the rule catalog are written in English, and the English
text is the key of every translation. A language is available as soon as one of its files exists, so a
user adds a language without touching the code:

- resources/strings.<code>.json: {"_language": "<native name>", "<English text>": "<translation>", ...};
- rules/lang/<code>.toml: per rule id the translated fields (title, summary, effect, risk, versions,
  verify, rollback), parameter titles (params.<name>), option titles (values.<name>."<value>") and search
  tags (tags = [...]); the table _groups holds group titles and summaries; an optional top-level
  _language = "<native name>" names the language when there is no strings file.

Anything missing (a file, a rule, a field, a string) falls back to the English source.
"""

from __future__ import annotations

import json
import locale
import logging
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import Catalog, Group, Param, Rule

log = logging.getLogger(__name__)
SOURCE_LANGUAGE = "en"
SOURCE_NAME = "English"
RULE_FIELDS = ("title", "summary", "effect", "risk", "versions", "verify", "rollback")
_CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


@dataclass
class CatalogTexts:
    """Texts of the catalog in one language, with fallback to the English source."""

    language: str
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, rules_dir: Path, language: str) -> CatalogTexts:
        """The language file, or the English source when the language has no catalog file."""
        path = rules_dir / "lang" / f"{language}.toml"
        if language == SOURCE_LANGUAGE or not path.exists():
            return cls(language)
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        data.pop("_language", None)
        groups = data.pop("_groups", {})
        return cls(language, rules=data, groups=groups)

    def rule(self, rule: Rule, name: str) -> str:
        value = self.rules.get(rule.id, {}).get(name)
        return str(value) if value else str(getattr(rule, name))

    def group(self, group: Group, name: str) -> str:
        value = self.groups.get(group.id, {}).get(name)
        return str(value) if value else str(getattr(group, name) or "")

    def param(self, rule: Rule, param: Param) -> str:
        value = self.rules.get(rule.id, {}).get("params", {}).get(param.name)
        return str(value) if value else param.title

    def option(self, rule: Rule, param: Param, value: Any, title: str) -> str:
        translated = self.rules.get(rule.id, {}).get("values", {}).get(param.name, {}).get(str(value))
        return str(translated) if translated else title

    def tags(self, rule: Rule) -> list[str]:
        """Search tags in this language (the English tags are always searched as well)."""
        value = self.rules.get(rule.id, {}).get("tags")
        return [str(t) for t in value] if isinstance(value, list) else []

    def missing(self, catalog: Catalog) -> list[str]:
        """Every text of the catalog that has no translation in this language (tags are optional)."""
        if self.language == SOURCE_LANGUAGE:
            return []
        out: list[str] = []
        for rule in catalog.rules.values():
            entry = self.rules.get(rule.id, {})
            out += [f"{rule.id}.{name}" for name in RULE_FIELDS if getattr(rule, name) and not entry.get(name)]
            for param in rule.params.values():
                if not entry.get("params", {}).get(param.name):
                    out.append(f"{rule.id}.params.{param.name}")
                for value, _title in param.values:
                    if not entry.get("values", {}).get(param.name, {}).get(str(value)):
                        out.append(f"{rule.id}.values.{param.name}.{value}")
        for group in catalog.groups.values():
            entry = self.groups.get(group.id, {})
            if not entry.get("title"):
                out.append(f"_groups.{group.id}.title")
            if group.summary and not entry.get("summary"):
                out.append(f"_groups.{group.id}.summary")
        return out

    def unknown(self, catalog: Catalog) -> list[str]:
        """Entries of the language file that the catalog does not know (renamed or removed rules)."""
        return sorted([r for r in self.rules if r not in catalog.rules] + [f"_groups.{g}" for g in self.groups if g not in catalog.groups])


# --------------------------------------------------------------------------- languages


def available_languages(resources_dir: Path | None, rules_dir: Path | None) -> dict[str, str]:
    """Language code -> native name, English first: every strings.<code>.json and rules/lang/<code>.toml."""
    found: dict[str, str] = {}
    if resources_dir is not None:
        for path in sorted(resources_dir.glob("strings.*.json")):
            code = path.name[len("strings."):-len(".json")]
            if not _CODE.match(code) or code == SOURCE_LANGUAGE:
                continue
            try:
                name = json.loads(path.read_text(encoding="utf-8")).get("_language")
            except (OSError, ValueError, AttributeError) as exc:
                log.warning("%s ignored: %s", path.name, exc)
                continue
            found[code] = str(name or code)
    if rules_dir is not None:
        for path in sorted((rules_dir / "lang").glob("*.toml")):
            code = path.stem
            if not _CODE.match(code) or code == SOURCE_LANGUAGE or code in found:
                continue
            try:
                with path.open("rb") as handle:
                    name = tomllib.load(handle).get("_language")
            except (OSError, ValueError) as exc:
                log.warning("%s ignored: %s", path.name, exc)
                continue
            found[code] = str(name or code)
    return {SOURCE_LANGUAGE: SOURCE_NAME, **dict(sorted(found.items(), key=lambda item: item[1].lower()))}


def system_language() -> str:
    """The language of the Windows interface ("uk", "ru", "en"...), or "" when unknown."""
    name = ""
    if sys.platform == "win32":
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            name = locale.windows_locale.get(langid, "")
        except (AttributeError, OSError):
            name = ""
    if not name:
        name = locale.getlocale()[0] or ""
    return name.split("_")[0].split("-")[0].lower()


def resolve_language(wanted: str, resources_dir: Path | None, rules_dir: Path | None) -> str:
    """The language to use: the wanted one if its files exist; "" means the Windows language; else English."""
    languages = available_languages(resources_dir, rules_dir)
    code = wanted or system_language()
    return code if code in languages else SOURCE_LANGUAGE


# --------------------------------------------------------------------------- interface strings
#
# The English text is the key (as in gettext): tr("Save") returns the translation from
# resources/strings.<lang>.json or the text itself. Templates use positional fields:
# tr("Profile \"{0}\" opened", name). N_() only marks a text for translation where it is stored before
# the language is known (module-level constants); the text is translated with tr() where it is shown.

_strings: dict[str, str] = {}
_language = SOURCE_LANGUAGE
_catalog_texts = CatalogTexts(SOURCE_LANGUAGE)


def load_strings(resources_dir: Path, language: str) -> dict[str, str]:
    """The translations of one language; an absent file gives none (English is shown)."""
    path = resources_dir / f"strings.{language}.json"
    if language == SOURCE_LANGUAGE or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {str(k): str(v) for k, v in data.items() if v and not str(k).startswith("_")}


def set_language(language: str, resources_dir: Path | None = None, rules_dir: Path | None = None) -> None:
    """Switch the interface language. "" follows Windows; an unknown language or a broken file gives
    English for the part that failed."""
    global _strings, _language, _catalog_texts
    code = resolve_language(language, resources_dir, rules_dir) if resources_dir is not None or rules_dir is not None else (
        language if language == SOURCE_LANGUAGE else SOURCE_LANGUAGE)
    try:
        _strings = load_strings(resources_dir, code) if resources_dir is not None else {}
    except (OSError, ValueError) as exc:
        log.warning("interface translation %s ignored: %s", code, exc)
        _strings = {}
    try:
        _catalog_texts = CatalogTexts.load(rules_dir, code) if rules_dir is not None else CatalogTexts(code)
    except (OSError, ValueError) as exc:
        log.warning("catalog translation %s ignored: %s", code, exc)
        _catalog_texts = CatalogTexts(code)
    _language = code


def language() -> str:
    return _language


def catalog_texts() -> CatalogTexts:
    return _catalog_texts


def tr(text: str, *args: Any) -> str:
    template = _strings.get(text, text)
    if not args:
        return template
    try:
        return template.format(*args)
    except (IndexError, KeyError, ValueError):
        return text.format(*args)


def N_(text: str) -> str:  # noqa: N802 - the conventional gettext name
    return text
