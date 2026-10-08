"""Generate rules/17-shell.json: File Explorer namespaces and desktop icons (customer request 1 of 04.10.2026).

Each entry was checked read-only on Windows 11 (registry of build 26300, ADMX of this Windows) and against Microsoft
documentation where it exists; what only third parties report is marked in the rule texts and listed in
docs/technical/reference/20-explorer-namespaces.md, which also explains why some entries are not offered.

Run after editing the tables below:
    cd WinKickOff
    python tools/make_shell_rules.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from winkickoff.core import jsonfile  # noqa: E402

DOC = "docs/technical/reference/20-explorer-namespaces.md"
HKLM_NS = "HKLM:\\SOFTWARE\\{view}Microsoft\\Windows\\CurrentVersion\\Explorer\\MyComputer\\NameSpace\\"
PIN_PATHS = ("HKCU:\\Software\\Classes\\CLSID\\", "HKCU:\\Software\\Classes\\WOW6432Node\\CLSID\\")
ICON_KEY = "DU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\HideDesktopIcons\\"
VIEWS = "Written to both the 64-bit and the 32-bit (WOW6432Node) branches so that dialogs of 32-bit programs match File Explorer."

# This PC entries: (id suffix, CLSID, name, extra tags)
THIS_PC = [
    ("recycle-bin", "{645FF040-5081-101B-9F08-00AA002F954E}", "Recycle Bin", ["recycle bin", "trash"]),
    ("control-panel", "{26EE0668-A00A-44D7-9371-BEB064C98683}", "Control Panel", ["control panel"]),
]
# Navigation pane pins of the user: (id suffix, CLSID, value 1 shows 0 hides, name, risk, extra tags)
PINS = [
    ("libraries", "{031E4825-7B94-4dc3-B131-E946B44C8DD5}", 1, "Libraries", "",
     ["libraries", "show libraries"]),
    ("network-hidden", "{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}", 0, "Network",
     "Shared folders of other computers can no longer be browsed from the navigation pane of File Explorer and of file "
     "dialogs; typing \\\\computer\\share in the address bar still works. Workgroups that share folders need the item.",
     ["network", "shares", "workgroup"]),
    ("recycle-bin", "{645FF040-5081-101B-9F08-00AA002F954E}", 1, "Recycle Bin", "", ["recycle bin", "trash"]),
    ("user-folder", "{59031a47-3f72-44a7-89c5-5595fe6b30ee}", 1, "the user folder", "", ["user folder", "profile"]),
    ("linux-hidden", "{B2B4A4D1-2754-4140-A2EB-9A76D9D7CDC6}", 0, "Linux", "",
     ["linux", "wsl", "windows subsystem for linux"]),
    ("control-panel", "{26EE0668-A00A-44D7-9371-BEB064C98683}", 1, "Control Panel",
     "Not verified: Windows may ignore the per-user value for this item; check in a virtual machine.",
     ["control panel"]),
]
# Desktop icons: (group, id suffix, CLSID, value 0 shows 1 hides, name, both keys, conflicts, extra tags, note)
DESKTOP = "system.explorer.desktop"
FOLDERS = "system.explorer.desktop.folders"
ICONS = [
    (DESKTOP, "this-pc", "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", 0, "This PC", True, [], ["this pc", "computer"], ""),
    (DESKTOP, "user-files", "{59031a47-3f72-44a7-89c5-5595fe6b30ee}", 0, "the user folder", True, [],
     ["user folder", "user's files"], ""),
    (DESKTOP, "network", "{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}", 0, "Network", True, [], ["network"], ""),
    (DESKTOP, "control-panel", "{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}", 0, "Control Panel", True, [],
     ["control panel"], ""),
    (DESKTOP, "recycle-bin-hidden", "{645FF040-5081-101B-9F08-00AA002F954E}", 1, "Recycle Bin", True, [],
     ["recycle bin", "trash"], ""),
    (DESKTOP, "libraries", "{031E4825-7B94-4dc3-B131-E946B44C8DD5}", 0, "Libraries", True, [], ["libraries"],
     "The value name is the one Windows keeps for Libraries in its machine defaults."),
    (DESKTOP, "spotlight-icon-hidden", "{2cc5ca98-6485-489a-920e-b3e88a6ccce3}", 1, "Learn about this picture", False, [],
     ["spotlight", "learn about this picture", "bing"],
     "The icon appears only when Windows Spotlight is the desktop background and opens Bing in the browser."),
    (FOLDERS, "documents", "{A8CDFF1C-4878-43be-B5FD-F8091C1C60D0}", 0, "Documents", True, [], ["documents"], ""),
    (FOLDERS, "downloads", "{374DE290-123F-4565-9164-39C4925E467B}", 0, "Downloads", True, [], ["downloads"], ""),
    (FOLDERS, "music", "{1CF1260C-4DD0-4ebb-811F-33C572699FDE}", 0, "Music", True, [], ["music"], ""),
    (FOLDERS, "pictures", "{3ADD1653-EB32-4cb0-BBD7-DFA0ABB5ACCA}", 0, "Pictures", True, [], ["pictures"], ""),
    (FOLDERS, "videos", "{A0953C92-50DC-43bf-BE83-3742FED03C9C}", 0, "Videos", True, [], ["videos"], ""),
    (FOLDERS, "desktop-folder", "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}", 0, "Desktop", True, [],
     ["desktop folder"], ""),
    (FOLDERS, "gallery", "{e88865ea-0e1c-4e20-9aa6-edcd0212c87c}", 0, "Gallery", True, ["nav.gallery-hidden"],
     ["gallery"], "Conflicts with hiding \"Gallery\" in the navigation pane, which hides the same item."),
    (FOLDERS, "home", "{f874310e-b6b7-47dc-bc84-b9e6b38f5903}", 0, "Home", True, ["nav.home-hidden"], ["home"],
     "Conflicts with hiding \"Home\" in the navigation pane, which hides the same item."),
]
DIALOG_ICONS = {"this-pc", "user-files", "network", "control-panel", "recycle-bin-hidden"}  # what the dialog offers
REMOVABLE_SCRIPT = r"""
foreach ($root in 'HKLM:\SOFTWARE\Microsoft', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft') {
    $key = $root + '\Windows\CurrentVersion\Explorer\Desktop\NameSpace\DelegateFolders\{F5FB2C77-0E2F-4A16-A381-3E560C68BC83}'
    if (Test-Path -LiteralPath $key) {
        try { Remove-Item -LiteralPath $key -Recurse -Force -ErrorAction Stop; Write-Log "removed $key" 'OK' }
        catch { Write-Log ("remove {0}: {1}" -f $key, $_.Exception.Message) 'WARN' }
    }
}
"""


def head(rule_id: str, group: str, phase: str, title: str, tag_list: list[str], anchor: str, summary: str, effect: str,
         risk: str, versions: str, verify: str, rollback: str, conflicts: list[str] | None = None) -> dict:
    rule = {"id": rule_id, "group": group, "phase": phase, "title": title, "level": "optional", "default": False}
    if conflicts:
        rule["conflicts"] = list(conflicts)
    rule |= {"tags": list(dict.fromkeys(tag_list)), "doc": f"{DOC}#{anchor}", "summary": summary, "effect": effect}
    if risk:
        rule["risk"] = risk
    rule |= {"versions": versions, "verify": verify, "rollback": rollback}
    return rule


def reg(path: str, name: str, value: int, default: str | int | None = None) -> dict:
    action = {"type": "reg", "path": path, "name": name, "kind": "DWord", "value": value}
    if default is not None:
        action["default"] = default
    return action


def catalog_file() -> dict:
    rules = []
    for suffix, clsid, name, extra in THIS_PC:
        rule = head(f"thispc.{suffix}", "system.explorer.thispc", "specialize", f'Show "{name}" in "This PC"',
                    ["this pc", "file explorer", "namespace", *extra], "this-pc",
                    f'"{name}" appears in "This PC" next to the drives, for all users.',
                    "Adds a namespace entry; nothing is moved. Off by default: \"This PC\" shows only the drives, as in "
                    "Windows 11.",
                    "Reported by third parties for Windows 10 and 11; check on 25H2 in a virtual machine.",
                    f"Windows 10 and 11, all editions. {VIEWS}",
                    f'reg query "{HKLM_NS.format(view="")[:-1].replace(":", "")}\\{clsid}"',
                    "Value 1 in both branches hides the entry again (the automatic return to defaults writes it). To "
                    f"remove the entry completely, delete the {clsid} key in both NameSpace branches.")
        rule["actions"] = [reg(f"{HKLM_NS.format(view=view)}{clsid}", "HiddenByDefault", 0, 1)
                           for view in ("", "WOW6432Node\\")]
        rules.append(rule)
    for suffix, clsid, value, name, risk, extra in PINS:
        verb = "Show" if value else "Hide"
        quoted = name if name.startswith("the ") else f'"{name}"'
        rule = head(f"nav.{suffix}", "system.explorer.nav", "user-first-logon",
                    f"{verb} {quoted} in the File Explorer navigation pane",
                    ["navigation pane", "file explorer", "namespace", "ispinnedtonamespacetree", *extra],
                    "navigation-pane",
                    f"{quoted[0].upper() + quoted[1:]} is {'shown' if value else 'not shown'} in the left pane of File "
                    "Explorer and of file dialogs.",
                    "Written for each user at the first sign-in (Active Setup); the user can change it again. Accounts that "
                    "already exist are not changed, and \"Apply\" on this PC does not run first sign-in rules.",
                    risk,
                    "Windows 10 and 11, all editions. "
                    + ("WSL registers the item only when it is installed, and the value System.IsPinnedToNameSpaceTree "
                       if suffix == "linux-hidden" else "The machine registration of the item belongs to TrustedInstaller, "
                       "so the value System.IsPinnedToNameSpaceTree ")
                    + "is set per user, also for 32-bit file dialogs (WOW6432Node). Microsoft documents the value for "
                    "cloud storage providers; for this item it is reported by third parties.",
                    f'reg query "HKCU\\Software\\Classes\\CLSID\\{clsid}" /v System.IsPinnedToNameSpaceTree',
                    f"Delete the value System.IsPinnedToNameSpaceTree under HKCU\\Software\\Classes\\CLSID\\{clsid} "
                    "and its WOW6432Node twin of the user.")
        rule["actions"] = [reg(path + clsid, "System.IsPinnedToNameSpaceTree", value, "absent") for path in PIN_PATHS]
        rules.append(rule)
    rule = head("nav.show-all-folders", "system.explorer.nav", "default-user",
                "Show all folders in the File Explorer navigation pane",
                ["navigation pane", "file explorer", "show all folders", "navpaneshowallfolders"], "navigation-pane",
                "The left pane also shows Desktop, the user folder, Control Panel and Recycle Bin, as with \"Show all "
                "folders\".",
                "For accounts created after installation; the user can change it again (right-click the navigation "
                "pane).", "",
                "Windows 10 and 11, all editions. The option is documented; the value name is reported by third parties.",
                'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced" /v NavPaneShowAllFolders',
                "Right-click the navigation pane and clear \"Show all folders\".")
    rule["actions"] = [reg("DU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", "NavPaneShowAllFolders",
                           1, "absent")]
    rules.append(rule)
    rule = head("nav.removable-drives-once", "system.explorer.nav", "specialize",
                "Show USB drives only under \"This PC\" in the navigation pane",
                ["usb", "removable", "duplicate", "navigation pane", "delegatefolders"], "navigation-pane",
                "Removable drives no longer appear a second time as separate items at the top of the left pane.",
                "Deletes the \"Removable Drives\" delegate folder of the desktop namespace in both branches; the drives "
                "stay under \"This PC\".",
                "Reported by third parties; a feature update of Windows may create the key again. The automatic return "
                "to defaults cannot restore a deleted key.",
                "Windows 10 and 11, all editions.",
                'reg query "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Desktop\\NameSpace\\'
                'DelegateFolders\\{F5FB2C77-0E2F-4A16-A381-3E560C68BC83}" and the same path under '
                'HKLM\\SOFTWARE\\WOW6432Node\\Microsoft: after the rule both answer that the key cannot be found (before '
                'it they show the default value "Removable Drives"); C:\\ProgramData\\Unattend\\Logs\\Setup-System.log '
                'has two OK lines "removed ...".',
                "Create the key again in both branches with the default value \"Removable Drives\".")
    rule["actions"] = [{"type": "ps", "script": REMOVABLE_SCRIPT.strip("\n").split("\n")}]
    rules.append(rule)
    rule = head("nav.home-cloud-files-off", "system.explorer.nav", "specialize",
                "No cloud files and activity in File Explorer \"Home\"",
                ["home", "recent", "recommended", "cloud", "policy", "disablegraphrecentitems"], "navigation-pane",
                "File Explorer does not request the metadata of cloud files and shows no files based on the account and "
                "cloud activity in \"Home\" (Recent, Recommended, Shared).",
                "Local recent files stay. Value 1 of the policy FileExplorer/DisableGraphRecentItems, which Microsoft "
                "calls \"Turn off account-based insights, recent, favorite, and recommended files in File Explorer\" (the "
                "ADMX of Windows names it \"Show files based on your account and cloud provider activity\").", "",
                "Windows 11 22H2 and later. Explorer.admx sets no edition limit; the Policy CSP lists Pro, Enterprise "
                "and Education, as it covers delivery through MDM. Check the effect on Home in a virtual machine.",
                'reg query "HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer" /v DisableGraphRecentItems',
                "Delete the DisableGraphRecentItems value.")
    rule["actions"] = [reg("HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\Explorer", "DisableGraphRecentItems", 1)]
    rules.append(rule)
    for group, suffix, clsid, value, name, both, conflicts, extra, note in ICONS:
        verb = "Show" if value == 0 else "Hide"
        quoted = name if name.startswith("the ") else f'"{name}"'
        keys = "NewStartPanel and ClassicStartMenu" if both else "NewStartPanel"
        if suffix in DIALOG_ICONS:
            effect = ("For accounts created after installation; the user can change it in Settings, Personalization, "
                      "Themes, Desktop icon settings. Accounts that already exist are not changed.")
            versions = f"Windows 10 and 11, all editions. Written as the Desktop icon settings dialog writes it ({keys})."
        else:
            effect = ("For accounts created after installation. Accounts that already exist are not changed. The Desktop "
                      f"icon settings dialog does not offer this icon; to undo it for a user, delete the value {clsid} "
                      f"under HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\HideDesktopIcons ({keys}).")
            versions = ("Windows 10 and 11, all editions. Written in the same form as the values of the Desktop icon "
                        f"settings dialog ({keys}).")
        rule = head(f"desktop.{suffix}", group, "default-user",
                    f"{verb} the {quoted} icon on the desktop".replace("the the ", "the "),
                    ["desktop", "icons", "hidedesktopicons", *extra], "desktop-icons",
                    f"New accounts {'get' if value == 0 else 'do not get'} the {quoted} icon on the desktop.".replace(
                        "the the ", "the "),
                    effect + (" " + note if note else ""), "", versions,
                    f'reg query "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\HideDesktopIcons\\NewStartPanel" '
                    f'/v "{clsid}"',
                    f"Delete the value {clsid} in HideDesktopIcons\\NewStartPanel"
                    + (" and ClassicStartMenu" if both else "") + " of the user.", conflicts)
        rule["actions"] = [reg(ICON_KEY + sub, clsid, value, "absent")
                           for sub in (("NewStartPanel", "ClassicStartMenu") if both else ("NewStartPanel",))]
        rules.append(rule)
    return {
        "comment": ["File Explorer namespaces and desktop icons (customer request 1 of 04.10.2026). Generated by",
                    "tools/make_shell_rules.py; edit the tables in that tool, not this file."],
        "rules": rules,
    }


if __name__ == "__main__":
    target = ROOT / "rules" / "17-shell.json"
    data = catalog_file()
    jsonfile.write(target, data)
    print(f"written {target.relative_to(ROOT)}: {len(data['rules'])} rules")
