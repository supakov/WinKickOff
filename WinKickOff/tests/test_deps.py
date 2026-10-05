"""core/deps.py: cascading enable/disable, conflicts, groups, order."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from winkickoff.core.catalog import load_catalog
from winkickoff.core.deps import Resolver
from winkickoff.core.profile import Profile

GROUPS = {"groups": [{"id": "g", "title": "G"}, {"id": "g.sub", "parent": "g", "title": "Sub"}]}


def rule(rid: str, group: str = "g", phase: str = "specialize", requires: tuple[str, ...] = (),
         conflicts: tuple[str, ...] = (), default: bool = True) -> dict:
    return {"id": rid, "group": group, "phase": phase, "title": rid, "level": "optional", "default": default,
            "requires": list(requires), "conflicts": list(conflicts), "doc": "README.md", "summary": "s", "effect": "e",
            "actions": [{"type": "reg", "path": "HKLM:\\SOFTWARE\\T", "name": rid, "kind": "DWord", "value": 1}]}


class ResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "rules").mkdir()
        (root / "README.md").write_text("doc", encoding="utf-8")
        (root / "rules" / "groups.json").write_text(json.dumps(GROUPS), encoding="utf-8")
        rules = [
            rule("c"),
            rule("b", requires=("c",)),
            rule("a", requires=("b",)),
            rule("x", conflicts=("y",), default=False),
            rule("y"),
            rule("z", group="g.sub", requires=("y",)),
            rule("late", phase="post-oobe", requires=("a",)),
        ]
        (root / "rules" / "10-t.json").write_text(json.dumps({"rules": rules}), encoding="utf-8")
        self.catalog = load_catalog(root / "rules", docs_root=root)
        self.resolver = Resolver(self.catalog)
        self.profile = Profile.from_catalog(self.catalog)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_disable_cascades_to_dependents(self) -> None:
        changes = self.resolver.disable(self.profile, "c")
        self.assertEqual([c.rule_id for c in changes], ["c", "b", "a", "late"])
        self.assertEqual(changes[1].reason, "requires c")
        self.assertFalse(self.profile.is_enabled("a"))

    def test_disable_is_idempotent(self) -> None:
        self.resolver.disable(self.profile, "c")
        self.assertEqual(self.resolver.disable(self.profile, "c"), [])

    def test_enable_cascades_to_requirements(self) -> None:
        self.resolver.disable(self.profile, "c")
        changes = self.resolver.enable(self.profile, "a")
        self.assertEqual([c.rule_id for c in changes], ["a", "b", "c"])
        self.assertEqual(changes[1].reason, "required by a")
        self.assertFalse(self.profile.is_enabled("late"))

    def test_enable_disables_conflicts_and_their_dependents(self) -> None:
        changes = self.resolver.enable(self.profile, "x")
        ids = [c.rule_id for c in changes]
        self.assertEqual(ids, ["x", "y", "z"])
        self.assertFalse(self.profile.is_enabled("y"))
        self.assertFalse(self.profile.is_enabled("z"))
        self.assertEqual(changes[1].reason, "conflicts with x")

    def test_group_toggle(self) -> None:
        changes = self.resolver.set_group(self.profile, "g.sub", False)
        self.assertEqual([c.rule_id for c in changes], ["z"])
        changes = self.resolver.set_group(self.profile, "g", False)
        self.assertTrue(all(not self.profile.is_enabled(r) for r in ("a", "b", "c", "y", "late")))
        self.assertNotIn("z", [c.rule_id for c in changes])  # already off

    def test_reset_group_restores_defaults(self) -> None:
        self.resolver.set_group(self.profile, "g", False)
        self.resolver.reset_group(self.profile, "g")
        self.assertTrue(self.profile.is_enabled("a"))
        self.assertFalse(self.profile.is_enabled("x"))

    def test_apply_order_respects_requires_and_phases(self) -> None:
        order = self.resolver.apply_order(self.profile)
        self.assertLess(order.index("c"), order.index("b"))
        self.assertLess(order.index("b"), order.index("a"))
        self.assertEqual(order[-1], "late")
        self.assertNotIn("x", order)

    def test_dependents_closure(self) -> None:
        self.assertEqual(self.resolver.dependents("c"), ["b", "a", "late"])


if __name__ == "__main__":
    unittest.main()
