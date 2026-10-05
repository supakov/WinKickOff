# 04. Testing strategy

Revision 0.2 of 25.09.2026, updated 04.10.2026 (T23) and 05.10.2026 (`RoundFourTest`). Tool: `unittest` from the
standard library (`python -m unittest discover -s tests`), pytest compatibility is kept. No test changes the
state of the machine: tests read project files and write only to the test's temporary folders.

Window tests stay invisible on the screen of the person who runs them (customer rule of 04.10.2026, `AGENTS.md`
section 4, rule 12): every test module that opens a window imports `tests/quiet_tk.py` before its first `tk.Tk()`,
including the probe `tk.Tk(); destroy()` that decides whether Tk is available. The module patches `tk.Tk` and
`tk.Toplevel` so that every window is fully transparent (alpha 0) from its creation and, on Windows, a tool window
without a taskbar button; the windows still exist and are laid out, so the tests that need a mapped window (the
Treeview lays out rows only then) work as before. Message boxes and file dialogs are mocked, and subprocesses get
`CREATE_NO_WINDOW`. A throwaway script that needs Tk imports `tests/quiet_tk.py` first or sets the two attributes
right after `tk.Tk()`, before any update.

## 1. Levels

| Level | What it verifies | Where it runs |
|---|---|---|
| Catalog | Integrity of `rules/*.json`: unique ids, existing groups and dependencies, no cycles, valid action types and required fields, known fields only, filled-in descriptions, links to existing reference files | Everywhere |
| Catalog files | Canonical layout of every catalog file, ASCII rule files, generated files up to date, strict JSON reading (`test_catalog_format.py`); catalog files of imported templates: export, import, checks, limits, trust order, catalogs of the program (`test_package.py`) | Everywhere |
| Semantic golden | Each action of the v0.2 file is present in the catalog under the v0.2 reference profile with the same value | Everywhere |
| Resolver | Disable and enable cascade, conflicts, group operations, application order | Everywhere |
| Profile | Loading, saving, completeness, migration, `unknown`, comparison, fields of a wrong shape | Everywhere |
| Generator | Determinism; only enabled rules in the output; correct order; parameter substitution; escaping; 259 limit; well-formed XML | Everywhere |
| Validator | Each check catches its own bad profile or XML and stays silent on a good one | Everywhere |
| External verification | The built XML passes `tools/Validate-Unattend.ps1`; the scripts are parsed by PowerShell 5.1 | Windows only, skipped without `powershell.exe` |
| UI smoke | The window is created fully transparent (`tests/quiet_tk.py`) and outside the screen, the tree is built, search filters, a check box calls the resolver | Windows with a display; skipped without Tk |
| Portability | Checklist in a VM | Manual |
| Acceptance | Installation in a VM, README checklist | Manual |

## 2. Semantic golden (the main porting test)

1. `tests/v02_actions.py` parses the v0.2 `autounattend.xml` (`docs/appendices/B-autounattend-v0.2/`, constant `V02`):
   extracts the three scripts from CDATA, finds the calls to `Set-Reg`, `Remove-Reg`, `Set-ServiceStart`,
   `Invoke-Exe` and reduces them to tuples `("reg", path, name, kind, value)`, `("reg-remove", path, name)`,
   `("service", name, start)`, `("exe", file, args)`. The values of `$Config.X` and `$du` are substituted
   with the known v0.2 defaults.
2. The catalog with the v0.2 reference profile (`reference_profile()`: the catalog defaults with
   `V02_DIFFERENCES` and `V02_PARAMS`, because the defaults have moved on since 26.09.2026) is expanded into
   the same kind of tuple set (`DU:` is replaced the same way).
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
- Strict JSON (T23): a misspelt field of a rule, a group, a parameter, an option or an action, a key other than the
  list and `comment` at the top of a file, a duplicate key, `null`, `NaN` or a byte order mark, and a text field that
  is not a string are refused; a parameter takes only the fields of its type (`min` of an enum, `pairs` of a string
  are errors) and an enum value is a string or an integer; a field of a type no check foresaw gives a `CatalogError`
  naming the file and the rule; a `ps` script of several lines is a list of lines in the file and `note` is accepted;
  no TOML file is left in `rules/`.

### core/i18n.py

- `tests/test_i18n.py`: a file added to `rules/lang/` or `resources/` adds a language and gaps fall back to English; a
  translation file of a wrong shape (`i18n.language_file_problem`: an unknown key or field, a text that is not a
  string) and an interface strings file that is not a JSON object (`i18n.load_strings`) are refused, and the program
  shows the English source instead of failing; every marked interface text has its Russian and Ukrainian
  translation. `tests/test_docs.py` requires complete catalog translations without entries for unknown rules or
  groups.

### Catalog files (task T23)

- `tests/test_catalog_format.py`: every file of `rules/`, `rules/lang/` and `catalogs/` is in the canonical layout
  of `tools/format_catalog.py`; `rules/*.json` are ASCII; `rules/14-browsers.json` and `rules/17-shell.json` equal
  what their generators write now; `tools/format_catalog.py` on a temporary tree (exit codes 0, 1 with `--check`, 2
  for a file it cannot read, which it leaves as it is); a catalog of the program made by `tools/make_admx_catalogs.py`
  holds `null` and is canonical, and one that is not a catalog file is refused. `core/jsonfile.py` writes the canonical
  layout and refuses what it could not read back (keys that are not strings, also nested in objects and lists, and
  numbers that are not finite); it refuses duplicate keys, `null`, `NaN`, `Infinity`, numbers too large for a float,
  lone surrogate escapes and deep nesting (also 100 000 brackets), counts the values before it parses (the parser is
  never called above the limit), quotes only a little of the file in a message, reads gzip and xz with limits (a cut
  stream, data after the stream, a small file that unpacks above the limit, a bomb stopped while it unpacks, with
  spies on the gzip and the xz decoder that are never asked for more than the limit plus one byte, the memory of the
  xz decoder, a lack of memory) and refuses text that is not UTF-8.
- `tests/test_package.py`, by class:
  - `ExportImportTest`: an exported import is the envelope with the same records, without the folder of this
    computer, and importing it gives the same rules; compressed files are read; a build with a policy of the file
    writes its value.
  - `RefusedFilesTest`: refused envelopes, JSON that is not strict, records the parser never writes (also `]]>` in a
    value name or a key), bad elements, chains of parent categories deeper than 32 levels and a cycle (32 levels are
    accepted), sections of the records, a lone surrogate (no folder is left by the failed import), long messages and
    size limits; a tampered policy of a saved import is skipped while the others load.
  - `TrustAndBundledTest`: the more trusted source makes the shared rules while the trees keep their order (bundled,
    then system, then folder, then package); the catalogs of the program, the files of `catalogs/` and
    `tools/pack_catalogs.py` (also two files with the same import id).
  - `DamagedStoreTest`: damaged `import.json` and `policies.json` files are reported by `with_imports`, never raised;
    an import saved by an older version with odd records (a culture `en-US - Copy`, DEL in a title, the class
    `machine`, a path of this computer in a problem) still loads, with the odd policy skipped and the path reduced to
    the file name, also in an export; long folder names and names of older versions are cut to 120 characters.
  - `ParserAndBoundsTest`: the template parser skips what the check would refuse (the class `machine`, an empty name,
    a check box with equal values, a key of backslashes only, `]]>` in a name; a culture folder `en-US - Copy`; DEL in
    a text becomes a space) and the import goes on; a fixed text with braces stays text in a build, from templates and
    from a catalog file; 5000 policies with one id and a chain of 32 categories load in less than 15 seconds; the ids
    are the same in English and Russian, and a policy named `off` is numbered instead of taking the `<id>.off` of
    another policy; a choice made in the templates of this Windows waits in `unknown` when only a catalog file holds
    the policy, and comes back with those templates.
  - `RoundFourTest` (the fixes of 05.10.2026, after the review of round 3): `without_paths` cuts 200 problems of 4096
    characters with a quote that never closes in less than 2 seconds and reduces single- and double-quoted drive and
    UNC paths (also with an apostrophe inside a double-quoted path) to file names; a profile nested 600 levels deep
    raises `ValueError` from `Profile.from_dict` and from `Profile.load`, and an answer file whose embedded profile is
    20 000 brackets deep gives `ImportFailed`; a choice made in a catalog file and then used with the templates of this
    Windows is saved with the source `system` and held when only the catalog file holds the policy again; a choice
    saved by 1.2 (no `source`) is held when only a catalog file has the policy and used with a folder of templates; a
    Disabled rule `<id>.off` of a catalog file never replaces the rule of a policy named `Off` of the templates of
    this Windows (the policy of the file is left out, no problem is reported); `load_import` refuses an `import.json`
    whose id names another import; U+FFFF and the C1 control U+0085 are unsafe in names and values, keys with a `..`,
    `.` or empty segment (also with slashes) are unsafe while `Vendor.App` is a safe segment, and a catalog file with
    the key `..\.DEFAULT\Control Panel` is refused; the MCP `normalise_param_value` refuses `false` for an enum, and a
    boolean saved for an enum by MCP of 1.2 loads as the integer option 0; two policies with one id are numbered by
    their English titles with the Russian interface (the later one in the file, first by its title, gets the bare id);
    `enabled` 0 loads as off, `enabled` `"yes"`, `install.edition` 5 and `languages.ui_language` 7 give their
    defaults with warnings, and `"install": 5` loads.
  - `PackageWindowTest`: in the window, the three new entries of the ADMX menu, the import of an exported file in the
    background as a new tree, a second import of the same file (Yes, No, Cancel), a catalog of the program, errors
    cut for the message box, and the commands that do nothing while the window is busy (message boxes and file
    dialogs mocked).

  Everything is written into temporary folders.

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
- Wrong shapes (T23): fields of a wrong type (`format_version`, `install`, `languages`, accounts that are not
  objects, rule entries that are not objects, `enabled` and parameter values of a wrong type) load with their
  defaults and a warning where the data model names one; a profile that is not a JSON object raises `ValueError`.
- The name and the author stay on one line (LF, CRLF and U+2028 become spaces); the comment keeps its lines.
- Provenance of imported choices (`tests/test_package.py`, `ParserAndBoundsTest` and `RoundFourTest`): `source` is
  written as the most trusted kind the choice was in effect in, a choice is held in `unknown` while only a less trusted
  source holds its policy, and an entry without `source` counts as `folder`.
- Strict reading and wrong types (`RoundFourTest`): a profile nested deeper than 32 levels is a `ValueError` from a
  file, from an object and from an answer file; `enabled` 0 and 1 are false and true, other wrong types give defaults
  with warnings; a boolean saved for an enum becomes the option it equals.

### core/apply.py

- `tests/test_apply.py` checks the plans and the generated scripts of T15 and never runs them. Since T23 also: a
  profile name with LF, CR and U+2028 stays on the one comment line of the Apply, Undo and Audit scripts, and no line
  of the name becomes a command.

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
- Importing a v0.2 file without an embedded profile yields a profile equal to the v0.2 reference profile in its
  rules (via action matching); unmatched actions are listed.

### core/pscheck.py

- Without `powershell.exe` the result is "skipped"; with it, a syntax error is detected.

### ui

- `MainWindow` made invisible by `tests/quiet_tk.py` (alpha 0, a tool window) and placed outside the screen: the tree
  contains all groups and rules; searching for "PUAProtection" leaves one rule; toggling a node changes the profile
  and redraws the dependents; a parameter in the panel changes the profile. The tests are skipped when Tk cannot
  create a window (`skipUnless(TK_OK)`), and a test that needs row geometry skips itself when the Treeview has none.

### mcp (task T22)

`tests/test_mcp_protocol.py` (JSON-RPC parsing, the schema checker, redaction, the journal, the handshake and every
method of `McpServer.handle` on a `HeadlessWorkspace`), `test_mcp_tools.py` (every tool in every mode, secrets never
leave any tool or resource, the forbidden functions are unreachable, no tool takes a path), `test_mcp_transports.py`
(stdio in memory, the command line, the HTTP transport on 127.0.0.1 port 0 with `http.client`, which the tests may
import), `test_mcp_window.py` (the bridge and the menu on a withdrawn window, the monitor), `test_mcp_settings.py`.
Rules: loopback port 0 only, no PowerShell, no server outside `unittest` on the customer's PC, log assertions through
`assertLogs("winkickoff.mcp")` and never through the log file, two `-X importtime` subprocesses prove that a headless
start never imports tkinter.

## 4. Portability checklist and acceptance test

Unchanged from revision 0.1 (sections 4 and 5 of the old document): a clean VM, launch from
a flash drive, snapshots of the registry and `%APPDATA%` before and after, moving the folder, removal without traces; an acceptance
installation of Windows 11 with a file from the "Office" preset according to the README checklist.

## 5. Organization

- `python -m unittest discover -s tests -v` in the `WinKickOff/` folder; `tools/run-tests.ps1` does the same
  and additionally runs `tools/Validate-Unattend.ps1` on the built file.
- Coverage (if `coverage` is available in the VM): `core` at least 80%.
- Tests do not write outside `tempfile.TemporaryDirectory()`.
