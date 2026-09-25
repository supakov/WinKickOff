"""Checks and rollback steps derived from the actions of a rule.

The catalog may carry hand-written `verify` and `rollback` texts; when it does not, the editor shows
these derived steps instead, so every rule tells how to check it on an installed PC and how to undo it.
The same derivation is the starting point of the read-only audit planned in task T15.
All commands here are read-only checks or instructions for a person; nothing is executed.
"""

from __future__ import annotations

from typing import Any

from winkickoff.core.catalog import Action, Rule
from winkickoff.core.render import substitute

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
    return {key: substitute(value, params) for key, value in action.fields.items()}


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
            steps.append(f'reg query "{reg_cli_path(str(f["path"]))}" {_value_arg(str(f["name"]))}: ожидается {f["kind"]} {_value_text(str(f["kind"]), f["value"])}')
        elif t == "reg-remove":
            du_note |= str(f["path"]).startswith("DU:\\")
            steps.append(f'reg query "{reg_cli_path(str(f["path"]))}" {_value_arg(str(f["name"]))}: значения быть не должно')
        elif t == "service":
            start = int(f["start"])
            steps.append(f"sc qc {f['name']}: START_TYPE {start} {SERVICE_START.get(start, '')}".rstrip())
        elif t == "feature":
            steps.append(f"Get-WindowsOptionalFeature -Online -FeatureName {f['name']}: State {f['state']}")
        elif t == "capability":
            steps.append(f'Get-WindowsCapability -Online -Name "{f["pattern"]}": State NotPresent')
        elif t == "appx":
            for name in f["names"]:
                steps.append(f"Get-AppxPackage -AllUsers -Name {name}: пустой результат")
        elif t == "xml-oobe":
            steps.append(f"Во время установки не появляется соответствующий экран OOBE ({f['element']} = {f['value']})")
        elif t in ("xml-pe-command", "xml-specialize-command"):
            steps.append(f"{SETUP_LOG}: команда «{f['description']}» выполнена без ошибки")
        elif t == "exe":
            steps.append(f"{PHASE_LOGS.get(rule.phase, SYSTEM_LOG)}: строка о запуске {f['file']} без ERROR")
    if du_note:
        steps.append("Значения HKCU проверяются под учётной записью, созданной при установке или позже.")
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
                steps.append(f'reg delete "{path}" {value} /f: политика снимается, Windows вернётся к поведению по умолчанию')
            else:
                steps.append(
                    f'reg add "{path}" {value} /t {REG_TYPES.get(str(f["kind"]), f["kind"])} /d <прежнее значение> /f: '
                    "значение вне ветки Policies возвращают, а не удаляют"
                )
        elif t == "reg-remove":
            steps.append(f'Значение {f["name"]} в "{reg_cli_path(str(f["path"]))}" удалялось: вернуть его можно, если известно прежнее значение')
        elif t == "service":
            steps.append(f"sc config {f['name']} start= demand (или тип запуска, который был до установки)")
        elif t == "feature":
            state = str(f["state"])
            command = "Enable-WindowsOptionalFeature" if state == "Disabled" else "Disable-WindowsOptionalFeature"
            steps.append(f"{command} -Online -FeatureName {f['name']} (от администратора, затем перезагрузка)")
        elif t == "capability":
            steps.append(f'Add-WindowsCapability -Online -Name "<полное имя по шаблону {f["pattern"]}>" (нужен доступ к Windows Update)')
        elif t == "appx":
            steps.append("Удалённые приложения устанавливаются заново из Microsoft Store: " + ", ".join(str(n) for n in f["names"]))
        elif t in ("xml-oobe", "xml-pe-command", "xml-specialize-command"):
            steps.append("Действует только при установке: выключить правило и собрать файл ответов заново")
    return steps if any(a.type not in ("exe", "ps") for a in rule.actions) else []
