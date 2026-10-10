"""Reading the settings of a running Windows into a profile (task T25, 1.4.0): cloning a reference PC, or studying a
damaged or infected one.

The read is the read-only audit of core/apply.py (Audit.runtime.ps1) over every rule that can be checked on a running
Windows, built-in and imported, plus the data forms (templates/section-read-system.ps1). Nothing on the computer
changes. The new profile starts as a copy of the open one, so that the rules no running Windows can show (installation
only, first sign-in, steps that cannot be checked) keep their state; every rule the audit could read takes the state
of the computer:

- in effect (every check matches) is on, with the parameter values read from the computer: a parameter whose value
  is written whole by a registry action ("{seconds}") takes the value found there when it is a valid value of the
  parameter;
- partly in effect is off and listed, so that a person decides; not in effect is off;
- an imported policy whose values an enabled built-in rule already writes stays off (the built-in rule covers it).

The values read are data of that computer: on a damaged or infected PC they may be anything. They are checked like any
profile (core/validate.py) before a build.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.apply import _audit_path, audit_rules, parse_audit_report, render_audit
from winkickoff.core.catalog import Catalog, Param, Rule, is_imported
from winkickoff.core.i18n import tr
from winkickoff.core.profile import Account, Profile, one_line
from winkickoff.core.render import EDITION_KEYS
from winkickoff.core.resources import PAIR_RE, find_keyboard

# EditionID of HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion to the editions of render.EDITION_KEYS
EDITION_IDS = {
    "Professional": "Pro", "ProfessionalN": "Pro N", "ProfessionalWorkstation": "Pro for Workstations",
    "ProfessionalWorkstationN": "Pro for Workstations N", "ProfessionalEducation": "Pro Education",
    "ProfessionalEducationN": "Pro Education N", "Education": "Education", "EducationN": "Education N",
    "Enterprise": "Enterprise", "EnterpriseN": "Enterprise N", "EnterpriseG": "Enterprise G", "EnterpriseGN": "Enterprise G N",
    "EnterpriseS": "Enterprise LTSC 2024 / 2021 / 2019", "EnterpriseSN": "Enterprise N LTSC",
}
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{4})?(-[A-Z]{2})?$")
_PLACEHOLDER = re.compile(r"^\{([a-z_][a-z0-9_]*)\}$")
TRANSIENT_LCID = "2000"  # a language without a numeric code (ru-UA): Windows gives it this id for the session only
MAX_TEXT = 256  # characters of a text read from the computer that a profile keeps (names, descriptions)


@dataclass
class CaptureSummary:
    """What the read found, for the message list of the window and for MCP."""

    computer: str = ""
    admin: bool = False
    time: str = ""
    in_effect: list[str] = field(default_factory=list)  # rules now on
    partly: list[str] = field(default_factory=list)  # rules off because only some of their values match
    not_in_effect: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)  # the audit could not read them: their state is the open profile's
    kept: list[str] = field(default_factory=list)  # no running Windows shows them: their state is the open profile's
    covered: list[str] = field(default_factory=list)  # imported policies left off: a built-in rule writes their values
    params: list[tuple[str, str, Any]] = field(default_factory=list)  # (rule, parameter, value read)
    forms: list[str] = field(default_factory=list)  # the profile fields taken from the computer (install.time_zone, ...)
    notes: list[str] = field(default_factory=list)  # translated remarks
    differs: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # rule: its checks that do not match
    system: dict[str, Any] = field(default_factory=dict)  # what the data forms section read (no passwords, no keys)


def capture_rules(catalog: Catalog) -> tuple[list[str], list[tuple[Rule, str]]]:
    """Every rule of the catalog that a running Windows can show, and the others with the reason."""
    return audit_rules(catalog, [f"r:{rule_id}" for rule_id in catalog.order])


def render_capture(catalog: Catalog, profile: Profile, templates_dir: Path, app_version: str = "0.0.0") -> str:
    """The read-only script: the audit of every rule it can check and the data forms."""
    rule_ids, _ = capture_rules(catalog)
    return render_audit(rule_ids, profile, catalog, templates_dir, app_version, read_system=True)


# --------------------------------------------------------------------------- parameters


def _param_value(param: Param, text: str) -> Any:
    """The value of a parameter that a registry value read as text stands for, or None."""
    if param.type == "int":
        try:
            value = int(text)
        except ValueError:
            return None
        if (param.min is not None and value < param.min) or (param.max is not None and value > param.max):
            return None
        return value
    if param.type == "enum":
        for option, _title in param.values:
            if str(option) == text or (isinstance(option, int) and not isinstance(option, bool) and text.lstrip("-").isdigit()
                                       and int(text) == option):
                return option
        return None
    if param.type == "string":
        return text if len(text) <= 4096 and "\n" not in text else None
    return None  # bool and list parameters of imported policies are not read back


def _same(param: Param, value: Any, text: str) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return text.lstrip("-").isdigit() and int(text) == value
    return str(value) == text


def read_rule(rule: Rule, checks: list[dict[str, str]], params: dict[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    """The status of a rule (applied, partial, not-applied, unknown) with the parameter values read from the checks of the
    audit and the status of each check after that; params are the values the audit compared with (the open profile)."""
    by_check: dict[str, dict[str, str]] = {}
    for check in checks:
        by_check.setdefault(check.get("check", ""), check)
    statuses = [check.get("status", "unknown") for check in checks]
    read: dict[str, Any] = {}
    for action in rule.actions:
        if action.type != "reg" or action.fields.get("literal"):
            continue
        whole = _PLACEHOLDER.match(str(action.fields.get("value", "")))
        if not whole or whole.group(1) not in rule.params:
            continue
        name = whole.group(1)
        param = rule.params[name]
        key = f"{_audit_path(str(action.fields['path']))[0]}\\{action.fields['name']}"
        check = by_check.get(key)
        if check is None or check.get("status") not in ("ok", "differs") or check.get("current", "") == "":
            continue
        text = check["current"]
        if name not in read:
            value = _param_value(param, text)
            if value is None:
                continue
            read[name] = value
        index = checks.index(check)
        statuses[index] = "ok" if _same(param, read[name], text) else "differs"
    known = set(statuses) - {"unknown"}
    if not known:
        status = "unknown"
    elif known == {"ok"}:
        status = "applied"
    elif "ok" in known:
        status = "partial"
    else:
        status = "not-applied"
    return status, {**params, **read}, statuses


# --------------------------------------------------------------------------- data forms


def _text(value: Any) -> str:
    return one_line(str(value or ""))[:MAX_TEXT]


def _input_items(entries: Any, keyboards: list[dict[str, Any]]) -> list[str]:
    """The input languages of the profile for the language list of the user (Get-WinUserLanguageList)."""
    items: list[str] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        tag = str(entry.get("tag") or "")
        tips = entry.get("tips") if isinstance(entry.get("tips"), list) else []
        found = False
        for tip in (str(t) for t in tips):
            pair = tip.split("{", 1)[0].upper()  # an IME tip adds {profile}{CLSID}: only keyboard layouts are kept
            if not PAIR_RE.match(pair) or pair.split(":")[0] == TRANSIENT_LCID:
                continue
            first = find_keyboard(keyboards, tag) if tag else None
            item = tag if first and f"{first.get('lcid')}:{first.get('klid')}".upper() == pair else pair
            if item not in items:
                items.append(item)
            found = True
        if not found and tag and find_keyboard(keyboards, tag) is not None and tag not in items:
            items.append(tag)  # a language without a numeric code, such as ru-UA
    return items


def _forms(profile: Profile, system: Any, keyboards: list[dict[str, Any]], summary: CaptureSummary) -> None:
    if not isinstance(system, dict):
        summary.notes.append(tr("The data forms were not read; they stay as in the open profile."))
        return
    summary.system = {key: _text(system.get(key)) for key in ("computer_name", "edition_id", "build", "display_version",
                                                               "time_zone", "ui_language", "system_locale", "user_locale")}
    summary.system["input"] = [_text(entry.get("tag")) for entry in system.get("input") or [] if isinstance(entry, dict)]
    summary.system["accounts"] = [{"name": _text(entry.get("name")), "group": _text(entry.get("group"))}
                                  for entry in system.get("accounts") or [] if isinstance(entry, dict)]
    edition = EDITION_IDS.get(str(system.get("edition_id") or ""))
    if edition in EDITION_KEYS:
        profile.install["edition"] = edition
        summary.forms.append("install.edition")
    elif system.get("edition_id"):
        summary.notes.append(tr("Edition {0} of this PC has no generic key in WinKickOff; the edition of the open profile stays.",
                                _text(system.get("edition_id"))))
    zone = _text(system.get("time_zone"))
    if zone:
        profile.install["time_zone"] = zone
        summary.forms.append("install.time_zone")
    for key in ("ui_language", "system_locale", "user_locale"):
        value = _text(system.get(key))
        if _LOCALE.match(value):
            profile.languages[key] = value
            summary.forms.append(f"languages.{key}")
    inputs = _input_items(system.get("input"), keyboards)
    if inputs:
        profile.languages["input"] = inputs
        summary.forms.append("languages.input")
    accounts = []
    for entry in system.get("accounts") if isinstance(system.get("accounts"), list) else []:
        if isinstance(entry, dict) and _text(entry.get("name")):
            name = _text(entry.get("name"))
            accounts.append(Account(name, _text(entry.get("full_name")) or name,
                                    "Administrators" if entry.get("group") == "Administrators" else "Users",
                                    _text(entry.get("description")), ""))
    if any(a.group == "Administrators" for a in accounts):
        profile.accounts = accounts
        profile.install["account_mode"] = "file"
        summary.forms.append("accounts")
        summary.notes.append(tr("The accounts of this PC were read without their passwords; set the passwords in the form "
                                "if they are needed."))
    elif accounts or system.get("accounts_error"):
        summary.notes.append(tr("The local accounts were not read completely; the accounts of the open profile stay."))
    name = _text(system.get("computer_name"))
    if name:
        summary.notes.append(tr("This PC is named {0}; the computer name of the profile stays as it was, so that the "
                                "computers installed from it do not share one name.", name))


# --------------------------------------------------------------------------- the profile


def capture_profile(catalog: Catalog, base: Profile, report_text: str,
                    keyboards: list[dict[str, Any]]) -> tuple[Profile, CaptureSummary]:
    """A new profile with the state of the computer of the report (render_capture), starting from base. Raises ValueError
    for a report that is not one."""
    try:
        meta, results = parse_audit_report(report_text)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(tr("The report of the read is damaged: {0}", str(exc)[:200])) from exc
    summary = CaptureSummary(computer=_text(meta.get("computer")), admin=str(meta.get("admin")).lower() == "true",
                             time=_text(meta.get("time")))
    profile = base.copy()
    profile.path = None
    rule_ids, skipped = capture_rules(catalog)
    summary.kept = [rule.id for rule, _reason in skipped]
    for rule_id in rule_ids:
        rule = catalog.rules[rule_id]
        result = results.get(rule_id)
        if result is None:
            summary.unknown.append(rule_id)
            continue
        status, params, statuses = read_rule(rule, result.checks, base.params_for(catalog, rule_id))
        if status in ("partial", "not-applied"):
            summary.differs[rule_id] = [check for check, verdict in zip(result.checks, statuses) if verdict == "differs"]
        state = profile.rules[rule_id]
        if status == "unknown":
            summary.unknown.append(rule_id)
            continue
        state.enabled = status == "applied"
        if status == "applied":
            summary.in_effect.append(rule_id)
            for name, value in params.items():
                if name in rule.params and value != rule.params[name].default:
                    state.params[name] = value
                elif name in state.params and value == rule.params[name].default:
                    del state.params[name]
            summary.params += [(rule_id, name, value) for name, value in params.items()
                               if name in rule.params and value != base.params_for(catalog, rule_id).get(name)]
        elif status == "partial":
            summary.partly.append(rule_id)
        else:
            summary.not_in_effect.append(rule_id)
    for rule_id in list(summary.in_effect):  # an imported policy that an enabled built-in rule writes stays off
        if is_imported(rule_id) and any(profile.is_enabled(other) and not is_imported(other)
                                        for other in catalog.same_values(rule_id)):
            profile.rules[rule_id].enabled = False
            summary.in_effect.remove(rule_id)
            summary.covered.append(rule_id)
    _forms(profile, meta.get("system"), keyboards, summary)
    if not summary.admin:
        summary.notes.append(tr("The read ran without administrator rights: optional features, capabilities and the apps of "
                                "other users could not be read, so their rules keep the state of the open profile."))
    when = summary.time.replace("T", " ")
    profile.name = one_line(tr("Settings of {0}", summary.computer or tr("this PC")))
    profile.comment = tr("Read from {0} on {1} by WinKickOff; rules that a running Windows cannot show keep the state of "
                         "profile \"{2}\".", summary.computer or tr("this PC"), when, tr(base.name))
    return profile, summary


def summary_lines(summary: CaptureSummary, title: Any) -> list[tuple[str, str, str]]:
    """(level, target, message) for the message list; title(rule_id) gives the title of a rule."""
    lines = [("info", "profile", tr("Read from {0}: in effect {1}, partly {2}, not in effect {3}, not readable {4}, kept from "
                                    "the open profile {5}.", summary.computer, len(summary.in_effect), len(summary.partly),
                                    len(summary.not_in_effect), len(summary.unknown), len(summary.kept)))]
    lines += [("warning", rule_id, tr("Partly in effect on this PC, so it is off in the new profile: \"{0}\"", title(rule_id)))
              for rule_id in summary.partly]
    lines += [("info", rule_id, tr("Parameter {0} read from this PC: {1}", name, value)) for rule_id, name, value in summary.params]
    lines += [("info", rule_id, tr("Off: an enabled built-in rule writes the same values")) for rule_id in summary.covered]
    lines += [("info", "profile", note) for note in summary.notes]
    if summary.forms:
        lines.append(("info", "profile", tr("Data forms read from this PC: {0}", ", ".join(summary.forms))))
    return lines
