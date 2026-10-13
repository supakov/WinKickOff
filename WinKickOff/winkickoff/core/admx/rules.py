"""Policy records to catalog rules: rule ids, parameters, actions, the subtree of an import (catalog_part) and
the catalog with every shown import (with_imports)."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import IMPORTED_PREFIX, Action, Catalog, Group, Param, Rule, RuleOrigin, merge
from winkickoff.core.i18n import tr
from winkickoff.core.admx.base import (
    LEGACY_SKIPS,
    SKIP_REASONS,
    SIDE_TITLES,
    NO_CATEGORY,
    IMPORTED_RISK,
    STATE_TITLE,
    STATE_ENABLED,
    STATE_DISABLED,
    TITLE_ENABLED,
    TITLE_DISABLED,
    ON,
    OFF,
    VALUE,
    NO_EXPLAIN,
)
from winkickoff.core.admx.check import MAX_CATEGORY_DEPTH, conform
from winkickoff.core.admx.templates import pick
from winkickoff.core.admx.store import ImportInfo, trust_order, load_import

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- policy records to rules


def _id_part(text: str, keep_dots: bool) -> str:
    parts = text.lower().split(".") if keep_dots else [text.lower()]
    cleaned = [re.sub(r"[^a-z0-9]+", "-", part).strip("-") or "x" for part in parts]
    return ".".join(cleaned)


def _action(write: dict[str, Any], prefix: str, rule_id: str, value: Any = None) -> Action:
    path = prefix + str(write["key"])
    if write["kind"] == "delete":
        return Action("reg-remove", {"path": path, "name": write["name"]}, rule_id)
    if value is None and isinstance(write["value"], str):  # a fixed text of the template: "{id}" in it is text, never a
        return Action("reg", {"path": path, "name": write["name"], "kind": write["kind"], "value": write["value"],  # parameter
                              "literal": True}, rule_id)
    return Action("reg", {"path": path, "name": write["name"], "kind": write["kind"],
                          "value": write["value"] if value is None else value}, rule_id)


def _is_list(element: dict[str, Any]) -> bool:
    return element.get("element") == "list"


def _list_action(element: dict[str, Any], prefix: str, rule_id: str, value: Any) -> Action:
    """The values of a list element; an empty literal list (the Disabled state) leaves the key without values."""
    fields: dict[str, Any] = {"path": prefix + str(element["key"]), "kind": element["kind"], "value": value}
    if value == []:
        return Action("reg-list", fields, rule_id)
    if "prefix" in element:
        fields["prefix"] = element["prefix"]
    if element.get("explicit"):
        fields["explicit"] = True
    if element.get("additive"):
        fields["additive"] = True
    return Action("reg-list", fields, rule_id)


def _unique(actions: list[Action]) -> tuple[Action, ...]:
    """Later writes of the same value (or list) replace earlier ones (a policy value repeated by an element)."""
    seen: dict[tuple[str, str | None], Action] = {}
    for action in actions:
        name = action.fields.get("name")
        target = (str(action.fields["path"]).lower(), None if name is None else str(name).lower())
        seen.pop(target, None)
        seen[target] = action
    return tuple(seen.values())


def _param(element: dict[str, Any], language: str, only: bool) -> Param:
    # some templates leave the label empty; the only element of a policy is simply its value
    title = pick(element.get("label"), language) or (tr(VALUE) if only else element.get("id") or element["param"])
    if element["type"] == "list":
        return Param(element["param"], "list", title, list(element["default"]), required=bool(element.get("required")),
                     pairs=bool(element.get("explicit")))
    if element["type"] == "enum":
        # texts None: the two states of a check box with its own values
        values = tuple((value, tr(ON if i == 0 else OFF) if texts is None else pick(texts, language) or str(value))
                       for i, (value, texts) in enumerate(element["values"]))
        return Param(element["param"], "enum", title, element["default"], values=values)
    if element["type"] == "int":
        return Param(element["param"], "int", title, element["default"], min=element.get("min"), max=element.get("max"))
    return Param(element["param"], element["type"], title, element["default"], required=bool(element.get("required", True)))


def _texts(policy: dict[str, Any], language: str) -> tuple[str, str, str]:
    """Title, summary (the first paragraph of the explanation) and the rest of the explanation."""
    title = pick(policy.get("title"), language) or policy["name"]
    explain = pick(policy.get("explain"), language).replace("\r\n", "\n").strip()
    if not explain:
        return title, tr(NO_EXPLAIN), ""
    first, _, rest = explain.partition("\n\n")
    first = first.strip()
    if len(first) > 400:
        return title, first[:397].rstrip() + "...", explain
    return title, first, rest.strip()


def policy_rules(policy: dict[str, Any], rule_id: str, group: str, language: str, source: str) -> list[Rule]:
    """The rule of the Enabled state (or the one rule with a state parameter) and the Disabled rule, if any."""
    machine = policy.get("class") != "User"
    phase, prefix = ("specialize", "HKLM:\\") if machine else ("default-user", "DU:\\")
    title, summary, explain = _texts(policy, language)
    supported = pick(policy.get("supported"), language)
    names = sorted({str(w["name"]).lower() for w in policy["enabled"] + policy["elements"] if w.get("name")})
    tags = tuple(dict.fromkeys(["admx", policy["file"].rsplit(".", 1)[0].lower(), policy["name"].lower(), *names]))
    common = dict(group=group, phase=phase, level="optional", default=False, doc="", summary=summary, effect=explain,
                  tags=tags, risk=tr(IMPORTED_RISK), versions=supported, source=source)
    enabled, disabled, elements = policy["enabled"], policy["disabled"], policy["elements"]
    one_value = (not elements and len(enabled) == 1 and len(disabled) == 1
                 and enabled[0]["kind"] != "delete" and enabled[0]["kind"] == disabled[0]["kind"]
                 and (enabled[0]["key"].lower(), enabled[0]["name"].lower()) == (disabled[0]["key"].lower(), disabled[0]["name"].lower())
                 and enabled[0]["value"] != disabled[0]["value"])
    if one_value:
        state = Param("state", "enum", tr(STATE_TITLE), enabled[0]["value"],
                      values=((enabled[0]["value"], tr(STATE_ENABLED)), (disabled[0]["value"], tr(STATE_DISABLED))))
        action = _action(enabled[0], prefix, rule_id, "{state}")
        return [Rule(id=rule_id, title=title, params={"state": state}, actions=(action,), **common)]
    params = {e["param"]: _param(e, language, len(elements) == 1) for e in elements}
    lists = [e for e in elements if _is_list(e)]
    values = [e for e in elements if not _is_list(e)]
    # lists first: a list that is not additive deletes the other values of its key before they are written
    on_actions = [_list_action(e, prefix, rule_id, "{" + e["param"] + "}") for e in lists]
    on_actions += [_action(w, prefix, rule_id) for w in enabled]
    on_actions += [_action(e, prefix, rule_id, "{" + e["param"] + "}") for e in values]
    writes_off = [w for w in disabled if w["kind"] != "delete"]
    off_id = rule_id + ".off"
    if not writes_off:
        return [Rule(id=rule_id, title=title, params=params, actions=_unique(on_actions), **common)]
    off_actions = [_list_action(e, prefix, off_id, []) for e in lists]
    off_actions += [_action(w, prefix, off_id) for w in disabled]
    off_actions += [_action({**e, "kind": "delete"}, prefix, off_id) for e in values]
    return [
        Rule(id=rule_id, title=tr(TITLE_ENABLED, title), params=params, actions=_unique(on_actions), conflicts=(off_id,), **common),
        Rule(id=off_id, title=tr(TITLE_DISABLED, title), actions=_unique(off_actions), conflicts=(rule_id,), **common),
    ]


def _rule_ids(policies: list[dict[str, Any]]) -> list[str]:
    """The rule id of every policy (by position): the namespace and the name. Two policies with the same id are
    numbered (base, base-2, ...) in the order of their English titles, then of their position, so the ids never
    depend on the interface language; an id is never the "<id>.off" of another policy's Disabled state. Linear in the number of
    policies. Profiles keep these ids, so they fit any import of the same templates."""
    # 1.2 numbered by the title in the interface language; the English title keeps the ids of English users and never
    # changes with the language (no template of Windows has two policies with one id, so their ids are the same anyway)
    titles = [(pick(p.get("title"), "en") or str(p.get("name", ""))).lower() for p in policies]
    order = sorted(range(len(policies)), key=lambda i: (titles[i], i))
    reserved: set[str] = set()
    counters: dict[str, int] = {}
    ids = [""] * len(policies)
    for i in order:
        base = f"{IMPORTED_PREFIX}{_id_part(policies[i]['namespace'], True)}.{_id_part(policies[i]['name'], False)}"
        index = counters.get(base, 1)
        rule_id = base if index == 1 else f"{base}-{index}"
        while rule_id in reserved or rule_id + ".off" in reserved:
            index += 1
            rule_id = f"{base}-{index}"
        counters[base] = index
        reserved.update((rule_id, rule_id + ".off"))
        ids[i] = rule_id
    return ids


def _named_policies(data: dict[str, Any], language: str) -> Iterator[tuple[dict[str, Any], str]]:
    """The policies of an import with the ids of their rules (_rule_ids), in the order of their titles in the
    interface language (the order of the tree)."""
    policies = data.get("policies", [])
    ids = _rule_ids(policies)
    titles = [(pick(p.get("title"), language) or p.get("name", "")).lower() for p in policies]
    for i in sorted(range(len(policies)), key=lambda i: (titles[i], ids[i])):
        yield policies[i], ids[i]


def policy_ids(data: dict[str, Any], language: str = "en") -> set[str]:
    """The ids of the policies of an import, as their rules get them (without the "<id>.off" of a Disabled state)."""
    return set(_rule_ids(data.get("policies", [])))


def has_policy(ids: set[str], rule_id: str) -> bool:
    """A rule id of a profile belongs to one of these policies: the policy itself or its Disabled state."""
    return rule_id in ids or (rule_id.endswith(".off") and rule_id[:-len(".off")] in ids)


@dataclass
class ImportedPart:
    groups: dict[str, Group] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    origins: dict[str, RuleOrigin] = field(default_factory=dict)
    aliases: dict[str, list[str]] = field(default_factory=dict)  # rules of imports loaded before, shown here too
    shared: int = 0  # policies of this import that are already rules
    disabled: set[str] = field(default_factory=set)  # ids of the Disabled rules ("<id>.off") of its policies


def catalog_part(info: ImportInfo, data: dict[str, Any], language: str, taken: set[str], order: int = 10000,
                 disabled: set[str] | frozenset[str] = frozenset()) -> ImportedPart:
    """Groups and rules of one import in the interface language. A policy that is already a rule (taken: rules
    of the imports loaded before) is shown in this tree too, as an alias of that rule: one check mark for both.
    disabled: the ids among taken that are Disabled rules of a policy; a policy whose own id is one of them (a policy
    named "Off") is another policy and is left out, never shown as that Disabled state."""
    part = ImportedPart()
    root = f"{IMPORTED_PREFIX}{info.id}"
    categories: dict[str, dict[str, Any]] = data.get("categories", {})
    titles = {key: pick(value.get("title"), language) or key.split(":", 1)[-1] for key, value in categories.items()}
    rank = {key: index for index, key in enumerate(sorted(titles, key=lambda k: (titles[k].lower(), k)))}
    number = {key: index for index, key in enumerate(sorted(categories))}
    part.groups[root] = Group(root, info.name, order, None, "", f"admx:{info.id}")
    made: dict[tuple[str, str], str] = {}  # (side, category) -> group id, so a chain is walked once per category

    def group_for(side: str, category: str) -> str:
        if (side, category) in made:
            return made[(side, category)]
        side_id = f"{root}.{side}"
        if side_id not in part.groups:
            part.groups[side_id] = Group(side_id, tr(SIDE_TITLES[side]), 1 if side == "machine" else 2, root, "", f"admx:{info.id}")
        if category not in categories:
            other = f"{side_id}.none"
            part.groups.setdefault(other, Group(other, tr(NO_CATEGORY), 1_000_000, side_id, "", f"admx:{info.id}"))
            made[(side, category)] = other
            return other
        chain: list[str] = []
        seen: set[str] = set()
        current = category
        while current in categories and current not in seen and len(chain) < MAX_CATEGORY_DEPTH:
            chain.append(current)
            seen.add(current)
            current = categories[current]["parent"]
        parent = side_id
        for key in reversed(chain):
            group_id = f"{side_id}.c{number[key]}"
            part.groups.setdefault(group_id, Group(group_id, titles[key], rank[key], parent, "", f"admx:{info.id}"))
            parent = group_id
        made[(side, category)] = parent
        return parent

    for policy, rule_id in _named_policies(data, language):
        side = "user" if policy.get("class") == "User" else "machine"
        if rule_id in taken:
            if rule_id in disabled:  # the Disabled rule of a policy of another import, not this policy
                log.warning("import %s: policy %s skipped: its rule id is the Disabled rule of a policy of another import",
                            info.id, policy.get("name"))
                continue
            group = group_for(side, policy.get("category", ""))
            part.aliases.setdefault(rule_id, []).append(group)
            if rule_id + ".off" in disabled:  # not a policy named "Off" of another import
                part.aliases.setdefault(rule_id + ".off", []).append(group)
            part.shared += 1
            continue
        try:
            rules = policy_rules(policy, rule_id, group_for(side, policy.get("category", "")), language, f"admx:{info.id}")
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("import %s: policy %s skipped: %s", info.id, policy.get("name"), exc)
            continue
        if any(rule.id in taken for rule in rules):  # its Disabled rule would replace a rule of another import
            log.warning("import %s: policy %s skipped: its rule id is taken by another import", info.id, policy.get("name"))
            continue
        origin = RuleOrigin(info.id, info.name, info.folder, str(policy.get("file", "")), str(policy.get("name", "")))
        for rule in rules:
            part.rules[rule.id] = rule
            part.origins[rule.id] = origin
        part.disabled.update(rule.id for rule in rules[1:])
    # counted from the records: a policy that an older version kept and this one skips (conform) is among the skipped
    counts = tr("{0} policies as {1} rules; {2} skipped", len(data.get("policies", [])), len(part.rules) + len(part.aliases),
                len(data.get("skipped", [])))
    if part.shared:
        counts += tr("; {0} of the policies come from another imported tree of a more trusted source or shown higher, "
                     "with one check mark for both",
                     part.shared)
    older = sum(1 for item in data.get("skipped", []) if item.get("reason") in LEGACY_SKIPS)
    if older:
        counts += tr("; {0} policies with lists were skipped by an earlier version of WinKickOff, import the templates "
                     "again to get them", older)
    part.groups[root] = Group(root, info.name, order, None, tr("Imported from {0} on {1}: {2}. Languages: {3}.", info.folder,
                              info.created.replace("T", " "), counts, ", ".join(info.cultures) or "-"), f"admx:{info.id}")
    return part


def with_imports(base: Catalog, admx_root: Path, import_ids: Iterable[str], language: str) -> tuple[Catalog, list[str]]:
    """The catalog with the subtrees of the given saved imports; problems are messages for the user."""
    problems: list[str] = []
    groups: dict[str, Group] = {}
    rules: dict[str, Rule] = {}
    origins: dict[str, RuleOrigin] = {}
    aliases: dict[str, list[str]] = {}
    disabled: set[str] = set()
    shown = list(dict.fromkeys(import_ids))  # the order of the trees
    for import_id in trust_order(shown):  # the order in which they take the policies they share
        try:
            info, data = load_import(admx_root, import_id)
            part = catalog_part(info, data, language, set(base.rules) | set(rules), 10000 + shown.index(import_id), disabled)
        except Exception as exc:  # noqa: BLE001 - a broken import is reported, the program starts without it
            problems.append(tr("Imported templates {0} were not loaded: {1}", import_id, str(exc)[:500]))
            continue
        groups.update(part.groups)
        rules.update(part.rules)
        origins.update(part.origins)
        disabled.update(part.disabled)
        for rule_id, group_ids in part.aliases.items():
            aliases.setdefault(rule_id, []).extend(group_ids)
    if not rules and not groups:
        return base, problems
    return merge(base, groups, rules, origins, aliases), problems


def skip_summary(data: dict[str, Any]) -> list[tuple[str, int]]:
    """(reason text, count) of the skipped policies, most frequent first."""
    counts: dict[str, int] = {}
    for item in data.get("skipped", []):
        counts[item.get("reason", "broken")] = counts.get(item.get("reason", "broken"), 0) + 1
    return sorted(((tr(SKIP_REASONS.get(reason, SKIP_REASONS["broken"])), count) for reason, count in counts.items()),
                  key=lambda pair: -pair[1])
