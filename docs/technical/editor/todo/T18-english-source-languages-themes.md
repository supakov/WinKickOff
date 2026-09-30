# T18. English source language; languages and colour themes as files

Status: done (30.09.2026). Stage 6 (additional). Dependencies: T14.

## Goal

The customer's list of 29.09.2026:

1. English is the main language of the interface and of the catalog texts; Russian becomes a translation file
   like Ukrainian; every code comment is English.
2. The set of languages comes from the translation files, so a user adds a language by adding files.
3. A missing part of a translation shows the English source text.
4. Colour schemes in separate files: Light (the previous look), Dark and a playful Matrix; follow the Windows
   setting where possible.

## Result

- Interface: every `tr()` and `N_()` literal of the package is English; `resources/strings.ru.json` and
  `strings.uk.json` are keyed by the English text and carry `_language` (native name). The inversion lost no
  translation (every former key was matched; no two Russian texts had the same English translation).
- Catalog: `rules/*.toml` texts, tags and comments are English; `rules/lang/ru.toml` holds the Russian texts and
  the Russian search tags, `rules/lang/uk.toml` the Ukrainian ones, both with `_language`. The browser table of
  `tools/make_browser_rules.py` is English and generates the same `14-browsers.toml`. Preset names are the
  English data values Office, Strict, Laptop and are shown through `tr()`; "Imported from XML" likewise.
- `core/i18n.py`: `available_languages()` scans `strings.*.json` and `rules/lang/*.toml` (a code matches
  `^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$`), English is always first; `resolve_language("")` follows the Windows
  interface language (`GetUserDefaultUILanguage`), otherwise English; every gap (file, rule, field, string)
  falls back to English with a log line for a broken file. Search also matches the translated title, summary
  and tags.
- `core/themes.py` and `resources/themes/{light,dark,latte,matrix}.json`: `native` keeps the vista look and recolours
  texts and marks, `clam` takes every colour (Dark, Latte, Matrix); missing or bad colours fall back to the light
  palette, a broken file is skipped; `""` follows `AppsUseLightTheme` (read only). A dark theme also gets a dark
  title bar (`DwmSetWindowAttribute`, attribute 20, then 19 for older builds). Check box images are drawn in
  the theme colours. Menus "Language" and "Theme" start with "As in Windows"; the choice is stored in
  `settings.json` and the window is rebuilt with the open profile.
- Tests: `test_i18n.py` (English sources, complete ru and uk, a file adds a language, fallback), `test_themes.py`
  (bundled and user themes, broken files, following Windows, the window in every theme), `test_sources.py`
  (English code, comments and catalog; registry reads only in `core/themes.py`, writes nowhere).

## Acceptance criteria

- `python -m unittest discover -s tests` is green; the window opens in English, Russian and Ukrainian and in
  the three themes.
- A file `strings.<code>.json` or `rules/lang/<code>.toml` copied into the folders adds a language without code.

## Open points

- The themes are checked by tests and by screenshots of the window with an open menu; how they look on the
  customer's screens is to be judged by the customer.

30.09.2026, first bug report: the menu bar stayed white in every theme. Windows paints its native menu bar in
system colours only, so coloured themes now get a row of menu buttons in the theme colours (Alt + underlined
letter, F10), and `ui/winmenus.py` repaints the light 2 px margin around drop-down menus (WinEvent hook of this
thread, `SetMenuInfo`); a 1 px grey outline drawn by Windows remains. Menus of the Matrix theme now use its
font (on Windows menus take the system font unless `*Menu.font` is set). The same day the customer asked for
a beige, coffee and milk theme: `latte.json`.
