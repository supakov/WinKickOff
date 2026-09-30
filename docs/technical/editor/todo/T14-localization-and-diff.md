# T14. uk localization, profile comparison, "Laptop" preset

Status: done (25.09.2026). Stage 6 (additional). Dependencies: T13 (only formally; done before the VM acceptance).

## Goal

Ukrainian UI and rule translations, a profile comparison dialog, a third preset.

## Steps

1. `core/i18n.py`: UI strings from `resources/strings.<lang>.json`; rule translations from
   `rules/lang/uk.toml` keyed by identifier; switching via the menu.
2. Translation of UI strings and rule fields (`title`, `summary`, `effect`, `risk`, `versions`,
   `rollback`, parameter names); a test for completeness and for the absence of dashes.
3. The "Compare with profile" dialog: a table of `Profile.diff()`.
4. `profiles/preset-laptop.json`: lock after 10 minutes, `PreventAutoDeviceEncryption`
   turned off with a validator warning about the recovery key.

## Acceptance criteria

- Language switching without rebuilding; the translation completeness test is green.

## Implementer notes

30.09.2026: superseded in part by T18. The source language is now English; Russian and Ukrainian are
translation files, `strings.en.json` and `rules/lang/en.toml` are gone. The notes below describe the state
of 25.09.2026.

25.09.2026 (from T16): the rule texts are translated completely into Ukrainian and English
(`rules/lang/uk.toml`, `rules/lang/en.toml`, loaded by `core/i18n.py`; completeness is tested by
`tests/test_docs.py`). Remaining for T14: interface strings, the language switch in the window, the
comparison dialog and the "Laptop" preset.

25.09.2026, T14 done:
- Interface in Russian, Ukrainian and English. The Russian text is the key (gettext style): every user-facing
  string of the package is wrapped in `tr()` (templates with positional fields) or marked with `N_()` at module
  level; `resources/strings.uk.json` and `strings.en.json` hold 324 translations. Validation messages,
  derived verification and rollback steps, import warnings and dialogs are translated too; rule, group,
  parameter and option names come from `rules/lang/*.toml` through `core/i18n.catalog_texts()`.
- Menu "Language" with the native names «Русский», «Українська», English; the choice is stored in `settings.json`; the window is
  rebuilt (`app.run` loop) with the open profile, its unsaved changes and the selected node. Search also finds
  translated rule titles and summaries. Time zone titles have uk and en variants in `resources/timezones.json`.
- "File, Compare with profile...": a table of differences by effective values
  (`Profile.diff(other, catalog)`); a double click leads to the rule or data node.
- `profiles/preset-laptop.json`: Office, lock after 600 seconds, automatic device encryption allowed; the
  validator warns to save the BitLocker recovery key (`manage-bde -protectors -get C:`).
- User documentation in uk and en names interface elements in its own language.
- Tests: `test_i18n.py` (every string translated, same placeholders and line breaks, no stale entries, no
  dashes, window in English, switching back keeps the profile), laptop preset, effective diff, comparison dialog.
