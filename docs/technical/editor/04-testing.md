# 04. Testing strategy

Revision 0.2 of 25.09.2026. Tool: `unittest` from the standard library
(`python -m unittest discover -s tests`), pytest compatibility is kept. No test changes the
state of the machine: tests read project files and write only to the test's temporary folders.

## 1. Levels

| Level | What it verifies | Where it runs |
|---|---|---|
| Catalog | Integrity of `rules/*.toml`: unique ids, existing groups and dependencies, no cycles, valid action types and required fields, filled-in descriptions, links to existing reference files | Everywhere |
| Semantic golden | Each action of the v0.2 file is present in the catalog under the "Office" preset with the same value | Everywhere |
| Resolver | Disable and enable cascade, conflicts, group operations, application order | Everywhere |
| Profile | Loading, saving, completeness, migration, `unknown`, comparison | Everywhere |
| Generator | Determinism; only enabled rules in the output; correct order; parameter substitution; escaping; 259 limit; well-formed XML | Everywhere |
| Validator | Each check catches its own bad profile or XML and stays silent on a good one | Everywhere |
| External verification | The built XML passes `tools/Validate-Unattend.ps1`; the scripts are parsed by PowerShell 5.1 | Windows only, skipped without `powershell.exe` |
| UI smoke | The window is created hidden, the tree is built, search filters, a check box calls the resolver | Windows with a display |
| Portability | Checklist in a VM | Manual |
| Acceptance | Installation in a VM, README checklist | Manual |

## 2. Semantic golden (the main porting test)

1. `tests/v02_actions.py` parses the v0.2 `autounattend.xml` (`docs/appendices/B-autounattend-v0.2/`, constant `V02`):
   extracts the three scripts from CDATA, finds the calls to `Set-Reg`, `Remove-Reg`, `Set-ServiceStart`,
   `Invoke-Exe` and reduces them to tuples `("reg", path, name, kind, value)`, `("reg-remove", path, name)`,
   `("service", name, start)`, `("exe", file, args)`. The values of `$Config.X` and `$du` are substituted
   with the known v0.2 defaults.
2. The catalog with the "Office" preset is expanded into the same kind of tuple set (default parameters,
   `DU:` is replaced the same way).
3. Assertion: the v0.2 set is a subset of the catalog set; each missing item is reported
   together with the expected rule. Actions of type `ps` are compared by normalized text
   for known fragments (NetFx3, SMB1, apps, profile hive, Post-OOBE task).
4. Reverse verification (warning, not error): catalog actions missing from v0.2 are listed
   in the test output so that new rules are added deliberately.

## 3. Per-module tests

### core/catalog.py

- Loading all files in `rules/`; the number of rules and groups is greater than zero; each rule has actions.
- Faulty catalogs in a temporary folder: duplicate id, unknown group, `requires` pointing to a nonexistent
  rule, cycle `a → b → a`, action without a required field, unknown action type, invalid
  phase, parameter without a default: each yields a `CatalogError` with the identifier and the file.
- For a rule, the search index contains its id, title, tags, summary and action strings (path, name, command).

### core/deps.py

- `a requires b`: disabling `b` disables `a`; enabling `a` enables `b`.
- Chain `a → b → c`: disabling `c` disables `b` and `a`; the list of changes contains the reasons.
- `conflicts`: enabling `x` disables `y` and every rule that requires `y`.
- Group: disabling a group disables the group's rules and the external dependents.
- Idempotency: disabling again yields an empty list of changes.
- `apply_order`: the required rule comes before the requiring one; phase order is respected; rules of the same phase without
  dependencies keep the catalog order.

### core/profile.py

- A profile from the catalog equals the "Office" preset (file `profiles/preset-office.json`).
- A save/load cycle yields an equal object; the `rules` keys are in catalog order.
- A profile missing some rules is completed with defaults, with warnings; unknown rules go to `unknown`.
- Migration of a format 1 profile (via the `config → rules` table) yields the expected states.
- `diff` of two profiles lists the differences in rules, parameters and data.

### core/render.py

- Two calls on the same profile yield the same bytes.
- A profile with a disabled rule: not a single line of its actions appears in the output; the block
  `# [id]` is absent.
- A phase without rules: the phase infrastructure is absent (no Active Setup, no Post-OOBE task).
- Parameters are substituted; a string with a single quote is escaped.
- Every `Path` in the XML is no longer than 259; the XML is parsed by `xml.etree`; the profile is embedded and reads back.
- The build of the "Office" preset contains all rules of the preset, by the identifiers in the comments.

### core/validate.py

One bad profile or XML for each row of the table in specification section 3.5; a good profile yields
zero errors. Separately: a disabled baseline rule yields a warning; an enabled risky rule yields
a warning with the risk text.

### core/importer.py

- Importing XML with an embedded profile returns an equal profile.
- Importing a v0.2 file without an embedded profile yields a profile equal to the "Office" preset in its rules
  (via action matching); unmatched actions are listed.

### core/pscheck.py

- Without `powershell.exe` the result is "skipped"; with it, a syntax error is detected.

### ui

- `MainWindow` with `withdraw()`: the tree contains all groups and rules; searching for "PUAProtection" leaves
  one rule; toggling a node changes the profile and redraws the dependents; a parameter in the panel
  changes the profile. The tests are marked and skipped without a display (`tk.TclError`).

## 4. Portability checklist and acceptance test

Unchanged from revision 0.1 (sections 4 and 5 of the old document): a clean VM, launch from
a flash drive, snapshots of the registry and `%APPDATA%` before and after, moving the folder, removal without traces; an acceptance
installation of Windows 11 with a file from the "Office" preset according to the README checklist.

## 5. Organization

- `python -m unittest discover -s tests -v` in the `WinKickOff/` folder; `tools/run-tests.ps1` does the same
  and additionally runs `tools/Validate-Unattend.ps1` on the built file.
- Coverage (if `coverage` is available in the VM): `core` at least 80%.
- Tests do not write outside `tempfile.TemporaryDirectory()`.
