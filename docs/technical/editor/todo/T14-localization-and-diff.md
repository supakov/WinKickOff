# T14. uk localization, profile comparison, «Ноутбук» (Laptop) preset

Status: todo. Stage 6 (additional). Dependencies: T13.

## Goal

Ukrainian UI and rule translations, a profile comparison dialog, a third preset.

## Steps

1. `core/i18n.py`: UI strings from `resources/strings.<lang>.json`; rule translations from
   `rules/lang/uk.toml` keyed by identifier; switching via the menu.
2. Translation of UI strings and rule fields (`title`, `summary`, `effect`, `risk`, `versions`,
   `rollback`, parameter names); a test for completeness and for the absence of dashes.
3. The «Сравнить с профилем» (Compare with profile) dialog: a table of `Profile.diff()`.
4. `profiles/preset-laptop.json`: lock after 10 minutes, `PreventAutoDeviceEncryption`
   turned off with a validator warning about the recovery key.

## Acceptance criteria

- Language switching without rebuilding; the translation completeness test is green.

## Implementer notes

25.09.2026 (from T16): the rule texts are translated completely into Ukrainian and English
(`rules/lang/uk.toml`, `rules/lang/en.toml`, loaded by `core/i18n.py`; completeness is tested by
`tests/test_docs.py`). Remaining for T14: interface strings, the language switch in the window, the
comparison dialog and the «Ноутбук» (Laptop) preset.
