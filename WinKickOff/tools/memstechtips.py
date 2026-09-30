"""The memstechtips preset: the original UnattendedWinstall answer file mapped onto the catalog (issue #2).

The original (docs/appendices/A-unattendedwinstall/autounattend.xml, by memstechtips) is parsed into
normalised actions: Set-RegistryValue and Remove-RegistryValue calls of its scripts (HKCU values of its
per-user part are compared with the default-user rules), registry commands of the windowsPE and specialize
passes, OOBE elements, the lists of removed apps, capabilities and optional features and the list of
disabled scheduled tasks.

A catalog rule is enabled when the original contains at least one of its checkable actions and none of its
actions contradicts the original (the same registry value, service or OOBE element with another value).
A rule required by an enabled rule is enabled too unless it contradicts the original. Actions an enabled
rule adds beyond the original, contradictions and everything the original does that no rule covers are
listed in docs/technical/memstechtips-profile.md. Rules made of PowerShell steps only cannot be matched.

Used by tools/make_presets.py; tests/test_presets.py checks that the preset and the report are current.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from winkickoff.core.actions_parser import DU_PREFIX, rule_actions
from winkickoff.core.catalog import Catalog, Rule
from winkickoff.core.i18n import CatalogTexts
from winkickoff.core.importer import _infer_params
from winkickoff.core.profile import Profile
from winkickoff.core.render import substitute

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT.parent / "docs" / "appendices" / "A-unattendedwinstall" / "autounattend.xml"
REPORT = ROOT.parent / "docs" / "technical" / "memstechtips-profile.md"
U = "{urn:schemas-microsoft-com:unattend}"
SQ = r"'((?:[^']|'')*)'"
SET_RE = re.compile(r"Set-RegistryValue -Path " + SQ + r" -Name " + SQ + r" -Type '(\w+)' -Value (" + SQ + r"|@\([^)]*\)|\S+)(?: -Description " + SQ + ")?")
REMOVE_RE = re.compile(r"Remove-RegistryValue -Path " + SQ + r" -Name " + SQ + r"(?: -Description " + SQ + ")?")
REMOVE_KEY_RE = re.compile(r"Remove-RegistryKey -Path " + SQ + r"(?: -Description " + SQ + ")?")
REG_ADD_RE = re.compile(r'reg(?:\.exe)? add "([^"]+)" /v (\S+) /t (REG_\w+) /d (\S+)', re.I)
KIND = {"REG_DWORD": "DWord", "REG_SZ": "String", "REG_QWORD": "QWord", "REG_EXPAND_SZ": "ExpandString"}
# values of the original that have the same effect as the catalog's value on Windows 11 Pro
# (empty since 28.09.2026: the diagnostic data level of privacy.telemetry-minimal became a parameter, so the
# original's AllowTelemetry = 0 now maps onto the parameter value 0 directly)
EQUIVALENT: dict[tuple, tuple] = {}
# mechanisms of the original that are not transferred on purpose (Appendix C, sections 6 and 7)
MECHANISMS = (
    ("EdgeRemoval.ps1", "Removes Microsoft Edge and repeats the removal at every start by a scheduled task. Not "
     "transferred: the PC is left without a browser, and updates bring Edge back. WinKickOff keeps Edge and restricts "
     "it with the policies of the \"Browsers\" section."),
    ("OpenWebSearch.cmd", "Sends `microsoft-edge:` links and web results of Windows search to another browser by "
     "rewriting protocol handlers; `OpenWebSearchRepair.ps1` and its task restore them after updates. Not "
     "transferred: it only makes sense after Edge is removed."),
    ("OneDriveRemoval.ps1", "Removes OneDrive with `takeown` and deletion of files at restart, again at every "
     "sign-in. The intent is transferred as the rule `apps.remove.onedrive` (new users get no OneDrive); the deletion "
     "of system files and the repeating task are not."),
    ("BloatRemoval.ps1", "Removes apps, capabilities and optional features. Its lists are mapped above; the "
     "scheduled task that repeats the removal is not transferred: WinKickOff removes apps once, in specialize."),
    ("WinhanceUserCustomizations", "A task running as SYSTEM applies the per-user settings in the session of the "
     "signed-in user and restarts the PC 20 seconds later. Not transferred: WinKickOff writes these settings into "
     "the default user profile, so every user gets them without a restart."),
)
# scripts of the original whose intent a catalog rule implements in another way
MECHANISM_RULES = {"OneDriveRemoval.ps1": "apps.remove.onedrive"}


def _unquote(text: str) -> str:
    return text.replace("''", "'")


def normalise_path(path: str) -> str:
    p = path.replace("ControlSet001", "CurrentControlSet")
    lower = p.lower()
    if lower.startswith("hkcu:\\"):
        return DU_PREFIX + lower[len("hkcu:\\"):]
    if lower.startswith("hklm\\"):
        return "hklm:\\" + lower[len("hklm\\"):]
    return lower


def _value(raw: str) -> str:
    if raw.startswith("'"):
        return _unquote(raw[1:-1])
    if raw.startswith("@("):
        return ",".join(str(int(v, 0)) for v in re.findall(r"0x[0-9a-fA-F]+|\d+", raw))
    return str(int(raw)) if re.fullmatch(r"-?\d+", raw) else raw


def _command(m: re.Match[str]) -> tuple[Any, ...]:
    """A `reg add` command of a Setup pass as a normalised action."""
    return ("cmd", normalise_path(m.group(1)), m.group(2).lower(), KIND.get(m.group(3).upper(), m.group(3)), _value(m.group(4)))


def _is_service_start(action: tuple[Any, ...]) -> bool:
    return action[0] == "reg" and action[2] == "start" and re.search(r"\\services\\[^\\]+$", str(action[1])) is not None


def _slot(action: tuple[Any, ...]) -> tuple[Any, ...] | None:
    """What an action sets, without the value: two actions with one slot and different values contradict."""
    kind = action[0]
    if kind in ("reg", "reg-remove", "cmd"):
        return ("cmd" if kind == "cmd" else "reg", action[1], action[2])
    if kind in ("service", "oobe"):
        return (kind, action[1])
    return None


@dataclass
class Original:
    actions: set[tuple[Any, ...]] = field(default_factory=set)
    described: dict[tuple[Any, ...], str] = field(default_factory=dict)  # action -> the original's description
    key: str = ""
    show_ui: str = ""
    key_removals: list[tuple[str, str]] = field(default_factory=list)
    unparsed: int = 0
    text: str = ""

    def counted(self) -> list[tuple[Any, ...]]:
        """Actions for the report: a service start type is counted once, as the service action."""
        return sorted((a for a in self.actions if not _is_service_start(a)), key=lambda a: (a[0], str(a[1:])))


def _list(text: str, name: str) -> list[str]:
    block = re.search(rf"\${name} = @\((.*?)\n\)", text, re.S)
    return re.findall(r"'([^']+)'", block.group(1)) if block else []


def parse_original(text: str) -> Original:
    o = Original(text=text)
    calls = text.count("Set-RegistryValue -Path")
    for m in SET_RE.finditer(text):
        path, name, kind, raw, desc = m.group(1), m.group(2), m.group(3), m.group(4), m.group(6) or ""
        action: tuple[Any, ...] = ("reg", normalise_path(_unquote(path)), _unquote(name).lower(), kind, _value(raw))
        o.actions.add(action)
        o.described[action] = _unquote(desc)
        service = re.fullmatch(r"hklm:\\system\\currentcontrolset\\services\\([^\\]+)", action[1])
        if service and action[2] == "start":
            o.actions.add(("service", service.group(1), int(action[4])))
    o.unparsed = calls - len(SET_RE.findall(text))
    for m in REMOVE_RE.finditer(text):
        action = ("reg-remove", normalise_path(_unquote(m.group(1))), _unquote(m.group(2)).lower())
        o.actions.add(action)
        o.described[action] = _unquote(m.group(3) or "")
    for m in REMOVE_KEY_RE.finditer(text):
        o.key_removals.append((_unquote(m.group(1)), _unquote(m.group(2) or "")))
    for name in _list(text, "packages"):
        o.actions.add(("appx", name.lower()))
    for name in _list(text, "capabilities"):
        o.actions.add(("capability", name.lower().rstrip("*")))
    for name in _list(text, "optionalFeatures"):
        o.actions.add(("feature", name.lower(), "Disabled"))
    for tn, act in re.findall(r'TN="([^"]+)"; Action="(/\w+)"', text):
        o.actions.add(("exe", "schtasks.exe", ("/Change", "/TN", tn, act)))
    root = ET.fromstring(text.encode("utf-8"))
    for settings in root.findall(f"{U}settings"):
        for cmd in settings.iter(f"{U}RunSynchronousCommand"):
            m = REG_ADD_RE.search(cmd.findtext(f"{U}Path") or "")
            if m:
                o.actions.add(_command(m))
        for comp in settings.findall(f"{U}component"):
            oobe = comp.find(f"{U}OOBE")
            if oobe is not None:
                o.actions.update(("oobe", child.tag.replace(U, ""), (child.text or "").strip()) for child in oobe)
            key = comp.find(f"{U}UserData/{U}ProductKey")
            if key is not None:
                o.key = (key.findtext(f"{U}Key") or "").strip()
                o.show_ui = (key.findtext(f"{U}WillShowUI") or "").strip()
    return o


def _checkable(catalog: Catalog, profile: Profile, rule: Rule) -> set[tuple[Any, ...]]:
    """Normalised actions of a rule that can be compared with the original."""
    result = {("capability", a[1].rstrip("*")) if a[0] == "capability" else a for a in rule_actions(catalog, profile, rule)}
    params = profile.params_for(catalog, rule.id)
    for action in rule.actions:
        f = {k: substitute(v, params) for k, v in action.fields.items()}
        if action.type in ("xml-pe-command", "xml-specialize-command"):
            m = REG_ADD_RE.search(str(f["command"]))
            if m:
                result.add(_command(m))
        elif action.type == "xml-oobe":
            result.add(("oobe", str(f["element"]), str(f["value"])))
    return result


def _equivalent(action: tuple[Any, ...]) -> tuple[Any, ...]:
    return EQUIVALENT[action][0] if action in EQUIVALENT else action


def build(catalog: Catalog, text: str) -> tuple[Profile, dict[str, Any]]:
    original = parse_original(text)
    found = {_equivalent(a) for a in original.actions}
    slots: dict[tuple[Any, ...], list[tuple[Any, ...]]] = defaultdict(list)
    for action in sorted(found, key=str):
        slot = _slot(action)
        if slot is not None:
            slots[slot].append(action)
    profile = Profile.from_catalog(catalog, name="memstechtips")
    evidence: dict[str, tuple[list[Any], list[Any], list[Any]]] = {}
    for rule in catalog.rules.values():
        _infer_params(rule, profile, catalog, found)
        present: list[tuple[Any, ...]] = []
        absent: list[tuple[Any, ...]] = []
        conflicts: list[tuple[tuple[Any, ...], tuple[Any, ...]]] = []
        for action in sorted(_checkable(catalog, profile, rule), key=str):
            slot = _slot(action)
            if action in found:
                present.append(action)
            elif slot in slots:
                conflicts.append((action, slots[slot][0]))
            else:
                absent.append(action)
        evidence[rule.id] = (present, absent, conflicts)
        profile.rules[rule.id].enabled = bool(present) and not conflicts
    # rules whose intent the original implements with a script of its own
    by_script = [r for name, r in MECHANISM_RULES.items() if name in text and r in catalog.rules and not evidence[r][2]]
    for rule_id in by_script:
        profile.rules[rule_id].enabled = True
    # a required rule is switched on unless it contradicts the original; otherwise the rule is switched off
    required: set[str] = set()
    dropped: set[str] = set()
    changed = True
    while changed:
        changed = False
        for rule in catalog.rules.values():
            missing = [r for r in rule.requires if not profile.is_enabled(r)]
            if not profile.is_enabled(rule.id) or not missing:
                continue
            if any(evidence[r][2] for r in missing):
                profile.rules[rule.id].enabled = False
                dropped.add(rule.id)
            else:
                for r in missing:
                    profile.rules[r].enabled = True
                    required.add(r)
            changed = True
    enabled = [r for r in catalog.order if profile.is_enabled(r)]
    for rule_id in catalog.rules:
        if not profile.is_enabled(rule_id):
            profile.rules[rule_id].params.clear()
    covered: set[tuple[Any, ...]] = set()
    for rule_id in enabled:
        covered |= _checkable(catalog, profile, catalog.rules[rule_id])
    if original.key == "00000-00000-00000-00000-00000" or original.show_ui == "Always":
        profile.install.update(product_key_mode="ask", product_key="")
    facts = {
        "original": original,
        "covered": covered,
        "full": [r for r in enabled if r not in required and r not in by_script and not evidence[r][1]],
        "extended": {r: evidence[r] for r in enabled if r not in required and r not in by_script and evidence[r][1]},
        "by_script": {r: name for name, r in MECHANISM_RULES.items() if r in by_script},
        "required": {r: evidence[r] for r in enabled if r in required},
        "conflicts": {r: evidence[r] for r in catalog.order if evidence[r][2]},
        "dropped": sorted(dropped),
    }
    return profile, facts


def _kind_title(action: tuple[Any, ...]) -> str:
    return {"reg": "Registry value", "reg-remove": "Registry value removed", "service": "Service start type",
            "appx": "App removed", "capability": "Capability removed", "feature": "Optional feature disabled",
            "exe": "Scheduled task", "cmd": "Registry command of a Setup pass", "oobe": "OOBE element"}.get(action[0], action[0])


def _describe(action: tuple[Any, ...]) -> str:
    t = action[0]
    if t in ("reg", "cmd"):
        path = str(action[1]).replace(DU_PREFIX, "hkcu:\\")
        return f"`{path}\\{action[2]} = {action[4]}` ({action[3]})"
    if t == "reg-remove":
        return f"`{str(action[1]).replace(DU_PREFIX, 'hkcu:' + chr(92))}\\{action[2]}` removed"
    if t == "service":
        return f"service `{action[1]}`: start {action[2]}"
    if t == "exe":
        return f"task `{action[2][2]}` {action[2][3]}"
    if t == "oobe":
        return f"`<{action[1]}>{action[2]}</{action[1]}>`"
    if t == "appx":
        return f"app `{action[1]}` removed"
    if t == "capability":
        return f"capability `{action[1]}` removed"
    if t == "feature":
        return f"feature `{action[1]}` {action[2].lower()}"
    return f"`{action[1]}`"


def _cut(text: str) -> str:
    text = text.replace("|", "/")
    return (text[:150] + "...") if len(text) > 150 else text


def report(catalog: Catalog, profile: Profile, facts: dict[str, Any]) -> str:
    original: Original = facts["original"]
    english = CatalogTexts.load(ROOT / "rules", "en")

    def title(rule_id: str) -> str:
        return english.rule(catalog.rules[rule_id], "title")

    counted = original.counted()
    covered = [a for a in counted if _equivalent(a) in facts["covered"]]
    held: set[tuple[Any, ...]] = set()
    contradicted: set[tuple[Any, ...]] = set()
    for present, _, conflicts in facts["conflicts"].values():
        held |= set(present)
        contradicted |= {theirs for _, theirs in conflicts}
    missing = [a for a in counted if _equivalent(a) not in facts["covered"]]
    held_back = [a for a in missing if _equivalent(a) in held]
    against = [a for a in missing if _equivalent(a) in contradicted and _equivalent(a) not in held]
    no_rule = [a for a in missing if _equivalent(a) not in held | contradicted]
    enabled = [r for r in catalog.order if profile.is_enabled(r)]
    added = sum(len(e[1]) for e in facts["extended"].values()) + sum(len(e[1]) for e in facts["required"].values())
    lines = [
        "# memstechtips profile: the original UnattendedWinstall file mapped onto WinKickOff",
        "",
        "Generated by `WinKickOff/tools/make_presets.py` (module `tools/memstechtips.py`) for issue #2 of the",
        "repository; do not edit by hand. Source: [Appendix A](../appendices/A-unattendedwinstall/SOURCE.md),",
        "the answer file of the UnattendedWinstall project by memstechtips.",
        "",
        "## How the mapping works",
        "",
        "The original is parsed into normalised actions: `Set-RegistryValue` and `Remove-RegistryValue` calls of",
        "its scripts (its per-user HKCU values are compared with the default user rules of the catalog), registry",
        "commands of the windowsPE and specialize passes, OOBE elements, the lists of removed apps, capabilities",
        "and optional features, and the list of disabled scheduled tasks. A catalog rule is enabled in the preset",
        "`profiles/preset-memstechtips.json` when the original contains at least one of its actions and none of",
        "its actions contradicts the original (the same registry value, service or OOBE element with another",
        "value). So every option of the original that has a non-contradicting rule is transferred; where a rule",
        "does more than the original, the additions are listed below. A rule required by an enabled rule is",
        "enabled too, unless it contradicts the original. Rules made of PowerShell steps only cannot be matched",
        "and stay off.",
        "",
        "The product key is asked during installation, as in the original. The original sets no languages, time",
        "zone or accounts, so the preset keeps the WinKickOff defaults for them (the answer file needs them to",
        "skip the language page and to create an administrator).",
        "",
        "## Summary",
        "",
        "| Item | Count |",
        "|---|---|",
        f"| Actions found in the original | {len(counted)} |",
        f"| Transferred: covered by enabled rules of the preset | {len(covered)} |",
        f"| Held back: belong to rules that contradict the original elsewhere | {len(held_back)} |",
        f"| Contradict a catalog rule (the catalog sets another value) | {len(against)} |",
        f"| Not transferable: no rule in the catalog | {len(no_rule)} |",
        f"| Registry key removals (context menu and viewer tweaks), not transferable | {len(set(original.key_removals))} |",
        f"| Rules enabled in the preset | {len(enabled)} of {len(catalog.rules)} |",
        f"| Actions enabled rules add beyond the original | {added} |",
        f"| Rules left off because they contradict the original | {len(facts['conflicts'])} |",
        "",
        "## Enabled rules",
        "",
        "### Every action is in the original",
        "",
    ]
    lines += [f"- `{r}`: {title(r)}" for r in facts["full"]] or ["- none"]
    lines += ["", "### Rules that do more than the original", "",
              "The original has part of the rule; the preset also gets the listed actions.", ""]
    for rule_id, (present, absent, _) in facts["extended"].items():
        lines.append(f"- `{rule_id}`: {title(rule_id)} ({len(present)} of {len(present) + len(absent)} actions in the original). Adds:")
        lines += [f"  - {_describe(a)}" for a in absent]
    if not facts["extended"]:
        lines.append("- none")
    if facts["by_script"]:
        lines += ["", "### Implemented by a script of the original", "",
                  "The original reaches the goal of the rule with a script of its own (see the mechanisms below).", ""]
        lines += [f"- `{r}`: {title(r)}, as `{name}` does" for r, name in facts["by_script"].items()]
    if facts["required"]:
        lines += ["", "### Required by an enabled rule", ""]
        for rule_id, (present, absent, _) in facts["required"].items():
            needed_by = [r for r in catalog.order if profile.is_enabled(r) and rule_id in catalog.rules[r].requires]
            lines.append(f"- `{rule_id}`: {title(rule_id)}, required by " + ", ".join(f"`{r}`" for r in needed_by) + ". Adds:")
            lines += [f"  - {_describe(a)}" for a in absent]
    used = [(a, why) for a, (_, why) in EQUIVALENT.items() if a in original.actions]
    if used:
        lines += ["", "## Values treated as equivalent", ""]
        lines += [f"- {_describe(a)}: {why}" for a, why in used]
    lines += ["", "## Rules left off because they contradict the original", "",
              "| Rule | The original | The rule | Other actions of the rule found in the original |", "|---|---|---|---|"]
    for rule_id, (present, _, conflicts) in facts["conflicts"].items():
        theirs = "<br>".join(_describe(t) for _, t in conflicts)
        ours = "<br>".join(_describe(o) for o, _ in conflicts)
        lines.append(f"| `{rule_id}`: {title(rule_id)} | {theirs} | {ours} | {len(present)} |")
    if facts["dropped"]:
        lines += ["", "Turned off because a required rule contradicts the original: " + ", ".join(f"`{r}`" for r in facts["dropped"]) + "."]
    lines += ["", "## Not transferable", "",
              "What the original does and the catalog has no rule for. Most of it is cosmetics and convenience",
              "tweaks that WinKickOff leaves out on purpose (see Appendix C, the review of the original); some",
              "items weaken security and must not be transferred. A needed item becomes a new catalog rule.", ""]
    by_kind: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for action in no_rule:
        by_kind[_kind_title(action)].append(action)
    for kind in sorted(by_kind):
        lines += [f"### {kind}", "", "| Action | Description in the original |", "|---|---|"]
        lines += [f"| {_describe(a)} | {_cut(original.described.get(a, ''))} |" for a in by_kind[kind]]
        lines.append("")
    if original.key_removals:
        lines += ["### Registry key removals", "", "| Key | Description in the original |", "|---|---|"]
        lines += [f"| `{path}` | {_cut(desc)} |" for path, desc in sorted(set(original.key_removals))]
        lines.append("")
    mechanisms = [(name, why) for name, why in MECHANISMS if name in original.text]
    if mechanisms:
        lines += ["## Mechanisms of the original that are not transferred", "", "| Script or task | What it does and why |", "|---|---|"]
        lines += [f"| `{name}` | {why} |" for name, why in mechanisms]
        lines.append("")
    baseline_off = [r for r in catalog.order if catalog.rules[r].level == "baseline" and not profile.is_enabled(r)]
    if baseline_off:
        lines += ["## Baseline rules of WinKickOff that are off in the preset", "",
                  "The preset follows the original: these rules contradict it (see the table above) or are absent from",
                  "it, so they are off and the editor warns about each of them. Turning them on is recommended;",
                  "\"File, Compare with profile...\" shows every difference from the \"Office\" preset.", ""]
        lines += [f"- `{r}`: {title(r)}" for r in baseline_off]
        lines.append("")
    text = "\n".join(lines).rstrip() + "\n"
    for c in (0x2013, 0x2014):
        text = text.replace(chr(c), "-")  # the original's descriptions may contain dashes; the project style forbids them
    return text


def load(catalog: Catalog) -> tuple[Profile, dict[str, Any]]:
    return build(catalog, ORIGINAL.read_text(encoding="utf-8"))
