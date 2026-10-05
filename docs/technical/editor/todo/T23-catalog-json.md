# T23. Catalog in JSON; catalog files of imported templates

Status: done in code (04.10.2026; the fixes of its adversarial reviews up to 05.10.2026), version 1.3.0-rc.1; the
catalogs of the program wait for the license check.
Stage 9. Dependencies: T19, T20.

## Goal

The customer's request of 04.10.2026, item 5:

1. One format for the built-in catalog and for the imported one: JSON everywhere, TOML removed.
2. Export and import of such JSON files.
3. Catalog files may be compressed; the build script compresses them, an import compresses nothing.
4. The program ships ready catalogs imported from the ADMX templates of the system.

Decisions of the customer:

- The records of imported ADMX templates travel in a JSON envelope, a catalog file (package) that holds the same
  records as `admx/<id>/policies.json`.
- The catalogs of the program wait for a check of the license of the Microsoft templates; the code, the menu entry
  and the build step are ready, no package is committed.
- The dashes in the texts of Microsoft templates stay as Microsoft wrote them; the folder `catalogs/` is exempt from
  the dash check.
- Only the catalogs of the program are compressed, by the build; the repository keeps them as plain JSON, and the
  built-in catalog stays separate JSON files in `rules/`.

## Result

- Catalog files (`../03-data-model.md`, sections 1-3): `rules/groups.json` is `{"comment": [lines], "groups": [...]}`,
  `rules/NN-<area>.json` is `{"comment": [...], "rules": [...]}`, `rules/lang/<code>.json` is `{"_language": ...,
  "_comment": [...], "<rule id>": {...}, "_groups": {...}}`. The fields of rules, groups, parameters and actions
  keep their names and meaning; a rule may hold `note`, a remark for catalog editors shown nowhere (the former
  comments between rules), and the leading comment of a file became `comment`. A `ps` script of several lines is a
  list of lines (joined with a line break, no trailing one); a one-line script stays a string. Registry paths need
  doubled backslashes. Every TOML file was removed; `core/catalog.py` and `core/i18n.py` no longer import `tomllib`.
- `core/jsonfile.py`: strict reading (a duplicate key, `null`, `NaN` or `Infinity`, a number too large for a float, a
  lone surrogate escape, nesting deeper than 32 levels, more than 1 000 000 values counted before the text is parsed,
  text that is not UTF-8 and a byte order mark are errors; messages quote at most 60 characters of the file), gzip and
  xz recognised by their first bytes and unpacked with a size limit (xz also with a memory limit of 128 MB), one
  stream and nothing after it, and the canonical writer, which refuses what it could not read back.
- Known fields only: an unknown key of a file, rule, group, parameter, enum option or action is a `CatalogError`
  naming the field (`GROUP_KEYS`, `RULE_KEYS`, `PARAM_KEYS`, `OPTION_KEYS`), and a parameter takes only the fields of
  its type (`PARAM_TYPE_KEYS`); text fields must be strings. A misspelt field is no longer ignored silently. A field of
  a type no check foresaw still gives a `CatalogError` naming the file and the rule, never a crash of the loader.
- Translation files: `i18n.language_file_problem` checks the shape of `rules/lang/<code>.json` (known keys
  `_language`, `_comment`, `_groups` and rule ids, known fields of a rule entry, strings where texts belong). A file
  that fails is not used: the window (`i18n.set_language`) and the MCP server (`ToolRegistry.texts`) log a warning and
  show the English source.
- Canonical layout: two spaces of indent, an object or an array on one line when it fits in 120 columns, CRLF, UTF-8
  without a byte order mark; `rules/*.json` are pure ASCII. `tools/format_catalog.py` rewrites the files (`--check`
  only lists them). The generators write JSON: `tools/make_browser_rules.py` writes `rules/14-browsers.json`,
  `tools/make_shell_rules.py` writes `rules/17-shell.json`.
- `core/package.py`: the envelope `{"format": "winkickoff-catalog", "version": 1, "kind": "admx", "name", "windows",
  "created", "comment" (optional), "templates"}`; file names `*.json`, `*.json.gz`, `*.json.xz`; limits 64 MB as
  stored and 64 MB unpacked, at most 1 000 000 values, 128 MB for the xz decoder; `null` allowed in packages and in the
  saved records (a deleted value, the texts of the two states of a check box), never in the rule catalog;
  `export_package`, `parse_package`, `read_package`, `find_package_imports`, `import_package`, `bundled_catalogs`,
  `bundled_collisions`, `import_bundled` (`../03-data-model.md`, section 10).
- `core/admx.py`: `check_templates` checks every record of a package and of every saved import against what the
  template parser writes (known fields; safe keys, value names and strings; write kinds and ranges; parameter names;
  enum and int defaults; list and multiText shapes; class; file name; texts by culture; counts); a record of a shape
  no check foresaw is refused, never passed on. `load_import` reads `import.json` strictly (`_read_meta`, `_info`: at
  most 64 KB, every field of its type, and the id must be the name of the folder, because the kind of an import and
  the ids of its groups come from the folder) and `policies.json` through `core/jsonfile.py` (64 MB, `null` allowed)
  and checks the records on every load, because the program folder is writable: `conform` checks each policy once,
  then `check_templates(data, policies=False)` only the sections; `with_imports` never raises: an import
  that fails is a message, which the window shows at start, and the program starts without it. `store_import` checks
  before it writes and encodes both files before it creates the folder, so a failed import leaves no folder;
  `check_name` is shared with the rename, `save_import` cuts a long folder name so that the date of the import stays,
  and `fit_name` cuts a name kept by an older version to 120 characters on export. The registry branches are not
  limited to the policy branches: the templates of Windows write about 50 values under `System\CurrentControlSet` and
  `Software\Microsoft` (build 26300).
- Records of the parser and of older imports (`admx.conform`, `../03-data-model.md` section 8): the template parser
  (`read_templates`) and `load_import` (imports saved by an older version) bring the records into the shape
  `check_templates` accepts. Texts lose control characters (DEL included) and keys that are not culture names; a
  culture matches a bounded pattern (2 or 3 letters, at most 4 subtags), and `adml_cultures` ignores folders such as
  `en-US - Copy`; a chain of categories longer than `MAX_CATEGORY_DEPTH` (32) or a cycle is cut; the problems lose the
  quoted paths of this computer (`without_paths`: single- or double-quoted drive or UNC paths, a pattern without nested
  repetition that runs in linear time, after each problem is cut to 4096 characters; an earlier pattern backtracked
  quadratically, so a saved import with long problems could hang the start); a policy the check would refuse (class
  `machine`, an empty name, a check box with equal checked and cleared values, a key of backslashes only or with a
  `..` segment, `]]>` in a name) becomes a skipped policy with the reason `unsafe` or `broken` instead of refusing the
  whole import. A catalog file is never conformed: it is refused. `check_templates` refuses a chain of parent
  categories deeper than 32 levels or a cycle, and `safe_name` refuses `]]>`.
- Keys and characters (05.10.2026): the C1 controls 0x80-0x9F and the non-characters U+FFFE and U+FFFF are unsafe in
  keys, value names and string values (`safe_name`, `safe_value`): an XML document cannot hold U+FFFE and U+FFFF, and
  the C1 controls are control characters that XML 1.0 discourages and XML 1.1 allows only as references; a key may
  not have a segment that is empty, `.` or `..` between its backslashes or slashes (`admx.safe_key`), because
  PowerShell resolves `..` even with `-LiteralPath`, and a user policy with the key `..\.DEFAULT\...` would leave the
  default user profile. The template parser skips such a policy (`unsafe`), and a catalog file with one is refused.
- Rule ids of an import (`admx._rule_ids`): policies with the same id are numbered by their English titles in lower
  case, then by their position, as 1.2 numbered them for an English interface (1.2 took the titles of the interface
  language), never by the interface language, with a counter per base id (linear); every id reserves its `<id>.off`,
  so an id is never another policy's `<id>.off`. `catalog_part` never lets a rule replace a rule of another import: a
  policy whose Disabled rule `<id>.off` is already the rule of a policy named `Off` of an import made into rules before
  it is left out and logged. `catalog_part.group_for` remembers the group of each category, and `with_imports` reads
  and converts each import (`load_import` and `catalog_part`) in one `try`, so it never raises.
- Fixed string values of imported policies are literal: `admx._action` marks them `"literal": true`, and
  `render.substitute_fields` takes them as they are (`https://example.com/{id}` stays text). "Check" (F7), "Build
  autounattend.xml" (F9) and the MCP tools that build (`check_profile`, `preview_build`, `write_answer_file`, through
  `mcp/workspace.check_and_build` or the window's checks) turn a `KeyError`, `ValueError` or `TypeError` of the build
  into a build issue.
- Profiles (`../03-data-model.md` section 4): the rule entry of an imported policy holds `source`, the most trusted
  kind of import the choice has been in effect in (`catalog.IMPORT_KINDS`, `import_kind`, `import_rank`,
  `RuleOrigin.kind`, `RuleState.source`): `from_dict` and `to_dict(catalog)` keep the more trusted of the saved kind
  and the kind of the import that holds the policy now. A choice whose policy now comes from a less trusted kind is
  held: it waits in `unknown` with a warning and comes back when an import of its kind or a more trusted one is shown
  again. An entry without `source` (profiles saved before 1.3) counts as `folder` (`profile.LEGACY_SOURCE`), because
  catalog files did not exist then: it is held when only a catalog file has the policy and used as before with a
  folder, system or bundled import. The window describes a held choice as held (`UNKNOWN_HELD`), offers "Show ..."
  only for hidden imports of its kind or a more trusted one, and after a restart of the window shows the warning about
  held choices in the message list (`app.create_app`), not only in the log.
- Profiles of a wrong shape: `Profile.load` reads the file strictly through `jsonfile.read` (16 MB, `null` allowed, a
  duplicate key, `NaN` or nesting deeper than 32 levels refused), and the embedded profile of an answer file is read
  with `jsonfile.loads` (`importer`); `Profile.from_dict` refuses a profile that is not an object with `ValueError`,
  checks the depth of an object given directly (`jsonfile.check_depth`), turns any `TypeError`, `AttributeError`,
  `KeyError` or `RecursionError` into `ValueError`, gives fields of a wrong type their defaults, with a warning for
  the format, rule entries, `enabled`, parameter values (`profile._fits`) and the values of `install` and `languages`
  (`"install": 5` no longer refuses the profile), takes `enabled` 0 or 1 as false or true (as 1.2 did), turns a
  boolean that MCP of 1.2 saved for an enum into the option it equals (`profile._as_option`), and keeps the name and
  the author on one line (`profile.one_line`). The MCP `set_param` refuses a boolean for an enum (`True == 1` in
  Python). `apply._label` uses `render.ascii_text`, so a profile name with line breaks stays on the comment line of
  the Apply, Audit and Undo scripts.
- Smaller fixes: `export_package` writes the problems without paths; `tools/make_admx_catalogs.py` checks `--windows`
  (`package.WINDOWS_RE`) and the whole package before it writes, through a temporary file; `jsonfile.dumps` checks the
  key types at every level; `i18n.load_strings` refuses a strings file that is not an object (the interface stays
  English); renaming and deleting imported templates show their errors through `error_text`; the description of an
  imported tree counts the skipped policies from the records.
- Import ids: `package-YYYYMMDD-HHMMSS` for a catalog file, `bundled-<file name in lowercase words>` for a catalog of
  the program, `system-...` and `folder-...` as before.
- Trust order (`IMPORT_KINDS`, `trust_order`): a policy held by two imports takes its rule and registry values from
  the catalogs of the program, then the templates of this Windows, then a folder of templates, then a catalog file;
  within one kind, in the order shown. Before 1.3 the import loaded first won. The other trees show the policy as an
  alias with the same check mark; the trees keep their order. `load_import` refuses an `import.json` whose id names
  another import, so a file in a folder cannot give the folder the trust of another kind.
- Window, menu "ADMX" (never through MCP): "Import a catalog file..." (dialog "Import a catalog file", file type
  "WinKickOff catalog"; the same file imported again asks Yes to update the import in place, No to add a tree,
  Cancel), "Import a catalog of the program" (a submenu by file name, greyed out without catalogs; importing again
  updates the same tree and keeps a name the user gave it), "Export imported templates" (a submenu of the saved
  imports; plain canonical JSON with CRLF, without the folder of the original import). Reading runs in a background
  thread; meanwhile the other imports, showing or hiding, renaming and deleting imported trees and a change of the
  language or the theme do nothing, because each would rebuild the window. Errors are cut to 1500 characters for the
  message box (`error_text`). The buttons of an unknown policy also offer "Import a catalog file...". Russian and
  Ukrainian labels in `resources/strings.ru.json` and `strings.uk.json`.
- Catalogs of the program: `WinKickOff/catalogs/` (README and packages `<name>.json` in the canonical layout);
  `tools/make_admx_catalogs.py <templates folder> <catalogs/name.json> --name "<tree name>" [--windows 10.0.26200]`
  makes a package with the ADML of every language of the program; `tools/build.ps1` runs `tools/pack_catalogs.py`,
  which refuses two files with the same import id, checks every package, writes `_internal/catalogs/<name>.json.xz`
  (xz preset 9 extreme) and reads it back, and the build fails when the counts differ. All templates of Windows 11
  build 26300 (224 files, 3532 policies, 20 skipped; en-US, ru-RU, uk-UA) take about 13 MB as JSON and 0.83 MB in xz.
- Version 1.3.0-rc.1 (`APP_VERSION`) also carries the customer requests of 04.10.2026 committed before T23: File
  Explorer namespaces and desktop icons (26 rules, card 20), the account asked during installation (profile format
  3), the keys that switch the input language (`default-user.input-switch-keys`, also on the sign-in screen), the
  edition chosen during installation (key mode `ask`), catalog and runtime 0.6 (278 rules, 40 groups) and the
  security fix of placeholders (parameters are filled in only in values, never in registry paths or value names).
- Tests: `tests/test_catalog_format.py` (canonical layout of every catalog file, ASCII rule files, generated files up
  to date, the format tool, strict reading, the value count, compressed files with size and memory limits, a spy on
  the gzip and xz decoders that are never asked for more than the limit, the writer refusing keys that are not
  strings at any level), `tests/test_package.py` (export and import, compressed files, refused envelopes and records
  including `]]>` and chains of categories, size limits, a tampered saved import, `DamagedStoreTest`: damaged
  `import.json` and `policies.json` reported and never raised, an import of an older version with odd records, long
  names; `ParserAndBoundsTest`: the parser skips what the check would refuse, fixed texts with braces stay text, 5000
  policies with one id load in seconds, ids independent of the language and of `<id>.off`, a choice that never moves
  to a less trusted source; `RoundFourTest`: paths cut in linear time with both quotes, deep profiles refused as
  `ValueError` from a file, an object and an answer file, the most trusted kind kept as `source`, a choice saved before
  1.3 never moving to a catalog file, a Disabled rule never replacing a rule of another import, the id of an import
  taken from its folder, C1 controls, U+FFFF and dot segments of keys refused, a boolean never becoming an enum value,
  ids numbered by the English titles, wrong types of a profile warned about; trust order, the catalogs of the program
  and the pack tool, the window: menu, background import, a second import, errors, busy guards),
  `tests/test_catalog.py` (misspelt fields, parameter fields by type, strict JSON, scripts as lists of lines, notes, no
  TOML left), `tests/test_i18n.py` (translation and strings files of a wrong shape fall back to English),
  `tests/test_profile.py` (profiles of a wrong shape, the name and the author on one line), `tests/test_apply.py` (a
  profile name never leaves the comment line); 787 tests.
  `tests/quiet_tk.py` keeps every window of the tests invisible (alpha 0, a tool window from its creation); every
  test module that opens a window imports it first.

## Acceptance criteria

- `python -m unittest discover -s tests` is green.
- The conversion changes nothing in the result: the four presets and a profile with every rule on build
  byte-identical answer files and scripts before and after it; the catalog objects and the translations are equal
  (nine scripts of several lines lost a trailing line break, which the build drops anyway). The catalog version
  stays 0.6 (`templates/VERSION` unchanged) and profiles are unchanged.
- A package exported by one WinKickOff and imported by another gives the same rules, plain or compressed; a package
  with a record the parser never writes is refused with the policy and the field named.
- One odd policy of a folder of templates or of a saved import (also one saved by an older version) is skipped with a
  reason, never refusing the import; a catalog file with such a record is refused.
- The ids of imported policies do not depend on the interface language, and a choice made in a more trusted source
  never moves silently to a less trusted one; neither does a choice saved before 1.3 move to a catalog file.
- A rule of one import never replaces a rule of another, and a profile or an answer file from someone else cannot
  crash the program by its nesting or its types.

## Open points

- The license check of the Microsoft templates, which the customer asked for, before a package is committed to
  `catalogs/`; until then "Import a catalog of the program" is greyed out.
- A portable build with a catalog in `_internal/catalogs` has not run yet, since there is no package; the pack step is
  covered by `tests/test_package.py`.
