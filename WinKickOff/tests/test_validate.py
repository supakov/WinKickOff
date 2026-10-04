"""core/validate.py: profile checks before the build and answer file checks after it."""

from __future__ import annotations

import json
import re
import tempfile
import textwrap
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import Account, Profile
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.validate import check_account_name, has_errors, validate_catalog, validate_profile, validate_xml

from v02_actions import V02

ROOT = Path(__file__).resolve().parents[1]
BAD_PROFILES = Path(__file__).resolve().parent / "profiles"


def errors(issues, target: str | None = None) -> list[str]:
    return [i.message for i in issues if i.level == "error" and (target is None or i.target == target)]


class ProfileValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.keyboards = Resources.load(ROOT / "resources").keyboards

    def setUp(self) -> None:
        self.profile = Profile.from_catalog(self.catalog)

    def check(self):
        return validate_profile(self.profile, self.catalog, self.keyboards)

    def test_catalog_defaults_have_no_errors(self) -> None:
        self.assertEqual(errors(self.check()), [])

    def test_custom_key_must_look_like_a_key(self) -> None:
        self.profile.install["product_key_mode"] = "custom"
        self.profile.install["product_key"] = "12345"
        self.assertTrue(errors(self.check(), "install.product_key"))
        self.profile.install["product_key"] = "abcde-fghij-klmno-pqrst-uvwxy"
        self.assertEqual(errors(self.check(), "install.product_key"), [])

    def test_generic_key_needs_a_known_edition(self) -> None:
        self.profile.install["edition"] = "Home"
        self.assertTrue(errors(self.check(), "install.edition"))
        self.profile.install["product_key_mode"] = "ask"
        self.assertEqual(errors(self.check(), "install.edition"), [])

    def test_time_zone_and_locales_are_required(self) -> None:
        self.profile.install["time_zone"] = " "
        self.profile.languages["user_locale"] = "Ukrainian"
        issues = self.check()
        self.assertTrue(errors(issues, "install.time_zone"))
        self.assertTrue(errors(issues, "languages.user_locale"))

    def test_unknown_input_language_is_an_error(self) -> None:
        self.profile.languages["input"] = ["en-US", "xx-XX"]
        self.assertTrue(errors(self.check(), "languages.input"))
        self.profile.languages["input"] = []
        self.assertTrue(errors(self.check(), "languages.input"))

    def test_enabled_rule_with_disabled_requirement_is_an_error(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if r.requires and r.default)
        self.profile.rules[rule.requires[0]].enabled = False  # bypasses the resolver on purpose
        self.assertTrue(errors(self.check(), rule.id))

    def test_disabled_baseline_rule_is_a_warning(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if r.level == "baseline" and not r.requires)
        dependents = [r for r in self.catalog.rules.values() if rule.id in r.requires]
        for other in dependents:
            self.profile.rules[other.id].enabled = False
        self.profile.rules[rule.id].enabled = False
        issues = self.check()
        self.assertIn("warning", {i.level for i in issues if i.target == rule.id})

    def test_param_out_of_range_is_an_error(self) -> None:
        rule, param = next(
            (r, p) for r in self.catalog.rules.values() for p in r.params.values() if p.type == "int" and p.max is not None
        )
        self.profile.set_param(rule.id, param.name, param.max + 1)
        self.assertTrue(errors(self.check(), rule.id))

    def test_enum_param_must_be_listed(self) -> None:
        rule, param = next((r, p) for r in self.catalog.rules.values() for p in r.params.values() if p.type == "enum")
        self.profile.set_param(rule.id, param.name, "no-such-value")
        self.assertTrue(errors(self.check(), rule.id))

    def test_accounts(self) -> None:
        self.profile.accounts = [Account("User", "User", "Users"), Account("user", "User 2", "Users")]
        issues = self.check()
        self.assertTrue(errors(issues, "accounts"))  # no administrator
        self.assertTrue(errors(issues, "accounts[1]"))  # duplicate, names are case-insensitive

    def test_account_asked_during_installation(self) -> None:
        self.profile.install["account_mode"] = "ask"
        self.profile.accounts = [Account("User", "User", "Users")]  # no administrator: not used in this mode
        issues = self.check()
        self.assertEqual(errors(issues), [])
        self.assertTrue(any(i.level == "info" and i.target == "accounts" for i in issues))
        for rule_id in ("oobe.hide-online-account", "install.bypass-nro"):
            self.profile.rules[rule_id].enabled = False
        warned = {i.target for i in self.check() if i.level == "warning"}
        self.assertLessEqual({"oobe.hide-online-account", "install.bypass-nro"}, warned)
        self.profile.install["account_mode"] = "later"
        self.assertTrue(errors(self.check(), "accounts"))

    def test_edition_chosen_during_installation_is_explained(self) -> None:
        self.profile.install["product_key_mode"] = "ask"
        self.assertTrue(any(i.level == "info" and i.target == "install.product_key_mode" for i in self.check()))

    def test_switch_keys_may_not_be_the_same(self) -> None:
        rule_id = "default-user.input-switch-keys"
        self.profile.rules[rule_id].enabled = True
        self.profile.set_param(rule_id, "layout", "1")  # the language keys are "1" by default
        self.assertTrue(errors(self.check(), rule_id))
        self.profile.set_param(rule_id, "language", "3")
        self.profile.set_param(rule_id, "layout", "3")  # both "not assigned" is allowed
        self.assertEqual(errors(self.check(), rule_id), [])

    def test_password_is_only_a_warning(self) -> None:
        self.profile.accounts[0].password = "secret"
        issues = self.check()
        self.assertEqual(errors(issues), [])
        self.assertIn("warning", {i.level for i in issues if i.target == "accounts[0]"})

    def test_enabled_risky_rule_is_a_warning_with_its_risk(self) -> None:
        rule = next(r for r in self.catalog.rules.values() if r.level == "risky")
        for req in rule.requires:
            self.profile.rules[req].enabled = True
        self.profile.rules[rule.id].enabled = True
        warnings = [i.message for i in self.check() if i.level == "warning" and i.target == rule.id]
        self.assertTrue(any(rule.risk[:30] in m for m in warnings), warnings)

    def test_bad_profile_files(self) -> None:
        files = sorted(BAD_PROFILES.glob("bad-*.json"))
        self.assertGreaterEqual(len(files), 5)
        for path in files:
            with self.subTest(profile=path.name):
                expected = json.loads(path.read_text(encoding="utf-8"))["_expect"]
                profile, _ = Profile.load(path, self.catalog)
                issues = validate_profile(profile, self.catalog, self.keyboards)
                targets = {i.target for i in issues if i.level == "error"}
                self.assertTrue(set(expected) <= targets, f"expected errors on {expected}, got {sorted(targets)}")

    def test_account_names(self) -> None:
        self.assertIsNone(check_account_name("Admin"))
        self.assertIsNone(check_account_name("Оператор"))
        for bad in ("", "Administrator", "guest", "a/b", "x" * 21, "name.", " name"):
            self.assertIsNotNone(check_account_name(bad), bad)


class XmlValidationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        renderer = Renderer(catalog, ROOT / "templates", Resources.load(ROOT / "resources").keyboards)
        cls.xml = renderer.build(Profile.from_catalog(catalog), app_version="test").xml

    def assert_rejected(self, text: str, fragment: str) -> None:
        messages = errors(validate_xml(text))
        self.assertTrue(any(fragment in m for m in messages), messages)

    def test_build_is_clean(self) -> None:
        self.assertFalse(has_errors(validate_xml(self.xml)))

    @unittest.skipUnless(V02.exists(), "v0.2 answer file not found")
    def test_v02_is_clean(self) -> None:
        self.assertEqual(validate_xml(V02.read_text(encoding="utf-8")), [])  # no errors and no warnings

    def test_broken_xml(self) -> None:
        self.assert_rejected(self.xml[:-40], "XML")

    def test_comment_inside_component(self) -> None:
        self.assert_rejected(self.xml.replace("<RunSynchronous>", "<RunSynchronous><!-- note -->", 1), "Comment inside component")

    def test_command_longer_than_259(self) -> None:
        text = re.sub(r"<Path>[^<]*</Path>", "<Path>cmd.exe /c " + "x" * 260 + "</Path>", self.xml, count=1)
        self.assert_rejected(text, "longer than")

    def test_duplicate_order(self) -> None:
        text = self.xml.replace("<Order>2</Order>", "<Order>1</Order>", 1)
        self.assert_rejected(text, "Order")

    def test_incomplete_international_core(self) -> None:
        text = re.sub(r"<UserLocale>[^<]*</UserLocale>", "", self.xml)
        self.assert_rejected(text, "UserLocale")

    def test_bad_input_locale(self) -> None:
        text = re.sub(r"<InputLocale>[^<]*</InputLocale>", "<InputLocale>0409:0409;english</InputLocale>", self.xml)
        self.assert_rejected(text, "InputLocale")

    def test_no_administrator(self) -> None:
        self.assert_rejected(self.xml.replace("<Group>Administrators</Group>", "<Group>Users</Group>"), "Administrators")

    def test_accounts_without_groups_have_no_administrator(self) -> None:
        # an account without a Group is not an administrator; only a file without any LocalAccount leaves it to OOBE
        self.assert_rejected(re.sub(r"<Group>[^<]*</Group>", "", self.xml), "Administrators")

    def test_script_must_end_with_exit_0(self) -> None:
        text = re.sub(r"exit 0(\s*)\]\]>", r"exit 1\1]]>", self.xml, count=1)
        self.assert_rejected(text, "exit 0")


GROUPS = """
[[group]]
id = "a"
title = "A"
order = 1
"""

RULE = """
[[rule]]
id = "a.{name}"
group = "a"
phase = "{phase}"
title = "{name}"
level = "optional"
default = true
doc = "README.md{anchor}"
summary = "s"
effect = "e"
[[rule.actions]]
{action}
"""

REG = """type = 'reg'
path = 'HKLM:\\SOFTWARE\\Policies\\Test'
name = 'X'
kind = 'DWord'
value = 1"""

PS = """type = 'ps'
script = 'Write-Log 1'"""

README = """# Title

## Section one
"""


class CatalogValidationTest(unittest.TestCase):
    def check(self, rules: str) -> list:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rules").mkdir()
            (root / "rules" / "groups.toml").write_text(textwrap.dedent(GROUPS), encoding="utf-8")
            (root / "rules" / "10-test.toml").write_text(rules, encoding="utf-8")
            (root / "README.md").write_text(README, encoding="utf-8")
            _, issues = validate_catalog(root / "rules", root)
            return issues

    def test_real_catalog_has_no_remarks(self) -> None:
        catalog, issues = validate_catalog(ROOT / "rules", ROOT.parent)
        self.assertIsNotNone(catalog)
        self.assertEqual([(i.target, i.message) for i in issues], [])

    def test_loader_error_is_reported_not_raised(self) -> None:
        issues = self.check("[[rule]]\nid = ")
        self.assertEqual([i.level for i in issues], ["error"])
        self.assertIn("TOML", issues[0].message)

    def test_missing_anchor_is_a_warning(self) -> None:
        good = RULE.format(name="one", phase="specialize", anchor="#section-one", action=REG)
        bad = RULE.format(name="two", phase="specialize", anchor="#no-such-section", action=REG)
        issues = self.check(good + bad)
        self.assertEqual([i.target for i in issues], ["a.two"])
        self.assertEqual(issues[0].level, "warning")

    def test_script_rule_without_texts_is_a_warning(self) -> None:
        issues = self.check(RULE.format(name="one", phase="specialize", anchor="", action=PS))
        self.assertEqual(sorted(i.level for i in issues), ["warning", "warning"])


if __name__ == "__main__":
    unittest.main()


