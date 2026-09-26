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
from winkickoff.core.i18n import tr

FORMAT_VERSION = 2

DEFAULT_INSTALL: dict[str, Any] = {
    "edition": "Pro",
    "product_key_mode": "generic",  # generic | custom | ask
    "product_key": "",
    "time_zone": "FLE Standard Time",
}
DEFAULT_LANGUAGES: dict[str, Any] = {
    "ui_language": "uk-UA",  # must equal the language of the installation ISO
    "system_locale": "uk-UA",
    "user_locale": "uk-UA",
    "input": ["en-US", "uk-UA", "ru-UA"],  # tags or LCID:KLID pairs; the first is the default
}
# The country (GeoID) is a parameter of the rule default-user.region, not a profile field.


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


REGION_RULE = "default-user.region"


def _migrate_catalog_02(
    data: dict[str, Any], raw_languages: dict[str, Any], rules: dict[str, RuleState], catalog: Catalog, warnings: list[str]
) -> None:
    """Profiles of catalog 0.2 kept the country in languages.geo_id and had install.iso_language."""
    geo_id = raw_languages.get("geo_id")
    region = catalog.rules.get(REGION_RULE)
    if geo_id is not None and region is not None and "geo_id" in region.params and "geo_id" not in rules[REGION_RULE].params:
        value = str(geo_id) if region.params["geo_id"].type == "string" else geo_id
        if value != region.params["geo_id"].default:
            rules[REGION_RULE].params["geo_id"] = value
            warnings.append(
                tr("languages.geo_id = {0} перенесено в параметр правила {1}; проверьте код страны geo_name", geo_id, REGION_RULE)
            )
    if "iso_language" in (data.get("install") or {}):
        warnings.append(tr("поле install.iso_language больше не используется: язык интерфейса всегда равен языку ISO"))


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
            warnings.append(tr("формат профиля {0}, ожидался {1}: применены значения по умолчанию для недостающего", fmt, FORMAT_VERSION))
        raw_rules = data.get("rules", {}) if isinstance(data.get("rules"), dict) else {}
        rules: dict[str, RuleState] = {}
        new_rules: list[str] = []
        for rule in catalog.rules.values():
            entry = raw_rules.get(rule.id)
            if entry is None:
                rules[rule.id] = RuleState(enabled=rule.default)
                if raw_rules:
                    new_rules.append(rule.id)
                continue
            params: dict[str, Any] = {}
            for pname, pvalue in (entry.get("params") or {}).items():
                if pname in rule.params:
                    params[pname] = pvalue
                else:
                    warnings.append(tr("{0}: неизвестный параметр {1} пропущен", rule.id, pname))
            rules[rule.id] = RuleState(enabled=bool(entry.get("enabled", rule.default)), params=params)
        if new_rules:
            enabled = sum(1 for r in new_rules if rules[r].enabled)
            shown = ", ".join(new_rules[:12]) + (", ..." if len(new_rules) > 12 else "")
            warnings.append(tr("новых правил каталога: {0}, из них включено по умолчанию {1}: {2}", len(new_rules), enabled, shown))
        unknown = {rid: entry for rid, entry in raw_rules.items() if rid not in catalog.rules}
        if unknown:
            warnings.append(tr("правила, отсутствующие в каталоге, сохранены в 'unknown': ") + ", ".join(sorted(unknown)))
        stored_unknown = data.get("unknown") if isinstance(data.get("unknown"), dict) else {}
        unknown = {**stored_unknown, **unknown}
        install = dict(DEFAULT_INSTALL)
        install.update({k: v for k, v in (data.get("install") or {}).items() if k in DEFAULT_INSTALL})
        languages = copy.deepcopy(DEFAULT_LANGUAGES)
        raw_languages = data.get("languages") or {}
        languages.update({k: v for k, v in raw_languages.items() if k in DEFAULT_LANGUAGES})
        _migrate_catalog_02(data, raw_languages, rules, catalog, warnings)
        accounts_raw = data.get("accounts")
        accounts = [Account.from_dict(a) for a in accounts_raw] if isinstance(accounts_raw, list) else [copy.copy(a) for a in DEFAULT_ACCOUNTS]
        catalog_version = str(data.get("catalog_version", catalog.version))
        if catalog_version != catalog.version:
            warnings.append(tr("профиль сохранён каталогом {0}, текущий {1}", catalog_version, catalog.version))
        profile = cls(
            name=str(data.get("name", tr("Профиль"))),
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

    def diff(self, other: Profile, catalog: Catalog | None = None) -> list[Difference]:
        """Differences from other. With the catalog, parameters are compared by their effective values
        (an explicit default equals an omitted one) and rules follow the catalog order."""
        out: list[Difference] = []
        ids = [r for r in catalog.order if r in self.rules or r in other.rules] if catalog is not None else sorted(set(self.rules) | set(other.rules))
        for rule_id in ids:
            a, b = self.rules.get(rule_id), other.rules.get(rule_id)
            a_on, b_on = (a.enabled if a else None), (b.enabled if b else None)
            if a_on != b_on:
                out.append(Difference("rule", rule_id, a_on, b_on))
            if catalog is not None and rule_id in catalog.rules:
                a_params, b_params = self.params_for(catalog, rule_id), other.params_for(catalog, rule_id)
            else:
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
