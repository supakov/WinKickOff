# T19. Import of policy templates (ADMX, ADML) as a subtree of rules

Status: done (30.09.2026), version 1.1.0-rc.1. Stage 7. Dependencies: T18.

## Goal

The customer's list of 30.09.2026:

1. The user chooses the import of the system catalog in a menu.
2. A new subtree with a generated name appears.
3. The import is kept in a subfolder of the portable program and is available at later starts through the same
   menu.
4. When a policy of the subtree matches the main catalog, its description links to the built-in rule.
5. Texts of the subtree come only from ADML.

Decisions of the customer: imported policies can be selected and built like catalog rules (check box,
parameters, profile, autounattend.xml, This PC); the source is the PolicyDefinitions folder of this Windows or
any folder with templates (Edge, Chrome, Office).

## Result

- `core/admx.py`: reading (limits, no DTD, BOM decoding, unsafe characters refused), store `admx/<id>/`
  (import.json, policies.json), conversion to rules in the interface language, `with_imports()`; details in
  `../03-data-model.md` section 8.
- `core/catalog.py`: indexes of children, group rules and positions (the tree of about 3900 rules builds in
  0.4 s), `RuleOrigin`, `Catalog.origins`, `same_values()`, `registry_values()`, `merge()`; the prefix `admx.`
  is reserved.
- `core/profile.py`: imported policies are written only when on or with parameters; states in `unknown` come back
  when the rules do; `rebind()` for a window rebuilt with another catalog.
- `core/apply.py`: an unchecked imported policy is not reverted by an apply; a revert takes imported policies
  selected one by one (`not_configured` counts the others).
- `core/validate.py`: parameters of unchecked imported policies are not checked; optional texts may be empty;
  strings with control characters or `]]>` are errors; a warning when an imported policy repeats an enabled
  built-in rule.
- Window: the ADMX menu (import of this Windows, import from a folder, a check mark per saved import, delete),
  reading in a background thread with progress, the window is rebuilt with the open profile; sections "Built into
  the catalog" / "Also in imported templates" with links, "Source"; the group check box of an imported branch
  only switches off; group descriptions list at most 300 rules.
- The templates of this PC (build 26300): 224 files, 3362 policies as 3652 rules, 190 skipped (125 list elements,
  45 multi-line texts, 16 value lists, 4 values out of range), 89 rules share a value with the built-in catalog;
  reading 1.5 s, 8.7 MB in policies.json.
- Tests: `tests/test_admx.py` (synthetic templates: states, elements, pairs, skips, DTD, unsafe key, cultures and
  fallback, store, build, validation, profile, apply, reserved prefix, window; the templates of this Windows are
  read and every rule renders).

## Open points

- List and multi-line elements need a new action type (a key with a variable number of values); not done.
- ADML of uk-UA in Windows covers 5 of 224 templates: the Ukrainian interface shows the subtree mostly in English.
