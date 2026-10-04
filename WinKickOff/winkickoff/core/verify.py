"""Checks and rollback steps derived from the actions of a rule.

The catalog may carry hand-written `verify` and `rollback` texts; when it does not, the editor shows
these derived steps instead, so every rule tells how to check it on an installed PC and how to undo it.
The same derivation is the starting point of the read-only audit planned in task T15.
All commands here are read-only checks or instructions for a person; nothing is executed.
"""

from __future__ import annotations

from typing import Any

from winkickoff.core.catalog import Action, Rule
from winkickoff.core.render import RenderError, list_entries, substitute_fields
from winkickoff.core.i18n import tr

SERVICE_START = {0: "BOOT_START", 1: "SYSTEM_START", 2: "AUTO_START", 3: "DEMAND_START", 4: "DISABLED"}
SETUP_LOG = "C:\\Windows\\Panther\\setupact.log"
SYSTEM_LOG = "C:\\ProgramData\\Unattend\\Logs\\Setup-System.log"
USER_LOG = "C:\\ProgramData\\Unattend\\Logs\\Setup-User-<user>.log"
POST_LOG = "C:\\ProgramData\\Unattend\\Logs\\Post-OOBE.log"
PHASE_LOGS = {"specialize": SYSTEM_LOG, "default-user": SYSTEM_LOG, "user-first-logon": USER_LOG, "post-oobe": POST_LOG}


def reg_cli_path(path: str) -> str:
    """Registry path for reg.exe. Default-user values reach every account created after
    installation, so on an installed PC they are checked in HKCU of such an account."""
    if path.startswith("HKLM:\\"):
        return "HKLM\\" + path[6:]
    if path.startswith("HKCU:\\"):
        return "HKCU\\" + path[6:]
    if path.startswith("DU:\\"):
        return "HKCU\\" + path[4:]
    return path


REG_TYPES = {"DWord": "REG_DWORD", "QWord": "REG_QWORD", "String": "REG_SZ", "ExpandString": "REG_EXPAND_SZ",
             "MultiString": "REG_MULTI_SZ", "Binary": "REG_BINARY"}


def _value_arg(name: str) -> str:
    """reg.exe addresses the default value of a key with /ve instead of /v <name>."""
    return "/ve" if name == "(Default)" else f"/v {name}"


def _is_policy(path: str) -> bool:
    return "\\policies\\" in path.lower()


def _value_text(kind: str, value: Any) -> str:
    if isinstance(value, bool):
        value = int(value)
    if kind in ("DWord", "QWord") and isinstance(value, int):
        return f"{value} (0x{value:x})"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _fields(action: Action, params: dict[str, Any]) -> dict[str, Any]:
    return substitute_fields(action.fields, params)


def _list_step(f: dict[str, Any]) -> str:
    """The check of a key that holds a list of values (reg-list)."""
    path = reg_cli_path(str(f["path"]))
    try:
        entries = list_entries(f)
    except RenderError:
        return tr("reg query \"{0}\": the list of values in the profile is not valid", path)
    if not entries and f.get("additive"):
        return tr("reg query \"{0}\": nothing to check, the list is empty", path)
    if not entries:
        return tr("reg query \"{0}\": the key has no values", path)
    shown = "; ".join(f"{name} = {data}" for name, data in entries)
    kind = REG_TYPES.get(str(f["kind"]), str(f["kind"]))
    if f.get("additive"):
        return tr("reg query \"{0}\": expected {1} values {2} (other values may stay)", path, kind, shown)
    return tr("reg query \"{0}\": expected {1} values {2} and no other values", path, kind, shown)


def verify_steps(rule: Rule, params: dict[str, Any]) -> list[str]:
    """One line per action: what to run or where to look on an installed PC, and what to expect.
    Empty when no action can be checked generically (ps and exe need a hand-written text)."""
    steps: list[str] = []
    du_note = False
    for action in rule.actions:
        f = _fields(action, params)
        t = action.type
        if t == "reg":
            du_note |= str(f["path"]).startswith("DU:\\")
            steps.append(tr("reg query \"{0}\" {1}: expected {2} {3}", reg_cli_path(str(f["path"])), _value_arg(str(f["name"])), f["kind"], _value_text(str(f["kind"]), f["value"])))
        elif t == "reg-remove":
            du_note |= str(f["path"]).startswith("DU:\\")
            steps.append(tr("reg query \"{0}\" {1}: the value must not exist", reg_cli_path(str(f["path"])), _value_arg(str(f["name"]))))
        elif t == "reg-list":
            du_note |= str(f["path"]).startswith("DU:\\")
            steps.append(_list_step(f))
        elif t == "service":
            start = int(f["start"])
            steps.append(f"sc qc {f['name']}: START_TYPE {start} {SERVICE_START.get(start, '')}".rstrip())
        elif t == "feature":
            steps.append(f"Get-WindowsOptionalFeature -Online -FeatureName {f['name']}: State {f['state']}")
        elif t == "capability":
            steps.append(f'Get-WindowsCapability -Online -Name "{f["pattern"]}": State NotPresent')
        elif t == "appx":
            for name in f["names"]:
                steps.append(tr("Get-AppxPackage -AllUsers -Name {0}: empty result", name))
        elif t == "xml-oobe":
            steps.append(tr("The corresponding OOBE screen does not appear during installation ({0} = {1})", f['element'], f['value']))
        elif t in ("xml-pe-command", "xml-specialize-command"):
            steps.append(tr("{0}: command \"{1}\" completed without errors", SETUP_LOG, f['description']))
        elif t == "exe":
            steps.append(tr("{0}: a line about running {1} with no ERROR", PHASE_LOGS.get(rule.phase, SYSTEM_LOG), f['file']))
    if du_note:
        steps.append(tr("Check HKCU values while signed in with an account created during or after installation."))
    return steps if any(a.type not in ("exe", "ps") for a in rule.actions) else []


def rollback_steps(rule: Rule, params: dict[str, Any]) -> list[str]:
    """How to undo the rule on an installed PC, one line per action; empty when there is no
    generic way (ps and exe need a hand-written text)."""
    steps: list[str] = []
    for action in rule.actions:
        f = _fields(action, params)
        t = action.type
        if t == "reg":
            path, value = reg_cli_path(str(f["path"])), _value_arg(str(f["name"]))
            if _is_policy(str(f["path"])):
                steps.append(tr("reg delete \"{0}\" {1} /f: removes the policy, Windows returns to its default behavior", path, value))
            else:
                steps.append(
                    tr("reg add \"{0}\" {1} /t {2} /d <previous value> /f: a value outside the Policies key is restored, not deleted", path, value, REG_TYPES.get(str(f["kind"]), f["kind"]))
                )
        elif t == "reg-remove":
            steps.append(tr("Value {0} in \"{1}\" was deleted: it can be restored if the previous value is known", f["name"], reg_cli_path(str(f["path"]))))
        elif t == "reg-list":
            path = reg_cli_path(str(f["path"]))
            if _is_policy(str(f["path"])):
                steps.append(tr("reg delete \"{0}\" /va /f: removes every value of the list, Windows returns to its default behavior", path))
            else:
                steps.append(tr("The values of the list in \"{0}\" were replaced: they can be restored if the previous values are known", path))
        elif t == "service":
            steps.append(tr("sc config {0} start= demand (or the startup type it had before installation)", f['name']))
        elif t == "feature":
            state = str(f["state"])
            command = "Enable-WindowsOptionalFeature" if state == "Disabled" else "Disable-WindowsOptionalFeature"
            steps.append(tr("{0} -Online -FeatureName {1} (as administrator, then restart)", command, f['name']))
        elif t == "capability":
            steps.append(tr("Add-WindowsCapability -Online -Name \"<full name matching pattern {0}>\" (requires access to Windows Update)", f["pattern"]))
        elif t == "appx":
            steps.append(tr("Reinstall the removed apps from Microsoft Store: ") + ", ".join(str(n) for n in f["names"]))
        elif t in ("xml-oobe", "xml-pe-command", "xml-specialize-command"):
            steps.append(tr("Applies only during installation: disable the rule and build the answer file again"))
    return steps if any(a.type not in ("exe", "ps") for a in rule.actions) else []
