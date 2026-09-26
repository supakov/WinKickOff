"""core/apply.py: plan, audit, apply and undo scripts for a running Windows (task T15).

Nothing here changes the computer: the scripts are only generated and parsed; the runner test uses a
harmless script that writes a report into a temporary folder; elevation is never started.
"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from winkickoff.core.apply import (
    parse_audit_report,
    plan_apply,
    plan_revert,
    render_apply,
    render_audit,
    render_revert,
    render_undo,
    run_audit,
    windows_default,
)
from winkickoff.core.catalog import load_catalog
from winkickoff.core.profile import Profile
from winkickoff.core.pscheck import check_scripts, powershell_path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
MUTATING = re.compile(r"\b(Set-ItemProperty|New-Item|Remove-Item|Remove-ItemProperty|Set-Service|Stop-Service|"
                      r"Disable-WindowsOptionalFeature|Enable-WindowsOptionalFeature|Remove-Appx\w*|Remove-WindowsCapability|"
                      r"Add-WindowsCapability|reg\.exe|Invoke-Exe|Set-Reg|Remove-Reg|Start-Process|New-PSDrive)\b")


class PlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", cls.catalog)

    def plan(self, *items: str):
        return plan_apply(self.catalog, self.office, list(items))

    def test_requirements_are_added(self) -> None:
        plan = self.plan("r:asr.ransomware")
        by_id = {p.rule.id: p for p in plan.rules}
        self.assertFalse(by_id["asr.ransomware"].requirement)
        self.assertTrue(by_id["defender.asr"].requirement)
        self.assertLess(plan.rule_ids.index("defender.asr"), plan.rule_ids.index("asr.ransomware"))

    def test_install_only_and_user_rules_are_never_applied(self) -> None:
        groups = ["g:" + g for g in self.catalog.groups if self.catalog.groups[g].parent is None]
        plan = self.plan(*groups)
        planned = set(plan.rule_ids)
        for rule in self.catalog.rules.values():
            if rule.phase in ("windowspe", "specialize-xml", "oobe-xml", "user-first-logon"):
                self.assertNotIn(rule.id, planned)
        excluded = {rule.id for rule, _ in plan.excluded}
        self.assertIn("user-logon.input-languages", excluded)
        self.assertIn("install.bypass-tpm", excluded)

    def test_disabled_rules_are_excluded_with_reason(self) -> None:
        plan = self.plan("r:network.netbios-off")
        self.assertEqual(plan.rules, [])
        self.assertEqual(plan.excluded[0][0].id, "network.netbios-off")

    def test_flags(self) -> None:
        plan = self.plan("r:apps.remove.solitaire", "r:remote.registry-off")
        by_id = {p.rule.id: p for p in plan.rules}
        self.assertTrue(by_id["apps.remove.solitaire"].irreversible)
        self.assertFalse(by_id["remote.registry-off"].irreversible)
        self.assertTrue(by_id["remote.registry-off"].reboot)


class ScriptsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", cls.catalog)
        groups = ["g:" + g for g in cls.catalog.groups if cls.catalog.groups[g].parent is None]
        cls.plan = plan_apply(cls.catalog, cls.office, groups)
        cls.apply = render_apply(cls.plan, cls.office, cls.catalog, TEMPLATES, "test")
        cls.undo = render_undo(TEMPLATES, cls.office, "test")
        cls.audit = render_audit(cls.plan.rule_ids, cls.office, cls.catalog, TEMPLATES, "test")

    def test_apply_saves_state_and_needs_admin(self) -> None:
        self.assertIn("IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)", self.apply)
        self.assertIn("Save-RegState $Path $Name", self.apply)
        self.assertIn("ConvertTo-Json", self.apply)
        self.assertTrue(self.apply.rstrip().endswith("exit 0"))
        for rule_id in self.plan.rule_ids:
            self.assertIn(f"# [{rule_id}]", self.apply)
        self.assertNotIn("# [user-logon.input-languages]", self.apply)

    def test_default_user_rules_run_inside_the_mounted_hive(self) -> None:
        start = self.apply.index("if (Mount-DefaultUser) {")
        end = self.apply.index("Dismount-DefaultUser\n}", start)
        self.assertIn("# [default-user.show-file-extensions]", self.apply[start:end])
        self.assertIn("$accounts = @('Admin','User')", self.apply)

    def test_audit_only_reads(self) -> None:
        body = self.audit.split("{{", 1)[0]
        self.assertEqual(MUTATING.findall(body), [])
        self.assertEqual(body.count("Set-Content"), 1)  # the report
        self.assertIn("Test-Reg -Rule 'defender.pua'", body)
        self.assertIn("HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced", body)

    def test_undo_restores_from_backup(self) -> None:
        self.assertIn("ConvertFrom-Json", self.undo)
        self.assertIn("Set-ItemProperty -LiteralPath $e.path", self.undo)
        self.assertIn("cannot be restored automatically", self.undo)

    @unittest.skipUnless(powershell_path(), "powershell.exe not found")
    def test_scripts_parse_in_windows_powershell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = check_scripts({"Apply.ps1": self.apply, "Undo-Apply.ps1": self.undo, "Audit.ps1": self.audit}, Path(tmp))
        self.assertTrue(result.ok, result)


class RevertTest(unittest.TestCase):
    """Return to the values of a clean Windows (context menu «Вернуть выбранное к умолчаниям Windows»)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        cls.office, _ = Profile.load(ROOT / "profiles" / "preset-office.json", cls.catalog)

    def plan(self, *items: str):
        return plan_revert(self.catalog, list(items))

    def test_uac_prompt_level_returns_to_5(self) -> None:
        plan = self.plan("r:uac.admin-always-notify")
        self.assertEqual(plan.rule_ids, ["uac.admin-always-notify"])
        self.assertIn("-Name 'ConsentPromptBehaviorAdmin' -Type DWord -Value 5", plan.rules[0].lines[0])

    def test_policies_are_removed_without_data(self) -> None:
        plan = self.plan("r:defender.pua")
        self.assertTrue(plan.rules and all(line.startswith("Remove-Reg ") for line in plan.rules[0].lines))
        self.assertEqual(plan.rules[0].skipped, [])

    def test_dependents_come_along(self) -> None:
        by_id = {p.rule.id: p for p in self.plan("r:uac.baseline").rules}
        self.assertFalse(by_id["uac.baseline"].dependent)
        self.assertTrue(by_id["uac.admin-always-notify"].dependent)
        self.assertIn("-Name 'EnableLUA' -Type DWord -Value 1", "\n".join(by_id["uac.baseline"].lines))

    def test_rules_without_defaults_are_excluded_with_reason(self) -> None:
        plan = self.plan("r:apps.remove.solitaire", "r:update.unblock", "r:install.bypass-tpm", "r:apps.remove.onedrive")
        self.assertTrue(all(p.dependent for p in plan.rules))  # only rules that require update.unblock
        reasons = {rule.id: reason for rule, reason in plan.excluded}
        self.assertIn("неизвестны", reasons["apps.remove.solitaire"])
        self.assertIn("update.unblock", reasons)  # removals of blocks are the default already; its script step is not undone
        self.assertIn("при установке", reasons["install.bypass-tpm"])
        self.assertIn("неизвестны", reasons["apps.remove.onedrive"])

    def test_services_and_unknown_values(self) -> None:
        by_id = {p.rule.id: p for p in self.plan("r:privacy.telemetry-minimal", "r:network.smb-signing").rules}
        self.assertIn("Set-ServiceStart -Name 'DiagTrack' -Start 2", by_id["privacy.telemetry-minimal"].lines)
        self.assertNotIn("network.smb-signing", by_id)  # the defaults changed between builds: not guessed

    def test_every_script_rule_has_a_known_outcome(self) -> None:
        groups = ["g:" + g for g in self.catalog.groups if self.catalog.groups[g].parent is None]
        plan = self.plan(*groups)
        self.assertEqual(len(plan.rules) + len(plan.excluded), len(self.catalog.rules))
        for rule in self.catalog.rules.values():
            for action in rule.actions:
                step = windows_default(action)
                if step is not None and step[0] == "set":
                    self.assertNotEqual(action.fields.get("default"), "absent")

    def test_script_is_the_apply_script_with_a_backup(self) -> None:
        plan = self.plan("g:security", "g:default-user")
        script = render_revert(plan, self.office, TEMPLATES, "test")
        self.assertIn("(return to Windows defaults)", script)
        self.assertIn("Save-RegState $Path $Name", script)
        self.assertIn("# [uac.baseline] Windows defaults", script)
        start = script.index("if (Mount-DefaultUser) {")
        self.assertIn("Remove-Reg -Path \"$du\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\Advanced\" -Name 'HideFileExt'", script[start:])
        self.assertTrue(script.rstrip().endswith("exit 0"))
        if powershell_path():
            with tempfile.TemporaryDirectory() as tmp:
                self.assertTrue(check_scripts({"Apply.ps1": script}, Path(tmp)).ok)


class ReportTest(unittest.TestCase):
    def test_statuses(self) -> None:
        report = {"computer": "PC", "admin": False, "results": [
            {"rule": "a", "check": "x", "status": "ok"},
            {"rule": "b", "check": "x", "status": "ok"}, {"rule": "b", "check": "y", "status": "differs"},
            {"rule": "c", "check": "x", "status": "differs"}, {"rule": "c", "check": "y", "status": "unknown"},
            {"rule": "d", "check": "x", "status": "unknown"},
        ]}
        meta, results = parse_audit_report(chr(0xFEFF) + json.dumps(report))
        self.assertEqual(meta["computer"], "PC")
        self.assertEqual({k: v.status for k, v in results.items()},
                         {"a": "applied", "b": "partial", "c": "not-applied", "d": "unknown"})

    @unittest.skipUnless(powershell_path(), "powershell.exe not found")
    def test_runner_returns_the_report(self) -> None:
        script = "param([string]$Report)\n'{\"results\": []}' | Set-Content -LiteralPath $Report -Encoding UTF8\nexit 0\n"
        with tempfile.TemporaryDirectory() as tmp:
            text = run_audit(script, Path(tmp), timeout=120)
        self.assertEqual(json.loads(text), {"results": []})


if __name__ == "__main__":
    unittest.main()
