"""The workspace the tools act on: the open profile of the window, or a profile held in memory without a window.

Everything that changes a profile follows the same rules as the window (the Resolver cascade, linked policies,
parameter validation), so an agent can do nothing the user could not do by clicking. apply_rule_states() is the shared
core used by both implementations.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from winkickoff.core import linked
from winkickoff.core.catalog import Catalog, Param, Rule, is_imported
from winkickoff.core.deps import Change, Resolver
from winkickoff.core.i18n import N_, catalog_texts, tr
from winkickoff.core.paths import AppPaths, display_path
from winkickoff.core.profile import Profile
from winkickoff.core.render import BuildResult, Renderer, RenderError, write_answer_file
from winkickoff.core.resources import Resources
from winkickoff.core.validate import Issue, check_param, has_errors, validate_profile, validate_xml
from winkickoff.mcp.errors import ToolError
from winkickoff.mcp.redact import check_name, safe_child

log = logging.getLogger(__name__)
PRESET_IDS = ("office", "strict", "laptop", "memstechtips")
POWERSHELL_NOTE = N_("PowerShell syntax not checked: build the file in the window (F9) to check it")  # Check (F7) does not run it, only Build (F9)
GROUP_ACTIONS = ("on", "off", "defaults")


@dataclass(frozen=True)
class Snapshot:
    """What a read tool works on: the shared catalog and a copy of the profile, taken on the owning thread."""

    catalog: Catalog
    profile: Profile
    resources: Resources
    paths: AppPaths
    dirty: bool
    profile_file: str  # display path of the profile file, or ""
    selected: str  # the tree item shown in the window, or ""
    issues: list[Issue]
    language: str


class Workspace(Protocol):
    def snapshot(self) -> Snapshot: ...
    def set_rules(self, items: list[tuple[str, bool]]) -> tuple[list[Change], list[tuple[str, str]]]: ...
    def set_group(self, group_id: str, action: str) -> list[Change]: ...
    def set_param(self, rule_id: str, name: str, value: Any) -> Any: ...
    def set_profile_info(self, name: str | None, author: str | None, comment: str | None) -> tuple[str, str, str]: ...
    def load_profile(self, path: Path, force: bool) -> list[str]: ...
    def show_item(self, item: str) -> bool: ...
    def save_profile_to(self, path: Path) -> None: ...
    def write_answer_file_to(self, path: Path) -> tuple[BuildResult, list[Issue]]: ...
    def current_issues(self) -> list[Issue]: ...
    def is_dirty(self) -> bool: ...
    def error_count(self) -> int: ...
    def is_busy(self) -> bool: ...


# --------------------------------------------------------------------------- shared logic


def apply_rule_states(catalog: Catalog, profile: Profile, resolver: Resolver,
                      items: list[tuple[str, bool]]) -> tuple[list[Change], list[tuple[str, str]]]:
    """Switch rules on or off as the tree does: the Resolver cascade, linked imported policies that follow a
    built-in rule, and policies that became redundant. Returns (changes, refused as (id, reason))."""
    changes: list[Change] = []
    refused: list[tuple[str, str]] = []
    for rule_id, enabled in items:
        if rule_id not in catalog.rules:
            refused.append((rule_id, "unknown rule"))
            continue
        found = linked.link(catalog, profile, rule_id) if is_imported(rule_id) else None
        if found is not None and not profile.is_enabled(rule_id):
            if profile.is_enabled(found.rule):
                if enabled:
                    continue  # already on through the built-in rule
                if not found.equal:
                    refused.append((rule_id, f"set by the built-in rule {found.rule}, which also sets other values; "
                                             "switch that rule off instead"))
                    continue
                changes += resolver.set_rule(profile, found.rule, False)
                continue
            if found.equal and enabled:
                changes += resolver.set_rule(profile, found.rule, True)  # the same setting: the reviewed rule is used
                continue
        if profile.is_enabled(rule_id) != enabled:
            changes += resolver.set_rule(profile, rule_id, enabled)
    changes += drop_redundant(catalog, profile)
    return changes, refused


def drop_redundant(catalog: Catalog, profile: Profile) -> list[Change]:
    """Switch off imported policies that an enabled built-in rule now writes anyway (the window does the same)."""
    dropped: list[Change] = []
    for rule_id, other in linked.redundant(catalog, profile):
        profile.rules[rule_id].enabled = False
        dropped.append(Change(rule_id, False, "covered by " + other))
    return dropped


def apply_group_action(catalog: Catalog, profile: Profile, resolver: Resolver, group_id: str, action: str) -> list[Change]:
    """The group check box and the group buttons: on, off or catalog defaults; an imported group only off."""
    if group_id not in catalog.groups:
        raise ToolError("unknown_id", f"unknown group {group_id}", {"id": group_id})
    if action not in GROUP_ACTIONS:
        raise ToolError("invalid_arguments", f"action must be one of {GROUP_ACTIONS}")
    if is_imported(group_id) and action != "off":
        raise ToolError("refused", "imported policies are switched on one by one; a group of them can only be switched off",
                        {"id": group_id})
    if action == "defaults":
        changes = resolver.reset_group(profile, group_id)
    else:
        changes = resolver.set_group(profile, group_id, action == "on")
    return changes + drop_redundant(catalog, profile)


def normalise_param_value(rule: Rule, param: Param, value: Any) -> Any:
    """The value in the type of the parameter, or a ToolError invalid_arguments."""
    if param.type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            raise ToolError("invalid_arguments", f"{param.name}: an integer is required", {"name": param.name})
        return value
    if param.type == "bool":
        if not isinstance(value, bool):
            raise ToolError("invalid_arguments", f"{param.name}: true or false is required", {"name": param.name})
        return value
    if param.type == "enum":
        allowed = [v for v, _ in param.values]
        if value not in allowed:
            raise ToolError("invalid_arguments", f"{param.name}: the value must be one of {allowed}",
                            {"name": param.name, "values": allowed})
        return value
    if param.type == "list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ToolError("invalid_arguments", f"{param.name}: a list of strings is required", {"name": param.name})
        items = [item.strip() for item in value]
        return [item for item in items if item]
    if not isinstance(value, str):
        raise ToolError("invalid_arguments", f"{param.name}: text is required", {"name": param.name})
    return value.strip()


def change_param(catalog: Catalog, profile: Profile, resources: Resources, rule_id: str, name: str,
                 value: Any) -> tuple[Any, bool]:
    """Set one parameter as the parameter panel does; a value that introduces a validation error is rejected and the
    profile restored. Returns the stored value and whether the profile changed (the current value changes nothing)."""
    rule = catalog.rules.get(rule_id)
    if rule is None:
        raise ToolError("unknown_id", f"unknown rule {rule_id}", {"id": rule_id})
    param = rule.params.get(name)
    if param is None:
        raise ToolError("invalid_arguments", f"rule {rule_id} has no parameter {name}",
                        {"id": rule_id, "params": list(rule.params)})
    value = normalise_param_value(rule, param, value)
    problem = check_param(rule, param, value)
    if problem:
        raise ToolError("invalid_arguments", problem, {"id": rule_id, "name": name})
    state = profile.rules[rule_id]
    previous = dict(state.params)
    if value == param.default:
        state.params.pop(name, None)
    else:
        state.params[name] = value
    if state.params == previous:
        return value, False  # the current value: the panel does not mark the profile dirty either
    before_errors = {i.message for i in validate_profile(_with_params(profile, rule_id, previous), catalog, resources.keyboards)
                     if i.level == "error"}
    new_errors = [i.message for i in validate_profile(profile, catalog, resources.keyboards)
                  if i.level == "error" and i.message not in before_errors]
    if new_errors:
        state.params.clear()
        state.params.update(previous)
        raise ToolError("validation_failed", "; ".join(new_errors), {"id": rule_id, "name": name})
    return value, True


def _with_params(profile: Profile, rule_id: str, params: dict[str, Any]) -> Profile:
    """A copy of the profile with the given parameters of one rule (to validate the state before a change)."""
    copied = profile.copy()
    copied.rules[rule_id].params.clear()
    copied.rules[rule_id].params.update(params)
    return copied


def clean_info(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    from winkickoff.mcp.redact import clean_text  # local import: redact imports profile, not this module

    return clean_text(text, limit).strip()


def check_and_build(catalog: Catalog, profile: Profile, resources: Resources, templates: Path,
                    app_version: str) -> tuple[BuildResult | None, list[Issue]]:
    """validate_profile, Renderer.build and validate_xml: the window's Check without PowerShell."""
    issues = validate_profile(profile, catalog, resources.keyboards)
    if has_errors(issues):
        return None, issues
    try:
        result = Renderer(catalog, templates, resources.keyboards).build(profile, app_version=app_version)
    except RenderError as exc:
        return None, issues + [Issue("error", "build", str(exc))]
    return result, issues + validate_xml(result.xml)


# --------------------------------------------------------------------------- profile files


def is_preset_id(name: str) -> bool:
    return unicodedata.normalize("NFC", name).lower() in PRESET_IDS


def profile_file(paths: AppPaths, name: str) -> Path:
    """A preset id (office, strict, laptop, memstechtips) inside the data folder, or profiles/<name>.json."""
    if is_preset_id(name):
        return paths.data / "profiles" / f"preset-{unicodedata.normalize('NFC', name).lower()}.json"
    return safe_child(paths.profiles, name, ".json")


def profile_display(path: Path | None, root: Path) -> str:
    """The profile file as clients see it: its path inside the program folder, or the file name alone when it lies
    elsewhere (the folder layout of the user's disk never leaves the machine)."""
    if path is None:
        return ""
    shown = display_path(path, root)
    return path.name if Path(shown).is_absolute() else shown


def list_profile_files(paths: AppPaths) -> tuple[list[dict[str, Any]], int]:
    """Presets from the data folder and user profiles from the program folder, by name; the count of files whose
    names the server does not accept."""
    found: list[dict[str, Any]] = []
    unlisted = 0
    seen: set[Path] = set()
    for folder, kind in ((paths.data / "profiles", "preset"), (paths.profiles, "user")):
        try:
            entries = sorted(folder.glob("*.json"))
        except OSError:
            continue
        for path in entries:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            is_preset = path.name.lower().startswith("preset-")
            if (kind == "preset") != is_preset:
                continue  # not counted as seen: the same folder is scanned again for the other kind when data == root
            seen.add(resolved)
            stem = path.stem[len("preset-"):] if is_preset else path.stem
            if check_name(stem) or (is_preset and stem.lower() not in PRESET_IDS):
                unlisted += 1
                continue
            found.append({"name": stem, "kind": kind, **_profile_summary(path)})
    return found, unlisted


def _profile_summary(path: Path) -> dict[str, Any]:
    import json

    from winkickoff.mcp.redact import clean_text

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (OSError, ValueError):
        return {"title_text": "", "modified": "", "catalog_version": "", "readable": False}
    return {"title_text": clean_text(data.get("name", ""), 80), "modified": clean_text(data.get("modified", ""), 40),
            "catalog_version": clean_text(data.get("catalog_version", ""), 20), "readable": True}


# --------------------------------------------------------------------------- headless


@dataclass
class HeadlessWorkspace:
    """A profile in memory without a window: the stdio server and the tests."""

    paths: AppPaths
    catalog: Catalog
    profile: Profile
    resources: Resources
    app_version: str = "0.0.0"
    dirty: bool = False
    issues: list[Issue] = field(default_factory=list)
    resolver: Resolver = field(init=False)

    def __post_init__(self) -> None:
        self.resolver = Resolver(self.catalog)

    def snapshot(self) -> Snapshot:
        from winkickoff.core.i18n import language

        return Snapshot(self.catalog, self.profile.copy(), self.resources, self.paths, self.dirty,
                        profile_display(self.profile.path, self.paths.root), "", list(self.issues), language())

    def set_rules(self, items: list[tuple[str, bool]]) -> tuple[list[Change], list[tuple[str, str]]]:
        changes, refused = apply_rule_states(self.catalog, self.profile, self.resolver, items)
        if changes:
            self.dirty = True
        return changes, refused

    def set_group(self, group_id: str, action: str) -> list[Change]:
        changes = apply_group_action(self.catalog, self.profile, self.resolver, group_id, action)
        if changes:
            self.dirty = True
        return changes

    def set_param(self, rule_id: str, name: str, value: Any) -> Any:
        stored, changed = change_param(self.catalog, self.profile, self.resources, rule_id, name, value)
        if changed:
            self.dirty = True
        return stored

    def set_profile_info(self, name: str | None, author: str | None, comment: str | None) -> tuple[str, str, str]:
        wanted = (self.profile.name if name is None else name, self.profile.author if author is None else author,
                  self.profile.comment if comment is None else comment)
        if wanted != (self.profile.name, self.profile.author, self.profile.comment):
            self.profile.name, self.profile.author, self.profile.comment = wanted
            self.dirty = True
        return wanted

    def load_profile(self, path: Path, force: bool) -> list[str]:
        if self.dirty and not force:
            raise ToolError("unsaved_changes", "the open profile has unsaved changes; save it or pass force")
        try:
            profile, warnings = Profile.load(path, self.catalog)
        except (OSError, ValueError) as exc:
            raise ToolError("load_failed", f"the profile could not be opened: {type(exc).__name__}", {"name": path.stem}) from exc
        self.profile = profile
        self.dirty = False
        self.issues = [Issue("info", "profile", warning) for warning in warnings]  # the window shows them the same way
        return warnings

    def show_item(self, item: str) -> bool:
        return False

    def save_profile_to(self, path: Path) -> None:
        previous = self.profile.name
        self.profile.name = path.stem
        try:
            self.profile.save(path, self.catalog)
        except OSError:
            self.profile.name = previous  # a failed save leaves the profile as it was
            raise
        self.dirty = False

    def write_answer_file_to(self, path: Path) -> tuple[BuildResult, list[Issue]]:
        result, issues = check_and_build(self.catalog, self.profile, self.resources, self.paths.templates, self.app_version)
        if result is None or has_errors(issues):
            self.issues = issues
            raise ToolError("validation_failed", "the profile has errors; run check_profile",
                            {"errors": [i.message for i in issues if i.level == "error"]})
        write_answer_file(result, path)
        self.issues = issues + [Issue("info", "powershell", tr(POWERSHELL_NOTE))]
        return result, self.issues

    def current_issues(self) -> list[Issue]:
        return list(self.issues)

    def is_dirty(self) -> bool:
        return self.dirty

    def error_count(self) -> int:
        return sum(1 for i in validate_profile(self.profile, self.catalog, self.resources.keyboards) if i.level == "error")

    def is_busy(self) -> bool:
        return False


def rule_title(catalog: Catalog, rule_id: str) -> str:
    return catalog_texts().rule(catalog.rules[rule_id], "title")
