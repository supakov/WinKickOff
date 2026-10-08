"""Profile: which rules are enabled, their parameter values, and the install data (accounts,
languages, product key, time zone). Stored as JSON next to the executable."""

from __future__ import annotations

import contextlib
import copy
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.catalog import IMPORT_KINDS, Catalog, Param, import_rank, is_imported
from winkickoff.core.i18n import tr

PROFILE_MAX_BYTES = 16 * 1024 * 1024
LEGACY_SOURCE = "folder"  # an imported choice saved before 1.3 (no "source"): catalog files did not exist then
FORMAT_VERSION = 4  # 3: install.account_mode (1.3.0-rc.1); 4: install.computer_name_mode and computer_name (rc.2)
READ_FORMATS = (2, 3, 4)  # read without a warning: a missing field means its default

ACCOUNT_MODES = ("file", "ask")  # the accounts of the profile, or Windows Setup asks for one administrator
DEFAULT_INSTALL: dict[str, Any] = {
    "edition": "Pro",
    "product_key_mode": "generic",  # generic | custom | ask (Setup shows the key page and the list of editions)
    "product_key": "",
    "time_zone": "FLE Standard Time",
    "account_mode": "file",
    "computer_name_mode": "random",  # random | fixed | template (core/computername.py)
    "computer_name": "",  # the name in mode fixed, the template in mode template
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
    source: str = ""  # an imported policy: the kind of import it was chosen in (catalog.IMPORT_KINDS), kept in the file


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
                tr("languages.geo_id = {0} was moved to a parameter of rule {1}; check the geo_name country code", geo_id, REGION_RULE)
            )
    if "iso_language" in (data.get("install") or {}):
        warnings.append(tr("the install.iso_language field is no longer used: the display language always matches the ISO language"))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def one_line(text: str) -> str:
    """A name or an author on one line: control characters and line separators become spaces."""
    return "".join(" " if ord(ch) < 32 or 0x7F <= ord(ch) <= 0x9F or ch in (chr(0x2028), chr(0x2029)) else ch for ch in text)


def held_warning(held: list[str]) -> str:
    """The warning about held choices (Profile.held): the window shows it in the message list at every start."""
    shown = ", ".join(held[:8]) + (", ..." if len(held) > 8 else "")
    return tr("{0} policies were chosen in templates of a more trusted source than the one that holds them now (for "
              "example a catalog file instead of the templates of this Windows); the choices are kept but not used until "
              "those templates are shown again: {1}", len(held), shown)


def _owner_kind(catalog: Catalog, rule_id: str) -> str:
    origin = catalog.origins.get(rule_id)
    return origin.kind if origin is not None else ""


def _as_option(param: Param, value: Any) -> Any:
    """A boolean saved for an enum of 0 and 1 (MCP of 1.2 accepted true and false there) as the option it equals."""
    if param.type == "enum" and isinstance(value, bool):
        for option, _title in param.values:
            if not isinstance(option, bool) and isinstance(option, int) and option == value:
                return option
    return value


def _fits(param: Param, value: Any) -> bool:
    """A saved parameter value has the JSON type the parameter takes (the check of the profile tells the rest)."""
    if param.type == "list":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if param.type == "bool":
        return isinstance(value, bool)
    if param.type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if param.type == "string":
        return isinstance(value, str)
    return isinstance(value, (str, int)) and not isinstance(value, bool)  # enum


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
    def from_catalog(cls, catalog: Catalog, name: str = "Office") -> Profile:
        rules = {rule.id: RuleState(enabled=rule.default, source=_owner_kind(catalog, rule.id)) for rule in catalog.rules.values()}
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

    def asks_for_account(self) -> bool:
        """Windows Setup asks for the account: the answer file holds no account (the list is kept for later)."""
        return self.install.get("account_mode") == "ask"

    def answer_file_accounts(self) -> list[Account]:
        """The accounts written into the answer file and given to the scripts: none when Setup asks for one."""
        return [] if self.asks_for_account() else list(self.accounts)

    def unknown_entries(self) -> list[tuple[str, bool, dict[str, Any]]]:
        """Choices kept in "unknown" (rules the loaded catalog does not have, such as policies of imported templates
        that are not loaded) as (id, enabled, params), sorted by id. The file may hold anything there: an entry that
        is not an object counts as off without parameters."""
        entries = []
        for rule_id, entry in sorted(self.unknown.items()):
            entry = entry if isinstance(entry, dict) else {}
            params = entry.get("params")
            entries.append((str(rule_id), bool(entry.get("enabled", False)), dict(params) if isinstance(params, dict) else {}))
        return entries

    # ----------------------------------------------------------------- serialisation

    def to_dict(self, catalog: Catalog | None = None) -> dict[str, Any]:
        """Imported policies are written only when they are on or have parameters: an imported policy without a
        check mark is "not configured", and thousands of them would only bloat the file."""
        order = catalog.order if catalog is not None else list(self.rules)
        ordered_rules: dict[str, Any] = {}
        for rule_id in [*order, *self.rules]:  # then rules not in the catalog order (another catalog)
            state = self.rules.get(rule_id)
            if state is None or rule_id in ordered_rules or (is_imported(rule_id) and not state.enabled and not state.params):
                continue
            entry: dict[str, Any] = {"enabled": state.enabled}
            if state.params:
                entry["params"] = dict(state.params)
            source = state.source
            if catalog is not None and is_imported(rule_id):  # the more trusted of the kind kept and the owner now
                source = min((kind for kind in (source, _owner_kind(catalog, rule_id)) if kind), key=import_rank, default="")
            if is_imported(rule_id) and source:
                entry["source"] = source
            ordered_rules[rule_id] = entry
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
        """A profile from its JSON object. A field of the wrong type falls back to its default with a warning; a file
        that cannot be read at all raises ValueError, never another error (a profile may come from someone else)."""
        if not isinstance(data, dict):
            raise ValueError(tr("the profile must be a JSON object"))
        try:
            jsonfile.check_depth(data)  # also for a profile given as an object (embedded in an answer file, MCP)
            return cls._from_dict(data, catalog)
        except (TypeError, AttributeError, KeyError, RecursionError) as exc:
            raise ValueError(tr("the profile has a field of an unexpected type: {0}", str(exc)[:200])) from exc

    @classmethod
    def _from_dict(cls, data: dict[str, Any], catalog: Catalog) -> tuple[Profile, list[str]]:
        warnings: list[str] = []
        raw_fmt = data.get("format_version", 0)
        fmt = raw_fmt if isinstance(raw_fmt, int) and not isinstance(raw_fmt, bool) else 0
        if fmt not in READ_FORMATS:
            warnings.append(tr("profile format {0}, expected {1}: default values were applied to missing items", fmt, FORMAT_VERSION))
        raw_rules = data.get("rules", {}) if isinstance(data.get("rules"), dict) else {}
        stored_unknown = data.get("unknown") if isinstance(data.get("unknown"), dict) else {}
        # rules kept in "unknown" come back when their catalog part is there again (templates loaded again)
        returning = {rid: entry for rid, entry in stored_unknown.items() if rid in catalog.rules and isinstance(entry, dict)}
        raw_rules = {**returning, **raw_rules}
        stored_unknown = {rid: entry for rid, entry in stored_unknown.items() if rid not in returning}
        rules: dict[str, RuleState] = {}
        new_rules: list[str] = []
        held: dict[str, Any] = {}  # imported choices made in a more trusted source than the one that holds the policy now
        for rule in catalog.rules.values():
            entry = raw_rules.get(rule.id)
            owner = _owner_kind(catalog, rule.id)
            if entry is not None and not isinstance(entry, dict):
                warnings.append(tr("{0}: the saved state is not an object; the default is used", rule.id))
                entry = None
            if entry is None:
                rules[rule.id] = RuleState(enabled=rule.default, source=owner)
                if raw_rules and not is_imported(rule.id):  # an imported policy not in the file is "not configured"
                    new_rules.append(rule.id)
                continue
            source = entry.get("source") if entry.get("source") in IMPORT_KINDS else (LEGACY_SOURCE if is_imported(rule.id) else "")
            if is_imported(rule.id) and owner and import_rank(owner) > import_rank(source):
                held[rule.id] = entry  # kept as it is in "unknown" until the templates of that source are shown again
                rules[rule.id] = RuleState(enabled=False, source=owner)
                continue
            params: dict[str, Any] = {}
            raw_params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
            for pname, pvalue in raw_params.items():
                if pname not in rule.params:
                    warnings.append(tr("{0}: unknown parameter {1} skipped", rule.id, pname))
                    continue
                pvalue = _as_option(rule.params[pname], pvalue)
                if not _fits(rule.params[pname], pvalue):
                    warnings.append(tr("{0}: the value of parameter {1} has the wrong type; the default is used", rule.id, pname))
                else:
                    params[pname] = pvalue
            enabled = entry.get("enabled", rule.default)
            if enabled in (0, 1) and not isinstance(enabled, bool) and isinstance(enabled, int):
                enabled = bool(enabled)  # 1.2 took bool() of the value
            if not isinstance(enabled, bool):
                warnings.append(tr("{0}: the saved state is not true or false; the default is used", rule.id))
                enabled = rule.default
            # the most trusted kind the choice was in effect in: chosen in a catalog file, used later from the templates
            # of this Windows, it must not go back to a catalog file without a word
            kept = min((kind for kind in (source, owner) if kind), key=import_rank, default="")
            rules[rule.id] = RuleState(enabled=enabled, params=params, source=kept)
        if held:
            warnings.append(held_warning(sorted(held)))
        if new_rules:
            enabled = sum(1 for r in new_rules if rules[r].enabled)
            shown = ", ".join(new_rules[:12]) + (", ..." if len(new_rules) > 12 else "")
            warnings.append(tr("new catalog rules: {0}, of them on by default {1}: {2}", len(new_rules), enabled, shown))
        unknown = {rid: entry for rid, entry in raw_rules.items() if rid not in catalog.rules}
        own = sorted(rid for rid in unknown if not is_imported(rid))
        if own:
            warnings.append(tr("rules missing from the catalog were saved to 'unknown': ") + ", ".join(own))
        policies = sorted(rid for rid in unknown if is_imported(rid))
        if policies:
            shown = ", ".join(policies[:8]) + (", ..." if len(policies) > 8 else "")
            warnings.append(tr("{0} policies of imported templates that are not loaded were kept: {1}. Load the templates "
                               "in the ADMX menu to use them.", len(policies), shown))
        unknown = {**stored_unknown, **unknown, **held}
        install = dict(DEFAULT_INSTALL)
        raw_install = data.get("install") if isinstance(data.get("install"), dict) else {}
        for key, value in raw_install.items():
            if key in DEFAULT_INSTALL and isinstance(value, str):
                install[key] = value
            elif key in DEFAULT_INSTALL:
                warnings.append(tr("install.{0} has the wrong type; the default is used", key))
        languages = copy.deepcopy(DEFAULT_LANGUAGES)
        raw_languages = data.get("languages") if isinstance(data.get("languages"), dict) else {}
        for key, value in raw_languages.items():
            if key == "input" and isinstance(value, list) and all(isinstance(item, str) for item in value) \
                    or key in DEFAULT_LANGUAGES and key != "input" and isinstance(value, str):
                languages[key] = value
            elif key in DEFAULT_LANGUAGES:
                warnings.append(tr("languages.{0} has the wrong type; the default is used", key))
        _migrate_catalog_02(dict(data, install=raw_install), raw_languages, rules, catalog, warnings)
        accounts_raw = data.get("accounts")
        if isinstance(accounts_raw, list):
            accounts = [Account.from_dict(a) for a in accounts_raw if isinstance(a, dict)]
            if len(accounts) != len(accounts_raw):
                warnings.append(tr("accounts that are not objects were skipped"))
        else:
            accounts = [copy.copy(a) for a in DEFAULT_ACCOUNTS]
        catalog_version = str(data.get("catalog_version", catalog.version))
        if catalog_version != catalog.version:
            warnings.append(tr("the profile was saved with catalog {0}, the current catalog is {1}", catalog_version, catalog.version))
        profile = cls(
            name=one_line(str(data.get("name", tr("Profile")))),
            catalog_version=catalog.version,
            rules=rules,
            format_version=FORMAT_VERSION,
            author=one_line(str(data.get("author", ""))),
            created=str(data.get("created", _now())),
            modified=str(data.get("modified", _now())),
            comment=str(data.get("comment", "")),
            install=install,
            languages=languages,
            accounts=accounts,
            unknown=unknown,
        )
        return profile, warnings

    def held(self, catalog: Catalog) -> list[str]:
        """The ids of the choices kept in "unknown" although the catalog has their rule: imported policies chosen in a
        more trusted kind of import than the one that holds them now (see from_dict)."""
        return sorted(rule_id for rule_id in self.unknown if rule_id in catalog.rules)

    def rebind(self, catalog: Catalog) -> tuple[Profile, list[str]]:
        """The same profile for another catalog (templates loaded or unloaded): states of rules that are not in it
        are kept in "unknown" and come back when the rules do."""
        profile, warnings = Profile.from_dict(self.to_dict(), catalog)
        profile.path = self.path
        return profile, warnings

    @classmethod
    def load(cls, path: Path, catalog: Catalog) -> tuple[Profile, list[str]]:
        # strict JSON with a depth and size limit: a profile may come from someone else (nulls of old files are allowed)
        data = jsonfile.read(path, file_limit=PROFILE_MAX_BYTES, json_limit=PROFILE_MAX_BYTES, nulls=True)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: profile must be a JSON object")
        profile, warnings = cls.from_dict(data, catalog)
        profile.path = path
        return profile, warnings

    def save(self, path: Path, catalog: Catalog | None = None) -> None:
        """UTF-8 with CRLF. The text is encoded before any file is opened and goes to a temporary file that then replaces
        the old one, so a failed save never leaves an empty or half-written profile. A lone surrogate (half of an emoji
        that a Tk entry leaves) is saved as U+FFFD: the strict reader refuses it, and the check of the profile names it."""
        self.modified = _now()
        payload = self.to_dict(catalog)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        data = jsonfile.without_surrogates(text).replace("\n", "\r\n").encode("utf-8")
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        except OSError:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise
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
