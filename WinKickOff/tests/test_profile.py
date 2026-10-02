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


if __name__ == "__main__":
    unittest.main()
