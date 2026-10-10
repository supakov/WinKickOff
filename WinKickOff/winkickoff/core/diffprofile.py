"""Diff profiles (1.4.0-rc.2): only the differences of one profile from another, saved as a file and merged into an open
profile.

A diff file is {"format": "winkickoff-diff", "version": 1, "name", "base", "created", "catalog_version", "rules",
"install", "languages", "accounts"?}: "rules" maps a rule id to {"enabled"?, "params"?} with only what differs (the
state when it differs, the parameter values that differ, by their effective values), "install" and "languages" hold
only the differing fields, and "accounts" the whole account list when it differs. Merging switches rules on and off
with the dependency cascade of the tree (core/deps.py), sets the parameters that are valid values of their rules and
the known fields; everything it cannot take is a warning, never a failure.
"""

from __future__ import annotations

import json
import os
import contextlib
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.catalog import Catalog
from winkickoff.core.deps import Resolver
from winkickoff.core.i18n import tr
from winkickoff.core.profile import DEFAULT_INSTALL, DEFAULT_LANGUAGES, PROFILE_MAX_BYTES, Account, Profile, _now, one_line

FORMAT = "winkickoff-diff"
VERSION = 1


def make_diff(mine: Profile, base: Profile, catalog: Catalog) -> dict[str, Any]:
    """The differences of mine from base, in the shape of a diff file."""
    rules: dict[str, dict[str, Any]] = {}
    for d in mine.diff(base, catalog):
        if d.kind == "rule" and d.before is not None:
            rules.setdefault(d.key, {})["enabled"] = bool(d.before)
        elif d.kind == "param":
            rule_id, _, name = d.key.rpartition(".")
            if d.before is not None:
                rules.setdefault(rule_id, {}).setdefault("params", {})[name] = d.before
    out: dict[str, Any] = {"format": FORMAT, "version": VERSION, "name": one_line(mine.name), "base": one_line(base.name),
                           "created": _now(), "catalog_version": catalog.version, "rules": rules,
                           "install": {k: v for k, v in mine.install.items() if base.install.get(k) != v},
                           "languages": {k: v for k, v in mine.languages.items() if base.languages.get(k) != v}}
    if [a.to_dict() for a in mine.accounts] != [a.to_dict() for a in base.accounts]:
        out["accounts"] = [a.to_dict() for a in mine.accounts]
    return out


def is_empty(diff: dict[str, Any]) -> bool:
    return not (diff.get("rules") or diff.get("install") or diff.get("languages") or "accounts" in diff)


def save_diff(path: Path, diff: dict[str, Any]) -> None:
    """UTF-8 with CRLF through a temporary file (as Profile.save). Raises OSError."""
    data = jsonfile.without_surrogates(json.dumps(diff, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n")
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_bytes(data.encode("utf-8"))
        os.replace(temporary, path)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink(missing_ok=True)
        raise


def load_diff(path: Path) -> dict[str, Any]:
    """A diff file, read as strictly as a profile. Raises ValueError for anything else."""
    data = jsonfile.read(path, file_limit=PROFILE_MAX_BYTES, json_limit=PROFILE_MAX_BYTES)
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError(tr("{0} is not a diff profile of WinKickOff", path.name))
    for key, kind in (("rules", dict), ("install", dict), ("languages", dict)):
        if not isinstance(data.get(key, {}), kind):
            raise ValueError(tr("{0}: the field {1} has the wrong type", path.name, key))
    return data


def merge_diff(profile: Profile, diff: dict[str, Any], catalog: Catalog) -> tuple[int, list[str]]:
    """Apply a diff to the profile in place; returns how many items changed and the warnings (translated)."""
    from winkickoff.core.validate import check_param  # imported here: validate imports this package's profile module

    resolver = Resolver(catalog)
    changed, warnings = 0, []
    for rule_id, entry in diff.get("rules", {}).items():
        if rule_id not in catalog.rules:
            warnings.append(tr("{0}: no such rule in this catalog; skipped", rule_id))
            continue
        if not isinstance(entry, dict):
            warnings.append(tr("{0}: the entry is not an object; skipped", rule_id))
            continue
        enabled = entry.get("enabled")
        if isinstance(enabled, bool) and profile.is_enabled(rule_id) != enabled:
            (resolver.enable if enabled else resolver.disable)(profile, rule_id)
            changed += 1
        rule = catalog.rules[rule_id]
        for name, value in (entry.get("params") or {}).items() if isinstance(entry.get("params"), dict) else ():
            param = rule.params.get(name)
            if param is None or check_param(rule, param, value) is not None:
                warnings.append(tr("{0}: the value of parameter {1} does not fit; skipped", rule_id, name))
                continue
            if profile.param(catalog, rule_id, name) != value:
                profile.set_param(rule_id, name, value)
                changed += 1
    for section, defaults, target in (("install", DEFAULT_INSTALL, profile.install),
                                      ("languages", DEFAULT_LANGUAGES, profile.languages)):
        for key, value in diff.get(section, {}).items():
            fits = (key in defaults and (isinstance(value, str) if key != "input" else
                                         isinstance(value, list) and all(isinstance(v, str) for v in value)))
            if not fits:
                warnings.append(tr("{0}.{1}: not a field of this version; skipped", section, key))
            elif target.get(key) != value:
                target[key] = value
                changed += 1
    accounts = diff.get("accounts")
    if isinstance(accounts, list):
        parsed = [Account.from_dict(a) for a in accounts if isinstance(a, dict)]
        if len(parsed) != len(accounts):
            warnings.append(tr("accounts that are not objects were skipped"))
        if [a.to_dict() for a in parsed] != [a.to_dict() for a in profile.accounts]:
            profile.accounts = parsed
            changed += 1
    return changed, warnings
