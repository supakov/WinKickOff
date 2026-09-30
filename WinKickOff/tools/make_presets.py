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
sys.path.insert(0, str(ROOT / "tools"))

from winkickoff.core.catalog import Catalog, load_catalog  # noqa: E402
from winkickoff.core.deps import Resolver  # noqa: E402
from winkickoff.core.profile import Profile  # noqa: E402

import memstechtips as memstechtips_map  # noqa: E402

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


def memstechtips(catalog: Catalog) -> Profile:
    profile, _ = memstechtips_map.load(catalog)
    profile.comment = (
        "The original UnattendedWinstall answer file (memstechtips, Appendix A) carried over: the rules whose actions "
        "are in the original and do not contradict it are on. The product key is asked during installation. "
        "Baseline rules of WinKickOff that the original lacks or contradicts are off: read the warnings before use. "
        "What is added beyond the original, what is not carried over and why: docs/technical/memstechtips-profile.md."
    )
    return profile


def memstechtips_report(catalog: Catalog) -> str:
    profile, facts = memstechtips_map.load(catalog)
    return memstechtips_map.report(catalog, profile, facts)


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
    write(memstechtips(catalog), catalog, ROOT / "profiles" / "preset-memstechtips.json")
    memstechtips_map.REPORT.write_text(memstechtips_report(catalog), encoding="utf-8", newline="\r\n")
    print(f"written {memstechtips_map.REPORT.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
