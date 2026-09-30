# T21. Imported policies follow the built-in rules that set the same values

Status: done (30.09.2026), version 1.1.0-rc.4. Stage 7. Dependencies: T20.

## Goal

The customer's remark on T20: the check marks of the built-in catalog and of the imported trees were not in
sync. T20 synchronised one policy across several imported trees; the customer meant a built-in rule and the
imported policy that sets the same registry value.

## Result

- `core/linked.py`: `registry_writes`, `link` (the built-in rule that writes everything a policy writes, for the
  current parameters or one value of its first choice parameter; an equal rule first), `covering`, `redundant`.
- Window: a policy covered by an enabled built-in rule is shown checked (tag `linked`, link colour), counted in its
  groups, described as "Set by the built-in rule", and its parameter panel says the values come from that rule.
  Its own state stays off, so nothing is written twice. Toggling it: equal, the built-in rule switches with it;
  covered only in part, a question before the whole rule goes off. After every toggle a policy that became
  redundant is switched off with a message.
- The templates of this Windows: 95 imported policies share a value with the catalog, 51 are covered by the
  Office preset.
- Tests: `tests/test_linked.py` (links, covering, redundancy, the window: display, equal and partial toggling,
  stepping back, group counts).
