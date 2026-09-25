"""core/verify.py: every rule tells how to check and undo it, by hand-written text or derived steps."""

from __future__ import annotations

import unittest
from pathlib import Path

from winkickoff.core.catalog import Action, Rule, load_catalog
from winkickoff.core.profile import Profile
from winkickoff.core.verify import reg_cli_path, rollback_steps, verify_steps

ROOT = Path(__file__).resolve().parents[1]


def rule_with(*actions: tuple[str, dict], phase: str = "specialize") -> Rule:
    return Rule(
        id="t.rule", group="g", phase=phase, title="T", level="optional", default=True, doc="d.md",
        summary="s", effect="e", actions=tuple(Action(t, f, "t.rule") for t, f in actions),
    )


class VerifyTest(unittest.TestCase):
    def test_every_rule_can_be_checked_and_undone(self) -> None:
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        profile = Profile.from_catalog(catalog)
        for rule in catalog.rules.values():
            params = profile.params_for(catalog, rule.id)
            with self.subTest(rule=rule.id):
                self.assertTrue(rule.verify or verify_steps(rule, params))
                self.assertTrue(rule.rollback or rollback_steps(rule, params))

    def test_registry_paths(self) -> None:
        self.assertEqual(reg_cli_path("HKLM:\\SOFTWARE\\X"), "HKLM\\SOFTWARE\\X")
        self.assertEqual(reg_cli_path("DU:\\Software\\X"), "HKCU\\Software\\X")

    def test_policy_value_is_deleted_other_value_is_restored(self) -> None:
        policy = rule_with(("reg", {"path": "HKLM:\\SOFTWARE\\Policies\\Microsoft\\X", "name": "A", "kind": "DWord", "value": 1}))
        other = rule_with(("reg", {"path": "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Lsa", "name": "B", "kind": "DWord", "value": 1}))
        self.assertIn("reg delete", rollback_steps(policy, {})[0])
        self.assertIn("reg add", rollback_steps(other, {})[0])
        self.assertNotIn("reg delete", rollback_steps(other, {})[0])

    def test_default_value_uses_ve(self) -> None:
        rule = rule_with(("reg", {"path": "HKLM:\\SOFTWARE\\Classes\\JSFile\\Shell\\Open\\Command", "name": "(Default)", "kind": "String", "value": "x"}))
        self.assertIn(" /ve", verify_steps(rule, {})[0])
        self.assertIn(" /ve", rollback_steps(rule, {})[0])

    def test_parameters_are_substituted(self) -> None:
        rule = rule_with(("reg", {"path": "HKLM:\\SOFTWARE\\Policies\\X", "name": "Seconds", "kind": "DWord", "value": "{seconds}"}))
        self.assertIn("900", verify_steps(rule, {"seconds": 900})[0])

    def test_default_user_values_are_checked_in_hkcu(self) -> None:
        rule = rule_with(("reg", {"path": "DU:\\Software\\X", "name": "A", "kind": "DWord", "value": 0}), phase="default-user")
        steps = verify_steps(rule, {})
        self.assertIn("HKCU\\Software\\X", steps[0])
        self.assertIn("учётной записью", steps[-1])

    def test_service_feature_appx(self) -> None:
        rule = rule_with(
            ("service", {"name": "RemoteRegistry", "start": 4}),
            ("feature", {"name": "SMB1Protocol", "state": "Disabled"}),
            ("appx", {"names": ["A.B", "C.D"]}),
        )
        steps = verify_steps(rule, {})
        self.assertIn("DISABLED", steps[0])
        self.assertIn("State Disabled", steps[1])
        self.assertEqual(len(steps), 4)
        self.assertIn("Enable-WindowsOptionalFeature", rollback_steps(rule, {})[1])

    def test_script_only_rule_needs_text(self) -> None:
        rule = rule_with(("ps", {"script": "Write-Log 'x'"}))
        self.assertEqual(verify_steps(rule, {}), [])
        self.assertEqual(rollback_steps(rule, {}), [])


if __name__ == "__main__":
    unittest.main()
