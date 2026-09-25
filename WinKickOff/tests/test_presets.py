"""profiles/preset-*.json: presets load cleanly and match what tools/make_presets.py produces."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import Profile
from winkickoff.core.resources import Resources
from winkickoff.core.validate import has_errors, validate_profile

ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "preset-office.json": "office",
    "preset-strict.json": "strict",
    "preset-laptop.json": "laptop",
    "preset-memstechtips.json": "memstechtips",
}


def load_maker():
    spec = importlib.util.spec_from_file_location("make_presets", ROOT / "tools" / "make_presets.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PresetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.keyboards = Resources.load(ROOT / "resources").keyboards
        cls.maker = load_maker()

    def test_presets_are_up_to_date(self) -> None:
        for file_name, factory in PRESETS.items():
            with self.subTest(preset=file_name):
                expected = getattr(self.maker, factory)(self.catalog)
                expected.created = expected.modified = self.maker.STAMP
                on_disk = json.loads((ROOT / "profiles" / file_name).read_text(encoding="utf-8"))
                self.assertEqual(
                    on_disk, expected.to_dict(self.catalog),
                    f"{file_name} is stale: run python tools/make_presets.py",
                )

    def test_presets_load_without_warnings_or_errors(self) -> None:
        for file_name in PRESETS:
            with self.subTest(preset=file_name):
                profile, warnings = Profile.load(ROOT / "profiles" / file_name, self.catalog)
                self.assertEqual(warnings, [])
                issues = validate_profile(profile, self.catalog, self.keyboards)
                self.assertFalse(has_errors(issues), [i.message for i in issues if i.level == "error"])

    def test_office_equals_catalog_defaults(self) -> None:
        office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        defaults = Profile.from_catalog(self.catalog)
        self.assertEqual(office.enabled_ids(), defaults.enabled_ids())
        for rule_id in self.catalog.rules:
            self.assertEqual(office.params_for(self.catalog, rule_id), defaults.params_for(self.catalog, rule_id), rule_id)

    def test_strict_is_stricter(self) -> None:
        strict, _ = Profile.load(ROOT / "profiles" / "preset-strict.json", self.catalog)
        self.assertTrue(strict.is_enabled("network.netbios-off"))
        self.assertTrue(strict.is_enabled("scripts.remove-vbscript"))
        self.assertEqual(strict.param(self.catalog, "defender.smartscreen-shell", "level"), "Block")
        office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        self.assertTrue(set(office.enabled_ids()) <= set(strict.enabled_ids()))

    def test_laptop_locks_sooner_and_allows_device_encryption(self) -> None:
        laptop, _ = Profile.load(ROOT / "profiles" / "preset-laptop.json", self.catalog)
        self.assertEqual(laptop.param(self.catalog, "accounts.inactivity-lock", "seconds"), 600)
        self.assertFalse(laptop.is_enabled("encryption.prevent-auto-bitlocker"))
        issues = validate_profile(laptop, self.catalog, self.keyboards)
        self.assertFalse(has_errors(issues))
        warning = [i.message for i in issues if i.target == "encryption.prevent-auto-bitlocker" and i.level == "warning"]
        self.assertTrue(any("manage-bde" in m for m in warning), warning)
        office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        self.assertEqual({d.key for d in office.diff(laptop, self.catalog)},
                         {"encryption.prevent-auto-bitlocker", "accounts.inactivity-lock.seconds"})

    def test_memstechtips_follows_the_original(self) -> None:
        mtt, _ = Profile.load(ROOT / "profiles" / "preset-memstechtips.json", self.catalog)
        for rule_id in ("install.bypass-tpm", "install.bypass-nro", "accounts.block-aad-join",
                        "apps.remove-quick-assist", "default-user.show-file-extensions"):
            self.assertTrue(mtt.is_enabled(rule_id), rule_id)
        # partly present without contradictions: on; AllowTelemetry 0 of the original acts as 1 on Pro
        for rule_id in ("privacy.telemetry-minimal", "privacy.copilot-recall-off", "privacy.consumer-content"):
            self.assertTrue(mtt.is_enabled(rule_id), rule_id)
        # absent from the original, or contradicting it (UAC without prompts, Xbox services on demand)
        for rule_id in ("defender.realtime", "uac.baseline", "apps.xbox-services-off", "edge.baseline",
                        "edge.diagnostic-data-off"):
            self.assertFalse(mtt.is_enabled(rule_id), rule_id)
        self.assertEqual(mtt.install["product_key_mode"], "ask")
        for rule_id in mtt.enabled_ids():
            for required in self.catalog.rules[rule_id].requires:
                self.assertTrue(mtt.is_enabled(required), f"{rule_id} requires {required}")

    def test_memstechtips_report_is_up_to_date(self) -> None:
        on_disk = self.maker.memstechtips_map.REPORT.read_bytes().decode("utf-8")
        expected = self.maker.memstechtips_report(self.catalog).replace("\n", "\r\n")
        self.assertEqual(on_disk, expected, "the memstechtips report is stale: run python tools/make_presets.py")

    def test_presets_hold_no_passwords(self) -> None:
        for file_name in PRESETS:
            profile, _ = Profile.load(ROOT / "profiles" / file_name, self.catalog)
            self.assertTrue(all(not a.password for a in profile.accounts), file_name)


if __name__ == "__main__":
    unittest.main()
