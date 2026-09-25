"""Translations of the rule catalog: rules/lang/<lang>.toml.

The catalog itself is written in Russian. A language file holds, per rule id, the translated fields
(title, summary, effect, risk, versions, verify, rollback), parameter titles (params.<name>) and option
titles (values.<name>."<value>"); the table _groups holds group titles and summaries. A missing
translation falls back to the Russian text of the catalog.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import Catalog, Group, Param, Rule

SOURCE_LANGUAGE = "ru"
LANGUAGES = ("ru", "uk", "en")
RULE_FIELDS = ("title", "summary", "effect", "risk", "versions", "verify", "rollback")


@dataclass
class CatalogTexts:
    """Texts of the catalog in one language, with fallback to the Russian source."""

    language: str
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    groups: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def load(cls, rules_dir: Path, language: str) -> CatalogTexts:
        if language == SOURCE_LANGUAGE:
            return cls(language)
        path = rules_dir / "lang" / f"{language}.toml"
        with path.open("rb") as handle:
            data = tomllib.load(handle)
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

    def missing(self, catalog: Catalog) -> list[str]:
        """Every text of the catalog that has no translation in this language."""
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


# --------------------------------------------------------------------------- interface strings
#
# The source language of the program is Russian and the Russian text itself is the key (as in
# gettext): tr("Сохранить") returns the translation from resources/strings.<lang>.json or the text
# itself. Templates use positional fields: tr("Профиль «{0}» открыт", name). N_() only marks a text
# for translation where it is stored before the language is known (module-level constants); the
# text is translated with tr() where it is shown.

LANGUAGE_NAMES = {"ru": "Русский", "uk": "Українська", "en": "English"}

_strings: dict[str, str] = {}
_language = SOURCE_LANGUAGE
_catalog_texts = CatalogTexts(SOURCE_LANGUAGE)


def load_strings(resources_dir: Path, language: str) -> dict[str, str]:
    if language == SOURCE_LANGUAGE:
        return {}
    import json

    with (resources_dir / f"strings.{language}.json").open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {str(k): str(v) for k, v in data.items() if v}


def set_language(language: str, resources_dir: Path | None = None, rules_dir: Path | None = None) -> None:
    """Switch the interface language. Unknown languages and missing files fall back to Russian."""
    global _strings, _language, _catalog_texts
    if language not in LANGUAGES:
        language = SOURCE_LANGUAGE
    try:
        _strings = load_strings(resources_dir, language) if resources_dir is not None else {}
        _catalog_texts = CatalogTexts.load(rules_dir, language) if rules_dir is not None else CatalogTexts(language)
    except (OSError, ValueError):
        _strings, _catalog_texts, language = {}, CatalogTexts(SOURCE_LANGUAGE), SOURCE_LANGUAGE
    _language = language


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
