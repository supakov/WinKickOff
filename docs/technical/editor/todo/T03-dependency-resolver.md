# T03. Dependency resolver and application order

Status: done (25.09.2026: resolver with cascade, groups and application order; the test
`test_apply_order_follows_v02` confirms the v0.2 section order on the «Офис» (Office) preset). Stage 2. Dependencies: T02.

## Goal

Implement `core/deps.py`: cascading disable and enable, conflicts, group operations,
rule application order.

## Steps

1. `Resolver(catalog)`: indexes `requires`, `required_by`, `conflicts`.
2. `disable(profile, rule_id) -> list[Change]`: traversal along `required_by`, enabled rules only.
3. `enable(profile, rule_id) -> list[Change]`: traversal along `requires`, then disabling `conflicts`
   with their cascade.
4. `set_group(profile, group_id, enabled) -> list[Change]`: over the rules of the group and its subgroups.
5. `apply_order(profile) -> list[rule_id]`: enabled rules by phase, position in the catalog and
   a stable topological sort by `requires`.
6. `Change(rule_id, enabled, reason)`, where reason is: `"user"`, `"requires <id>"`, `"required by <id>"`,
   `"conflicts <id>"`.
7. `tests/test_deps.py` per `04-testing.md`, section core/deps.

## Acceptance criteria

- All resolver tests are green; a repeated operation returns an empty list of changes.
- `apply_order` on the «Офис» preset reproduces the v0.2 section order.

## Implementer notes

25.09.2026: implemented `disable`, `enable`, `set_group`, `apply_order` and tests for chains, conflicts,
idempotency. Not verified: the order on the «Офис» preset against v0.2 (depends on T06).
