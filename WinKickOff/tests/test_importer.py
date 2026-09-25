"""core/importer.py: a built answer file gives back the profile it was built from."""

from __future__ import annotations

import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.deps import Resolver
from winkickoff.core.importer import ImportFailed, import_xml
from winkickoff.core.profile import Account, Profile
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT.parent / "autounattend.xml"


class ImporterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.renderer = Renderer(cls.catalog, ROOT / "templates", Resources.load(ROOT / "resources").keyboards)

    def test_round_trip(self) -> None:
        profile = Profile.from_catalog(self.catalog, name="Бухгалтерия")
        profile.comment = "Проверка ]]> внутри CDATA"
        Resolver(self.catalog).enable(profile, "network.netbios-off")
        profile.set_param("defender.smartscreen-shell", "level", "Block")
        profile.accounts.append(Account("Kasa", "Каса", "Users"))
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

    @unittest.skipUnless(V02.exists(), "v0.2 answer file not found")
    def test_hand_written_file_is_refused_with_a_reason(self) -> None:
        with self.assertRaises(ImportFailed) as ctx:
            import_xml(V02.read_text(encoding="utf-8"), self.catalog)
        self.assertIn("встроенного профиля", str(ctx.exception))

    def test_not_xml(self) -> None:
        with self.assertRaises(ImportFailed):
            import_xml("not xml at all", self.catalog)


if __name__ == "__main__":
    unittest.main()
