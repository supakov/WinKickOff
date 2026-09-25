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
