"""Read the effective actions of an answer file's scripts back into normalised tuples.

Used by the importer (a hand-written file such as v0.2, or a WinKickOff build without its embedded
profile) and by the semantic golden tests. Only what the script does unconditionally or under
conditions that can be evaluated statically is extracted:

- `$Config` switches are read from the script itself and `if ($Config.X)`, `if ($Config.X -gt 0)`,
  `$(if ($Config.X) { a } else { b })` are evaluated with those values;
- literal `foreach ($v in 'a','b')` loops are unrolled; other loops and `catch` blocks are skipped;
- loops over literal hashtables (`$AsrRules`, the audit subcategories) are unrolled;
- the v0.2 list `$AppsToRemove` counts only when an active line loops over it.

Tuples (all names and paths lower case, except the items of a list):
    ("reg", path, name, kind, value) ("reg-remove", path, name) ("service", name, start)
    ("exe", file, args) ("appx", name) ("feature", name, state) ("capability", pattern)
    ("reg-list", path, kind, ((value name, data), ...), additive)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from winkickoff.core.catalog import Catalog, Rule
from winkickoff.core.profile import Profile
from winkickoff.core.render import RenderError, list_entries, substitute_fields

Action = tuple[Any, ...]
DU_PREFIX = "hku:\\unattenddefault\\"
INFRASTRUCTURE_PATH_FRAGMENTS = ("active setup",)  # written by the runtime, not by rules
_COMPARE = {"-gt": lambda a, b: a > b, "-ge": lambda a, b: a >= b, "-lt": lambda a, b: a < b,
            "-le": lambda a, b: a <= b, "-eq": lambda a, b: a == b, "-ne": lambda a, b: a != b}
_LIST = r"@\((?:'(?:[^']|'')*'(?:,'(?:[^']|'')*')*)?\)"  # @('a','b''c') as rendered by ps_quote
# -Path of a registry function: ($du + '\...') now, "$du\..." in older builds, or a quoted or bare literal
_PATH = r"(\(\$\w+ \+ '(?:[^']|'')*'\)|\S+|\"[^\"]*\"|'[^']*')"
_JOINED = re.compile(r"\(\$(\w+) \+ '((?:[^']|'')*)'\)")


def extract_script(xml_text: str, name: str) -> str:
    """Text of an embedded script (<File path="...\\name"><![CDATA[...]]>)."""
    match = re.search(rf'{re.escape(name)}"><!\[CDATA\[(.*?)\]\]>', xml_text, re.S)
    if not match:
        raise ValueError(f"script {name} not found")
    return match.group(1)


def parse_config(script: str) -> dict[str, Any]:
    """Values of the v0.2 `$Config = @{ Name = value }` block; empty when the script has none."""
    block = re.search(r"\$Config = @\{(.*?)\n\}", script, re.S)
    config: dict[str, Any] = {}
    if not block:
        return config
    for line in block.group(1).splitlines():
        match = re.match(r"^\s*(\w+)\s*=\s*(\$true|\$false|-?\d+|'[^']*')", line)
        if not match:
            continue
        raw = match.group(2)
        config[match.group(1)] = True if raw == "$true" else False if raw == "$false" else int(raw) if raw.lstrip("-").isdigit() else raw[1:-1]
    return config


# --------------------------------------------------------------------------- loops


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


def parse_tables(lines: list[str]) -> dict[str, list[tuple[str, str, bool]]]:
    """Literal hashtables `$name = @{ 'key' = 'value' or number }` as (key, value, is_number) lists."""
    tables: dict[str, list[tuple[str, str, bool]]] = {}
    i = 0
    while i < len(lines):
        head = re.match(r"^\s*\$(\w+) = @\{\s*$", lines[i])
        if head:
            entries: list[tuple[str, str, bool]] = []
            j = i + 1
            while j < len(lines) and not re.match(r"^\s*\}\s*$", lines[j]):
                m = re.match(r"^\s*'([^']+)'\s*=\s*(?:'([^']*)'|(-?\d+))", lines[j])
                if m:
                    entries.append((m.group(1), m.group(2) if m.group(3) is None else m.group(3), m.group(3) is not None))
                j += 1
            tables[head.group(1)] = entries
            i = j
        i += 1
    return tables


def _substitute_entry(var: str, key: str, value: str, is_number: bool, text: str) -> str:
    """$($v.Key) inside strings becomes the raw key; $v.Key as a token becomes a quoted literal."""
    quoted_value = value if is_number else f"'{value}'"
    text = text.replace(f"$(${var}.Key)", key).replace(f"$(${var}.Value)", value)
    text = text.replace(f"([string]${var}.Value)", f"'{value}'").replace(f"([int]${var}.Value)", value if is_number else "0")
    text = re.sub(r"\$" + re.escape(var) + r"\.Key\b", f"'{key}'", text)
    return re.sub(r"\$" + re.escape(var) + r"\.Value\b", quoted_value, text)


def expand_foreach(lines: list[str], tables: dict[str, list[tuple[str, str, bool]]] | None = None) -> list[str]:
    """Inline `foreach ($v in 'a','b') { ... }` and `foreach ($v in $table.GetEnumerator()) { ... }`
    blocks over literal lists and hashtables; other loops are kept."""
    out: list[str] = []
    lines = _join_foreach_headers(lines)
    tables = parse_tables(lines) if tables is None else tables
    i = 0
    while i < len(lines):
        line = lines[i]
        enum = re.match(r"^(\s*)foreach \(\$(\w+) in \$(\w+)\.GetEnumerator\(\)\) \{\s*$", line)
        if enum and enum.group(3) in tables:
            depth, j, block = 1, i + 1, []
            while j < len(lines) and depth > 0:
                depth += lines[j].count("{") - lines[j].count("}")
                if depth > 0:
                    block.append(lines[j])
                j += 1
            inner = expand_foreach(block, tables)
            for key, value, is_number in tables[enum.group(3)]:
                out.extend(_substitute_entry(enum.group(2), key, value, is_number, b) for b in inner)
            i = j
            continue
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
                inner = expand_foreach(block, tables)
                pattern = re.compile(r"\$" + re.escape(var) + r"\b")
                for value in values:
                    out.extend(_substitute_var(pattern, value, b) for b in inner)
                i = j
                continue
        out.append(line)
        i += 1
    return out


# --------------------------------------------------------------------------- scanner


class _Scanner:
    """Walks the unrolled script line by line, keeps simple string variables and a stack of blocks
    (active or skipped), and turns active statements into action tuples."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.vars: dict[str, str] = {}
        self.stack: list[list[Any]] = []  # [depth_after_open, skip, kind]
        self.depth = 0
        self.active_lines: list[str] = []

    def skipping(self) -> bool:
        return any(entry[1] for entry in self.stack)

    # ---- expressions

    def condition(self, text: str) -> bool | None:
        """Value of a condition over $Config, or None when it cannot be evaluated statically."""
        text = text.strip()
        m = re.fullmatch(r"\$Config\.(\w+)", text)
        if m:
            return bool(self.config.get(m.group(1)))
        m = re.fullmatch(r"\$Config\.(\w+) (-gt|-ge|-lt|-le|-eq|-ne) (-?\d+)", text)
        if m:
            value = self.config.get(m.group(1))
            return isinstance(value, int) and _COMPARE[m.group(2)](value, int(m.group(3)))
        if text == "$loaded":
            return True  # the default-user hive is loaded during setup
        return None

    def interpolate(self, text: str) -> str | None:
        def repl(m: re.Match[str]) -> str:
            return self.vars.get(m.group(1), m.group(0))

        result = re.sub(r"\$(\w+)", repl, text)
        return None if "$" in result else result

    def expr(self, token: str) -> str | None:
        token = token.strip()
        joined = _JOINED.fullmatch(token)
        if joined:
            base = self.vars.get(joined.group(1))
            return None if base is None else str(base) + joined.group(2).replace("''", "'")
        if token.startswith("'") and token.endswith("'"):
            return token[1:-1]
        if token.startswith('"') and token.endswith('"'):
            return self.interpolate(token[1:-1])
        if token.startswith("$"):
            return self.interpolate(token)
        return token

    def value(self, token: str) -> Any:
        token = token.strip()
        if re.fullmatch(r"-?\d+", token):
            return int(token)
        m = re.fullmatch(r"\$Config\.(\w+)", token)
        if m:
            return self.config.get(m.group(1))
        m = re.fullmatch(r"\(\[int\]\$Config\.(\w+)\)", token)
        if m:
            raw = self.config.get(m.group(1))
            return int(raw) if raw is not None else None
        m = re.fullmatch(r"\$\(if \((.+?)\) \{ (.+?) \} else \{ (.+?) \}\)", token)
        if m:
            cond = self.condition(m.group(1))
            return None if cond is None else self.value(m.group(2) if cond else m.group(3))
        m = re.fullmatch(r"@\(((?:'(?:[^']|'')*'\s*,?\s*)*)\)", token)
        if m:  # MultiString: @('a','b'), compared as the list the catalog holds
            return [item.replace("''", "'") for item in re.findall(r"'((?:[^']|'')*)'", m.group(1))]
        return self.expr(token)

    # ---- lines

    def feed(self, line: str) -> list[Action]:
        stripped = line.strip()
        opens, closes = line.count("{"), line.count("}")
        result: list[Action] = []
        if re.fullmatch(r"\} else \{", stripped):
            if self.stack and self.stack[-1][0] == self.depth:
                entry = self.stack[-1]
                entry[1] = (not entry[1]) if entry[2] == "config" else True
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
        one_line_if = re.match(r"^if \((.+?)\) \{ (.+) \}$", stripped)
        if one_line_if and opens == closes:
            cond = self.condition(one_line_if.group(1))
            if not self.skipping() and cond is not False:
                for stmt in _split_statements(one_line_if.group(2)):
                    self.active_lines.append(stmt)
                    # A runtime guard (if the feature is present...) still states the intent of the
                    # script for components and apps; registry writes under it stay excluded.
                    result.extend(self._actions(stmt) if cond else self._text_actions(stmt))
            return result
        if not self.skipping():
            self.active_lines.append(stripped)
            result.extend(self._actions(stripped))
        net = opens - closes
        if net > 0:
            skip, kind = True, "dynamic"
            cond_match = re.match(r"^if \((.*)\) \{$", stripped)
            if cond_match:
                cond = self.condition(cond_match.group(1))
                if cond is not None:
                    kind, skip = "config", not cond
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
        m = re.match(rf"^Set-Reg -Path {_PATH} -Name (\S+|'[^']*') -Type (\w+) -Value (.+?)(?: -Why .*)?$", s)
        if m:
            path, name, value = self.expr(m.group(1)), self.expr(m.group(2)), self.value(m.group(4))
            if path is not None and name is not None and value is not None:
                out.append(("reg", path.lower(), name.lower(), m.group(3), str(value)))
            return out
        m = re.match(rf"^Remove-Reg -Path {_PATH} -Name (\S+|'[^']*')$", s)
        if m:
            path, name = self.expr(m.group(1)), self.expr(m.group(2))
            if path is not None and name is not None:
                out.append(("reg-remove", path.lower(), name.lower()))
            return out
        m = re.match(rf"^Set-RegList -Path {_PATH} -Type (\w+) -Names ({_LIST}) -Values ({_LIST})( -Additive)?$", s)
        if m:
            path, names, values = self.expr(m.group(1)), self.value(m.group(3)), self.value(m.group(4))
            if path is not None and isinstance(names, list) and isinstance(values, list):
                out.append(("reg-list", path.lower(), m.group(2), tuple(zip(names, values)), bool(m.group(5))))
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
            if "$" not in m.group(2):
                out.append(("exe", m.group(1).lower(), tuple(a or b for a, b in args)))
            return out
        m = re.match(r"^Remove-Apps @\((.*)\)$", s)
        if m:
            return [("appx", name.lower()) for name in re.findall(r"'([^']+)'", m.group(1))]
        m = re.match(r"^Set-Feature -Name '([^']+)' -State (\w+)$", s)
        if m:
            return [("feature", m.group(1).lower(), m.group(2))]
        m = re.match(r"^Remove-Capability -Pattern '([^']+)'$", s)
        if m:
            return [("capability", m.group(1).lower())]
        return self._text_actions(s)

    @staticmethod
    def _text_actions(s: str) -> list[Action]:
        """Components and apps written as plain cmdlets (the v0.2 style)."""
        out: list[Action] = []
        for m in re.finditer(r"(Disable|Enable)-WindowsOptionalFeature -Online -FeatureName '?([\w.-]+)'?", s):
            out.append(("feature", m.group(2).lower(), "Disabled" if m.group(1) == "Disable" else "Enabled"))
        for m in re.finditer(r"Get-WindowsCapability -Online -Name '([^']+)'", s):
            out.append(("capability", m.group(1).lower()))
        if "Get-AppxProvisionedPackage" in s:
            out.extend(("appx", m.group(1).lower()) for m in re.finditer(r"DisplayName -eq '([^']+)'", s))
        return out


APP_LIST_NAMES = ("AppsToRemove",)  # v0.2 arrays of app names removed by a foreach loop


def parse_app_lists(script: str) -> dict[str, list[str]]:
    """Literal arrays of app names: `$AppsToRemove = @( 'Name' ... )`."""
    lists: dict[str, list[str]] = {}
    for name in APP_LIST_NAMES:
        block = re.search(rf"\${name} = @\((.*?)\n\)", script, re.S)
        if block:
            lists[name] = [m.group(1) for m in (re.match(r"\s*'([^']+)'", line) for line in block.group(1).splitlines()) if m]
    return lists


@dataclass
class ScriptActions:
    actions: list[Action]  # in the order the script performs them, first occurrence only
    active_text: str  # every statement in an active block, one per line (for ps signatures)
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def action_set(self) -> set[Action]:
        return set(self.actions)


def parse_script(script: str) -> ScriptActions:
    config = parse_config(script)
    scanner = _Scanner(config)
    actions: list[Action] = []
    seen: set[Action] = set()

    def add(action: Action) -> None:
        if action[0] in ("reg", "reg-remove") and any(f in action[1] for f in INFRASTRUCTURE_PATH_FRAGMENTS):
            return
        if action not in seen:
            seen.add(action)
            actions.append(action)

    app_lists = parse_app_lists(script)
    for line in expand_foreach(script.splitlines()):
        active_before = not scanner.skipping()
        for action in scanner.feed(line):
            add(action)
        loop = re.match(r"^\s*foreach \(\$\w+ in \$(\w+)\) \{", line)
        if active_before and loop and loop.group(1) in app_lists:
            for name in app_lists[loop.group(1)]:  # the apps are removed here, in list order
                add(("appx", name.lower()))
    return ScriptActions(actions, "\n".join(scanner.active_lines), config)


# --------------------------------------------------------------------------- catalog side


def rule_actions(catalog: Catalog, profile: Profile, rule: Rule, du_prefix: str = DU_PREFIX) -> set[Action]:
    """Tuples of one rule with the parameter values of the profile (script actions only)."""
    out: set[Action] = set()
    params = profile.params_for(catalog, rule.id)
    for action in rule.actions:
        f = substitute_fields(action.fields, params)
        t = action.type
        if t in ("reg", "reg-remove"):
            path = str(f["path"]).lower()
            if path.startswith("du:\\"):
                path = du_prefix + path[4:]
            if t == "reg":
                out.add(("reg", path, str(f["name"]).lower(), str(f["kind"]), str(int(f["value"]) if isinstance(f["value"], bool) else f["value"])))
            else:
                out.add(("reg-remove", path, str(f["name"]).lower()))
        elif t == "reg-list":
            path = str(f["path"]).lower()
            if path.startswith("du:\\"):
                path = du_prefix + path[4:]
            try:
                entries = tuple(list_entries(f))
            except RenderError:
                continue  # an invalid list in the profile matches nothing
            out.add(("reg-list", path, str(f["kind"]), entries, bool(f.get("additive"))))
        elif t == "service":
            out.add(("service", str(f["name"]).lower(), int(f["start"])))
        elif t == "exe":
            out.add(("exe", str(f["file"]).lower(), tuple(str(a) for a in f["args"])))
        elif t == "appx":
            out.update(("appx", str(n).lower()) for n in f["names"])
        elif t == "feature":
            out.add(("feature", str(f["name"]).lower(), str(f["state"])))
        elif t == "capability":
            out.add(("capability", str(f["pattern"]).lower()))
    return out


def catalog_actions(catalog: Catalog, profile: Profile, du_prefix: str = DU_PREFIX) -> set[Action]:
    """Tuples of every enabled rule of the profile."""
    out: set[Action] = set()
    for rule in catalog.rules.values():
        if profile.is_enabled(rule.id):
            out |= rule_actions(catalog, profile, rule, du_prefix)
    return out
