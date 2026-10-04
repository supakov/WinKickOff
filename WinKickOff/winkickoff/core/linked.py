"""Built-in rules and imported policies that set the same registry values (T21).

An imported policy is linked to a built-in rule when everything the policy writes, with its current parameters or
with one value of its first choice parameter (the policy state, an option, a check box), is also written by the
built-in rule. While that rule is on, the policy counts as on: it is shown with a check mark, it is not written
separately, and its check mark follows the built-in rule. A policy that writes exactly what the rule writes
("equal") is the same setting: switching the policy on switches the reviewed built-in rule on. A policy that
writes only a part of the rule ("covered") is switched off together with the whole rule only after a question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from winkickoff.core.catalog import Catalog, Rule, is_imported
from winkickoff.core.profile import Profile
from winkickoff.core.render import substitute_fields

Write = tuple[str, str, str, str, Any]  # scope, key, value name, kind ("remove" for a removal), value


@dataclass(frozen=True)
class Link:
    rule: str  # the built-in rule
    equal: bool  # with params, the policy writes exactly what the built-in rule writes
    params: dict[str, Any]  # parameter values of the policy that match the built-in rule


def _value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, list):
        return tuple(value)
    return value


def registry_writes(rule: Rule, params: dict[str, Any]) -> frozenset[Write] | None:
    """What a rule writes into the registry with these parameters; None when it also does anything else."""
    found: set[Write] = set()
    for action in rule.actions:
        fields = substitute_fields(action.fields, params)
        if action.type not in ("reg", "reg-remove"):
            return None
        path = str(fields["path"])
        scope = "machine" if path.upper().startswith("HKLM:\\") else "user"
        key = path.split(":\\", 1)[-1].strip("\\").lower()
        if action.type == "reg":
            found.add((scope, key, str(fields["name"]).lower(), str(fields["kind"]), _value(fields["value"])))
        else:
            found.add((scope, key, str(fields["name"]).lower(), "remove", None))
    return frozenset(found)


def _variants(rule: Rule, current: dict[str, Any]) -> list[dict[str, Any]]:
    """The current parameters, then every value of the first enum or bool parameter."""
    variants = [current]
    for name, param in rule.params.items():
        if param.type == "enum":
            variants += [{**current, name: value} for value, _ in param.values if value != current.get(name)]
            break
        if param.type == "bool":
            variants.append({**current, name: not current.get(name)})
            break
    return variants


def link(catalog: Catalog, profile: Profile, rule_id: str) -> Link | None:
    """The built-in rule an imported policy is linked to (an equal one first), or None."""
    if not is_imported(rule_id) or rule_id not in catalog.rules:
        return None
    candidates = catalog.same_values(rule_id)
    if not candidates:
        return None
    rule = catalog.rules[rule_id]
    variants = [(params, registry_writes(rule, params)) for params in _variants(rule, profile.params_for(catalog, rule_id))]
    best: Link | None = None
    for other in candidates:
        theirs = registry_writes(catalog.rules[other], profile.params_for(catalog, other))
        if not theirs:
            continue
        for params, mine in variants:
            if not mine or not mine <= theirs:
                continue
            if mine == theirs:
                return Link(other, True, params)
            best = best or Link(other, False, params)
    return best


def covering(catalog: Catalog, profile: Profile, rule_id: str) -> Link | None:
    """The link when its built-in rule is on: the policy counts as on without being written itself."""
    found = link(catalog, profile, rule_id)
    return found if found is not None and profile.is_enabled(found.rule) else None


def redundant(catalog: Catalog, profile: Profile) -> list[tuple[str, str]]:
    """(imported policy, built-in rule): policies that are on although an enabled built-in rule already writes
    everything they write with their current parameters."""
    found: list[tuple[str, str]] = []
    for rule_id in profile.enabled_ids():
        if not is_imported(rule_id) or rule_id not in catalog.rules:
            continue
        mine = registry_writes(catalog.rules[rule_id], profile.params_for(catalog, rule_id))
        for other in catalog.same_values(rule_id):
            theirs = registry_writes(catalog.rules[other], profile.params_for(catalog, other))
            if profile.is_enabled(other) and mine and theirs and mine <= theirs:
                found.append((rule_id, other))
                break
    return found
