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
    "preset-home.json": "home",
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

    def test_laptop_locks_sooner(self) -> None:
        laptop, _ = Profile.load(ROOT / "profiles" / "preset-laptop.json", self.catalog)
        self.assertEqual(laptop.param(self.catalog, "accounts.inactivity-lock", "seconds"), 600)
        self.assertFalse(has_errors(validate_profile(laptop, self.catalog, self.keyboards)))
        office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        self.assertEqual({d.key for d in office.diff(laptop, self.catalog)}, {"accounts.inactivity-lock.seconds"})

    def test_device_encryption_is_prevented_in_every_preset(self) -> None:
        # 28.09.2026: BitLocker stays off everywhere; it comes later together with key escrow and user passwords
        for file_name in PRESETS:
            with self.subTest(preset=file_name):
                profile, _ = Profile.load(ROOT / "profiles" / file_name, self.catalog)
                self.assertTrue(profile.is_enabled("encryption.prevent-auto-bitlocker"))
        issues = validate_profile(Profile.from_catalog(self.catalog), self.catalog, self.keyboards)
        self.assertFalse(any(i.target == "encryption.prevent-auto-bitlocker" for i in issues))

    def test_home_is_the_allowlist(self) -> None:
        home, _ = Profile.load(ROOT / "profiles" / "preset-home.json", self.catalog)
        self.assertEqual(home.name, "Home")
        self.assertTrue(set(self.maker.HOME_RULES) <= set(self.catalog.rules))
        self.assertEqual(set(home.enabled_ids()), set(self.maker.HOME_RULES))
        # installation, OOBE, app removal and user privacy rules are on
        for rule_id in ("install.bypass-tpm", "install.bypass-nro", "accounts.block-aad-join",
                        "apps.remove-quick-assist", "default-user.show-file-extensions",
                        "privacy.telemetry-minimal", "privacy.copilot-recall-off", "privacy.consumer-content"):
            self.assertTrue(home.is_enabled(rule_id), rule_id)
        # the WinKickOff protection set is not applied: Windows keeps its defaults
        for rule_id in ("defender.realtime", "uac.baseline", "apps.xbox-services-off", "edge.baseline",
                        "edge.diagnostic-data-off", "post-oobe.delete-answer-file-copies"):
            self.assertFalse(home.is_enabled(rule_id), rule_id)
        office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", self.catalog)
        self.assertEqual(set(home.enabled_ids()) - set(office.enabled_ids()), {"nav.launch-to-this-pc"})
        self.assertEqual(home.param(self.catalog, "update.delivery-optimization-lan", "mode"), 99)
        self.assertEqual(home.param(self.catalog, "privacy.telemetry-minimal", "level"), 0)
        self.assertEqual(home.install["product_key_mode"], "ask")
        for rule_id in home.enabled_ids():
            for required in self.catalog.rules[rule_id].requires:
                self.assertTrue(home.is_enabled(required), f"{rule_id} requires {required}")

    def test_build_takes_every_preset(self) -> None:
        # tools/build.ps1 once listed two presets by name and the portable build lost the other two
        script = (ROOT / "tools" / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("-Filter 'preset-*.json'", script)
        for file_name in PRESETS:
            self.assertNotIn(file_name, script)

    def test_presets_hold_no_passwords(self) -> None:
        for file_name in PRESETS:
            profile, _ = Profile.load(ROOT / "profiles" / file_name, self.catalog)
            self.assertTrue(all(not a.password for a in profile.accounts), file_name)


if __name__ == "__main__":
    unittest.main()
