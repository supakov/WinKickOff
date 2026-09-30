# T07. Catalog, profile and XML validator

Status: done (25.09.2026: `validate_profile`, `validate_xml`, `validate_catalog` (the "Build, Check rule catalog"
command: loader errors, link anchors, verification and rollback texts, risk), bad profiles
`tests/profiles/bad-*.json`; the v0.2 baseline passes without a single finding. The row of table 3.5 about the ISO
language was replaced by an explanation in the form: the editor does not see the ISO). Stage 3. Dependencies: T06.

## Goal

Implement `core/validate.py` according to the table in `01-problem-statement.md`, section 3.5.

## Steps

1. `Issue(level, target, message, doc)`; `target` is a rule identifier, a profile field or an XML element.
2. `validate_catalog(catalog)`: a wrapper over the loader checks for the "Check rule catalog" command.
3. `validate_profile(profile, catalog)`: accounts, languages, parameters within range, base rules turned
   off (warning), risky rules turned on (warning with the risk text), password set, `ui_language` against
   the ISO language (profile field `iso_language`, if set).
4. `validate_xml(text)`: the same checks as in `tools/Validate-Unattend.ps1`, on `xml.etree`.
5. Bad profiles in `tests/profiles/bad-*.json`, bad XML strings in the test; a good profile without errors.

## Acceptance criteria

- Every row of table 3.5 is covered by a "catches it" test and a "does not fire on a good one" test.
- The v0.2 baseline passes `validate_xml` without errors or warnings.

## Implementer notes
