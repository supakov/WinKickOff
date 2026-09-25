"""Dependency resolver: cascading enable/disable and the order in which rules are applied."""

from __future__ import annotations

from dataclasses import dataclass

from winkickoff.core.catalog import PHASE_ORDER, Catalog
from winkickoff.core.profile import Profile


@dataclass(frozen=True)
class Change:
    rule_id: str
    enabled: bool
    reason: str  # "user", "requires <id>", "required by <id>", "conflicts with <id>"


class Resolver:
    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    # ----------------------------------------------------------------- toggling

    def disable(self, profile: Profile, rule_id: str, reason: str = "user") -> list[Change]:
        """Disable a rule and, transitively, every enabled rule that requires it."""
        changes: list[Change] = []
        stack: list[tuple[str, str]] = [(rule_id, reason)]
        while stack:
            current, why = stack.pop(0)
            state = profile.rules[current]
            if not state.enabled:
                continue
            state.enabled = False
            changes.append(Change(current, False, why))
            for dependent in self.catalog.required_by(current):
                stack.append((dependent, f"requires {current}"))
        return changes

    def enable(self, profile: Profile, rule_id: str, reason: str = "user") -> list[Change]:
        """Enable a rule and, transitively, everything it requires; disable its conflicts."""
        changes: list[Change] = []
        stack: list[tuple[str, str]] = [(rule_id, reason)]
        while stack:
            current, why = stack.pop(0)
            state = profile.rules[current]
            if state.enabled:
                continue
            state.enabled = True
            changes.append(Change(current, True, why))
            rule = self.catalog.rules[current]
            for req in rule.requires:
                stack.append((req, f"required by {current}"))
            for other in rule.conflicts:
                changes.extend(self.disable(profile, other, f"conflicts with {current}"))
        return changes

    def set_rule(self, profile: Profile, rule_id: str, enabled: bool) -> list[Change]:
        return self.enable(profile, rule_id) if enabled else self.disable(profile, rule_id)

    def set_group(self, profile: Profile, group_id: str, enabled: bool) -> list[Change]:
        changes: list[Change] = []
        for rule in self.catalog.rules_in_group(group_id):
            changes.extend(self.set_rule(profile, rule.id, enabled))
        return changes

    def reset_group(self, profile: Profile, group_id: str) -> list[Change]:
        """Return every rule of a group to its catalog default, cascading as usual."""
        changes: list[Change] = []
        for rule in self.catalog.rules_in_group(group_id):
            if profile.rules[rule.id].enabled != rule.default:
                changes.extend(self.set_rule(profile, rule.id, rule.default))
        return changes

    # ----------------------------------------------------------------- ordering

    def apply_order(self, profile: Profile) -> list[str]:
        """Enabled rules in application order: phase, then catalog position, with the
        constraint that a rule never precedes an enabled rule it requires within the same phase."""
        enabled = [rule_id for rule_id in self.catalog.order if profile.is_enabled(rule_id)]
        enabled_set = set(enabled)
        result: list[str] = []
        for phase in sorted({self.catalog.rules[r].phase for r in enabled}, key=lambda p: PHASE_ORDER[p]):
            remaining = [r for r in enabled if self.catalog.rules[r].phase == phase]
            emitted: set[str] = set()
            while remaining:
                for rule_id in remaining:
                    rule = self.catalog.rules[rule_id]
                    pending = [
                        req
                        for req in rule.requires
                        if req in enabled_set and self.catalog.rules[req].phase == phase and req not in emitted
                    ]
                    if not pending:
                        result.append(rule_id)
                        emitted.add(rule_id)
                        remaining.remove(rule_id)
                        break
                else:  # no progress: impossible after cycle check, but never loop forever
                    raise RuntimeError(f"cannot order rules in phase {phase}: {remaining}")
        return result

    # ----------------------------------------------------------------- queries

    def dependents(self, rule_id: str) -> list[str]:
        """Transitive closure of rules that require rule_id (for the description panel)."""
        seen: list[str] = []
        stack = list(self.catalog.required_by(rule_id))
        while stack:
            current = stack.pop(0)
            if current in seen:
                continue
            seen.append(current)
            stack.extend(self.catalog.required_by(current))
        return seen
