"""Regenerate the preset profiles in profiles/ from the rules catalog.

Run after changing the catalog (defaults, new rules):
    cd WinKickOff
    python tools/make_presets.py

Presets are deterministic (fixed timestamps), contain no passwords and are versioned in git.
tests/test_presets.py fails when a preset no longer matches the catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from winkickoff.core.catalog import Catalog, load_catalog  # noqa: E402
from winkickoff.core.deps import Resolver  # noqa: E402
from winkickoff.core.profile import Profile  # noqa: E402

STAMP = "2026-09-25T00:00:00"


def office(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Office")
    profile.comment = (
        "Security and updatability for workgroups without a domain; equals the catalog defaults. Based on the "
        "tested answer file v0.2 with the later changes: browser policies, AI and telemetry off, OneDrive not "
        "installed, administrator UAC as in Windows (no prompt for Task Manager), no ASR rule for USB, no updates "
        "of other Microsoft products, drives not encrypted. Starter accounts Admin and User without passwords."
    )
    return profile


def strict(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Strict")
    profile.comment = (
        "Office plus restrictions that may disturb old programs: Controlled Folder Access in block mode, SmartScreen "
        "blocks programs without a reputation, the ASR prevalence rule blocks, unsigned programs from USB do not run, "
        "UAC always asks the administrator, updates of other Microsoft products are on, NetBIOS is off, the VBScript "
        "engine is removed. Test on one PC before a wide rollout."
    )
    resolver = Resolver(catalog)
    profile.set_param("defender.controlled-folder-access", "mode", 1)
    profile.set_param("defender.smartscreen-shell", "level", "Block")
    profile.set_param("asr.prevalence", "mode", 1)
    for rule_id in ("asr.usb-untrusted", "uac.admin-always-notify", "update.other-microsoft-products",
                    "network.netbios-off", "scripts.remove-vbscript"):
        resolver.enable(profile, rule_id)
    return profile


def laptop(catalog: Catalog) -> Profile:
    profile = Profile.from_catalog(catalog, name="Laptop")
    profile.comment = (
        "Office for laptops: the screen locks after 10 minutes of inactivity. As in every preset, the drive is not "
        "encrypted by itself: BitLocker is turned on separately, together with the escrow of recovery keys and "
        "user passwords."
    )
    profile.set_param("accounts.inactivity-lock", "seconds", 600)
    return profile


# Home: the setup screens of Office (hardware checks bypassed, no Microsoft account or network screens,
# BitLocker prevented) with the removal of extra apps and the user privacy settings, without the WinKickOff
# protection set (only Defender notifications and Delivery Optimization stay) and without .NET 3.5, printing,
# region and language rules. An allowlist: a rule added to the catalog later stays off in Home until it is added here.
HOME_RULES = (
    "install.bypass-tpm", "install.bypass-secureboot", "install.bypass-cpu", "install.bypass-ram",
    "install.bypass-storage", "install.bypass-nro",
    "oobe.hide-eula", "oobe.hide-oem-registration", "oobe.hide-online-account", "oobe.hide-wireless",
    "oobe.protect-your-pc",
    "update.delivery-optimization-lan", "defender.notifications", "remote.assistance-off",
    "encryption.prevent-auto-bitlocker", "accounts.block-aad-join",
    "privacy.telemetry-minimal", "privacy.consumer-content", "privacy.copilot-recall-off", "privacy.widgets-off",
    "privacy.web-search-off", "system.long-paths", "telemetry.app-telemetry-off",
    "ads.lock-screen-spotlight-off", "ads.account-notifications-off", "ads.advertising-id-user-off",
    "search.user-cloud-off", "speech.online-user-off", "speech.narrator-online-off", "speech.narrator-extensions-off",
    "apps.remove-quick-assist",
    "apps.remove.bing-search", "apps.remove.bing-news", "apps.remove.bing-weather", "apps.remove.get-help",
    "apps.remove.get-started", "apps.remove.feedback-hub", "apps.remove.3d-viewer", "apps.remove.mixed-reality",
    "apps.remove.solitaire", "apps.remove.xbox-gaming-app", "apps.remove.xbox-app", "apps.remove.xbox-game-overlay",
    "apps.remove.xbox-gaming-overlay", "apps.remove.xbox-identity", "apps.remove.xbox-tcui", "apps.remove.maps",
    "apps.remove.people", "apps.remove.phone-link", "apps.remove.power-automate", "apps.remove.todo",
    "apps.remove.family", "apps.remove.dev-home", "apps.remove.clipchamp", "apps.remove.teams", "apps.remove.skype",
    "apps.remove.office-hub", "apps.remove.outlook-new", "apps.remove.mail-calendar", "apps.remove.copilot",
    "apps.remove.copilot-provider", "apps.remove.cortana", "apps.remove.onedrive",
    "onedrive.kfm-block",
    "default-user.show-file-extensions", "default-user.no-sync-provider-ads", "default-user.no-consumer-content",
    "default-user.copilot-off", "default-user.http-accept-language-optout",
    "nav.launch-to-this-pc",
)


def home(catalog: Catalog) -> Profile:
    unknown = sorted(set(HOME_RULES) - set(catalog.rules))
    if unknown:
        raise SystemExit("HOME_RULES names rules that are not in the catalog: " + ", ".join(unknown))
    profile = Profile.from_catalog(catalog, name="Home")
    profile.comment = (
        "A lighter setup for home PCs: the setup screens of Office (hardware checks bypassed, no Microsoft "
        "account or network screens, BitLocker prevented), extra apps, OneDrive and Quick Assist removed, ads, "
        "widgets, web search, Copilot and Recall off, minimal telemetry, file extensions shown, File Explorer opens "
        "This PC; the product key and the edition are chosen during installation. The WinKickOff protection set is not "
        "applied: "
        "the UAC, LSA, Defender (except visible notifications), ASR, SmartScreen, network, logging, update (except "
        "Delivery Optimization without the cloud), browser and post-installation rules are off and Windows keeps its "
        "defaults. Also off: .NET Framework 3.5 from the media, the automatic Print Spooler start, the user region, "
        "the input language list and the display language pin, AutoRun of removable media, and the AI settings of "
        "Notepad, Paint, Office and Edge. Check shows the baseline rules that are off. Use Office for work PCs."
    )
    for rule_id, state in profile.rules.items():
        state.enabled = rule_id in HOME_RULES
    profile.set_param("update.delivery-optimization-lan", "mode", 99)
    profile.set_param("privacy.telemetry-minimal", "level", 0)
    profile.install.update(product_key_mode="ask", product_key="")
    return profile


def write(profile: Profile, catalog: Catalog, path: Path) -> None:
    profile.created = STAMP
    profile.modified = STAMP
    text = json.dumps(profile.to_dict(catalog), ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\r\n")
    print(f"written {path.relative_to(ROOT)}")


def main() -> None:
    catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
    write(office(catalog), catalog, ROOT / "profiles" / "preset-office.json")
    write(strict(catalog), catalog, ROOT / "profiles" / "preset-strict.json")
    write(laptop(catalog), catalog, ROOT / "profiles" / "preset-laptop.json")
    write(home(catalog), catalog, ROOT / "profiles" / "preset-home.json")


if __name__ == "__main__":
    main()
