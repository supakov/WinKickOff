"""Applying rules to an already installed Windows (task T15): plan, read-only audit, apply, undo.

The editor itself never changes the computer. It generates PowerShell scripts:

- Audit-*.ps1 only reads and writes a JSON report; it may run without administrator rights;
- Apply-*.ps1 changes the system, saving the previous state of every registry value, service start
  type and optional feature to backup-<time>.json first; it runs elevated (UAC);
- Undo-Apply.ps1 restores from that backup;
- the same apply script can instead return rules to the values of a clean Windows (plan_revert): the
  `default` field of an action, or a missing value for anything under SOFTWARE\\Policies.

Applying makes the PC match the profile for the selection: rules that are on are applied, rules that are
off (and the rules that require them) return to the values of a clean Windows, so a rule without a check mark
is never silently skipped. Rules that act only during installation (windowsPE, XML commands, OOBE) and rules of
the first sign-in of each user (input languages: on 12.09.2026 a live change of layouts broke keyboard switching
on the customer's PC) are never applied; they are listed in the plan with the reason, like the rules that are
off and have no known Windows defaults.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.catalog import DEFAULT_ABSENT, DEFAULT_UNKNOWN, Action, Catalog, Rule, is_imported
from winkickoff.core.deps import Resolver
from winkickoff.core.i18n import N_, tr
from winkickoff.core.profile import Profile
from winkickoff.core.render import fill, ps_quote, render_block, render_reg_path, render_reg_value, substitute

INSTALL_ONLY_PHASES = {"windowspe", "specialize-xml", "oobe-xml"}
USER_PHASE = "user-first-logon"
IRREVERSIBLE_TYPES = {"appx", "capability", "ps", "exe"}
REBOOT_TYPES = {"feature", "capability", "service"}
REASON_INSTALL_ONLY = N_("takes effect only during Windows installation")
REASON_USER_PHASE = N_("runs at the first sign-in of each user; not applied to a running system")
REASON_NO_DEFAULTS = N_("the Windows defaults are unknown; roll back by hand as the rule describes")
REASON_ALREADY_DEFAULT = N_("the rule only removes values a clean Windows does not have: nothing to return")
REASON_DISABLED_NO_DEFAULTS = N_("off in the profile, but it cannot return to the Windows defaults automatically: roll back by hand as the rule describes")
REASON_DISABLED_ALREADY = N_("off in the profile; a clean Windows has none of these values, nothing to change")
STATUS_TITLES = {
    "applied": N_("in effect"),
    "not-applied": N_("not in effect"),
    "partial": N_("partly in effect"),
    "unknown": N_("not checked"),
}
GPO_ROOTS = ("HKLM:\\SOFTWARE\\POLICIES\\", "DU:\\SOFTWARE\\POLICIES\\", "HKCU:\\SOFTWARE\\POLICIES\\")


@dataclass
class PlannedRule:
    rule: Rule
    requirement: bool = False  # added because a selected rule needs it
    irreversible: bool = False
    reboot: bool = False


@dataclass
class PlannedRevert:
    rule: Rule
    lines: list[str]  # PowerShell calls that restore the Windows defaults
    skipped: list[Action] = field(default_factory=list)  # actions without a known default
    dependent: bool = False  # added because it requires a selected rule
    reboot: bool = False


@dataclass
class ApplyPlan:
    """Make the PC match the profile for the selection: rules that are on are applied, rules that are off
    (and the rules that require them) return to the values of a clean Windows."""
    rules: list[PlannedRule] = field(default_factory=list)
    reverts: list[PlannedRevert] = field(default_factory=list)
    excluded: list[tuple[Rule, str]] = field(default_factory=list)  # (rule, reason as N_ text)
    not_configured: int = 0  # imported policies without a check mark: left as they are

    @property
    def rule_ids(self) -> list[str]:
        return [p.rule.id for p in self.rules]

    @property
    def empty(self) -> bool:
        return not self.rules and not self.reverts


@dataclass
class RevertPlan:
    rules: list[PlannedRevert] = field(default_factory=list)
    excluded: list[tuple[Rule, str]] = field(default_factory=list)
    not_configured: int = 0  # imported policies selected only through a group: returned one by one

    @property
    def rule_ids(self) -> list[str]:
        return [p.rule.id for p in self.rules]


def selected_rules(catalog: Catalog, items: list[str]) -> list[str]:
    """Tree items ("r:<rule>", "g:<group>") to rule ids, in catalog order."""
    chosen: set[str] = set()
    for item in items:
        if item.startswith("r:") and item[2:] in catalog.rules:
            chosen.add(item[2:])
        elif item.startswith("g:") and item[2:] in catalog.groups:
            chosen.update(r.id for r in catalog.rules_in_group(item[2:]))
    return [rule_id for rule_id in catalog.order if rule_id in chosen]


def _running_phase_reason(rule: Rule) -> str | None:
    """Why a rule cannot act on a running Windows at all, or None."""
    if rule.phase in INSTALL_ONLY_PHASES:
        return REASON_INSTALL_ONLY
    if rule.phase == USER_PHASE:
        return REASON_USER_PHASE
    return None


def _needs_reboot(rule: Rule) -> bool:
    return any(a.type in REBOOT_TYPES for a in rule.actions) or any(
        a.type == "reg" and str(a.fields.get("path", "")).upper().startswith("HKLM:\\SYSTEM\\") for a in rule.actions)


def _with_dependents(catalog: Catalog, rule_ids: list[str], keep: Any = None) -> dict[str, bool]:
    """The rules and, transitively, the rules that require them (value True); keep filters the dependents."""
    wanted: dict[str, bool] = {rule_id: False for rule_id in rule_ids}
    stack = list(wanted)
    while stack:
        for dependent in catalog.required_by(stack.pop()):
            if dependent not in wanted and (keep is None or keep(dependent)):
                wanted[dependent] = True
                stack.append(dependent)
    return wanted


def _revert_entry(rule: Rule, dependent: bool) -> PlannedRevert | str:
    """The steps that return one rule to a clean Windows, or the reason (N_ text) why there are none."""
    reason = _running_phase_reason(rule)
    if reason:
        return reason
    params = {name: param.default for name, param in rule.params.items()}
    lines: list[str] = []
    skipped: list[Action] = []
    for action in rule.actions:
        step = windows_default(action)
        if step is None:
            skipped.append(action)
            continue
        line = _revert_line(action, step, params)
        if line:
            lines.append(line)
    if not lines:
        return REASON_NO_DEFAULTS if skipped else REASON_ALREADY_DEFAULT
    return PlannedRevert(rule, lines, skipped, dependent, _needs_reboot(rule))


def plan_apply(catalog: Catalog, profile: Profile, items: list[str]) -> ApplyPlan:
    plan = ApplyPlan()
    selected = selected_rules(catalog, items)
    wanted: dict[str, bool] = {}  # rule id -> added as a requirement
    stack = []
    for rule_id in selected:
        if profile.is_enabled(rule_id):
            wanted[rule_id] = False
            stack.append(rule_id)
    while stack:
        for req in catalog.rules[stack.pop()].requires:
            if req not in wanted and profile.is_enabled(req):
                wanted[req] = True
                stack.append(req)
    for rule_id in Resolver(catalog).apply_order(profile):
        if rule_id not in wanted:
            continue
        rule = catalog.rules[rule_id]
        reason = _running_phase_reason(rule)
        if reason:
            plan.excluded.append((rule, reason))
            continue
        types = {a.type for a in rule.actions}
        plan.rules.append(PlannedRule(rule, wanted[rule_id], bool(types & IRREVERSIBLE_TYPES), _needs_reboot(rule)))
    # rules that are off in the profile: back to the values of a clean Windows, with the rules that require them;
    # an imported policy without a check mark is "not configured" and stays as it is
    off = [rule_id for rule_id in selected if not profile.is_enabled(rule_id) and not is_imported(rule_id)]
    plan.not_configured = sum(1 for rule_id in selected if not profile.is_enabled(rule_id) and is_imported(rule_id))
    returning = _with_dependents(catalog, off, keep=lambda r: not profile.is_enabled(r))
    for rule_id in catalog.order:
        if rule_id not in returning:
            continue
        rule = catalog.rules[rule_id]
        entry = _revert_entry(rule, returning[rule_id])
        if isinstance(entry, PlannedRevert):
            plan.reverts.append(entry)
        else:
            reason = {REASON_NO_DEFAULTS: REASON_DISABLED_NO_DEFAULTS, REASON_ALREADY_DEFAULT: REASON_DISABLED_ALREADY}.get(entry, entry)
            plan.excluded.append((rule, reason))
    return plan


def audit_rules(catalog: Catalog, items: list[str]) -> tuple[list[str], list[tuple[Rule, str]]]:
    """Every selected rule that can be checked on a running Windows, whatever its state in the profile."""
    ids: list[str] = []
    excluded: list[tuple[Rule, str]] = []
    for rule_id in selected_rules(catalog, items):
        rule = catalog.rules[rule_id]
        reason = _running_phase_reason(rule)
        if reason:
            excluded.append((rule, reason))
        else:
            ids.append(rule_id)
    return ids, excluded


# --------------------------------------------------------------------------- scripts


def _label(profile: Profile, app_version: str) -> str:
    return f"# WinKickOff {app_version}, profile: {profile.name}".encode("ascii", "replace").decode("ascii")


def _revert_block(planned: PlannedRevert) -> str:
    return "\n".join([f"# [{planned.rule.id}] Windows defaults"] + planned.lines)


def _assemble(by_phase: dict[str, list[str]]) -> str:
    blocks: list[str] = []
    blocks += by_phase.get("specialize", [])
    if by_phase.get("default-user"):
        inner = "\n\n".join(by_phase["default-user"])
        blocks.append("if (Mount-DefaultUser) {\n" + "\n".join("    " + line if line else line for line in inner.splitlines())
                      + "\n    Dismount-DefaultUser\n}")
    blocks += by_phase.get("post-oobe", [])
    return "\n\n".join(blocks)


def _fill_apply(templates_dir: Path, profile: Profile, label: str, blocks: str, empty: str) -> str:
    accounts = ",".join(ps_quote(a.name) for a in profile.accounts)
    text = fill((templates_dir / "Apply.runtime.ps1").read_text(encoding="utf-8"),
                {"build_label": label, "accounts": accounts, "blocks": blocks or empty})
    return text.replace("\r\n", "\n")


def render_apply(plan: ApplyPlan, profile: Profile, catalog: Catalog, templates_dir: Path, app_version: str = "0.0.0") -> str:
    by_phase: dict[str, list[str]] = defaultdict(list)
    for planned in plan.rules:
        rule = planned.rule
        by_phase[rule.phase].append(render_block(rule, profile.params_for(catalog, rule.id)))
    for returning in plan.reverts:
        by_phase[returning.rule.phase].append(_revert_block(returning))
    label = _label(profile, app_version) + (" (rules that are off return to Windows defaults)" if plan.reverts else "")
    return _fill_apply(templates_dir, profile, label, _assemble(by_phase), "# (nothing to apply)")


def render_undo(templates_dir: Path, profile: Profile, app_version: str = "0.0.0") -> str:
    text = fill((templates_dir / "Undo.runtime.ps1").read_text(encoding="utf-8"), {"build_label": _label(profile, app_version)})
    return text.replace("\r\n", "\n")


# --------------------------------------------------------------------------- return to Windows defaults


def windows_default(action: Action) -> tuple[str, Any] | None:
    """How one action returns to a clean Windows: ("remove", None), ("set", value), ("service", start),
    ("feature", state), ("keep", None) when there is nothing to do, or None when the default is unknown.
    A value under SOFTWARE\\Policies needs no data: a missing policy is the Windows default."""
    default = action.fields.get("default")
    if default == DEFAULT_UNKNOWN:
        return None
    if action.type == "reg":
        if default is None:
            return ("remove", None) if str(action.fields["path"]).upper().startswith(GPO_ROOTS) else None
        return ("remove", None) if default == DEFAULT_ABSENT else ("set", default)
    if action.type == "reg-remove":
        return ("keep", None)
    if action.type == "service" and default is not None:
        return ("service", int(default))
    if action.type == "feature" and default is not None:
        return ("feature", str(default))
    return None


def _revert_line(action: Action, step: tuple[str, Any], params: dict[str, Any]) -> str | None:
    kind, value = step
    f = {key: substitute(v, params) for key, v in action.fields.items() if key != "default"}
    if kind == "remove":
        return f"Remove-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))}"
    if kind == "set":
        return (f"Set-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))} -Type {f['kind']} "
                f"-Value {render_reg_value(str(f['kind']), value)} -Why 'Windows default'")
    if kind == "service":
        return f"Set-ServiceStart -Name {ps_quote(str(f['name']))} -Start {int(value)}"
    if kind == "feature":
        return f"Set-Feature -Name {ps_quote(str(f['name']))} -State {value}"
    return None


def plan_revert(catalog: Catalog, items: list[str]) -> RevertPlan:
    """Return the selected rules, and the rules that require them, to the values of a clean Windows.
    The profile does not matter: the rules may have come from an installation or an earlier apply. Imported
    policies are returned only when selected one by one: a group of templates holds thousands of them."""
    plan = RevertPlan()
    chosen = {item[2:] for item in items if item.startswith("r:")}
    selected = selected_rules(catalog, items)
    plan.not_configured = sum(1 for rule_id in selected if is_imported(rule_id) and rule_id not in chosen)
    selected = [rule_id for rule_id in selected if not is_imported(rule_id) or rule_id in chosen]
    wanted = _with_dependents(catalog, selected)  # id -> dependent
    for rule_id in catalog.order:
        if rule_id not in wanted:
            continue
        entry = _revert_entry(catalog.rules[rule_id], wanted[rule_id])
        if isinstance(entry, PlannedRevert):
            plan.rules.append(entry)
        else:
            plan.excluded.append((catalog.rules[rule_id], entry))
    return plan


def render_revert(plan: RevertPlan, profile: Profile, templates_dir: Path, app_version: str = "0.0.0") -> str:
    """The apply script with blocks that restore Windows defaults; its backup works with Undo-Apply.ps1."""
    by_phase: dict[str, list[str]] = defaultdict(list)
    for planned in plan.rules:
        by_phase[planned.rule.phase].append(_revert_block(planned))
    return _fill_apply(templates_dir, profile, _label(profile, app_version) + " (return to Windows defaults)",
                       _assemble(by_phase), "# (nothing to return)")


def _audit_path(path: str) -> tuple[str, str]:
    if path.startswith("DU:\\"):
        return "HKCU:\\" + path[4:], "current user instead of the default profile"
    return path, ""


def render_audit_block(rule: Rule, params: dict[str, Any]) -> str:
    """Read-only checks of one rule (Test-* calls of Audit.runtime.ps1)."""
    rid = ps_quote(rule.id)
    lines = [f"# [{rule.id}]"]
    for action in rule.actions:
        f = {k: substitute(v, params) for k, v in action.fields.items()}
        t = action.type
        if t == "reg":
            path, note = _audit_path(str(f["path"]))
            lines.append(f"Test-Reg -Rule {rid} -Path {ps_quote(path)} -Name {ps_quote(str(f['name']))} -Kind {f['kind']} "
                         f"-Expected {render_reg_value(str(f['kind']), f['value'])} -Note {ps_quote(note)}")
        elif t == "reg-remove":
            path, note = _audit_path(str(f["path"]))
            lines.append(f"Test-RegAbsent -Rule {rid} -Path {ps_quote(path)} -Name {ps_quote(str(f['name']))} -Note {ps_quote(note)}")
        elif t == "service":
            lines.append(f"Test-ServiceStart -Rule {rid} -Name {ps_quote(str(f['name']))} -Start {int(f['start'])}")
        elif t == "feature":
            lines.append(f"Test-Feature -Rule {rid} -Name {ps_quote(str(f['name']))} -State {f['state']}")
        elif t == "capability":
            lines.append(f"Test-CapabilityAbsent -Rule {rid} -Pattern {ps_quote(str(f['pattern']))}")
        elif t == "appx":
            lines.extend(f"Test-AppAbsent -Rule {rid} -Name {ps_quote(str(n))}" for n in f["names"])
        else:
            lines.append(f"Add-Unknown -Rule {rid} -What {ps_quote(t)}")
    return "\n".join(lines)


def render_audit(rule_ids: list[str], profile: Profile, catalog: Catalog, templates_dir: Path, app_version: str = "0.0.0") -> str:
    blocks = [render_audit_block(catalog.rules[r], profile.params_for(catalog, r)) for r in rule_ids]
    text = fill((templates_dir / "Audit.runtime.ps1").read_text(encoding="utf-8"),
                {"build_label": _label(profile, app_version), "blocks": "\n\n".join(blocks) or "# (nothing to check)"})
    return text.replace("\r\n", "\n")


# --------------------------------------------------------------------------- audit report


@dataclass
class AuditResult:
    rule_id: str
    status: str  # applied | not-applied | partial | unknown
    checks: list[dict[str, str]]


def parse_audit_report(text: str) -> tuple[dict[str, Any], dict[str, AuditResult]]:
    data = json.loads(text.lstrip(chr(0xFEFF)))
    checks: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in data.get("results") or []:
        checks[str(item.get("rule"))].append({k: str(v) if v is not None else "" for k, v in item.items()})
    out: dict[str, AuditResult] = {}
    for rule_id, items in checks.items():
        statuses = {c["status"] for c in items}
        known = statuses - {"unknown"}
        if not known:
            status = "unknown"
        elif known == {"ok"}:
            status = "applied"
        elif "ok" in known:
            status = "partial"
        else:
            status = "not-applied"
        out[rule_id] = AuditResult(rule_id, status, items)
    meta = {k: v for k, v in data.items() if k != "results"}
    return meta, out


def status_title(status: str) -> str:
    return tr(STATUS_TITLES.get(status, status))


def write_script(path: Path, text: str) -> None:
    """PowerShell 5.1 reads UTF-8 with a BOM reliably; CRLF like every other Windows script."""
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))


def run_audit(script: str, work_dir: Path, timeout: int = 300) -> str:
    """Run the read-only audit in powershell.exe and return the JSON report text."""
    folder = work_dir / f"audit-{uuid.uuid4().hex[:8]}"
    folder.mkdir(parents=True, exist_ok=True)
    script_path, report = folder / "Audit.ps1", folder / "report.json"
    write_script(script_path, script)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                    "-File", str(script_path), "-Report", str(report)],
                   capture_output=True, text=True, timeout=timeout, creationflags=flags, check=False)
    if not report.exists():
        raise RuntimeError(tr("The check produced no report: {0}", script_path))
    return report.read_text(encoding="utf-8-sig")


def launch_elevated(script_path: Path) -> None:
    """Start the apply script in powershell.exe through the UAC prompt (the user confirms it there)."""
    if sys.platform != "win32":
        raise RuntimeError("elevation is available on Windows only")
    arguments = f'-NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", arguments, str(script_path.parent), 1)
    if result <= 32:
        raise RuntimeError(tr("The launch was cancelled or failed (code {0})", result))
