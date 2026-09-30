# T04. JSON profile, presets, migration, comparison

Status: done (25.09.2026: model, loading, saving, comparison; the "Office" and "Strict" presets are created by
`tools/make_presets.py`, and `test_presets.py` verifies them against the catalog. Migration of format 1 is not needed: no format 1
profiles exist). Stage 2. Dependencies: T02.

## Goal

Implement `core/profile.py` per `03-data-model.md`, section 4, and presets as files.

## Steps

1. `Profile` with the sections `meta`, `install`, `languages`, `accounts`, `rules`, `unknown`.
2. `Profile.from_catalog(catalog)`: all rules with `default`, parameters with their defaults.
3. `Profile.load(path, catalog) -> (Profile, warnings)`: adding new rules, `unknown`,
   migration of format 1 → 2 using the `config → rules` table.
4. `Profile.save(path)`: key order, indent 2, `ensure_ascii=False`.
5. `Profile.diff(other) -> list[Difference]`.
6. `profiles/preset-office.json` (= catalog defaults) and `preset-strict.json` (controlled
   folder access, SmartScreen Block, ASR prevalence set to block, NetBIOS disabled, VBScript removed).
7. `tests/test_profile.py`.

## Acceptance criteria

- A save and load cycle yields an equal object; the "Office" preset equals `from_catalog`.
- An unknown rule survives the cycle; a new catalog rule is added with a warning.

## Implementer notes

25.09.2026: `Profile`, `from_catalog`, `load`, `save`, `diff` and tests are created; the presets are not yet
written to files (they are generated from the catalog on first run; the task is to save them in `profiles/`).
