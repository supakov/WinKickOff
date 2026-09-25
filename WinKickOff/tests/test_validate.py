"""core/validate.py: profile checks before the build and answer file checks after it."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import Account, Profile
from winkickoff.core.render import Renderer
from winkickoff.core.resources import Resources
from winkickoff.core.validate import check_account_name, has_errors, validate_profile, validate_xml

ROOT = Path(__file__).resolve().parents[1]
V02 = ROOT.parent / "autounattend.xml"


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

    def test_password_is_only_a_warning(self) -> None:
        self.profile.accounts[0].password = "secret"
        issues = self.check()
        self.assertEqual(errors(issues), [])
        self.assertIn("warning", {i.level for i in issues if i.target == "accounts[0]"})

    def test_account_names(self) -> None:
        self.assertIsNone(check_account_name("Admin"))
        self.assertIsNone(check_account_name("Бухгалтерия"))
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
        self.assertFalse(has_errors(validate_xml(V02.read_text(encoding="utf-8"))))

    def test_broken_xml(self) -> None:
        self.assert_rejected(self.xml[:-40], "XML")

    def test_comment_inside_component(self) -> None:
        self.assert_rejected(self.xml.replace("<RunSynchronous>", "<RunSynchronous><!-- note -->", 1), "Комментарий")

    def test_command_longer_than_259(self) -> None:
        text = re.sub(r"<Path>[^<]*</Path>", "<Path>cmd.exe /c " + "x" * 260 + "</Path>", self.xml, count=1)
        self.assert_rejected(text, "длиннее")

    def test_duplicate_order(self) -> None:
        text = self.xml.replace("<Order>2</Order>", "<Order>1</Order>", 1)
        self.assert_rejected(text, "Order")

    def test_incomplete_international_core(self) -> None:
        text = re.sub(r"<UserLocale>[^<]*</UserLocale>", "", self.xml)
        self.assert_rejected(text, "UserLocale")

    def test_no_administrator(self) -> None:
        self.assert_rejected(self.xml.replace("<Group>Administrators</Group>", "<Group>Users</Group>"), "Administrators")

    def test_script_must_end_with_exit_0(self) -> None:
        text = re.sub(r"exit 0(\s*)\]\]>", r"exit 1\1]]>", self.xml, count=1)
        self.assert_rejected(text, "exit 0")


if __name__ == "__main__":
    unittest.main()
