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
PRESETS = {"preset-office.json": "office", "preset-strict.json": "strict"}


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

    def test_presets_hold_no_passwords(self) -> None:
        for file_name in PRESETS:
            profile, _ = Profile.load(ROOT / "profiles" / file_name, self.catalog)
            self.assertTrue(all(not a.password for a in profile.accounts), file_name)


if __name__ == "__main__":
    unittest.main()
