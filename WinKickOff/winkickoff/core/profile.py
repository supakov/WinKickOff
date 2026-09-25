"""Profile: which rules are enabled, their parameter values, and the install data (accounts,
languages, product key, time zone). Stored as JSON next to the executable."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import Catalog

FORMAT_VERSION = 2

DEFAULT_INSTALL: dict[str, Any] = {
    "edition": "Pro",
    "product_key_mode": "generic",  # generic | custom | ask
    "product_key": "",
    "time_zone": "FLE Standard Time",
    "iso_language": "uk-UA",
}
DEFAULT_LANGUAGES: dict[str, Any] = {
    "ui_language": "uk-UA",
    "system_locale": "uk-UA",
    "user_locale": "uk-UA",
    "geo_id": 241,
    "input": ["en-US", "uk-UA", "ru-UA"],
}


@dataclass
class Account:
    name: str
    display_name: str
    group: str  # Administrators | Users
    description: str = ""
    password: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "group": self.group,
            "description": self.description,
            "password": self.password,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Account:
        return cls(
            name=str(raw.get("name", "")),
            display_name=str(raw.get("display_name", raw.get("name", ""))),
            group=str(raw.get("group", "Users")),
            description=str(raw.get("description", "")),
            password=str(raw.get("password", "")),
        )


DEFAULT_ACCOUNTS: list[Account] = [
    Account("Admin", "Admin", "Administrators", "Local administrator (starter account)"),
    Account("User", "User", "Users", "Standard user (starter account)"),
]


@dataclass
class RuleState:
    enabled: bool
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Difference:
    kind: str  # rule | param | install | languages | accounts
    key: str
    before: Any
    after: Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Profile:
    name: str
    catalog_version: str
    rules: dict[str, RuleState]
    format_version: int = FORMAT_VERSION
    author: str = ""
    created: str = field(default_factory=_now)
    modified: str = field(default_factory=_now)
    comment: str = ""
    install: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_INSTALL))
    languages: dict[str, Any] = field(default_factory=lambda: copy.deepcopy(DEFAULT_LANGUAGES))
    accounts: list[Account] = field(default_factory=lambda: [copy.copy(a) for a in DEFAULT_ACCOUNTS])
    unknown: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    # ----------------------------------------------------------------- construction

    @classmethod
    def from_catalog(cls, catalog: Catalog, name: str = "Офис") -> Profile:
        rules = {rule.id: RuleState(enabled=rule.default) for rule in catalog.rules.values()}
        return cls(name=name, catalog_version=catalog.version, rules=rules)

    def copy(self) -> Profile:
        return copy.deepcopy(self)

    # ----------------------------------------------------------------- queries

    def is_enabled(self, rule_id: str) -> bool:
        state = self.rules.get(rule_id)
        return bool(state and state.enabled)

    def enabled_ids(self) -> list[str]:
        return [rule_id for rule_id, state in self.rules.items() if state.enabled]

    def param(self, catalog: Catalog, rule_id: str, name: str) -> Any:
        state = self.rules.get(rule_id)
        if state is not None and name in state.params:
            return state.params[name]
        return catalog.rules[rule_id].params[name].default

    def params_for(self, catalog: Catalog, rule_id: str) -> dict[str, Any]:
        return {name: self.param(catalog, rule_id, name) for name in catalog.rules[rule_id].params}

    def set_param(self, rule_id: str, name: str, value: Any) -> None:
        self.rules[rule_id].params[name] = value

    # ----------------------------------------------------------------- serialisation

    def to_dict(self, catalog: Catalog | None = None) -> dict[str, Any]:
        order = catalog.order if catalog is not None else list(self.rules)
        ordered_rules: dict[str, Any] = {}
        for rule_id in order:
            state = self.rules.get(rule_id)
            if state is None:
                continue
            entry: dict[str, Any] = {"enabled": state.enabled}
            if state.params:
                entry["params"] = dict(state.params)
            ordered_rules[rule_id] = entry
        for rule_id, state in self.rules.items():  # rules not in catalog order (should not happen)
            if rule_id not in ordered_rules:
                ordered_rules[rule_id] = {"enabled": state.enabled, **({"params": state.params} if state.params else {})}
        return {
            "format_version": self.format_version,
            "catalog_version": self.catalog_version,
            "name": self.name,
            "author": self.author,
            "created": self.created,
            "modified": self.modified,
            "comment": self.comment,
            "install": dict(self.install),
            "languages": copy.deepcopy(self.languages),
            "accounts": [a.to_dict() for a in self.accounts],
            "rules": ordered_rules,
            "unknown": copy.deepcopy(self.unknown),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], catalog: Catalog) -> tuple[Profile, list[str]]:
        warnings: list[str] = []
        fmt = int(data.get("format_version", 0))
        if fmt != FORMAT_VERSION:
            warnings.append(f"формат профиля {fmt}, ожидался {FORMAT_VERSION}: применены значения по умолчанию для недостающего")
        raw_rules = data.get("rules", {}) if isinstance(data.get("rules"), dict) else {}
        rules: dict[str, RuleState] = {}
        for rule in catalog.rules.values():
            entry = raw_rules.get(rule.id)
            if entry is None:
                rules[rule.id] = RuleState(enabled=rule.default)
                if raw_rules:
                    warnings.append(f"новое правило каталога {rule.id}: установлено значение по умолчанию")
                continue
            params: dict[str, Any] = {}
            for pname, pvalue in (entry.get("params") or {}).items():
                if pname in rule.params:
                    params[pname] = pvalue
                else:
                    warnings.append(f"{rule.id}: неизвестный параметр {pname} пропущен")
            rules[rule.id] = RuleState(enabled=bool(entry.get("enabled", rule.default)), params=params)
        unknown = {rid: entry for rid, entry in raw_rules.items() if rid not in catalog.rules}
        if unknown:
            warnings.append("правила, отсутствующие в каталоге, сохранены в 'unknown': " + ", ".join(sorted(unknown)))
        stored_unknown = data.get("unknown") if isinstance(data.get("unknown"), dict) else {}
        unknown = {**stored_unknown, **unknown}
        install = dict(DEFAULT_INSTALL)
        install.update({k: v for k, v in (data.get("install") or {}).items() if k in DEFAULT_INSTALL})
        languages = copy.deepcopy(DEFAULT_LANGUAGES)
        languages.update({k: v for k, v in (data.get("languages") or {}).items() if k in DEFAULT_LANGUAGES})
        accounts_raw = data.get("accounts")
        accounts = [Account.from_dict(a) for a in accounts_raw] if isinstance(accounts_raw, list) else [copy.copy(a) for a in DEFAULT_ACCOUNTS]
        catalog_version = str(data.get("catalog_version", catalog.version))
        if catalog_version != catalog.version:
            warnings.append(f"профиль сохранён каталогом {catalog_version}, текущий {catalog.version}")
        profile = cls(
            name=str(data.get("name", "Профиль")),
            catalog_version=catalog.version,
            rules=rules,
            format_version=FORMAT_VERSION,
            author=str(data.get("author", "")),
            created=str(data.get("created", _now())),
            modified=str(data.get("modified", _now())),
            comment=str(data.get("comment", "")),
            install=install,
            languages=languages,
            accounts=accounts,
            unknown=unknown,
        )
        return profile, warnings

    @classmethod
    def load(cls, path: Path, catalog: Catalog) -> tuple[Profile, list[str]]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: profile must be a JSON object")
        profile, warnings = cls.from_dict(data, catalog)
        profile.path = path
        return profile, warnings

    def save(self, path: Path, catalog: Catalog | None = None) -> None:
        self.modified = _now()
        payload = self.to_dict(catalog)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        path.write_text(text, encoding="utf-8", newline="\r\n")
        self.path = path

    # ----------------------------------------------------------------- comparison

    def diff(self, other: Profile) -> list[Difference]:
        out: list[Difference] = []
        for rule_id in sorted(set(self.rules) | set(other.rules)):
            a, b = self.rules.get(rule_id), other.rules.get(rule_id)
            a_on, b_on = (a.enabled if a else None), (b.enabled if b else None)
            if a_on != b_on:
                out.append(Difference("rule", rule_id, a_on, b_on))
            a_params, b_params = (a.params if a else {}), (b.params if b else {})
            for pname in sorted(set(a_params) | set(b_params)):
                if a_params.get(pname) != b_params.get(pname):
                    out.append(Difference("param", f"{rule_id}.{pname}", a_params.get(pname), b_params.get(pname)))
        for key in sorted(set(self.install) | set(other.install)):
            if self.install.get(key) != other.install.get(key):
                out.append(Difference("install", key, self.install.get(key), other.install.get(key)))
        for key in sorted(set(self.languages) | set(other.languages)):
            if self.languages.get(key) != other.languages.get(key):
                out.append(Difference("languages", key, self.languages.get(key), other.languages.get(key)))
        if [a.to_dict() for a in self.accounts] != [a.to_dict() for a in other.accounts]:
            out.append(Difference("accounts", "accounts", [a.name for a in self.accounts], [a.name for a in other.accounts]))
        return out
