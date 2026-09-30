# T20. Back and Forward; rename, update and shared policies of imported templates

Status: done (30.09.2026), version 1.1.0-rc.3. Stage 7. Dependencies: T19.

## Goal

The customer's list of 30.09.2026:

1. A history of jumps by links between rules, with Back and Forward buttons.
2. Editing the name of an imported tree.
3. The same selection in the catalog and the imported trees.
4. A second import of the system templates showed a smaller count of rules, even 0.

Decisions of the customer: (3) a policy found in several imported trees has one check mark in all of them;
(4) an import of a folder that is already imported asks whether to update the import or to add a tree.

## Cause of item 4

Rule ids follow the template and the policy, not the import (so profiles fit any import of the same
templates). T19 left out of a later import every policy that was already a rule, so a second import of the same
folder had an empty tree; only the summary of the tree said so.

## Result

- `core/catalog.py`: `aliases` (a rule shown in more groups), `placements()`; group rules include aliases, an
  imported group lists its rules by title; recursive lists count a rule once.
- `core/admx.py`: a policy that is already a rule becomes an alias in the later tree (`ImportedPart.aliases`,
  `shared`); `find_imports`, `save_import(replace=...)` (same id, files through a temporary file),
  `rename_import`, `ImportInfo.renamed`, `MAX_NAME`.
- Window: tree item ids `r:<rule>@<group>` for aliases, `rule_of()`; the This PC actions work on the rule;
  the description names every tree that shows a rule; the ADMX menu and the root of an imported tree rename it;
  an import of an imported folder asks Yes (update), No (add), Cancel; Back and Forward above the description and
  Alt+Left, Alt+Right: jumps by links, by messages and clicks in the tree are remembered (50 nodes), a new jump
  clears Forward, keyboard moves in the tree are not remembered.
- Tests: `tests/test_admx.py` (shared trees, update in place, rename, the question on a second import, one check
  mark in two trees, Back and Forward).
