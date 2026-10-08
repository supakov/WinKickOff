"""Validation of profiles and of built answer files.

Profile checks catch what the user can get wrong in the editor; XML checks repeat the hard limits
of Windows Setup (a violation aborts the install with 0x80220005) and mirror tools/Validate-Unattend.ps1.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from winkickoff.core import jsonfile
from winkickoff.core.admx import safe_name
from winkickoff.core.catalog import Catalog, CatalogError, heading_anchors, is_imported, load_catalog
from winkickoff.core.i18n import N_, catalog_texts, tr
from winkickoff.core.profile import ACCOUNT_MODES, Profile
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import find_keyboard
from winkickoff.core.verify import rollback_steps, verify_steps

RESERVED_ACCOUNT_NAMES = frozenset(
    {"administrator", "guest", "defaultaccount", "wdagutilityaccount", "system", "local service", "network service"}
)
_BAD_NAME_CHARS = re.compile(r'[\\/\[\]:;|=,+*?<>"@]')
_KEY_RE = re.compile(r"^[A-Z0-9]{5}(-[A-Z0-9]{5}){4}$")
_CONTROL_RE = re.compile("[" + chr(0) + "-" + chr(31) + chr(127) + "]")  # not allowed inside the scripts and XML
_LOCALE_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{4})?(-[A-Z]{2})?$")
_INPUT_LOCALE_ITEM = re.compile(r"^([0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}|[a-z]{2,3}(-[A-Za-z]{2,4})?(-[A-Z]{2})?)$")
U = "{urn:schemas-microsoft-com:unattend}"
EXT = "{urn:workgroup-unattend}"
MAX_PATH = 259
MAX_LIST_ITEM = 4096  # characters of one item of a list parameter
DEVICE_ENCRYPTION_RULE = "encryption.prevent-auto-bitlocker"


@dataclass(frozen=True)
class Issue:
    level: str  # error | warning | info
    target: str  # rule id, profile field (install.x, languages.x, accounts[i]) or "xml"
    message: str
    doc: str = ""


def has_errors(issues: list[Issue]) -> bool:
    return any(i.level == "error" for i in issues)


# --------------------------------------------------------------------------- profile


def check_account_name(name: str) -> str | None:
    """Reason why a local account name is invalid, or None."""
    if not name.strip():
        return tr("the name is empty")
    if len(name) > 20:
        return tr("longer than 20 characters")
    if _BAD_NAME_CHARS.search(name):
        return tr("contains invalid characters")
    if name.lower() in RESERVED_ACCOUNT_NAMES:
        return tr("reserved Windows name")
    if name.strip(". ") != name:
        return tr("cannot begin or end with a period or space")
    return None


# Rules that the mode "Windows Setup asks for the account" relies on: without them OOBE shows the Microsoft account
# screens (when online) or may stop at the network screen.
ASK_MODE_RULES = (
    ("oobe.hide-online-account", N_("Windows Setup asks for the account, but \"{0}\" is off: when the PC is online, "
                                    "Setup asks for a Microsoft account")),
    ("install.bypass-nro", N_("Windows Setup asks for the account, but \"{0}\" is off: without a network, Setup may stop "
                              "at the network screen")),
)


def validate_accounts(profile: Profile) -> list[Issue]:
    issues: list[Issue] = []
    mode = profile.install.get("account_mode", "file")
    if mode not in ACCOUNT_MODES:
        return [Issue("error", "accounts", tr("Unknown account mode '{0}'", mode))]
    if mode == "ask":
        return [Issue("info", "accounts", tr(
            "Windows Setup will ask for the name of one account, which becomes an administrator; the accounts of the "
            "form are not written into the file"))]
    seen: set[str] = set()
    for index, account in enumerate(profile.accounts):
        target = f"accounts[{index}]"
        reason = check_account_name(account.name)
        if reason:
            issues.append(Issue("error", target, tr("Account '{0}': {1}", account.name, reason)))
        if account.name.lower() in seen:
            issues.append(Issue("error", target, tr("Account '{0}' is duplicated", account.name)))
        seen.add(account.name.lower())
        if account.group not in ("Administrators", "Users"):
            issues.append(Issue("error", target, tr("Group '{0}' is not allowed (Administrators or Users)", account.group)))
        if account.password:
            issues.append(Issue("warning", target, tr("Password '{0}' will be written to the XML in plain text; keep the file secret", account.name)))
    if not any(a.group == "Administrators" for a in profile.accounts):
        issues.append(Issue("error", "accounts", tr("At least one account in the Administrators group is required")))
    return issues


def list_problem(value: Any, pairs: bool = False) -> str | None:
    """Why the items of a list parameter cannot be written into a script, or None. Every item is a line of text
    without control characters or "]]>"; with pairs every item is "name=value" with a safe, unique name."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return tr("must be a list of lines")
    names: set[str] = set()
    for number, item in enumerate(value, start=1):
        if not item.strip():
            return tr("line {0} is empty", number)
        if _CONTROL_RE.search(item) or "]]>" in item or len(item) > MAX_LIST_ITEM:
            return tr("line {0} is longer than {1} characters or contains characters that cannot be written into the script",
                      number, MAX_LIST_ITEM)
        if pairs:
            name, sep, _ = item.partition("=")
            name = name.strip()
            if not sep or not name:
                return tr("line {0} must be written as name=value", number)
            if not safe_name(name):
                return tr("line {0}: the name {1} contains characters that are not allowed in a value name", number, name)
            if name.lower() in names:
                return tr("line {0}: the name {1} is used twice", number, name)
            names.add(name.lower())
    return None


def check_param(rule: Any, param: Any, value: Any) -> str | None:
    """Why a parameter value is not acceptable (text in the interface language), or None."""
    title = catalog_texts().param(rule, param)
    if param.type == "list":
        problem = list_problem(value, param.pairs)
        if problem:
            return tr("'{0}': {1}", title, problem)
        if param.required and not value:
            return tr("'{0}' cannot be empty", title)
        return None
    if param.type == "int":
        if not isinstance(value, int) or isinstance(value, bool):
            return tr("'{0}' must be an integer", title)
        if param.min is not None and value < param.min or param.max is not None and value > param.max:
            return tr("'{0}' is out of range {1}..{2}", title, param.min, param.max)
    elif param.type == "enum":
        if value not in {v for v, _ in param.values}:
            return tr("'{0}': invalid value {1!r}", title, value)
    elif param.type == "bool":
        if not isinstance(value, bool):
            return tr("'{0}' must be yes or no", title)
    elif param.type == "string" and param.required and not str(value).strip():
        return tr("'{0}' cannot be empty", title)
    elif param.type == "string" and (_CONTROL_RE.search(str(value)) or "]]>" in str(value)):
        return tr("'{0}' contains characters that cannot be written into the script", title)
    return None


def validate_profile(profile: Profile, catalog: Catalog, keyboards: list[dict[str, Any]] | None = None) -> list[Issue]:
    issues = validate_accounts(profile)

    edition = profile.install.get("edition")
    mode = profile.install.get("product_key_mode")
    if mode not in ("generic", "custom", "ask"):
        issues.append(Issue("error", "install.product_key_mode", tr("Unknown key mode '{0}'", mode)))
    if mode == "generic" and edition not in EDITION_KEYS:
        issues.append(Issue("error", "install.edition", tr("Edition '{0}' has no generic key", edition)))
    if mode == "custom" and not _KEY_RE.match(str(profile.install.get("product_key", "")).strip().upper()):
        issues.append(Issue("error", "install.product_key", tr("The product key must be in the format XXXXX-XXXXX-XXXXX-XXXXX-XXXXX")))
    if not str(profile.install.get("time_zone", "")).strip():
        issues.append(Issue("error", "install.time_zone", tr("Time zone is not set")))

    for key, title in (("ui_language", tr("Display language")), ("system_locale", tr("Language for non-Unicode programs")), ("user_locale", tr("Date and number format"))):
        value = str(profile.languages.get(key, ""))
        if not _LOCALE_RE.match(value):
            issues.append(Issue("error", f"languages.{key}", tr("{0}: '{1}' does not look like a language tag such as uk-UA", title, value)))
    inputs = [str(i) for i in (profile.languages.get("input") or [])]
    if not inputs:
        issues.append(Issue("error", "languages.input", tr("At least one input language is required")))
    if len(set(inputs)) != len(inputs):
        issues.append(Issue("warning", "languages.input", tr("Duplicate input languages")))
    if keyboards is not None:
        for item in inputs:
            if find_keyboard(keyboards, item) is None:
                issues.append(Issue("error", "languages.input", tr("Unknown input language '{0}'", item)))

    for rule in catalog.rules.values():
        title = catalog_texts().rule(rule, "title")
        enabled = profile.is_enabled(rule.id)
        for pname, param in rule.params.items():
            if is_imported(rule.id) and not enabled:
                continue  # an imported policy without a check mark is not configured: its values do not matter
            problem = check_param(rule, param, profile.param(catalog, rule.id, pname))
            if problem:
                issues.append(Issue("error", rule.id, tr("\"{0}\": {1}", title, problem), rule.doc))
            elif param.differs_from is not None:
                value = profile.param(catalog, rule.id, pname)
                if value == profile.param(catalog, rule.id, param.differs_from) and value not in param.same_allowed:
                    texts = catalog_texts()
                    issues.append(Issue("error", rule.id, tr(
                        "\"{0}\": \"{1}\" and \"{2}\" cannot have the same value", title, texts.param(rule, param),
                        texts.param(rule, rule.params[param.differs_from])), rule.doc))
        if enabled:
            for req in rule.requires:
                if not profile.is_enabled(req):
                    issues.append(Issue("error", rule.id, tr("\"{0}\" is enabled but requires \"{1}\", which is disabled", title, catalog_texts().rule(catalog.rules[req], "title")), rule.doc))
            for other in rule.conflicts:
                if profile.is_enabled(other):
                    issues.append(Issue("error", rule.id, tr("\"{0}\" conflicts with \"{1}\", which is enabled", title, catalog_texts().rule(catalog.rules[other], "title")), rule.doc))
            if rule.level == "risky":
                issues.append(Issue("warning", rule.id, tr("Risky rule \"{0}\" is enabled: {1}", title, catalog_texts().rule(rule, "risk") or catalog_texts().rule(rule, "effect")), rule.doc))
            if is_imported(rule.id):
                for other in catalog.same_values(rule.id):
                    if profile.is_enabled(other):
                        issues.append(Issue("warning", rule.id, tr(
                            "Imported policy \"{0}\" sets the same registry value as the built-in rule \"{1}\", and both are "
                            "on: the value is written twice and the one applied later wins. Keep one of them.",
                            title, catalog_texts().rule(catalog.rules[other], "title"))))
        elif rule.level == "baseline":
            issues.append(Issue("warning", rule.id, tr("Baseline rule \"{0}\" is disabled", title), rule.doc))
    if profile.asks_for_account():
        for rule_id, text in ASK_MODE_RULES:
            if rule_id in catalog.rules and not profile.is_enabled(rule_id):
                issues.append(Issue("warning", rule_id, tr(text, catalog_texts().rule(catalog.rules[rule_id], "title"))))
    if profile.install.get("product_key_mode") == "ask":
        issues.append(Issue("info", "install.product_key_mode", tr(
            "The edition is chosen during installation: Setup shows the product key page, and \"I don't have a product "
            "key\" opens the list of editions. The protection of WinKickOff is made for Pro: on Home, deferred feature "
            "updates and BitLocker do not work, and some Copilot and Recall policies are not supported.")))
    encryption = catalog.rules.get(DEVICE_ENCRYPTION_RULE)
    if encryption is not None and not profile.is_enabled(encryption.id):
        issues.append(Issue("warning", encryption.id, tr(
            "Automatic device encryption is allowed: Windows may encrypt the system drive on its own, "
            "and with local accounts the recovery key is not saved anywhere. Right after installation, "
            "check Get-BitLockerVolume C: and store the key (manage-bde -protectors -get C:) away from "
            "the computer; otherwise the data will be lost if the TPM fails or the motherboard is "
            "replaced."), encryption.doc))
    issues.extend(Issue("error", target, tr(HALF_CHARACTER)) for target in half_characters(profile, catalog))
    if profile.unknown:
        issues.append(Issue("info", "profile", tr("The profile contains rules that are not in the catalog: ") + ", ".join(sorted(profile.unknown))))
    return issues


HALF_CHARACTER = N_("A text holds half of a character, left when an emoji or another character of two halves is deleted "
                    "in part; type the text again")


def _has_half(value: Any) -> bool:
    if isinstance(value, str):
        return jsonfile.has_surrogate(value)
    if isinstance(value, (list, tuple)):
        return any(_has_half(item) for item in value)
    if isinstance(value, dict):
        return any(_has_half(item) for item in value.values())
    return False


def half_characters(profile: Profile, catalog: Catalog) -> list[str]:
    """The places (Issue targets) whose texts hold a lone surrogate: it cannot be written as UTF-8 and the embedded
    profile would not read back. Choices the build never uses (unknown, imported policies off) do not count."""
    targets = ["profile"] if _has_half([profile.name, profile.author, profile.comment]) else []
    targets += [f"install.{key}" for key, value in profile.install.items() if _has_half(value)]
    targets += [f"languages.{key}" for key, value in profile.languages.items() if _has_half(value)]
    targets += [f"accounts[{index}]" for index, account in enumerate(profile.accounts) if _has_half(account.to_dict())]
    targets += [rule_id for rule_id, state in profile.rules.items()
                if rule_id in catalog.rules and (state.enabled or not is_imported(rule_id)) and _has_half(state.params)]
    return targets


# --------------------------------------------------------------------------- xml


def _text(element: ET.Element | None) -> str:
    return (element.text or "").strip() if element is not None else ""


# --------------------------------------------------------------------------- catalog


def validate_catalog(rules_dir: Path, docs_root: Path | None) -> tuple[Catalog | None, list[Issue]]:
    """Reload the catalog from disk (command "Check rule catalog"). Loader defects are errors; gaps in
    the descriptions are warnings: every rule must say how to check it and how to undo it, either
    in its own text or through steps derived from its actions (core/verify.py)."""
    try:
        catalog = load_catalog(rules_dir, docs_root=docs_root)
    except CatalogError as exc:
        return None, [Issue("error", exc.rule_id or "catalog", tr("The catalog cannot be loaded: {0}", exc))]
    issues: list[Issue] = []
    anchors: dict[Path, set[str]] = {}
    for rule in catalog.rules.values():
        params = {name: param.default for name, param in rule.params.items()}
        if not rule.verify and not verify_steps(rule, params):
            issues.append(Issue("warning", rule.id, tr("\"{0}\": no check text, and it cannot be derived from the actions", rule.title), rule.doc))
        if not rule.rollback and not rollback_steps(rule, params):
            issues.append(Issue("warning", rule.id, tr("\"{0}\": no rollback text, and it cannot be derived from the actions", rule.title), rule.doc))
        if rule.level == "risky" and not rule.risk:
            issues.append(Issue("warning", rule.id, tr("\"{0}\": risky rule with no risk description", rule.title), rule.doc))
        if docs_root is not None and "#" in rule.doc:
            file_part, anchor = rule.doc.split("#", 1)
            path = docs_root / file_part
            if path not in anchors:
                anchors[path] = heading_anchors(path.read_text(encoding="utf-8"))
            if anchor not in anchors[path]:
                issues.append(Issue("warning", rule.id, tr("\"{0}\": {1} has no heading for link #{2}", rule.title, file_part, anchor), rule.doc))
    for group_id in catalog.groups:
        if not catalog.rules_in_group(group_id):
            issues.append(Issue("info", "catalog", tr("Group {0} has no rules", group_id)))
    return catalog, issues


def validate_xml(text: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
        root = ET.fromstring(text.encode("utf-8"), parser=parser)
    except ET.ParseError as exc:
        return [Issue("error", "xml", tr("XML cannot be parsed: {0}", exc))]
    if root.tag != f"{U}unattend":
        issues.append(Issue("error", "xml", tr("The root element is not unattend in the Microsoft namespace")))

    for component in root.iter(f"{U}component"):
        name = component.get("name", "?")
        if any(node.tag is ET.Comment for node in component.iter()):
            issues.append(Issue("error", "xml", tr("Comment inside component {0}: Windows Setup will reject the file", name)))

    for sync in root.iter(f"{U}RunSynchronous"):
        orders = [_text(cmd.find(f"{U}Order")) for cmd in sync.findall(f"{U}RunSynchronousCommand")]
        if len(set(orders)) != len(orders):
            issues.append(Issue("error", "xml", tr("Duplicate Order values in RunSynchronous")))
    for cmd in root.iter(f"{U}RunSynchronousCommand"):
        path = _text(cmd.find(f"{U}Path"))
        description = _text(cmd.find(f"{U}Description"))
        if not path:
            issues.append(Issue("error", "xml", tr("Empty Path in RunSynchronousCommand")))
        elif len(path) > MAX_PATH:
            issues.append(Issue("error", "xml", tr("Command is longer than {0} characters ({1}): {2}...", MAX_PATH, len(path), path[:60])))
        if len(description) > MAX_PATH:
            issues.append(Issue("error", "xml", tr("Description is longer than {0} characters", MAX_PATH)))

    for settings in root.findall(f"{U}settings"):
        if settings.get("pass") != "oobeSystem":
            continue
        for component in settings.findall(f"{U}component"):
            arch = component.get("processorArchitecture", "?")
            if component.get("name") == "Microsoft-Windows-International-Core":
                for field in ("InputLocale", "SystemLocale", "UILanguage", "UserLocale"):
                    if not _text(component.find(f"{U}{field}")):
                        issues.append(Issue("error", "xml", tr("International-Core ({0}): {1} is not set; Windows Setup will show the language screen", arch, field)))
                for item in _text(component.find(f"{U}InputLocale")).split(";"):
                    if item and not _INPUT_LOCALE_ITEM.match(item):
                        issues.append(Issue("error", "xml", tr("InputLocale ({0}): invalid item '{1}'", arch, item)))
            if component.get("name") == "Microsoft-Windows-Shell-Setup":
                groups = [_text(g) for g in component.iter(f"{U}Group")]
                if any(True for _ in component.iter(f"{U}LocalAccount")) and "Administrators" not in groups:
                    issues.append(Issue("error", "xml", tr("LocalAccounts ({0}): no account in the Administrators group", arch)))

    extensions = root.find(f"{EXT}Extensions")
    files = extensions.findall(f"{EXT}File") if extensions is not None else []
    commands = " ".join(_text(c.find(f"{U}Path")) for c in root.iter(f"{U}RunSynchronousCommand"))
    if "Extensions.ExtractScript" in commands and not files:
        issues.append(Issue("error", "xml", tr("The script extraction command is present, but there are no embedded scripts")))
    names = {f.get("path", "").rsplit("\\", 1)[-1] for f in files}
    if "Setup-System.ps1" in commands and "Setup-System.ps1" not in names:
        issues.append(Issue("error", "xml", tr("The command that runs Setup-System.ps1 is present, but the script itself is missing")))
    for f in files:
        body = (f.text or "").strip()
        name = f.get("path", "?").rsplit("\\", 1)[-1]
        if not body:
            issues.append(Issue("error", "xml", tr("Script {0} is empty", name)))
        elif not re.search(r"(?m)^\s*exit 0\s*$", body):
            issues.append(Issue("error", "xml", tr("Script {0} does not end with 'exit 0'", name)))
    return issues
