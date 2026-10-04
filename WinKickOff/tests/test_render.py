"""core/render.py: action rendering, quoting, parameter substitution."""

from __future__ import annotations

import unittest
from pathlib import Path

from winkickoff.core.catalog import Action, load_catalog
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


class RenderCatalogTest(unittest.TestCase):
    def test_every_script_action_of_the_catalog_renders(self) -> None:
        catalog = load_catalog(ROOT / "rules", docs_root=ROOT.parent)
        profile = Profile.from_catalog(catalog)
        for rule in catalog.rules.values():
            if rule.phase in ("windowspe", "specialize-xml", "oobe-xml"):
                continue
            block = render_block(rule, profile.params_for(catalog, rule.id))
            self.assertEqual(block.splitlines()[0], f"# [{rule.id}]", rule.id)
            self.assertNotIn("{", block.splitlines()[1] if len(rule.actions) == 1 and rule.actions[0].type != "ps" else "", rule.id)


if __name__ == "__main__":
    unittest.main()
