"""core/render.py: action rendering, quoting, parameter substitution."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from winkickoff.core.catalog import PHASE_ACTION_TYPES, SCRIPT_PHASES, Action, load_catalog
from winkickoff.core.profile import Profile
from winkickoff.core.render import RenderError, ps_quote, render_action, render_block, substitute

ROOT = Path(__file__).resolve().parents[1]


def act(atype: str, **fields: object) -> Action:
    return Action(type=atype, fields=dict(fields), rule_id="t")


class RenderActionTest(unittest.TestCase):
    def test_reg_dword(self) -> None:
        line = render_action(act("reg", path="HKLM:\\SOFTWARE\\T", name="X", kind="DWord", value=1, why="w"), {})
        self.assertEqual(line, "Set-Reg -Path 'HKLM:\\SOFTWARE\\T' -Name 'X' -Type DWord -Value 1 -Why 'w'")

    def test_reg_string_quotes_are_doubled(self) -> None:
        line = render_action(act("reg", path="HKLM:\\T", name="N", kind="String", value="it's"), {})
        self.assertIn("-Value 'it''s'", line)

    def test_default_user_path_uses_du_variable(self) -> None:
        line = render_action(act("reg", path="DU:\\Software\\X", name="N", kind="DWord", value=0), {})
        self.assertTrue(line.startswith("Set-Reg -Path ($du + '\\Software\\X')"))

    def test_paths_and_names_are_never_expanded(self) -> None:
        """A parameter fills in only the value: a key or a value name of an imported template is literal text, and a DU
        path is a single-quoted literal joined to $du, so PowerShell never expands $ or $(...) in it (it used to be a
        double-quoted string, and a parameter could reach the key)."""
        line = render_action(act("reg", path="DU:\\Software\\P\\{e1}\\$(Get-Date)", name="{e1}", kind="String",
                                 value="{e1}"), {"e1": "$(Get-Date)"})
        self.assertEqual(line, "Set-Reg -Path ($du + '\\Software\\P\\{e1}\\$(Get-Date)') -Name '{e1}' -Type String "
                               "-Value '$(Get-Date)'")
        self.assertNotIn('"', line)

    def test_placeholder_keeps_int_type(self) -> None:
        self.assertEqual(substitute("{n}", {"n": 5}), 5)
        self.assertEqual(substitute("/x:{n}", {"n": 5}), "/x:5")
        line = render_action(act("reg", path="HKLM:\\T", name="N", kind="DWord", value="{n}"), {"n": 7})
        self.assertTrue(line.endswith("-Value 7"))

    def test_exe_and_service(self) -> None:
        self.assertEqual(render_action(act("exe", file="net.exe", args=["accounts", "/x:{n}"]), {"n": 3}), "Invoke-Exe 'net.exe' @('accounts','/x:3')")
        self.assertEqual(render_action(act("service", name="Spooler", start=2), {}), "Set-ServiceStart -Name 'Spooler' -Start 2")

    def test_feature_capability_appx_ps(self) -> None:
        self.assertEqual(render_action(act("feature", name="F", state="Disabled"), {}), "Set-Feature -Name 'F' -State Disabled")
        self.assertEqual(render_action(act("capability", pattern="X*"), {}), "Remove-Capability -Pattern 'X*'")
        self.assertEqual(render_action(act("appx", names=["A", "B"]), {}), "Remove-Apps @('A','B')")
        self.assertEqual(render_action(act("ps", script="\nWrite-Log 'x'\n"), {}), "Write-Log 'x'")

    def test_dword_with_string_is_an_error(self) -> None:
        with self.assertRaises(RenderError):
            render_action(act("reg", path="HKLM:\\T", name="N", kind="DWord", value="abc"), {})

    def test_xml_action_is_not_a_script_action(self) -> None:
        with self.assertRaises(RenderError):
            render_action(act("xml-oobe", element="E", value="v"), {})

    def test_ps_quote(self) -> None:
        self.assertEqual(ps_quote("a'b"), "'a''b'")


class RuntimeFunctionsTest(unittest.TestCase):
    FUNCTIONS = {"reg": "Set-Reg", "reg-remove": "Remove-Reg", "reg-list": "Set-RegList", "service": "Set-ServiceStart",
                 "exe": "Invoke-Exe", "feature": "Set-Feature", "capability": "Remove-Capability", "appx": "Remove-Apps"}
    RUNTIMES = {"specialize": "Setup-System.runtime.ps1", "default-user": "Setup-System.runtime.ps1",
                "user-first-logon": "Setup-User.runtime.ps1", "post-oobe": "Post-OOBE.runtime.ps1"}

    def test_the_script_of_every_phase_defines_the_functions_of_its_actions(self) -> None:
        """A rule may use an action type in a phase only when the script of that phase defines its function (a reg
        action of the per-user script used to fail with "Set-Reg is not recognized")."""
        self.assertEqual(set(self.RUNTIMES), set(SCRIPT_PHASES))
        for phase in SCRIPT_PHASES:
            text = (ROOT / "templates" / self.RUNTIMES[phase]).read_text(encoding="ascii")
            for atype in PHASE_ACTION_TYPES.get(phase, tuple(self.FUNCTIONS)):
                if atype in self.FUNCTIONS:
                    with self.subTest(phase=phase, type=atype):
                        self.assertRegex(text, rf"(?m)^function {re.escape(self.FUNCTIONS[atype])}\b")


class RenderCatalogTest(unittest.TestCase):
    def test_every_script_action_of_the_catalog_renders(self) -> None:
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        profile = Profile.from_catalog(catalog)
        for rule in catalog.rules.values():
            if rule.phase in ("windowspe", "specialize-xml", "oobe-xml"):
                continue
            block = render_block(rule, profile.params_for(catalog, rule.id))
            self.assertEqual(block.splitlines()[0], f"# [{rule.id}]", rule.id)
            for line in block.splitlines()[1:] if not any(a.type == "ps" for a in rule.actions) else []:
                # no placeholder is left; a CLSID such as {645FF040-...} in a key or a value name is literal text
                self.assertNotRegex(line, r"\{[a-z_][a-z0-9_]*\}", rule.id)


if __name__ == "__main__":
    unittest.main()
