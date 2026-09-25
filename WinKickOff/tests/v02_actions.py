"""Parse the v0.2 answer file (../autounattend.xml) into a set of normalised actions.

Used by the semantic golden test: every registry write, registry removal, service start type
and literal command of Setup-System.ps1 v0.2 must be present in the catalog with the same value.
Only the literal, unconditional (or $Config-default-true) parts are extracted; dynamic loops and
ps fragments are compared separately by key strings.
"""

from __future__ import annotations

import re
from pathlib import Path

CONFIG_FALSE = {"DisableNetBIOS", "RemoveVBScript"}
CONFIG_VALUES: dict[str, object] = {
    "SmartScreenLevel": "Warn",
    "InactivityLockSeconds": 900,
    "DeferFeatureUpdatesDays": 90,
    "ControlledFolderAccess": 0,
}
KNOWN_EXPR: dict[str, object] = {
    "$(if ($Config.UACAlwaysNotify) { 2 } else { 5 })": 2,
    "([int]$Config.ControlledFolderAccess)": 0,
}
INFRASTRUCTURE_PATH_FRAGMENTS = ("active setup",)  # handled by the runtime, not by rules

Action = tuple


def extract_script(xml_text: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}"><!\[CDATA\[(.*?)\]\]>', xml_text, re.S)
    if not match:
        raise ValueError(f"script {name} not found")
    return match.group(1)


def _literal_list(expr: str) -> list[str] | None:
    items = re.findall(r"'([^']*)'", expr)
    rebuilt = ",".join(f"'{i}'" for i in items)
    return items if items and rebuilt == expr.replace(", ", ",") else None


def _join_foreach_headers(lines: list[str]) -> list[str]:
    """A foreach header whose literal list spans several lines is merged into one line."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*foreach \(\$\w+ in ", line) and line.rstrip().endswith(","):
            merged = line.rstrip()
            while i + 1 < len(lines) and not merged.endswith("{"):
                i += 1
                merged += lines[i].strip()
            out.append(merged)
        else:
            out.append(line)
        i += 1
    return out


def _split_statements(text: str) -> list[str]:
    return [part.strip() for part in text.split("; ") if part.strip()]


def _substitute_var(pattern: re.Pattern[str], value: str, text: str) -> str:
    """Replace $var: quoted when it stands as a bare list element (after ',' or '('), raw inside strings."""

    def repl(m: re.Match[str]) -> str:
        before = text[m.start() - 1] if m.start() > 0 else ""
        return f"'{value}'" if before in ",(" else value

    return pattern.sub(repl, text)


def expand_foreach(lines: list[str]) -> list[str]:
    """Inline `foreach ($v in 'a','b') { ... }` blocks with literal lists; other loops are kept."""
    out: list[str] = []
    lines = _join_foreach_headers(lines)
    i = 0
    while i < len(lines):
        line = lines[i]
        single = re.match(r"^(\s*)foreach \(\$(\w+) in (.+?)\) \{ (.+) \}\s*$", line)
        if single:
            values = _literal_list(single.group(3))
            if values is not None:
                pattern = re.compile(r"\$" + re.escape(single.group(2)) + r"\b")
                for value in values:
                    for stmt in _split_statements(_substitute_var(pattern, value, single.group(4))):
                        out.append(single.group(1) + stmt)
                i += 1
                continue
        m = re.match(r"^(\s*)foreach \(\$(\w+) in (.+)\) \{\s*$", line)
        if m:
            var, expr = m.group(2), m.group(3)
            values = _literal_list(expr)
            depth, j, block = 1, i + 1, []
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                if depth > 0:
                    block.append(lines[j])
                j += 1
            if values is not None:
                inner = expand_foreach(block)
                pattern = re.compile(r"\$" + re.escape(var) + r"\b")
                for value in values:
                    out.extend(_substitute_var(pattern, value, b) for b in inner)
                i = j
                continue
        out.append(line)
        i += 1
    return out


class _Scanner:
    def __init__(self) -> None:
        self.vars: dict[str, str] = {}
        self.stack: list[list[object]] = []  # [depth_after_open, skip]
        self.depth = 0

    def skipping(self) -> bool:
        return any(entry[1] for entry in self.stack)

    def interpolate(self, text: str) -> str | None:
        def repl(m: re.Match[str]) -> str:
            return self.vars.get(m.group(1), m.group(0))

        result = re.sub(r"\$(\w+)", repl, text)
        return None if "$" in result else result

    def expr(self, token: str) -> str | None:
        token = token.strip()
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1]
        if token.startswith('"') and token.endswith('"'):
            return self.interpolate(token[1:-1])
        if token.startswith("$"):
            return self.interpolate(token)
        return token

    def value(self, token: str) -> object | None:
        token = token.strip()
        if token in KNOWN_EXPR:
            return KNOWN_EXPR[token]
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        m = re.fullmatch(r"\$Config\.(\w+)", token)
        if m:
            return CONFIG_VALUES.get(m.group(1))
        return self.expr(token)

    def feed(self, line: str) -> list[Action]:
        stripped = line.strip()
        opens, closes = line.count("{"), line.count("}")
        result: list[Action] = []
        if re.fullmatch(r"\} else \{", stripped):
            if self.stack and self.stack[-1][0] == self.depth:
                self.stack[-1][1] = not self.stack[-1][1] if self.stack[-1][2] == "config" else True
            return result
        if re.fullmatch(r"\} catch \{.*", stripped) and opens == closes:
            if self.stack and self.stack[-1][0] == self.depth:
                self.stack[-1][1] = True
            return result
        m = re.match(r"^\s*\$(\w+)\s*=\s*('[^']*'|\"[^\"]*\")\s*$", line)
        if m and not self.skipping():
            value = self.expr(m.group(2))
            if value is not None:
                self.vars[m.group(1)] = value
        one_line_if = re.match(r"^if \((\$Config\.\w+)\) \{ (.+) \}$", stripped)
        if one_line_if and opens == closes:
            if not self.skipping() and not any(f in one_line_if.group(1) for f in CONFIG_FALSE):
                for stmt in _split_statements(one_line_if.group(2)):
                    result.extend(self._actions(stmt))
            return result
        if not self.skipping():
            result.extend(self._actions(stripped))
        net = opens - closes
        if net > 0:
            skip, kind = True, "dynamic"
            cond = re.match(r"^if \((.*)\) \{$", stripped)
            if cond:
                c = cond.group(1)
                if c.startswith("$Config."):
                    kind, skip = "config", any(f in c for f in CONFIG_FALSE)
                elif c == "$loaded":
                    kind, skip = "config", False
            elif stripped == "try {":
                kind, skip = "try", False
            self.depth += net
            self.stack.append([self.depth, skip, kind])
        elif net < 0:
            self.depth += net
            while self.stack and self.stack[-1][0] > self.depth:
                self.stack.pop()
        return result

    def _actions(self, s: str) -> list[Action]:
        out: list[Action] = []
        m = re.match(r"^Set-Reg -Path (\S+|\"[^\"]*\"|'[^']*') -Name (\S+|'[^']*') -Type (\w+) -Value (.+?)(?: -Why .*)?$", s)
        if m:
            path, name, value = self.expr(m.group(1)), self.expr(m.group(2)), self.value(m.group(4))
            if path is not None and name is not None and value is not None:
                out.append(("reg", path.lower(), name.lower(), m.group(3), str(value)))
            return out
        m = re.match(r"^Remove-Reg -Path (\S+|\"[^\"]*\"|'[^']*') -Name (\S+|'[^']*')$", s)
        if m:
            path, name = self.expr(m.group(1)), self.expr(m.group(2))
            if path is not None and name is not None:
                out.append(("reg-remove", path.lower(), name.lower()))
            return out
        m = re.match(r"^Set-ServiceStart -Name (\S+|'[^']*') -Start (\d)$", s)
        if m:
            name = self.expr(m.group(1))
            if name is not None:
                out.append(("service", name.lower(), int(m.group(2))))
            return out
        m = re.match(r"^Invoke-Exe '([^']+)' @\((.*)\)$", s)
        if m:
            args = re.findall(r"'([^']*)'|\"([^\"]*)\"", m.group(2))
            flat = [a or b for a, b in args]
            if "$" not in m.group(2):
                out.append(("exe", m.group(1).lower(), tuple(flat)))
            return out
        return out


def parse_asr_rules(script: str) -> list[Action]:
    block = re.search(r"\$AsrRules = @\{(.*?)\n\}", script, re.S)
    if not block:
        return []
    path = r"hklm:\software\policies\microsoft\windows defender\windows defender exploit guard\asr\rules"
    out: list[Action] = []
    for line in block.group(1).splitlines():
        if line.strip().startswith("#"):
            continue
        m = re.match(r"\s*'([0-9a-f-]{36})'\s*=\s*(\d+)", line)
        if m:
            out.append(("reg", path, m.group(1), "String", m.group(2)))
    return out


def parse_v02_actions(source: Path | str) -> set[Action]:
    """Actions of Setup-System.ps1 embedded in an answer file (a path or the XML text itself)."""
    text = source.read_text(encoding="utf-8") if isinstance(source, Path) else source
    return parse_script_actions(extract_script(text, "Setup-System.ps1"))


def parse_script_actions(script: str) -> set[Action]:
    """Normalised actions of a Setup-System.ps1 text (v0.2 or a WinKickOff build)."""
    return set(parse_script_actions_ordered(script))


def parse_script_actions_ordered(script: str) -> list[Action]:
    """The same actions in the order the script performs them, first occurrence only.
    ASR rules of v0.2 come from the $AsrRules table and are listed at the end."""
    lines = expand_foreach(script.splitlines())
    scanner = _Scanner()
    actions: list[Action] = []
    seen: set[Action] = set()
    for line in lines:
        for action in scanner.feed(line):
            if action[0] in ("reg", "reg-remove") and any(f in action[1] for f in INFRASTRUCTURE_PATH_FRAGMENTS):
                continue
            if action not in seen:
                seen.add(action)
                actions.append(action)
    for action in parse_asr_rules(script):
        if action not in seen:
            seen.add(action)
            actions.append(action)
    return actions


def catalog_actions(catalog: object, profile: object, du_prefix: str = "hku:\\unattenddefault\\") -> set[Action]:
    """Expand enabled catalog rules into the same normalised tuples."""
    out: set[Action] = set()
    for rule in catalog.rules.values():  # type: ignore[attr-defined]
        if profile.is_enabled(rule.id):  # type: ignore[attr-defined]
            out |= rule_actions(catalog, profile, rule, du_prefix)
    return out


def rule_actions(catalog: object, profile: object, rule: object, du_prefix: str = "hku:\\unattenddefault\\") -> set[Action]:
    """Normalised tuples of one rule with the parameter values of the profile."""
    from winkickoff.core.render import substitute

    out: set[Action] = set()
    params = profile.params_for(catalog, rule.id)  # type: ignore[attr-defined]
    for action in rule.actions:  # type: ignore[attr-defined]
        f = {k: substitute(v, params) for k, v in action.fields.items()}
        if action.type in ("reg", "reg-remove"):
            path = str(f["path"]).lower()
            if path.startswith("du:\\"):
                path = du_prefix + path[4:]
            if action.type == "reg":
                out.add(("reg", path, str(f["name"]).lower(), str(f["kind"]), str(f["value"])))
            else:
                out.add(("reg-remove", path, str(f["name"]).lower()))
        elif action.type == "service":
            out.add(("service", str(f["name"]).lower(), int(f["start"])))
        elif action.type == "exe":
            out.add(("exe", str(f["file"]).lower(), tuple(str(a) for a in f["args"])))
    return out
