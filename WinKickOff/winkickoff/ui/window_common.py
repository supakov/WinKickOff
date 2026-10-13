"""Constants and helpers shared by the main window and its mixins: node ids, titles shown through tr(), the
workflow text, the limits of the window."""

from __future__ import annotations

import json
import time
from pathlib import Path

from winkickoff.core.deps import Change
from winkickoff.core.i18n import SOURCE_LANGUAGE, N_, language, tr
from winkickoff.core.profile import Profile



WORKFLOW_NODE = "info:workflow"
PRESET_NAMES = (N_("Office"), N_("Strict"), N_("Laptop"), N_("Home"))  # preset names are English data; shown through tr()
HISTORY_LIMIT = 50  # nodes kept for Back
GROUP_LIST_LIMIT = 300  # rules listed in the description of a group; imported branches hold thousands
MODE_TITLES = (N_("Read only"), N_("Read and change the open profile"), N_("Change and create files"))
THEME_NAMES = (N_("Light"), N_("Dark"), N_("Latte"), N_("Matrix"))  # names of the bundled themes; shown through tr()
DATA_NODES: tuple[tuple[str, str], ...] = (
    ("data:install", N_("Installation: edition, key, time zone")),
    ("data:accounts", N_("Accounts")),
    ("data:languages", N_("Languages and region")),
)
LEVEL_TITLES = {"baseline": N_("baseline"), "recommended": N_("recommended"), "optional": N_("optional"), "risky": N_("risky")}
PHASE_TITLES = {
    "windowspe": N_("Windows Setup (windowsPE)"),
    "specialize-xml": N_("first boot (command in XML)"),
    "specialize": N_("first boot (machine script Setup-System.ps1)"),
    "default-user": N_("default user profile"),
    "user-first-logon": N_("each user's first sign-in (Setup-User.ps1)"),
    "post-oobe": N_("after initial setup (Post-OOBE.ps1)"),
    "oobe-xml": N_("initial setup (OOBE)"),
}
ISSUE_TITLES = {"error": N_("error"), "warning": N_("warning"), "info": N_("information"), "change": N_("changed")}
VK_S, VK_O, VK_F = 83, 79, 70  # virtual-key codes: shortcuts work with any keyboard layout
UNKNOWN_NODE = "unknown"  # the root of the choices kept in the profile for rules the loaded catalog does not have
UNKNOWN_PREFIX = "u:"  # its items: "u:<rule id>" (Profile.unknown)
UNKNOWN_TITLE = N_("Unknown rules and policies")
UNKNOWN_SUMMARY = N_("The open profile keeps choices for rules that the loaded catalog does not have: policies of imported "
                     "templates that are not loaded, or rules of another version of WinKickOff. They come back when their "
                     "rules are there again; until then they are not written to autounattend.xml, not checked and not "
                     "applied to this PC.")
UNKNOWN_POLICY = N_("A policy of imported templates that are not loaded now. The profile keeps its state and parameters and "
                    "brings them back when the templates are shown or imported again (menu \"ADMX\"). Until then the policy "
                    "is not written to autounattend.xml, not checked and not applied to this PC.")
UNKNOWN_HELD = N_("The choice was made with the source \"{0}\", and the policy now comes only from the less trusted source "
                  "\"{1}\". The profile keeps the choice but does not use it, so a catalog file cannot take over a choice "
                  "made in trusted templates. Show templates of that kind again to use it, or choose the policy again in "
                  "its branch to use it from there.")
KIND_TITLES = {"bundled": N_("a catalog of the program"), "system": N_("the templates of this Windows"),
               "folder": N_("templates from a folder"), "package": N_("a catalog file")}
UNKNOWN_RULE = N_("A rule that is not in rule catalog {0}: the profile was probably saved by another version of WinKickOff. "
                  "The profile keeps its state and parameters and brings them back when the catalog has the rule. Until "
                  "then the rule is not written to autounattend.xml, not checked and not applied to this PC.")
VALUE_LIMIT = 300  # characters of a kept parameter value shown in the description
PARAMS_SHARE = 0.45  # the parameter editor above the description takes at most this share of the panel, then scrolls
PARAMS_MIN_HEIGHT = 120  # pixels the editor may always take, however small the window
READ_PC_TIMEOUT = 600  # seconds the read of this PC may take
DRAFT_INTERVAL_MS = 60_000  # how often unsaved changes go to the draft
BUSY_NOTE = N_("This may take a few minutes. The window closes by itself when the work is done.")
READ_SELECTION_NOTE = N_("WinKickOff reads the {0} selected rules on this computer and puts their state into the open "
                         "profile as unsaved changes: a rule in effect is switched on with the values found, the others "
                         "are switched off. The data forms stay as they are, and nothing on this computer changes.")
READ_PC_ADMIN_NOTE = N_("As administrator: Windows asks to confirm the rights once; the read itself runs hidden and still "
                        "changes nothing. Optional features, capabilities and the apps of every user are read too.")
READ_PC_NOTE = N_("WinKickOff reads the settings of this computer into a new profile: every rule a running Windows can "
                  "show, the edition, the time zone, the languages and the local accounts (without passwords). Nothing on "
                  "this computer changes. Rules that act only during installation or at the first sign-in keep the state "
                  "of the open profile. Without administrator rights some settings cannot be read. It may take a few "
                  "minutes.")

WORKFLOW = [
    ("h1", N_("Workflow")),
    ("", N_("WinKickOff builds an autounattend.xml file for automated installation of Windows 11. Put "
            "the file in the root of the Windows installation USB drive; Windows Setup finds it on its "
            "own and does everything selected here.")),
    ("h2", N_("1. Profile")),
    ("", N_("The \"Profile\" field in the top panel. \"Preset: Office\" reproduces the tested v0.2 answer "
            "file; \"Preset: Strict\" adds restrictions that may interfere with older programs. Presets "
            "are never modified: a changed profile is saved under its own name (the \"Save as\" button).")),
    ("h2", N_("2. Rules")),
    ("", N_("The tree on the left contains all installation settings. The checkbox before a name "
            "enables or disables the rule (or the whole group); \"+\" only expands the branch. Rules "
            "that depend on a disabled rule are disabled automatically, and enabling a rule enables "
            "what it needs: the changes are shown in the status bar and in the list below. Search "
            "(Ctrl+F) looks in names, tags and technical details, for example a registry key name.")),
    ("h2", N_("3. Description and parameters")),
    ("", N_("On the right, for the selected rule: what it does technically (registry keys, services, "
            "commands), effect, risks, Windows versions, check and rollback. The rule parameters "
            "(hours, modes, thresholds) are changed there too, above the description.")),
    ("h2", N_("4. Installation data")),
    ("", N_("The \"Installation\", \"Accounts\" and \"Languages and region\" nodes at the top of the tree: "
            "edition and key, time zone, initial accounts, display language (same as the ISO language) "
            "and input languages.")),
    ("h2", N_("5. Saving the profile")),
    ("", N_("\"Save\" (Ctrl+S) writes the profile to the profiles folder next to the program, so the "
            "installation can be repeated on other PCs. The profile is also embedded in every built "
            "file: \"File, Open profile from autounattend.xml\" restores the settings from a finished "
            "autounattend.xml.")),
    ("h2", N_("6. Check and build")),
    ("", N_("\"Check\" (F7) checks the profile and the resulting file. \"Build autounattend.xml\" (F9) "
            "builds the file from enabled rules only, checks Windows Setup limits and PowerShell "
            "syntax, and asks where to save it. Errors and warnings appear in the list below; "
            "double-click one to go to the rule.")),
    ("h2", N_("7. Installation")),
    ("", N_("Copy autounattend.xml to the root of a USB drive with the Windows 11 installation image "
            "and boot the PC from it. Windows Setup asks for the drive to install to, and also for the product key "
            "and the edition or for an account when the \"Installation\" or \"Accounts\" form says so. After "
            "installation, logs are in C:\\ProgramData\\Unattend\\Logs.")),
]


def rule_of(item: str) -> str:
    """The rule id of a tree item: "r:<rule>", or "r:<rule>@<group>" where one more imported tree shows the rule."""
    return item[2:].split("@", 1)[0]


def user_docs(docs_root: Path | None = None) -> str:
    """The user documentation in the interface language (docs/user/<code>/README.md), English when a language
    has no documentation."""
    wanted = f"docs/user/{language()}/README.md"
    if docs_root is not None and not (docs_root / wanted).exists():
        return f"docs/user/{SOURCE_LANGUAGE}/README.md"
    return wanted


def _profile_name(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return str(data.get("name") or path.stem)
    except (OSError, ValueError):
        return path.stem


def error_text(exc: BaseException, limit: int = 1500) -> str:
    """The text of an error for a message box, cut: a file can make an error message of any length."""
    text = str(exc) or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "..."
