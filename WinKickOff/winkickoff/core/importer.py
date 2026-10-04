"""Import a profile from an answer file.

1. A file built by WinKickOff carries its profile in Extensions/Profile: that JSON is read as is.
2. Any other file of the same family (the hand-written v0.2, or a build whose profile was removed)
   is imported by its actions: the scripts are parsed (core/actions_parser.py), the XML passes are
   read, and every catalog rule is enabled when all of its checkable actions are present.
   Rules whose presence cannot be decided (only PowerShell fragments that differ in wording) keep
   the catalog default and are listed in the warnings.
"""

from __future__ import annotations

import ast
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from winkickoff.core.actions_parser import ScriptActions, extract_script, parse_script, rule_actions
from winkickoff.core.catalog import Action, Catalog, Rule
from winkickoff.core.profile import Account, Profile
from winkickoff.core.render import ASK_KEY, EDITION_KEYS, substitute_fields
from winkickoff.core.resources import PAIR_RE, find_keyboard
from winkickoff.core.i18n import tr

EXT = "{urn:workgroup-unattend}"
U = "{urn:schemas-microsoft-com:unattend}"
SCRIPT_NAMES = ("Setup-System.ps1", "Setup-User.ps1", "Post-OOBE.ps1")
IMPORTED_NAME = "Imported from XML"  # name of a profile restored by actions; the UI replaces it with the file name


class ImportFailed(ValueError):
    pass


def import_xml(text: str, catalog: Catalog, keyboards: list[dict[str, Any]] | None = None) -> tuple[Profile, list[str]]:
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as exc:
        raise ImportFailed(tr("the file is not valid XML: {0}", exc)) from exc
    if root.tag != f"{U}unattend":
        raise ImportFailed(tr("this is not a Windows answer file: the root element is not unattend"))
    element = root.find(f"{EXT}Extensions/{EXT}Profile")
    if element is not None and (element.text or "").strip():
        try:
            data = json.loads(element.text or "")
        except json.JSONDecodeError as exc:
            raise ImportFailed(tr("the embedded profile is corrupted: {0}", exc)) from exc
        if not isinstance(data, dict):
            raise ImportFailed(tr("the embedded profile must be a JSON object"))
        profile, warnings = Profile.from_dict(data, catalog)
        profile.path = None
        return profile, warnings
    return import_by_actions(root, text, catalog, keyboards or [])


# --------------------------------------------------------------------------- import by actions


@dataclass
class _Facts:
    """What the answer file does, collected once."""

    script: ScriptActions | None
    texts: str  # active text of Setup-System plus the full other scripts, one statement per line
    pe_commands: set[str] = field(default_factory=set)
    specialize_commands: set[str] = field(default_factory=set)
    oobe: dict[str, str] = field(default_factory=dict)


def _normalise(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _first_component(root: ET.Element, pass_name: str, component: str) -> ET.Element | None:
    for settings in root.findall(f"{U}settings"):
        if settings.get("pass") != pass_name:
            continue
        for comp in settings.findall(f"{U}component"):
            if comp.get("name") == component:
                return comp
    return None


def _commands(root: ET.Element, pass_name: str) -> set[str]:
    out: set[str] = set()
    for settings in root.findall(f"{U}settings"):
        if settings.get("pass") == pass_name:
            out.update((cmd.findtext(f"{U}Path") or "").strip() for cmd in settings.iter(f"{U}RunSynchronousCommand"))
    return out


def _collect(root: ET.Element, text: str) -> _Facts:
    scripts: dict[str, str] = {}
    for name in SCRIPT_NAMES:
        try:
            scripts[name] = extract_script(text, name)
        except ValueError:
            continue
    parsed = parse_script(scripts["Setup-System.ps1"]) if "Setup-System.ps1" in scripts else None
    texts = "\n".join(
        [parsed.active_text if parsed else ""] + [body for name, body in scripts.items() if name != "Setup-System.ps1"]
    )
    facts = _Facts(parsed, _normalise(texts))
    facts.pe_commands = _commands(root, "windowsPE")
    facts.specialize_commands = _commands(root, "specialize")
    shell = _first_component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
    oobe = shell.find(f"{U}OOBE") if shell is not None else None
    if oobe is not None:
        facts.oobe = {child.tag.replace(U, ""): (child.text or "").strip() for child in oobe}
    return facts


def _ps_signature(script: str) -> str:
    """The longest statement of a fragment: distinctive enough to find it in another script."""
    lines = [line for line in _normalise(script).splitlines() if not line.startswith("#") and len(line) > 12]
    return max(lines, key=len) if lines else ""


def _list_items(action: Action, entries: tuple[tuple[str, str], ...]) -> list[str]:
    """The parameter value of a list read back from its (value name, data) pairs."""
    if action.fields.get("explicit"):
        return [f"{name}={data}" for name, data in entries]
    return [data for _, data in entries]


def _infer_params(rule: Rule, profile: Profile, catalog: Catalog, found: set[tuple[Any, ...]]) -> None:
    """A registry value or a list of values that is exactly a parameter ("{seconds}") is read back from the file."""
    index = {(a[1], a[2]): a[4] for a in found if a[0] == "reg"}
    lists = {(a[1], a[2], a[4]): a[3] for a in found if a[0] == "reg-list"}
    for action in rule.actions:
        if action.type not in ("reg", "reg-list"):
            continue
        value = action.fields.get("value")
        match = re.fullmatch(r"\{([a-z_][a-z0-9_]*)\}", str(value))
        if not match or match.group(1) not in rule.params:
            continue
        path = str(action.fields["path"]).lower()
        if path.startswith("du:\\"):
            path = "hku:\\unattenddefault\\" + path[4:]
        param = rule.params[match.group(1)]
        if action.type == "reg-list":
            entries = lists.get((path, str(action.fields["kind"]), bool(action.fields.get("additive"))))
            items = _list_items(action, entries) if entries is not None else None
            if items is not None and items != param.default:
                profile.rules[rule.id].params[param.name] = items
            continue
        raw = index.get((path, str(action.fields["name"]).lower()))
        if raw is None:
            continue
        converted: Any = raw
        if param.type == "list":  # a MultiString value, kept as the text of a Python list
            try:
                converted = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                converted = None
            if not isinstance(converted, list) or not all(isinstance(item, str) for item in converted):
                converted = None
        elif param.type == "int":
            converted = int(raw) if str(raw).lstrip("-").isdigit() else None
        elif param.type == "bool":
            converted = str(raw) in ("1", "True", "true")
        elif param.type == "enum":
            converted = next((v for v, _ in param.values if str(v) == str(raw)), None)
        if converted is not None and converted != param.default:
            profile.rules[rule.id].params[param.name] = converted


def _rule_evidence(rule: Rule, profile: Profile, catalog: Catalog, facts: _Facts) -> list[bool]:
    """One entry per checkable action: present in the file or not. PowerShell fragments count only
    when found (absence of a fragment written differently proves nothing)."""
    found = facts.script.action_set if facts.script else set()
    evidence = [a in found for a in rule_actions(catalog, profile, rule)]
    params = profile.params_for(catalog, rule.id)
    for action in rule.actions:
        f = substitute_fields(action.fields, params)
        if action.type == "xml-pe-command":
            evidence.append(str(f["command"]).strip() in facts.pe_commands)
        elif action.type == "xml-specialize-command":
            evidence.append(str(f["command"]).strip() in facts.specialize_commands)
        elif action.type == "xml-oobe":
            evidence.append(facts.oobe.get(str(f["element"])) == str(f["value"]))
        elif action.type == "ps":
            signature = _ps_signature(str(f["script"]))
            if signature and signature in facts.texts:
                evidence.append(True)
    return evidence


def import_by_actions(root: ET.Element, text: str, catalog: Catalog, keyboards: list[dict[str, Any]]) -> tuple[Profile, list[str]]:
    facts = _collect(root, text)
    profile = Profile.from_catalog(catalog, name=IMPORTED_NAME)
    warnings: list[str] = []
    undecided: list[str] = []
    partial: list[str] = []
    found = facts.script.action_set if facts.script else set()
    for rule in catalog.rules.values():
        _infer_params(rule, profile, catalog, found)
        evidence = _rule_evidence(rule, profile, catalog, facts)
        if not evidence:
            undecided.append(rule.id)
            continue
        if all(evidence):
            profile.rules[rule.id].enabled = True
        else:
            profile.rules[rule.id].enabled = False
            profile.rules[rule.id].params.clear()
            if any(evidence):
                partial.append(tr("{0} ({1} of {2})", rule.id, sum(evidence), len(evidence)))
    enabled = len(profile.enabled_ids())
    warnings.append(
        tr("Profile restored from the file's actions: {0} of {1} rules enabled. Check the result (F7) before building.", enabled, len(catalog.rules))
    )
    if partial:
        warnings.append(tr("Rules disabled because not all of their actions were found: ") + ", ".join(partial))
    if undecided:
        warnings.append(tr("Could not be determined from the file, left as in the catalog: ") + ", ".join(undecided))
    _import_install(root, profile, warnings)
    _import_languages(root, text, profile, keyboards, warnings)
    _import_accounts(root, profile)
    return profile, warnings


# --------------------------------------------------------------------------- install data


def _import_install(root: ET.Element, profile: Profile, warnings: list[str]) -> None:
    setup = _first_component(root, "windowsPE", "Microsoft-Windows-Setup")
    key_node = setup.find(f"{U}UserData/{U}ProductKey") if setup is not None else None
    if key_node is not None:
        key = (key_node.findtext(f"{U}Key") or "").strip().upper()
        show_ui = (key_node.findtext(f"{U}WillShowUI") or "").strip()
        editions = {v: k for k, v in EDITION_KEYS.items()}
        if key in editions:
            profile.install.update(edition=editions[key], product_key_mode="generic", product_key="")
        elif key == ASK_KEY or show_ui == "Always" or not key:
            profile.install.update(product_key_mode="ask", product_key="")
        else:
            profile.install.update(product_key_mode="custom", product_key=key)
            warnings.append(tr("The file contains a custom product key: the edition cannot be determined from the key, Pro is kept"))
    for pass_name in ("specialize", "oobeSystem"):
        shell = _first_component(root, pass_name, "Microsoft-Windows-Shell-Setup")
        zone = shell.findtext(f"{U}TimeZone") if shell is not None else None
        if zone and zone.strip():
            profile.install["time_zone"] = zone.strip()
            break


def _script_input_languages(text: str) -> list[str]:
    """Input languages as Setup-User.ps1 applies them: the WinKickOff list or the v0.2 calls."""
    try:
        script = extract_script(text, "Setup-User.ps1")
    except ValueError:
        return []
    m = re.search(r"\$InputLanguages = @\(([^)]*)\)", script)
    if m:
        return re.findall(r"'([^']+)'", m.group(1))
    m = re.search(r"New-WinUserLanguageList '([^']+)'", script)
    if not m:
        return []
    tags = [m.group(1)]
    for line in script[m.end():].splitlines()[1:]:
        added = re.match(r"\s*\$list\.Add\('([^']+)'\)", line)
        if added:
            tags.append(added.group(1))
        elif "Set-WinUserLanguageList" in line:
            break
    return tags


def _import_languages(root: ET.Element, text: str, profile: Profile, keyboards: list[dict[str, Any]], warnings: list[str]) -> None:
    intl = _first_component(root, "oobeSystem", "Microsoft-Windows-International-Core")
    if intl is not None:
        for key, element in (("ui_language", "UILanguage"), ("system_locale", "SystemLocale"), ("user_locale", "UserLocale")):
            value = (intl.findtext(f"{U}{element}") or "").strip()
            if value:
                profile.languages[key] = value
    tags = _script_input_languages(text)
    if tags and (not keyboards or all(find_keyboard(keyboards, t) is not None for t in tags)):
        profile.languages["input"] = tags
        return
    pairs = [p for p in ((intl.findtext(f"{U}InputLocale") if intl is not None else "") or "").split(";") if p.strip()]
    items: list[str] = []
    for pair in pairs:
        entry = find_keyboard(keyboards, pair.strip()) if PAIR_RE.match(pair.strip()) else None
        items.append(str(entry["tag"]) if entry and entry.get("tag") and find_keyboard(keyboards, str(entry["tag"])) is entry else pair.strip())
    if items:
        profile.languages["input"] = items
        warnings.append(tr("Input languages were taken from InputLocale: temporary languages (for example \"Russian (Ukraine)\") cannot be restored this way"))


def _import_accounts(root: ET.Element, profile: Profile) -> None:
    shell = _first_component(root, "oobeSystem", "Microsoft-Windows-Shell-Setup")
    if shell is None:
        return
    accounts = []
    for node in shell.iter(f"{U}LocalAccount"):
        name = (node.findtext(f"{U}Name") or "").strip()
        if not name:
            continue
        accounts.append(Account(
            name=name,
            display_name=(node.findtext(f"{U}DisplayName") or name).strip(),
            group=(node.findtext(f"{U}Group") or "Users").strip(),
            description=(node.findtext(f"{U}Description") or "").strip(),
            password=(node.findtext(f"{U}Password/{U}Value") or ""),
        ))
    if accounts:
        profile.accounts = accounts
