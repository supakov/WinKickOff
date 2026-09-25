"""The rules catalog: groups and rules loaded from rules/*.toml and checked for integrity.

The catalog is the single source of truth. Nothing here knows about tkinter or PowerShell text;
rendering lives in render.py, dependency arithmetic in deps.py.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PHASES: tuple[str, ...] = (
    "windowspe",
    "specialize-xml",
    "specialize",
    "default-user",
    "user-first-logon",
    "post-oobe",
    "oobe-xml",
)
PHASE_ORDER: dict[str, int] = {phase: index for index, phase in enumerate(PHASES)}
LEVELS: tuple[str, ...] = ("baseline", "recommended", "optional", "risky")
REG_KINDS: tuple[str, ...] = ("DWord", "QWord", "String", "ExpandString", "MultiString", "Binary")
REG_PREFIXES: tuple[str, ...] = ("HKLM:\\", "HKCU:\\", "DU:\\")
PARAM_TYPES: tuple[str, ...] = ("int", "enum", "string", "bool")

# action type -> (required fields, optional fields)
ACTION_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "reg": (("path", "name", "kind", "value"), ("why",)),
    "reg-remove": (("path", "name"), ()),
    "service": (("name", "start"), ()),
    "exe": (("file", "args"), ()),
    "feature": (("name", "state"), ()),
    "capability": (("pattern",), ()),
    "appx": (("names",), ()),
    "ps": (("script",), ()),
    "xml-pe-command": (("command", "description"), ()),
    "xml-specialize-command": (("command", "description"), ()),
    "xml-oobe": (("element", "value"), ()),
}
XML_ACTION_PHASE: dict[str, str] = {
    "xml-pe-command": "windowspe",
    "xml-specialize-command": "specialize-xml",
    "xml-oobe": "oobe-xml",
}
SCRIPT_PHASES: tuple[str, ...] = ("specialize", "default-user", "user-first-logon", "post-oobe")

_ID_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class CatalogError(ValueError):
    """A problem in the catalog files. Carries the file and rule so the UI can point at it."""

    def __init__(self, message: str, *, file: str | None = None, rule_id: str | None = None) -> None:
        self.file = file
        self.rule_id = rule_id
        where = " ".join(part for part in (f"[{file}]" if file else "", f"<{rule_id}>" if rule_id else "") if part)
        super().__init__(f"{where} {message}".strip())


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    title: str
    default: Any
    min: int | None = None
    max: int | None = None
    values: tuple[tuple[Any, str], ...] = ()


@dataclass(frozen=True)
class Action:
    type: str
    fields: dict[str, Any]
    rule_id: str

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    def search_text(self) -> str:
        parts: list[str] = [self.type]
        for key in ("path", "name", "file", "pattern", "element", "command", "description"):
            value = self.fields.get(key)
            if value:
                parts.append(str(value))
        for key in ("args", "names"):
            value = self.fields.get(key)
            if value:
                parts.extend(str(v) for v in value)
        value = self.fields.get("value")
        if value is not None:
            parts.append(str(value))
        return " ".join(parts)

    def placeholders(self) -> set[str]:
        found: set[str] = set()
        for value in self.fields.values():
            if isinstance(value, str):
                found.update(_PLACEHOLDER_RE.findall(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        found.update(_PLACEHOLDER_RE.findall(item))
        return found


@dataclass(frozen=True)
class Rule:
    id: str
    group: str
    phase: str
    title: str
    level: str
    default: bool
    doc: str
    summary: str
    effect: str
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    risk: str = ""
    versions: str = ""
    verify: str = ""
    rollback: str = ""
    params: dict[str, Param] = field(default_factory=dict)
    actions: tuple[Action, ...] = ()
    source: str = ""
    position: int = 0

    def search_text(self) -> str:
        parts = [self.id, self.title, self.summary, self.group, self.phase, " ".join(self.tags)]
        parts.extend(action.search_text() for action in self.actions)
        parts.extend(param.title for param in self.params.values())
        return " ".join(parts).lower()


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    order: int = 0
    parent: str | None = None
    summary: str = ""
    source: str = ""


class Catalog:
    def __init__(self, groups: dict[str, Group], rules: dict[str, Rule], version: str) -> None:
        self.groups = groups
        self.rules = rules  # insertion order = catalog order
        self.version = version
        self._required_by: dict[str, list[str]] = {rule_id: [] for rule_id in rules}
        for rule in rules.values():
            for req in rule.requires:
                # unknown targets are reported by _check(); do not fail here
                self._required_by.setdefault(req, []).append(rule.id)
        self._search: dict[str, str] = {rule.id: rule.search_text() for rule in rules.values()}

    @property
    def order(self) -> list[str]:
        return list(self.rules)

    def children(self, parent: str | None) -> list[Group]:
        found = [g for g in self.groups.values() if g.parent == parent]
        return sorted(found, key=lambda g: (g.order, g.id))

    def descendant_groups(self, group_id: str) -> list[str]:
        result: list[str] = []
        stack = [group_id]
        while stack:
            current = stack.pop()
            for child in self.children(current):
                result.append(child.id)
                stack.append(child.id)
        return result

    def rules_in_group(self, group_id: str, *, recursive: bool = True) -> list[Rule]:
        wanted = {group_id}
        if recursive:
            wanted.update(self.descendant_groups(group_id))
        return [rule for rule in self.rules.values() if rule.group in wanted]

    def required_by(self, rule_id: str) -> list[str]:
        return list(self._required_by.get(rule_id, ()))

    def search(self, query: str) -> list[str]:
        """Rule ids whose search text contains every word of the query (case-insensitive)."""
        words = [w for w in query.lower().split() if w]
        if not words:
            return self.order
        return [rule_id for rule_id, text in self._search.items() if all(w in text for w in words)]


# --------------------------------------------------------------------------- loading


def load_catalog(rules_dir: Path, *, docs_root: Path | None = None) -> Catalog:
    """Load groups.toml and every NN-*.toml in rules_dir; raise CatalogError on any defect."""
    if not rules_dir.is_dir():
        raise CatalogError(f"rules folder not found: {rules_dir}")
    groups = _load_groups(rules_dir / "groups.toml")
    version = _read_version(rules_dir)
    rules: dict[str, Rule] = {}
    position = 0
    for path in sorted(rules_dir.glob("*.toml")):
        if path.name == "groups.toml":
            continue
        data = _read_toml(path)
        for raw in data.get("rule", []):
            rule = _parse_rule(raw, path.name, position)
            if rule.id in rules:
                raise CatalogError(f"duplicate rule id (also in {rules[rule.id].source})", file=path.name, rule_id=rule.id)
            rules[rule.id] = rule
            position += 1
    catalog = Catalog(groups, rules, version)
    _check(catalog, docs_root)
    return catalog


def _read_version(rules_dir: Path) -> str:
    candidate = rules_dir.parent / "templates" / "VERSION"
    if candidate.exists():
        return candidate.read_text(encoding="utf-8").strip()
    return "0.0"


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise CatalogError(f"TOML syntax: {exc}", file=path.name) from exc


def _load_groups(path: Path) -> dict[str, Group]:
    if not path.exists():
        raise CatalogError("groups.toml is missing", file=path.name)
    data = _read_toml(path)
    groups: dict[str, Group] = {}
    for raw in data.get("group", []):
        group_id = _require_str(raw, "id", path.name)
        if not _ID_RE.match(group_id):
            raise CatalogError(f"bad group id '{group_id}'", file=path.name)
        if group_id in groups:
            raise CatalogError(f"duplicate group id '{group_id}'", file=path.name)
        groups[group_id] = Group(
            id=group_id,
            title=_require_str(raw, "title", path.name),
            order=int(raw.get("order", 0)),
            parent=raw.get("parent"),
            summary=str(raw.get("summary", "")),
            source=path.name,
        )
    for group in groups.values():
        if group.parent is not None and group.parent not in groups:
            raise CatalogError(f"group '{group.id}' has unknown parent '{group.parent}'", file=path.name)
    for group in groups.values():
        seen: set[str] = set()
        current: str | None = group.id
        while current is not None:
            if current in seen:
                raise CatalogError(f"group cycle at '{group.id}'", file=path.name)
            seen.add(current)
            current = groups[current].parent
    return groups


def _require_str(raw: dict[str, Any], key: str, file: str, rule_id: str | None = None) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"missing or empty '{key}'", file=file, rule_id=rule_id)
    return value.strip()


def _str_tuple(raw: dict[str, Any], key: str, file: str, rule_id: str) -> tuple[str, ...]:
    value = raw.get(key, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CatalogError(f"'{key}' must be a list of strings", file=file, rule_id=rule_id)
    return tuple(value)


def _parse_param(name: str, raw: dict[str, Any], file: str, rule_id: str) -> Param:
    ptype = raw.get("type")
    if ptype not in PARAM_TYPES:
        raise CatalogError(f"param '{name}': unknown type '{ptype}'", file=file, rule_id=rule_id)
    if "default" not in raw:
        raise CatalogError(f"param '{name}': missing default", file=file, rule_id=rule_id)
    title = _require_str(raw, "title", file, rule_id)
    default = raw["default"]
    values: tuple[tuple[Any, str], ...] = ()
    if ptype == "enum":
        raw_values = raw.get("values")
        if not isinstance(raw_values, list) or not raw_values:
            raise CatalogError(f"param '{name}': enum needs 'values'", file=file, rule_id=rule_id)
        values = tuple((v["value"], str(v.get("title", v["value"]))) for v in raw_values)
        if default not in {v for v, _ in values}:
            raise CatalogError(f"param '{name}': default not in values", file=file, rule_id=rule_id)
    if ptype == "int":
        if not isinstance(default, int) or isinstance(default, bool):
            raise CatalogError(f"param '{name}': int default must be an integer", file=file, rule_id=rule_id)
        lo, hi = raw.get("min"), raw.get("max")
        if lo is not None and default < lo or hi is not None and default > hi:
            raise CatalogError(f"param '{name}': default outside min..max", file=file, rule_id=rule_id)
    if ptype == "bool" and not isinstance(default, bool):
        raise CatalogError(f"param '{name}': bool default must be true or false", file=file, rule_id=rule_id)
    return Param(name=name, type=ptype, title=title, default=default, min=raw.get("min"), max=raw.get("max"), values=values)


def _parse_action(raw: dict[str, Any], file: str, rule_id: str, index: int) -> Action:
    atype = raw.get("type")
    if atype not in ACTION_FIELDS:
        raise CatalogError(f"action {index}: unknown type '{atype}'", file=file, rule_id=rule_id)
    required, optional = ACTION_FIELDS[atype]
    for key in required:
        if key not in raw:
            raise CatalogError(f"action {index} ({atype}): missing '{key}'", file=file, rule_id=rule_id)
    unknown = set(raw) - set(required) - set(optional) - {"type"}
    if unknown:
        raise CatalogError(f"action {index} ({atype}): unknown fields {sorted(unknown)}", file=file, rule_id=rule_id)
    fields = {k: v for k, v in raw.items() if k != "type"}
    if atype == "reg":
        if fields["kind"] not in REG_KINDS:
            raise CatalogError(f"action {index}: bad registry kind '{fields['kind']}'", file=file, rule_id=rule_id)
        if not str(fields["path"]).startswith(REG_PREFIXES):
            raise CatalogError(f"action {index}: registry path must start with one of {REG_PREFIXES}", file=file, rule_id=rule_id)
    if atype == "reg-remove" and not str(fields["path"]).startswith(REG_PREFIXES):
        raise CatalogError(f"action {index}: registry path must start with one of {REG_PREFIXES}", file=file, rule_id=rule_id)
    if atype == "service" and fields["start"] not in (2, 3, 4):
        raise CatalogError(f"action {index}: service start must be 2, 3 or 4", file=file, rule_id=rule_id)
    if atype == "exe" and (not isinstance(fields["args"], list) or not all(isinstance(a, str) for a in fields["args"])):
        raise CatalogError(f"action {index}: exe args must be a list of strings", file=file, rule_id=rule_id)
    if atype == "feature" and fields["state"] not in ("Enabled", "Disabled"):
        raise CatalogError(f"action {index}: feature state must be Enabled or Disabled", file=file, rule_id=rule_id)
    if atype == "appx" and (not isinstance(fields["names"], list) or not fields["names"]):
        raise CatalogError(f"action {index}: appx names must be a non-empty list", file=file, rule_id=rule_id)
    if atype == "ps" and not str(fields["script"]).strip():
        raise CatalogError(f"action {index}: empty ps script", file=file, rule_id=rule_id)
    return Action(type=atype, fields=fields, rule_id=rule_id)


def _parse_rule(raw: dict[str, Any], file: str, position: int) -> Rule:
    rule_id = _require_str(raw, "id", file)
    if not _ID_RE.match(rule_id):
        raise CatalogError("rule id must be lowercase words joined by '.' or '-'", file=file, rule_id=rule_id)
    phase = _require_str(raw, "phase", file, rule_id)
    if phase not in PHASES:
        raise CatalogError(f"unknown phase '{phase}'", file=file, rule_id=rule_id)
    level = _require_str(raw, "level", file, rule_id)
    if level not in LEVELS:
        raise CatalogError(f"unknown level '{level}'", file=file, rule_id=rule_id)
    if not isinstance(raw.get("default"), bool):
        raise CatalogError("'default' must be true or false", file=file, rule_id=rule_id)
    params_raw = raw.get("params", {})
    if not isinstance(params_raw, dict):
        raise CatalogError("'params' must be a table", file=file, rule_id=rule_id)
    params = {name: _parse_param(name, p, file, rule_id) for name, p in params_raw.items()}
    actions_raw = raw.get("actions", [])
    if not isinstance(actions_raw, list) or not actions_raw:
        raise CatalogError("rule has no actions", file=file, rule_id=rule_id)
    actions = tuple(_parse_action(a, file, rule_id, i) for i, a in enumerate(actions_raw))
    rule = Rule(
        id=rule_id,
        group=_require_str(raw, "group", file, rule_id),
        phase=phase,
        title=_require_str(raw, "title", file, rule_id),
        level=level,
        default=bool(raw["default"]),
        doc=_require_str(raw, "doc", file, rule_id),
        summary=_require_str(raw, "summary", file, rule_id),
        effect=_require_str(raw, "effect", file, rule_id),
        requires=_str_tuple(raw, "requires", file, rule_id),
        conflicts=_str_tuple(raw, "conflicts", file, rule_id),
        tags=_str_tuple(raw, "tags", file, rule_id),
        risk=str(raw.get("risk", "")).strip(),
        versions=str(raw.get("versions", "")).strip(),
        verify=str(raw.get("verify", "")).strip(),
        rollback=str(raw.get("rollback", "")).strip(),
        params=params,
        actions=actions,
        source=file,
        position=position,
    )
    return rule


# --------------------------------------------------------------------------- integrity


def _check(catalog: Catalog, docs_root: Path | None) -> None:
    for rule in catalog.rules.values():
        if rule.group not in catalog.groups:
            raise CatalogError(f"unknown group '{rule.group}'", file=rule.source, rule_id=rule.id)
        for ref in rule.requires + rule.conflicts:
            if ref == rule.id:
                raise CatalogError("rule references itself", file=rule.source, rule_id=rule.id)
            if ref not in catalog.rules:
                raise CatalogError(f"reference to unknown rule '{ref}'", file=rule.source, rule_id=rule.id)
        if set(rule.requires) & set(rule.conflicts):
            raise CatalogError("a rule cannot both require and conflict with the same rule", file=rule.source, rule_id=rule.id)
        for action in rule.actions:
            _check_action_phase(rule, action)
            missing = action.placeholders() - set(rule.params)
            if missing:
                raise CatalogError(f"action uses undeclared params {sorted(missing)}", file=rule.source, rule_id=rule.id)
        if docs_root is not None:
            doc_path = docs_root / rule.doc.split("#", 1)[0]
            if not doc_path.exists():
                raise CatalogError(f"doc file not found: {rule.doc}", file=rule.source, rule_id=rule.id)
    _check_cycles(catalog)


def _check_action_phase(rule: Rule, action: Action) -> None:
    expected = XML_ACTION_PHASE.get(action.type)
    if expected is not None and rule.phase != expected:
        raise CatalogError(f"action type '{action.type}' belongs to phase '{expected}'", file=rule.source, rule_id=rule.id)
    if expected is None and rule.phase not in SCRIPT_PHASES:
        raise CatalogError(f"action type '{action.type}' is not allowed in phase '{rule.phase}'", file=rule.source, rule_id=rule.id)
    if action.type in ("reg", "reg-remove"):
        path = str(action.fields["path"])
        if path.startswith("DU:\\") and rule.phase != "default-user":
            raise CatalogError("DU: paths are only valid in phase 'default-user'", file=rule.source, rule_id=rule.id)
        if path.startswith("HKCU:\\") and rule.phase != "user-first-logon":
            raise CatalogError("HKCU: paths are only valid in phase 'user-first-logon'", file=rule.source, rule_id=rule.id)
        if rule.phase == "default-user" and not path.startswith("DU:\\"):
            raise CatalogError("phase 'default-user' only writes DU: paths", file=rule.source, rule_id=rule.id)


def _check_cycles(catalog: Catalog) -> None:
    state: dict[str, int] = {}  # 0 unvisited, 1 visiting, 2 done

    def visit(rule_id: str, trail: list[str]) -> None:
        mark = state.get(rule_id, 0)
        if mark == 2:
            return
        if mark == 1:
            cycle = " -> ".join(trail[trail.index(rule_id):] + [rule_id])
            rule = catalog.rules[rule_id]
            raise CatalogError(f"dependency cycle: {cycle}", file=rule.source, rule_id=rule_id)
        state[rule_id] = 1
        for req in catalog.rules[rule_id].requires:
            visit(req, trail + [rule_id])
        state[rule_id] = 2

    for rule_id in catalog.rules:
        visit(rule_id, [])


def iter_actions(catalog: Catalog, rule_ids: Iterable[str]) -> list[Action]:
    return [action for rule_id in rule_ids for action in catalog.rules[rule_id].actions]


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def heading_anchors(markdown: str) -> set[str]:
    """Anchors of the headings of a Markdown text, built the way GitHub builds them: lower case,
    only letters, digits, spaces, hyphens and underscores kept, spaces turned into hyphens,
    repeated headings numbered -1, -2. Fenced code blocks are skipped."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    in_code = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        match = None if in_code else _HEADING_RE.match(line)
        if not match:
            continue
        slug = "".join(ch for ch in match.group(1).strip().lower() if ch.isalnum() or ch in " -_").replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors
