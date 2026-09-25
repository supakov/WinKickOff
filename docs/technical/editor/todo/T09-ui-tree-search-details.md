# T09. Tree with check boxes, search, description panel

Status: done (25.09.2026: tree with image check boxes, «+» only expands the branch, search, description;
dependencies and group rules as links; «Карточка справочника» (Reference card) opens the file; verification and
rollback for every rule, from the catalog or generated from the actions (`core/verify.py`); cascade in the status
bar and in the list at the bottom; smoke tests). Stage 4. Dependencies: T03, T04. Difference: everything is in
`ui/main_window.py`; separate `rule_tree.py` and `detail_panel.py` were not needed.

## Goal

The main window according to `02-architecture.md`, section 8: a tree of all rules with check boxes, search, a
description with a technical table of actions, a cascade status bar.

## Steps

1. `ui/main_window.py`: `PanedWindow`, menu, status bar, keyboard shortcuts.
2. `ui/rule_tree.py`: built from groups and rules; node text with a state symbol (☐ ☑ ◪);
   a click on the symbol or Space toggles via the resolver; redraw of changed nodes; group
   check box; preserving the expansion state.
3. Search: an index built from the catalog; filtering with a 150 ms delay; expanding the matches; reset.
4. `ui/detail_panel.py`: description from the rule data and a table of actions generated from `actions`;
   dependencies (requires, required by, conflicts with) as links, navigation on click; «Подробнее» (More details)
   opens the reference file.
5. Status bar: «Выключено также: N» (Also turned off: N); a click shows the list with reasons.
6. `tests/test_ui_smoke.py`: hidden window; full tree; search by registry key; toggling
   changes the profile.

## Acceptance criteria

- "Find, turn off, build" in 4 actions (search field, click, F9, path confirmation).
- The cascade is visible without a dialog.

## Implementer notes

25.09.2026: created the `main_window.py` skeleton with the tree, search over the catalog index, a description panel
with the actions table and a status bar; toggling via the resolver. Not done: preserving expansion during search,
dependency links, «Подробнее», smoke test.
