"""core/settings.py: settings.json next to the program; damaged files never stop the program."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from winkickoff.core.settings import MAX_RECENT, Settings


class SettingsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.file = self.root / "settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_gives_defaults(self) -> None:
        self.assertEqual(Settings.load(self.file), Settings())

    def test_damaged_file_gives_defaults(self) -> None:
        for text in ("{not json", "[1, 2]", '{"recent": "x", "geometry": "huge"}'):
            with self.subTest(text=text):
                self.file.write_text(text, encoding="utf-8")
                if text.startswith("{\""):
                    settings = Settings.load(self.file)  # valid JSON with bad values: silently cleaned
                else:
                    with self.assertLogs("winkickoff.core.settings", level="WARNING"):
                        settings = Settings.load(self.file)
                self.assertEqual(settings.recent, [])
                self.assertEqual(settings.geometry, "")

    def test_round_trip_without_leftovers(self) -> None:
        settings = Settings(geometry="1260x800+10+20", last_profile="profiles\\Профіль.json")
        settings.add_recent(self.root / "profiles" / "Профіль.json", self.root)
        settings.save(self.file)
        self.assertEqual(Settings.load(self.file), settings)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["settings.json"])

    def test_recent_is_relative_inside_the_program_folder(self) -> None:
        settings = Settings()
        inside = self.root / "profiles" / "a.json"
        outside = Path("C:/Elsewhere/b.xml")
        settings.add_recent(inside, self.root)
        settings.add_recent(outside, self.root)
        self.assertEqual(settings.recent[1], str(Path("profiles/a.json")))
        self.assertTrue(Path(settings.recent[0]).is_absolute())
        self.assertEqual(Settings.resolve(settings.recent[1], self.root), self.root / "profiles" / "a.json")

    def test_recent_is_unique_and_limited(self) -> None:
        settings = Settings()
        for index in range(MAX_RECENT + 3):
            settings.add_recent(self.root / f"p{index}.json", self.root)
        settings.add_recent(self.root / "P3.JSON", self.root)  # same file, other case: moves to the top
        self.assertEqual(len(settings.recent), MAX_RECENT)
        self.assertEqual(settings.recent[0], "P3.JSON")
        self.assertEqual(sum(1 for r in settings.recent if r.lower() == "p3.json"), 1)
        settings.forget(self.root / "p3.json", self.root)
        self.assertNotIn("P3.JSON", settings.recent)


if __name__ == "__main__":
    unittest.main()
