# T08. Profile import from XML and v0.2; PowerShell check

Status: done (25.09.2026: import of the embedded profile; action-based import for v0.2 and for builds without a profile
(`core/actions_parser.py`: `$Config` values are read from the file, conditions are evaluated, loops over lists
and hash tables are unrolled); `import_xml(v0.2)` equals the «Офис» (Office) preset across all 130 rules, parameters,
installation data, languages and accounts; PowerShell check). Stage 3. Dependencies: T06. Milestone M3 together with T07.

## Goal

Open any previously built file: one with an embedded profile directly, the v0.2 file by matching its
actions against the catalog; check script syntax with `powershell.exe`.

## Steps

1. `core/importer.py`: `import_xml(text, catalog) -> (Profile, warnings)`: if
   `Extensions/Profile` is present, parse the JSON; otherwise extract the actions from CDATA (code shared with
   `tests/v02_actions.py`, to be moved into `core/actions_parser.py`) and match them to rules
   by type, path and name; a rule is considered enabled if all of its actions are found.
2. Unmatched actions and partially found rules are returned as warnings.
3. `core/pscheck.py`: when `powershell.exe` is available, parse the scripts with
   `[System.Management.Automation.Language.Parser]::ParseFile` in the temporary folder `logs/tmp/`;
   30-second timeout; otherwise "skipped".
4. Tests: importing an XML with an embedded profile yields an equal profile; importing v0.2 yields «Офис».

## Acceptance criteria

- `import_xml(v0.2)` equals the «Офис» preset in rule states.
- Without PowerShell the function returns "skipped", not an exception.

## Implementer notes
