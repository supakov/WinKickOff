"""core/importer.py: a built answer file gives back the profile it was built from."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.deps import Resolver
from winkickoff.core.importer import IMPORTED_NAME, ImportFailed, import_xml
from winkickoff.core.profile import Account, Profile
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources

from v02_actions import V02, reference_profile

ROOT = Path(__file__).resolve().parents[1]


class ImporterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.keyboards = Resources.load(ROOT / "resources").keyboards
        cls.renderer = Renderer(cls.catalog, ROOT / "templates", cls.keyboards)

    def test_round_trip(self) -> None:
        profile = Profile.from_catalog(self.catalog, name="Профиль")
        profile.comment = "Проверка ]]> внутри CDATA"
        Resolver(self.catalog).enable(profile, "network.netbios-off")
        profile.set_param("defender.smartscreen-shell", "level", "Block")
        profile.accounts.append(Account("Operator", "Оператор", "Users"))
        profile.languages["input"] = ["uk-UA", "en-US"]
        xml = self.renderer.build(profile, app_version="test").xml

        restored, warnings = import_xml(xml, self.catalog)
        self.assertEqual(warnings, [])
        self.assertEqual(restored.name, profile.name)
        self.assertEqual(restored.comment, profile.comment)
        self.assertEqual(restored.enabled_ids(), profile.enabled_ids())
        self.assertEqual(restored.param(self.catalog, "defender.smartscreen-shell", "level"), "Block")
        self.assertEqual([a.to_dict() for a in restored.accounts], [a.to_dict() for a in profile.accounts])
        self.assertEqual(restored.languages, profile.languages)
        self.assertEqual(restored.install, profile.install)
        self.assertIsNone(restored.path)

    def test_rebuild_of_imported_profile_is_identical(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        first = self.renderer.build(profile, app_version="test").xml
        restored, _ = import_xml(first, self.catalog)
        self.assertEqual(self.renderer.build(restored, app_version="test").xml, first)

    def assert_same_settings(self, restored: Profile, expected: Profile) -> None:
        for rule_id in self.catalog.rules:
            self.assertEqual(restored.is_enabled(rule_id), expected.is_enabled(rule_id), rule_id)
            self.assertEqual(restored.params_for(self.catalog, rule_id), expected.params_for(self.catalog, rule_id), rule_id)
        self.assertEqual(restored.install, expected.install)
        self.assertEqual(restored.languages, expected.languages)
        self.assertEqual([a.to_dict() for a in restored.accounts], [a.to_dict() for a in expected.accounts])

    @unittest.skipUnless(V02.exists(), "v0.2 answer file not found")
    def test_hand_written_v02_gives_the_reference_profile(self) -> None:
        office = reference_profile(self.catalog)
        restored, warnings = import_xml(V02.read_text(encoding="utf-8"), self.catalog, self.keyboards)
        self.assertEqual(restored.name, IMPORTED_NAME)
        self.assert_same_settings(restored, office)
        self.assertIn("file's actions", warnings[0])

    def test_build_without_embedded_profile_is_imported_by_actions(self) -> None:
        for preset in ("preset-office.json", "preset-strict.json"):
            with self.subTest(preset=preset):
                source, _ = Profile.load(ROOT / "profiles" / preset, self.catalog)
                xml = self.renderer.build(source, app_version="test").xml
                stripped = re.sub(r"<Profile[ >].*?</Profile>", "", xml, flags=re.S)
                self.assertNotIn("<Profile", stripped)
                restored, warnings = import_xml(stripped, self.catalog, self.keyboards)
                self.assertEqual(restored.name, IMPORTED_NAME)
                self.assert_same_settings(restored, source)

    def test_disabled_rule_in_the_file_is_disabled_after_import(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        Resolver(self.catalog).disable(profile, "defender.pua")
        xml = re.sub(r"<Profile[ >].*?</Profile>", "", self.renderer.build(profile, app_version="test").xml, flags=re.S)
        restored, _ = import_xml(xml, self.catalog, self.keyboards)
        self.assertFalse(restored.is_enabled("defender.pua"))
        self.assertTrue(restored.is_enabled("defender.realtime"))

    def test_rules_of_the_user_scripts_are_imported_by_actions(self) -> None:
        # registry rules of Setup-User.ps1 (first sign-in) and the sign-in screen keys come back with their parameters
        profile = Profile.from_catalog(self.catalog)
        resolver = Resolver(self.catalog)
        for rule_id in ("nav.libraries", "nav.network-hidden", "default-user.input-switch-keys"):
            resolver.enable(profile, rule_id)
        profile.set_param("default-user.input-switch-keys", "language", "2")
        profile.set_param("default-user.input-switch-keys", "layout", "1")
        xml = re.sub(r"<Profile[ >].*?</Profile>", "", self.renderer.build(profile, app_version="test").xml, flags=re.S)
        restored, _ = import_xml(xml, self.catalog, self.keyboards)
        self.assert_same_settings(restored, profile)

    def test_file_without_accounts_asks_for_one(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        profile.install["account_mode"] = "ask"
        xml = re.sub(r"<Profile[ >].*?</Profile>", "", self.renderer.build(profile, app_version="test").xml, flags=re.S)
        restored, _ = import_xml(xml, self.catalog, self.keyboards)
        self.assertEqual(restored.install["account_mode"], "ask")
        # a file without the oobeSystem pass (so without Shell-Setup) creates no account either
        full = self.renderer.build(Profile.from_catalog(self.catalog), app_version="test").xml
        bare = re.sub(r'<settings pass="oobeSystem">.*?</settings>', "",
                      re.sub(r"<Profile[ >].*?</Profile>", "", full, flags=re.S), flags=re.S)
        self.assertIn("<UserAccounts>", full)
        self.assertNotIn("<UserAccounts>", bare)
        restored, _ = import_xml(bare, self.catalog, self.keyboards)
        self.assertEqual(restored.install["account_mode"], "ask")

    def test_not_xml(self) -> None:
        with self.assertRaises(ImportFailed):
            import_xml("not xml at all", self.catalog)

    def test_not_an_answer_file(self) -> None:
        with self.assertRaises(ImportFailed):
            import_xml("<root/>", self.catalog)


if __name__ == "__main__":
    unittest.main()
