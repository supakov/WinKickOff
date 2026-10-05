"""Translations of the interface and of the rule catalog.

The source language is English: the code and the rule catalog are written in English, and the English
text is the key of every translation. A language is available as soon as one of its files exists, so a
user adds a language without touching the code:

- resources/strings.<code>.json: {"_language": "<native name>", "<English text>": "<translation>", ...};
- rules/lang/<code>.json: {"_language": "<native name>", "_comment": [...], "<rule id>": {...}, "_groups": {...}};
  per rule id the translated fields (title, summary, effect, risk, versions, verify, rollback), parameter titles
  ("params": {"<name>": ...}), option titles ("values": {"<name>": {"<value>": ...}}) and search tags ("tags": [...]);
  "_groups" holds group titles and summaries; "_language" names the language when there is no strings file and
  "_comment" is a remark for translators. The file is strict JSON (core/jsonfile.py).

Anything missing (a file, a rule, a field, a string) falls back to the English source.
"""

from __future__ import annotations

import json
import locale
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.catalog import Catalog, Group, Param, Rule

log = logging.getLogger(__name__)
SOURCE_LANGUAGE = "en"
SOURCE_NAME = "English"
RULE_FIELDS = ("title", "summary", "effect", "risk", "versions", "verify", "rollback")
LANG_KEYS = ("_language", "_comment", "_groups")  # the keys of a language file that are not rule ids
GROUP_FIELDS = ("title", "summary")
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
        path = rules_dir / "lang" / f"{language}.json"
        if language == SOURCE_LANGUAGE or not path.exists():
            return cls(language)
        data = jsonfile.read(path)
        problem = language_file_problem(data)
        if problem:
            raise ValueError(f"{path.name}: {problem}")
        groups = data.pop("_groups", {})
        rules = {key: value for key, value in data.items() if key not in LANG_KEYS}
        return cls(language, rules=rules, groups=groups)

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


def language_file_problem(data: Any) -> str:
    """What is wrong with the shape of a rules/lang/<code>.json file, or "": a misspelt field is an error, like in
    the catalog, and a text of a wrong type never reaches the window."""
    if not isinstance(data, dict):
        return "the file must hold a JSON object"
    for key, value in data.items():
        if key == "_language" and not isinstance(value, str):
            return "_language must be a string"
        if key == "_comment" and not (isinstance(value, list) and all(isinstance(line, str) for line in value)):
            return "_comment must be a list of strings"
        if key == "_groups":
            if not isinstance(value, dict):
                return "_groups must be an object"
            for group_id, entry in value.items():
                if not isinstance(entry, dict) or set(entry) - set(GROUP_FIELDS) \
                        or not all(isinstance(text, str) for text in entry.values()):
                    return f"_groups.{group_id}: an object with the strings {list(GROUP_FIELDS)}"
        elif key.startswith("_") and key not in LANG_KEYS:
            return f"unknown key {key!r} (expected {list(LANG_KEYS)} or rule ids)"
        elif not key.startswith("_"):
            problem = _rule_entry_problem(value)
            if problem:
                return f"{key}: {problem}"
    return ""


def _rule_entry_problem(entry: Any) -> str:
    if not isinstance(entry, dict):
        return "the entry of a rule must be an object"
    for field_name, value in entry.items():
        if field_name in RULE_FIELDS:
            if not isinstance(value, str):
                return f"{field_name} must be a string"
        elif field_name == "params":
            if not isinstance(value, dict) or not all(isinstance(text, str) for text in value.values()):
                return "params must be an object of strings"
        elif field_name == "values":
            if not isinstance(value, dict) or not all(
                    isinstance(options, dict) and all(isinstance(text, str) for text in options.values())
                    for options in value.values()):
                return "values must be an object of objects of strings"
        elif field_name == "tags":
            if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
                return "tags must be a list of strings"
        else:
            return f"unknown field {field_name!r}"
    return ""


# --------------------------------------------------------------------------- languages


def available_languages(resources_dir: Path | None, rules_dir: Path | None) -> dict[str, str]:
    """Language code -> native name, English first: every strings.<code>.json and rules/lang/<code>.json."""
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
        for path in sorted((rules_dir / "lang").glob("*.json")):
            code = path.stem
            if not _CODE.match(code) or code == SOURCE_LANGUAGE or code in found:
                continue
            try:
                name = jsonfile.read(path).get("_language")
            except (OSError, ValueError, AttributeError) as exc:
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
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: the file must hold a JSON object")
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
