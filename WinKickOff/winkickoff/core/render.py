"""Rendering: catalog actions to PowerShell lines, and the whole answer file from a profile.

The answer file contains only enabled rules. Phases map to places in the file:

  windowspe          RunSynchronous of Microsoft-Windows-Setup (windowsPE pass)
  specialize-xml     RunSynchronous of Microsoft-Windows-Deployment, between script extraction
                     and the start of Setup-System.ps1
  specialize         blocks of Setup-System.ps1
  default-user       blocks inside the mounted default-user hive in Setup-System.ps1
  user-first-logon   blocks of Setup-User.ps1 (Active Setup is registered only if there are any)
  post-oobe          blocks of Post-OOBE.ps1 (its scheduled task is registered only if there are any)
  oobe-xml           elements of <OOBE> in the oobeSystem pass

Everything the generator writes by itself (header, block markers, embedded profile) is ASCII.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from winkickoff.core.catalog import PLACEHOLDER_FIELDS, Action, Catalog, Rule
from winkickoff.core.deps import Resolver
from winkickoff.core.profile import Profile
from winkickoff.core.resources import find_keyboard

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_SLOT_RE = re.compile(r"\{\{([a-z_]+)\}\}")

EDITION_KEYS: dict[str, str] = {
    # Generic installation keys: they select the edition and do not activate Windows.
    "Pro":                                "VK7JG-NPHTM-C97JM-9MPGT-3V66T",
    "Enterprise":                         "NPPR9-FWDCX-D2C8J-H872K-2YT43",
    "Education":                          "YNMGQ-8RYV3-4PGQ3-C8XTP-7CFBY",
    "Pro N":                              "MH37W-N47XK-V7XM9-C7227-GCQG9",
    "Pro for Workstations":               "NRG8B-VKK3Q-CXVCJ-9G2XF-6Q84J",
    "Pro for Workstations N":             "9FNHH-K3HBT-3W4TD-6383H-6XYWF",
    "Pro Education":                      "6TP4R-GNPTD-KYYHQ-7B7DP-J447Y",
    "Pro Education N":                    "YVWGF-BXNMC-HTQYQ-CPQ99-66QFC",
    "Education N":                        "2WH4N-8QGBV-H22JP-CT43Q-MDWWJ",
    "Enterprise N":                       "DPH2V-TTNVB-4X9Q3-TJR4H-KHJW4",
    "Enterprise G":                       "YYVX9-NTFWV-6MDM3-9PT4T-4M68B",
    "Enterprise G N":                     "44RPN-FTY23-9VTTB-MP9BX-T84FV",
    "Enterprise LTSC 2024 / 2021 / 2019": "M7XTQ-FN8P6-TTKYV-9D4CC-J462D",
    "Enterprise N LTSC":                  "92NFX-8DJQP-P6BBQ-THF9C-7CG2H",
}
ASK_KEY = "00000-00000-00000-00000-00000"
ARCHITECTURES: tuple[str, ...] = ("amd64", "arm64")
SCRIPTS_DIR = "C:\\ProgramData\\Unattend\\Scripts"
SCRIPT_ORDER: tuple[str, ...] = ("Setup-System.ps1", "Setup-User.ps1", "Post-OOBE.ps1")

EXTRACT_COMMAND = (
    'powershell.exe -NoProfile -WindowStyle Hidden -Command "try{$x=[xml]::new();'
    "$x.Load('C:\\Windows\\Panther\\unattend.xml');$s=[scriptblock]::Create($x.unattend.Extensions.ExtractScript);"
    'icm $s -Args $x}catch{$_>C:\\Windows\\Temp\\ua.err};exit 0"'
)
RUN_SYSTEM_COMMAND = (
    'powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "try{'
    "$p='C:\\ProgramData\\Unattend\\Scripts\\Setup-System.ps1';if(Test-Path $p){& $p}"
    "else{'no script'>C:\\Windows\\Temp\\ua.err}}catch{$_>C:\\Windows\\Temp\\ua.err};exit 0\""
)


class RenderError(ValueError):
    pass


# --------------------------------------------------------------------------- actions


# PowerShell takes the typographic single quotes for quotes too; each is doubled like the ASCII one
_PS_SINGLE_QUOTES = ("'", chr(0x2018), chr(0x2019), chr(0x201A), chr(0x201B))


def ps_quote(text: str) -> str:
    """Single-quoted PowerShell literal (the only quoting used for catalog strings)."""
    value = str(text)
    for quote in _PS_SINGLE_QUOTES:
        value = value.replace(quote, quote + quote)
    return "'" + value + "'"


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


def substitute_fields(fields: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """The fields of an action with its parameters filled in, only where placeholders belong (PLACEHOLDER_FIELDS).
    An action marked "literal" (a fixed value of an imported template) is taken as it is: braces in it are text."""
    if fields.get("literal"):
        return {key: value for key, value in fields.items() if key != "literal"}
    return {key: substitute(value, params) if key in PLACEHOLDER_FIELDS else value for key, value in fields.items()}


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
    """DU: paths are relative to the mounted default-user hive ($du in the runtime). The rest of the path is a single-
    quoted literal joined to $du, never a double-quoted string: PowerShell would expand $ and $(...) in it, and the key
    of an imported template is untrusted text."""
    if path.startswith("DU:\\"):
        return "($du + " + ps_quote(path[3:]) + ")"
    return ps_quote(path)


def list_entries(fields: dict[str, Any]) -> list[tuple[str, str]]:
    """(value name, data) of the items of a reg-list action whose parameters are substituted: "name=value" items
    with explicit names, prefix1, prefix2, ... with a prefix, otherwise the data is its own name."""
    items = fields.get("value")
    if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
        raise RenderError(f"a list of values needs a list of strings, got {items!r}")
    if fields.get("explicit"):
        pairs = [item.partition("=") for item in items]
        if any(not sep or not name.strip() for name, sep, _ in pairs):
            raise RenderError("every item of a list with explicit names is written as name=value")
        return [(name.strip(), data.strip()) for name, _, data in pairs]
    if "prefix" in fields:
        return [(f"{fields['prefix']}{number}", item) for number, item in enumerate(items, start=1)]
    return [(item, item) for item in items]


def render_list_args(fields: dict[str, Any]) -> str:
    """-Type, -Names and -Values of Set-RegList and Test-RegList; names and values pair up by position."""
    if fields.get("kind") not in ("String", "ExpandString"):
        raise RenderError(f"a list of values is String or ExpandString, got {fields.get('kind')!r}")
    entries = list_entries(fields)
    names = ",".join(ps_quote(name) for name, _ in entries)
    values = ",".join(ps_quote(data) for _, data in entries)
    return f"-Type {fields['kind']} -Names @({names}) -Values @({values})"


def render_action(action: Action, params: dict[str, Any]) -> str:
    """One action as PowerShell (script phases). XML actions are placed by the XML builder."""
    f = substitute_fields(action.fields, params)
    t = action.type
    if t == "reg":
        line = (
            f"Set-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))} "
            f"-Type {f['kind']} -Value {render_reg_value(str(f['kind']), f['value'])}"
        )
        if f.get("why"):
            line += f" -Why {ps_quote(str(f['why']))}"
        return line
    if t == "reg-remove":
        return f"Remove-Reg -Path {render_reg_path(str(f['path']))} -Name {ps_quote(str(f['name']))}"
    if t == "reg-list":
        line = f"Set-RegList -Path {render_reg_path(str(f['path']))} {render_list_args(f)}"
        return line + " -Additive" if f.get("additive") else line
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
    """The block of one enabled rule: an ASCII marker comment followed by its actions."""
    lines = [f"# [{rule.id}]"]
    for action in rule.actions:
        lines.append(render_action(action, params))
    return "\n".join(lines)


def fill(template: str, values: dict[str, str]) -> str:
    """Replace every {{slot}}; an unknown or unfilled slot is an error."""
    wanted = set(_SLOT_RE.findall(template))
    missing = wanted - set(values)
    if missing:
        raise RenderError(f"template slots without values: {sorted(missing)}")
    return _SLOT_RE.sub(lambda m: values[m.group(1)], template)


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else "" for line in text.split("\n"))


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip("\n") + "\n"


def ascii_text(text: str) -> str:
    """ASCII form of free text for comments (non-ASCII becomes \\uXXXX, '--' is not allowed in XML comments)."""
    encoded = json.dumps(str(text), ensure_ascii=True)[1:-1]
    while "--" in encoded:
        encoded = encoded.replace("--", "-")
    return encoded


# --------------------------------------------------------------------------- build


@dataclass
class Languages:
    input_locale: str
    user_tags: list[str]
    fallback_tags: list[str]
    transient_tags: list[str]


@dataclass
class BuildResult:
    xml: str  # final text with CRLF line endings, UTF-8 without BOM when written
    scripts: dict[str, str]  # file name -> script text (LF), in SCRIPT_ORDER
    rule_ids: list[str]  # enabled rules in application order
    warnings: list[str] = field(default_factory=list)


def write_answer_file(result: BuildResult, path: Path) -> None:
    """The answer file as Windows Setup reads it: UTF-8 without BOM, the CRLF text of the build as it is."""
    path.write_bytes(result.xml.encode("utf-8"))


class Renderer:
    def __init__(self, catalog: Catalog, templates_dir: Path, keyboards: list[dict[str, Any]]) -> None:
        self.catalog = catalog
        self.resolver = Resolver(catalog)
        self.templates_dir = Path(templates_dir)
        self.keyboards = keyboards

    def _template(self, name: str) -> str:
        path = self.templates_dir / name
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RenderError(f"template {name} cannot be read: {exc}") from exc

    # ----------------------------------------------------------------- languages

    def languages(self, profile: Profile) -> Languages:
        pairs: list[str] = []
        user_tags: list[str] = []
        fallback: list[str] = []
        transient: list[str] = []
        items = list(profile.languages.get("input") or [])
        if not items:
            raise RenderError("the profile has no input languages")
        for item in items:
            entry = find_keyboard(self.keyboards, str(item))
            if entry is None:
                raise RenderError(f"unknown input language '{item}'")
            if entry.get("transient"):
                base = find_keyboard(self.keyboards, str(entry.get("fallback") or ""))
                if base is None or not base.get("lcid"):
                    raise RenderError(f"input language '{item}' has no usable fallback")
                pair = f"{base['lcid']}:{base['klid']}"
                transient.append(str(entry["tag"]))
                fallback.append(str(entry["fallback"]))
            else:
                pair = f"{entry['lcid']}:{entry['klid']}"
                fallback.append(str(entry["tag"]) if entry.get("tag") else str(item))
            if entry.get("tag"):
                user_tags.append(str(entry["tag"]))
            if pair.upper() not in (p.upper() for p in pairs):
                pairs.append(pair)
        return Languages(";".join(pairs), user_tags, fallback, transient)

    # ----------------------------------------------------------------- main entry

    def build(self, profile: Profile, app_version: str = "0.0.0") -> BuildResult:
        order = self.resolver.apply_order(profile)
        rules_by_phase: dict[str, list[Rule]] = defaultdict(list)
        for rule_id in order:
            rule = self.catalog.rules[rule_id]
            rules_by_phase[rule.phase].append(rule)
        params = {rule_id: profile.params_for(self.catalog, rule_id) for rule_id in order}
        warnings: list[str] = []

        pe_commands = self._xml_commands(rules_by_phase["windowspe"], "xml-pe-command", params)
        specialize_commands = self._xml_commands(rules_by_phase["specialize-xml"], "xml-specialize-command", params)
        oobe_elements = [
            (str(a.fields["element"]), str(substitute(a.fields["value"], params[r.id])))
            for r in rules_by_phase["oobe-xml"]
            for a in r.actions
            if a.type == "xml-oobe"
        ]

        def blocks(phase: str) -> list[str]:
            return [render_block(r, params[r.id]) for r in rules_by_phase[phase]]

        system_blocks = blocks("specialize")
        default_user_blocks = blocks("default-user")
        user_blocks = blocks("user-first-logon")
        post_blocks = blocks("post-oobe")
        languages = self.languages(profile)
        label = f"WinKickOff {app_version}, catalog {self.catalog.version}, {len(order)} rules enabled"

        scripts: dict[str, str] = {}
        if system_blocks or default_user_blocks or user_blocks or post_blocks:
            scripts["Setup-System.ps1"] = self._setup_system(
                system_blocks, default_user_blocks, bool(user_blocks), bool(post_blocks), label
            )
        if user_blocks:
            scripts["Setup-User.ps1"] = self._setup_user(user_blocks, languages)
        if post_blocks:
            scripts["Post-OOBE.ps1"] = self._post_oobe(post_blocks, profile)
        for name, text in scripts.items():
            if "]]>" in text:
                raise RenderError(f"{name} contains ']]>' which cannot be placed into CDATA")

        xml = self._answer_file(profile, app_version, order, pe_commands, specialize_commands, oobe_elements, languages, scripts)
        return BuildResult(xml=xml.replace("\r\n", "\n").replace("\n", "\r\n"), scripts=scripts, rule_ids=order, warnings=warnings)

    # ----------------------------------------------------------------- scripts

    def _setup_system(self, blocks: list[str], du_blocks: list[str], has_user: bool, has_post: bool, label: str) -> str:
        du_section = ""
        if du_blocks:
            du_section = fill(self._template("section-default-user.ps1"), {"blocks": _indent("\n\n".join(du_blocks), 4)})
        text = fill(
            self._template("Setup-System.runtime.ps1"),
            {
                "build_label": label.replace("'", ""),
                "blocks": "\n\n".join(blocks),
                "default_user_section": du_section,
                "active_setup_section": self._template("section-active-setup.ps1") if has_user else "",
                "post_oobe_section": self._template("section-post-oobe-task.ps1") if has_post else "",
            },
        )
        return _tidy(text)

    def _setup_user(self, blocks: list[str], languages: Languages) -> str:
        text = fill(
            self._template("Setup-User.runtime.ps1"),
            {
                "input_languages": ",".join(ps_quote(t) for t in languages.user_tags),
                "input_fallback": ",".join(ps_quote(t) for t in languages.fallback_tags),
                "transient_languages": ",".join(ps_quote(t) for t in languages.transient_tags),
                "blocks": "\n\n".join(blocks),
            },
        )
        return _tidy(text)

    def _post_oobe(self, blocks: list[str], profile: Profile) -> str:
        text = fill(
            self._template("Post-OOBE.runtime.ps1"),
            {
                "accounts": ",".join(ps_quote(a.name) for a in profile.answer_file_accounts()),
                "blocks": "\n\n".join(blocks),
            },
        )
        return _tidy(text)

    # ----------------------------------------------------------------- xml

    def _xml_commands(self, rules: list[Rule], action_type: str, params: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for rule in rules:
            for action in rule.actions:
                if action.type == action_type:
                    out.append((str(action.fields["description"]), str(substitute(action.fields["command"], params[rule.id]))))
        return out

    @staticmethod
    def _component(name: str, arch: str) -> str:
        return (
            f'    <component name="{name}" processorArchitecture="{arch}" publicKeyToken="31bf3856ad364e35" '
            'language="neutral" versionScope="nonSxS">'
        )

    @staticmethod
    def _run_synchronous(commands: list[tuple[str, str]], indent: int) -> list[str]:
        pad = " " * indent
        lines = [f"{pad}<RunSynchronous>"]
        for order, (description, command) in enumerate(commands, start=1):
            lines += [
                f'{pad}  <RunSynchronousCommand wcm:action="add">',
                f"{pad}    <Order>{order}</Order>",
                f"{pad}    <Description>{xml_escape(description)}</Description>",
                f"{pad}    <Path>{xml_escape(command)}</Path>",
                f"{pad}  </RunSynchronousCommand>",
            ]
        lines.append(f"{pad}</RunSynchronous>")
        return lines

    def _product_key(self, profile: Profile) -> tuple[str, str]:
        mode = profile.install.get("product_key_mode", "generic")
        if mode == "ask":
            return ASK_KEY, "Always"
        if mode == "custom":
            key = str(profile.install.get("product_key", "")).strip().upper()
            if not key:
                raise RenderError("custom product key mode needs a key")
            return key, "OnError"
        edition = str(profile.install.get("edition", "Pro"))
        if edition not in EDITION_KEYS:
            raise RenderError(f"unknown edition '{edition}'")
        return EDITION_KEYS[edition], "OnError"

    def _settings(
        self,
        profile: Profile,
        pe_commands: list[tuple[str, str]],
        specialize_commands: list[tuple[str, str]],
        oobe_elements: list[tuple[str, str]],
        languages: Languages,
        scripts: dict[str, str],
    ) -> list[str]:
        key, show_ui = self._product_key(profile)
        out: list[str] = ['  <settings pass="windowsPE">']
        for arch in ARCHITECTURES:
            out.append(self._component("Microsoft-Windows-Setup", arch))
            out += [
                "      <UserData>",
                "        <ProductKey>",
                f"          <Key>{xml_escape(key)}</Key>",
                f"          <WillShowUI>{show_ui}</WillShowUI>",
                "        </ProductKey>",
                "        <AcceptEula>true</AcceptEula>",
                "      </UserData>",
            ]
            if pe_commands:
                out += self._run_synchronous(pe_commands, 6)
            out.append("    </component>")
        out.append("  </settings>")

        commands: list[tuple[str, str]] = []
        if scripts:
            commands.append(("Extract embedded scripts from this answer file", EXTRACT_COMMAND))
        commands += specialize_commands
        if "Setup-System.ps1" in scripts:
            commands.append(("Apply machine-wide settings", RUN_SYSTEM_COMMAND))
        out.append('  <settings pass="specialize">')
        for arch in ARCHITECTURES:
            if commands:
                out.append(self._component("Microsoft-Windows-Deployment", arch))
                out += self._run_synchronous(commands, 6)
                out.append("    </component>")
            out.append(self._component("Microsoft-Windows-Shell-Setup", arch))
            out.append(f"      <TimeZone>{xml_escape(str(profile.install.get('time_zone', 'UTC')))}</TimeZone>")
            out.append("    </component>")
        out.append("  </settings>")

        out.append('  <settings pass="oobeSystem">')
        for arch in ARCHITECTURES:
            out.append(self._component("Microsoft-Windows-International-Core", arch))
            out += [
                f"      <InputLocale>{xml_escape(languages.input_locale)}</InputLocale>",
                f"      <SystemLocale>{xml_escape(str(profile.languages.get('system_locale', '')))}</SystemLocale>",
                f"      <UILanguage>{xml_escape(str(profile.languages.get('ui_language', '')))}</UILanguage>",
                f"      <UserLocale>{xml_escape(str(profile.languages.get('user_locale', '')))}</UserLocale>",
                "    </component>",
            ]
            accounts = profile.answer_file_accounts()
            if oobe_elements or accounts:
                out.append(self._component("Microsoft-Windows-Shell-Setup", arch))
                if oobe_elements:
                    out.append("      <OOBE>")
                    out += [f"        <{name}>{xml_escape(value)}</{name}>" for name, value in oobe_elements]
                    out.append("      </OOBE>")
                if accounts:
                    out += ["      <UserAccounts>", "        <LocalAccounts>"]
                    for account in accounts:
                        out += [
                            '          <LocalAccount wcm:action="add">',
                            "            <Password>",
                            f"              <Value>{xml_escape(account.password)}</Value>",
                            "              <PlainText>true</PlainText>",
                            "            </Password>",
                        ]
                        if account.description:
                            out.append(f"            <Description>{xml_escape(account.description)}</Description>")
                        out += [
                            f"            <DisplayName>{xml_escape(account.display_name or account.name)}</DisplayName>",
                            f"            <Group>{xml_escape(account.group)}</Group>",
                            f"            <Name>{xml_escape(account.name)}</Name>",
                            "          </LocalAccount>",
                        ]
                    out += ["        </LocalAccounts>", "      </UserAccounts>"]
                out.append("    </component>")
        out.append("  </settings>")
        return out

    def _header(self, profile: Profile, app_version: str, order: list[str], scripts: dict[str, str]) -> str:
        lines = [
            f"    Generated by WinKickOff {app_version}, rules catalog {self.catalog.version}.",
            f"    Profile: {ascii_text(profile.name)}; modified {ascii_text(profile.modified)}.",
            f"    Enabled rules: {len(order)} of {len(self.catalog.rules)}. Disabled rules are absent from this file.",
            *(["    Accounts: none in this file; Windows Setup asks for the name of one administrator account."]
              if profile.asks_for_account() else []),
            *(["    Edition: chosen during Setup (the product key page, then \"I don't have a product key\")."]
              if profile.install.get("product_key_mode") == "ask" else []),
            "    The profile is embedded in Extensions/Profile and can be opened again in WinKickOff.",
            "",
            "    Hard limits of Windows Setup respected by this file (a violation aborts the install",
            '    with "The provided unattend file is not valid", 0x80220005):',
            "      - RunSynchronousCommand/Path is 259 characters or shorter;",
            "      - no XML comments inside <component> blocks;",
            "      - every synchronous command exits with code 0.",
        ]
        if scripts:
            lines += ["", "    Post-install artefacts:"]
            lines += [f"      {SCRIPTS_DIR}\\{name}" for name in scripts]
            lines.append("      C:\\ProgramData\\Unattend\\Logs\\*.log")
        return "\n".join(lines)

    def _answer_file(
        self,
        profile: Profile,
        app_version: str,
        order: list[str],
        pe_commands: list[tuple[str, str]],
        specialize_commands: list[tuple[str, str]],
        oobe_elements: list[tuple[str, str]],
        languages: Languages,
        scripts: dict[str, str],
    ) -> str:
        files: list[str] = []
        for name in SCRIPT_ORDER:
            if name in scripts:
                files += [f'    <File path="{SCRIPTS_DIR}\\{name}"><![CDATA[', scripts[name].rstrip("\n"), "]]></File>"]
        data = profile.to_dict(self.catalog)
        if profile.asks_for_account():  # Setup creates none of these accounts: their passwords stay out of the file
            for account in data["accounts"]:
                account["password"] = ""
        profile_json = json.dumps(data, ensure_ascii=True, indent=1)
        profile_json = profile_json.replace("]]>", "]]" + chr(92) + "u003e")  # JSON escape of '>' keeps CDATA valid
        return fill(
            self._template("autounattend.template.xml"),
            {
                "header": self._header(profile, app_version, order, scripts),
                "settings": "\n".join(self._settings(profile, pe_commands, specialize_commands, oobe_elements, languages, scripts)),
                "files": "\n".join(files),
                "profile_json": profile_json,
            },
        )
