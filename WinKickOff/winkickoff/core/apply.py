"""Applying rules to an already installed Windows (task T15): plan, read-only audit, apply, undo.

The editor itself never changes the computer. It generates PowerShell scripts:

- Audit-*.ps1 only reads and writes a JSON report; it may run without administrator rights;
- Apply-*.ps1 changes the system, saving the previous state of every registry value, service start
  type and optional feature to backup-<time>.json first; it runs elevated (UAC);
- Undo-Apply.ps1 restores from that backup.

Rules that act only during installation (windowsPE, XML commands, OOBE) and rules of the first sign-in
of each user (input languages: on 12.09.2026 a live change of layouts broke keyboard switching on the
customer's PC) are never applied; they are listed in the plan with the reason.
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

from winkickoff.core.catalog import Catalog, Rule
from winkickoff.core.deps import Resolver
from winkickoff.core.i18n import N_, tr
from winkickoff.core.profile import Profile
from winkickoff.core.render import fill, ps_quote, render_block, render_reg_value, substitute

INSTALL_ONLY_PHASES = {"windowspe", "specialize-xml", "oobe-xml"}
USER_PHASE = "user-first-logon"
IRREVERSIBLE_TYPES = {"appx", "capability", "ps", "exe"}
REBOOT_TYPES = {"feature", "capability", "service"}
REASON_INSTALL_ONLY = N_("действует только при установке Windows")
REASON_USER_PHASE = N_("выполняется при первом входе каждого пользователя; на работающей системе не применяется")
REASON_DISABLED = N_("выключено в профиле")
STATUS_TITLES = {
    "applied": N_("действует"),
    "not-applied": N_("не действует"),
    "partial": N_("действует частично"),
    "unknown": N_("не проверяется"),
}


@dataclass
class PlannedRule:
    rule: Rule
    requirement: bool = False  # added because a selected rule needs it
    irreversible: bool = False
    reboot: bool = False


@dataclass
class ApplyPlan:
    rules: list[PlannedRule] = field(default_factory=list)
    excluded: list[tuple[Rule, str]] = field(default_factory=list)  # (rule, reason as N_ text)

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


def plan_apply(catalog: Catalog, profile: Profile, items: list[str]) -> ApplyPlan:
    plan = ApplyPlan()
    wanted: dict[str, bool] = {}  # rule id -> added as a requirement
    stack = []
    for rule_id in selected_rules(catalog, items):
        if profile.is_enabled(rule_id):
            wanted[rule_id] = False
            stack.append(rule_id)
        else:
            plan.excluded.append((catalog.rules[rule_id], REASON_DISABLED))
    while stack:
        for req in catalog.rules[stack.pop()].requires:
            if req not in wanted and profile.is_enabled(req):
                wanted[req] = True
                stack.append(req)
    for rule_id in Resolver(catalog).apply_order(profile):
        if rule_id not in wanted:
            continue
        rule = catalog.rules[rule_id]
        if rule.phase in INSTALL_ONLY_PHASES:
            plan.excluded.append((rule, REASON_INSTALL_ONLY))
        elif rule.phase == USER_PHASE:
            plan.excluded.append((rule, REASON_USER_PHASE))
        else:
            types = {a.type for a in rule.actions}
            reboot = bool(types & REBOOT_TYPES) or any(
                a.type == "reg" and str(a.fields.get("path", "")).upper().startswith("HKLM:\\SYSTEM\\") for a in rule.actions
            )
            plan.rules.append(PlannedRule(rule, wanted[rule_id], bool(types & IRREVERSIBLE_TYPES), reboot))
    return plan


# --------------------------------------------------------------------------- scripts


def _label(profile: Profile, app_version: str) -> str:
    return f"# WinKickOff {app_version}, profile: {profile.name}".encode("ascii", "replace").decode("ascii")


def render_apply(plan: ApplyPlan, profile: Profile, catalog: Catalog, templates_dir: Path, app_version: str = "0.0.0") -> str:
    by_phase: dict[str, list[str]] = defaultdict(list)
    for planned in plan.rules:
        rule = planned.rule
        by_phase[rule.phase].append(render_block(rule, profile.params_for(catalog, rule.id)))
    blocks: list[str] = []
    blocks += by_phase.get("specialize", [])
    if by_phase.get("default-user"):
        inner = "\n\n".join(by_phase["default-user"])
        blocks.append("if (Mount-DefaultUser) {\n" + "\n".join("    " + line if line else line for line in inner.splitlines())
                      + "\n    Dismount-DefaultUser\n}")
    blocks += by_phase.get("post-oobe", [])
    accounts = ",".join(ps_quote(a.name) for a in profile.accounts)
    text = fill((templates_dir / "Apply.runtime.ps1").read_text(encoding="utf-8"),
                {"build_label": _label(profile, app_version), "accounts": accounts, "blocks": "\n\n".join(blocks) or "# (nothing to apply)"})
    return text.replace("\r\n", "\n")


def render_undo(templates_dir: Path, profile: Profile, app_version: str = "0.0.0") -> str:
    text = fill((templates_dir / "Undo.runtime.ps1").read_text(encoding="utf-8"), {"build_label": _label(profile, app_version)})
    return text.replace("\r\n", "\n")


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
        raise RuntimeError(tr("Проверка не дала отчёта: {0}", script_path))
    return report.read_text(encoding="utf-8-sig")


def launch_elevated(script_path: Path) -> None:
    """Start the apply script in powershell.exe through the UAC prompt (the user confirms it there)."""
    if sys.platform != "win32":
        raise RuntimeError("elevation is available on Windows only")
    arguments = f'-NoProfile -ExecutionPolicy Bypass -File "{script_path}"'
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "powershell.exe", arguments, str(script_path.parent), 1)
    if result <= 32:
        raise RuntimeError(tr("Запуск отменён или не удался (код {0})", result))
