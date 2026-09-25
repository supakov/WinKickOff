"""Rendering: catalog actions to PowerShell lines and (later, T06) whole files.

Implemented now: per-action rendering with parameter substitution and PowerShell quoting, and
per-rule blocks. The full build (runtime templates, phases, XML slots, embedded profile) is task T06.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from winkickoff.core.catalog import Action, Catalog, Rule

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")


class RenderError(ValueError):
    pass


def ps_quote(text: str) -> str:
    """Single-quoted PowerShell literal (the only quoting used for catalog strings)."""
    return "'" + str(text).replace("'", "''") + "'"


def substitute(value: Any, params: dict[str, Any]) -> Any:
    """Replace {name} placeholders. A string that is exactly one placeholder keeps the param's type."""
    if isinstance(value, str):
        whole = _PLACEHOLDER_RE.fullmatch(value)
        if whole:
            return params[whole.group(1)]
        return _PLACEHOLDER_RE.sub(lambda m: str(params[m.group(1)]), value)
    if isinstance(value, list):
        return [substitute(item, params) for item in value]
    return value


def render_reg_value(kind: str, value: Any) -> str:
    if kind in ("DWord", "QWord"):
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return str(value)
        raise RenderError(f"{kind} needs an integer, got {value!r}")
    if kind in ("String", "ExpandString"):
        return ps_quote(str(value))
    if kind == "MultiString":
        if not isinstance(value, list):
            raise RenderError("MultiString needs a list")
        return "@(" + ",".join(ps_quote(str(v)) for v in value) + ")"
    if kind == "Binary":
        if not isinstance(value, list):
            raise RenderError("Binary needs a list of bytes")
        return "([byte[]](" + ",".join(str(int(v)) for v in value) + "))"
    raise RenderError(f"unknown registry kind {kind}")


def render_reg_path(path: str) -> str:
    """DU: paths are relative to the mounted default-user hive ($du in the runtime)."""
    if path.startswith("DU:\\"):
        return '"$du\\' + path[4:] + '"'
    return ps_quote(path)


def render_action(action: Action, params: dict[str, Any]) -> str:
    """One action as PowerShell (script phases). XML actions are handled by the XML builder (T06)."""
    f = {key: substitute(value, params) for key, value in action.fields.items()}
    t = action.type
    if t == "reg":
        line = f"Set-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))} -Type {f['kind']} -Value {render_reg_value(str(f['kind']), f['value'])}"
        if f.get("why"):
            line += f" -Why {ps_quote(str(f['why']))}"
        return line
    if t == "reg-remove":
        return f"Remove-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))}"
    if t == "service":
        return f"Set-ServiceStart -Name {ps_quote(str(f['name']))} -Start {int(f['start'])}"
    if t == "exe":
        args = ",".join(ps_quote(str(a)) for a in f["args"])
        return f"Invoke-Exe {ps_quote(str(f['file']))} @({args})"
    if t == "feature":
        return f"Set-Feature -Name {ps_quote(str(f['name']))} -State {f['state']}"
    if t == "capability":
        return f"Remove-Capability -Pattern {ps_quote(str(f['pattern']))}"
    if t == "appx":
        names = ",".join(ps_quote(str(n)) for n in f["names"])
        return f"Remove-Apps @({names})"
    if t == "ps":
        return str(f["script"]).strip("\r\n")
    raise RenderError(f"action type {t} is not a script action")


def render_block(rule: Rule, params: dict[str, Any]) -> str:
    """The block for one enabled rule: a marker comment followed by its actions."""
    lines = [f"# [{rule.id}] {rule.title}"]
    for action in rule.actions:
        lines.append(render_action(action, params))
    return "\n".join(lines)


@dataclass
class BuildResult:
    xml: str
    scripts: dict[str, str]
    rule_ids: list[str]
    warnings: list[str]


class Renderer:
    """Full build: runtime templates plus blocks of enabled rules, per phase. Task T06."""

    def __init__(self, catalog: Catalog, templates_dir: Any) -> None:
        self.catalog = catalog
        self.templates_dir = templates_dir

    def build(self, profile: Any) -> BuildResult:  # pragma: no cover - placeholder until T06
        raise NotImplementedError("Renderer.build is implemented in task T06")
