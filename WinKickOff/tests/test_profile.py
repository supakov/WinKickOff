"""core/profile.py: defaults, JSON round trip, unknown rules, params, diff."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import FORMAT_VERSION, Account, Profile

ROOT = Path(__file__).resolve().parents[1]


class ProfileTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)

    def test_defaults_match_catalog(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        self.assertEqual(set(profile.rules), set(self.catalog.rules))
        for rule in self.catalog.rules.values():
            self.assertEqual(profile.is_enabled(rule.id), rule.default, rule.id)
        self.assertEqual(profile.param(self.catalog, "accounts.inactivity-lock", "seconds"), 900)
        self.assertEqual([a.name for a in profile.accounts], ["Admin", "User"])
        self.assertEqual(profile.languages["input"], ["en-US", "uk-UA", "ru-UA"])

    def test_a_failed_save_keeps_the_file_and_half_characters_are_saved(self) -> None:
        from unittest import mock

        from winkickoff.core.i18n import tr
        from winkickoff.core.validate import HALF_CHARACTER, validate_profile

        profile = Profile.from_catalog(self.catalog, name="Test")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            profile.save(path, self.catalog)
            before = path.read_bytes()
            profile.comment = "changed"
            with mock.patch("winkickoff.core.profile.os.replace", side_effect=PermissionError("busy")):
                with self.assertRaises(OSError):
                    profile.save(path, self.catalog)
            self.assertEqual(path.read_bytes(), before)  # the old file is whole
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["t.json"])  # no temporary file is left
            profile.comment = "smile " + chr(0xD83D)  # half of an emoji, as a Tk entry leaves it after a Backspace
            profile.accounts[0].display_name = chr(0xDE00)
            issues = validate_profile(profile, self.catalog)
            self.assertEqual({i.target for i in issues if i.message == tr(HALF_CHARACTER)}, {"profile", "accounts[0]"})
            profile.save(path, self.catalog)  # before 08.10.2026 this left an empty file
            loaded, _ = Profile.load(path, self.catalog)
            self.assertEqual(loaded.comment, "smile " + chr(0xFFFD))
            self.assertTrue(path.read_bytes().endswith(b"}\r\n"))

    def test_round_trip(self) -> None:
        profile = Profile.from_catalog(self.catalog, name="Тест")
        profile.rules["network.netbios-off"].enabled = True
        profile.set_param("accounts.inactivity-lock", "seconds", 600)
        profile.accounts.append(Account("Operator", "Оператор", "Users"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            profile.save(path, self.catalog)
            raw = path.read_text(encoding="utf-8")
            self.assertIn('"Оператор"', raw)  # cyrillic not escaped
            self.assertTrue(raw.startswith("{"))
            loaded, warnings = Profile.load(path, self.catalog)
        self.assertEqual(warnings, [])
        self.assertEqual(loaded.diff(profile), [])
        self.assertTrue(loaded.is_enabled("network.netbios-off"))
        self.assertEqual(loaded.param(self.catalog, "accounts.inactivity-lock", "seconds"), 600)
        self.assertEqual(loaded.accounts[2].display_name, "Оператор")

    def test_rules_written_in_catalog_order(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        data = profile.to_dict(self.catalog)
        self.assertEqual(list(data["rules"]), self.catalog.order)
        self.assertEqual(data["format_version"], FORMAT_VERSION)

    def test_unknown_rule_survives_and_new_rule_gets_default(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        data = profile.to_dict(self.catalog)
        data["rules"]["ghost.rule"] = {"enabled": True}
        del data["rules"]["defender.pua"]
        loaded, warnings = Profile.from_dict(data, self.catalog)
        self.assertIn("ghost.rule", loaded.unknown)
        self.assertTrue(loaded.is_enabled("defender.pua"))
        self.assertTrue(any("defender.pua" in w for w in warnings))
        self.assertTrue(any("ghost.rule" in w for w in warnings))
        self.assertIn("ghost.rule", loaded.to_dict(self.catalog)["unknown"])

    def test_account_mode(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        self.assertEqual(profile.install["account_mode"], "file")
        self.assertEqual([a.name for a in profile.answer_file_accounts()], ["Admin", "User"])
        profile.install["account_mode"] = "ask"
        self.assertEqual(profile.answer_file_accounts(), [])  # the file holds no account ...
        self.assertEqual(len(profile.accounts), 2)  # ... and the form keeps them for the way back
        loaded, warnings = Profile.from_dict(profile.to_dict(self.catalog), self.catalog)
        self.assertTrue(loaded.asks_for_account())
        self.assertEqual(warnings, [])

    def test_profiles_of_format_2_load_without_a_warning(self) -> None:
        data = Profile.from_catalog(self.catalog).to_dict(self.catalog)
        data["format_version"] = 2
        del data["install"]["account_mode"]
        loaded, warnings = Profile.from_dict(data, self.catalog)
        self.assertEqual(warnings, [])
        self.assertFalse(loaded.asks_for_account())
        data["format_version"] = 4  # a newer program
        self.assertTrue(Profile.from_dict(data, self.catalog)[1])

    def test_unknown_entries_for_the_tree(self) -> None:
        profile = Profile.from_catalog(self.catalog)
        profile.unknown = {"zeta.rule": {"enabled": True, "params": {"n": 2}}, "admx.a.b": {"params": "bad"}, "admx.a.c": 7}
        # sorted by id; whatever the file holds, an entry is a state and a dictionary of parameters
        self.assertEqual(profile.unknown_entries(), [("admx.a.b", False, {}), ("admx.a.c", False, {}), ("zeta.rule", True, {"n": 2})])

    def test_old_profile_gets_new_rules_in_one_warning(self) -> None:
        # a profile saved before the browser section: its rules keep their states, new rules get the defaults
        data = Profile.from_catalog(self.catalog).to_dict(self.catalog)
        data["rules"]["uac.admin-always-notify"] = {"enabled": True}
        new = [r for r in self.catalog.order if r.split(".")[0] in ("edge", "chrome", "brave")]
        for rule_id in new:
            del data["rules"][rule_id]
        loaded, warnings = Profile.from_dict(data, self.catalog)
        self.assertTrue(loaded.is_enabled("uac.admin-always-notify"))  # a saved state wins over a new default
        about_new = [w for w in warnings if "new catalog rules" in w]
        self.assertEqual(len(about_new), 1, warnings)
        self.assertIn(str(len(new)), about_new[0])
        for rule_id in new:
            self.assertEqual(loaded.is_enabled(rule_id), self.catalog.rules[rule_id].default)

    def test_diff_reports_rule_param_and_install_changes(self) -> None:
        a = Profile.from_catalog(self.catalog)
        b = a.copy()
        b.rules["defender.pua"].enabled = False
        b.set_param("update.defer-feature", "days", 30)
        b.install["time_zone"] = "UTC"
        kinds = {(d.kind, d.key) for d in a.diff(b)}
        self.assertIn(("rule", "defender.pua"), kinds)
        self.assertIn(("param", "update.defer-feature.days"), kinds)
        self.assertIn(("install", "time_zone"), kinds)

    def test_diff_with_catalog_compares_effective_values(self) -> None:
        a = Profile.from_catalog(self.catalog)
        b = a.copy()
        b.set_param("accounts.inactivity-lock", "seconds", 900)  # explicit value equal to the default
        self.assertTrue(any(d.kind == "param" for d in a.diff(b)))  # stored overrides differ
        self.assertEqual(a.diff(b, self.catalog), [])  # effective values are the same
        b.set_param("accounts.inactivity-lock", "seconds", 600)
        self.assertEqual([(d.key, d.before, d.after) for d in a.diff(b, self.catalog)],
                         [("accounts.inactivity-lock.seconds", 900, 600)])

    def test_catalog_02_fields_are_migrated(self) -> None:
        data = Profile.from_catalog(self.catalog).to_dict(self.catalog)
        data["languages"]["geo_id"] = 176  # an old profile with the country in the languages section
        data["install"]["iso_language"] = "uk-UA"
        profile, warnings = Profile.from_dict(data, self.catalog)
        self.assertEqual(profile.param(self.catalog, "default-user.region", "geo_id"), "176")
        self.assertNotIn("geo_id", profile.languages)
        self.assertNotIn("iso_language", profile.install)
        self.assertTrue(any("geo_id" in w for w in warnings))
        self.assertTrue(any("iso_language" in w for w in warnings))

        data["languages"]["geo_id"] = 241  # the default: nothing to carry over, no warning
        del data["install"]["iso_language"]
        profile, warnings = Profile.from_dict(data, self.catalog)
        self.assertNotIn("geo_id", profile.rules["default-user.region"].params)
        self.assertEqual(warnings, [])

    def test_bad_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps([1, 2]), encoding="utf-8")
            with self.assertRaises(ValueError):
                Profile.load(path, self.catalog)

    def test_a_profile_of_an_unexpected_shape_loads_with_warnings_or_raises_value_error(self) -> None:
        """A profile may come from someone else: a field of a wrong type falls back to its default, never an error
        that the window does not expect."""
        good = Profile.from_catalog(self.catalog).to_dict(self.catalog)
        cases = {
            "format_version": {},
            "accounts": ["Admin", {"name": "Operator", "display_name": "Operator", "group": "Users"}],
            "install": ["x"],
            "languages": {"input": "en-US", "ui_language": 5},
            "rules": {"defender.pua": "on", "accounts.inactivity-lock": {"enabled": "yes", "params": {"seconds": {"a": 1}}},
                      "defender.smartscreen-shell": {"enabled": True, "params": {"level": ["Block"]}}},
        }
        for key, value in cases.items():
            with self.subTest(field=key):
                data = dict(good, **{key: value})
                profile, warnings = Profile.from_dict(data, self.catalog)
                self.assertIsInstance(profile, Profile)
        profile, warnings = Profile.from_dict(dict(good, rules=cases["rules"]), self.catalog)
        self.assertEqual(profile.param(self.catalog, "accounts.inactivity-lock", "seconds"), 900)
        self.assertEqual(profile.param(self.catalog, "defender.smartscreen-shell", "level"), "Warn")
        self.assertTrue(any("wrong type" in w for w in warnings))
        profile, warnings = Profile.from_dict(dict(good, accounts=cases["accounts"]), self.catalog)
        self.assertEqual([a.name for a in profile.accounts], ["Operator"])
        self.assertEqual(Profile.from_dict(dict(good, languages=cases["languages"]), self.catalog)[0].languages["input"],
                         ["en-US", "uk-UA", "ru-UA"])
        for broken in ([], "text"):
            with self.assertRaises(ValueError):
                Profile.from_dict(broken, self.catalog)  # type: ignore[arg-type]

    def test_the_name_and_the_author_stay_on_one_line(self) -> None:
        data = dict(Profile.from_catalog(self.catalog).to_dict(self.catalog), name="Office\nWrite-Output 'x'",
                    author="A\r\nB" + chr(0x2028) + "C", comment="line 1\nline 2")
        profile, _ = Profile.from_dict(data, self.catalog)
        self.assertEqual((profile.name, profile.author), ("Office Write-Output 'x'", "A  B C"))
        self.assertEqual(profile.comment, "line 1\nline 2")  # a comment may have lines


if __name__ == "__main__":
    unittest.main()
