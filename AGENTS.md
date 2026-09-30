# AGENTS.md: map of the WinKickOff repository

For agents and developers: where things are, what to read first, which rules apply, the state of the
work. Updated with every change of structure, commands or task status.
Last update: 30.09.2026 (release 1.1.0-rc.4: imported policies follow the built-in rules with the same values, T21).

Repository: https://github.com/supakov/WinKickOff (private, branch `main`; other people push to it too, so
`git pull --ff-only` before starting work). The local clone and the repository must match: commit and push
after every finished task. Commit messages are in Russian (the customer reads the history), first line up to 72
characters, no em or en dashes, and a commit made by an agent ends with the line
`Co-Authored-By: <agent model> <noreply@anthropic.com>` (the model name of the current agent session,
for example `Claude Opus 5.5`).

## 1. The repository in three sentences

WinKickOff is a toolkit that installs and configures Windows 11 Pro in small workgroups without a domain,
where the PCs are used by non-professionals and the organisation is under constant cyber attack; priorities
are security and updatability, no cosmetics and no third-party programs. Its tools: the editor (Python 3.14,
tkinter, portable) that shows every installation rule in a searchable tree, disables dependent rules
automatically and assembles `autounattend.xml` from the selection only, the answer file checker
`tools/Validate-Unattend.ps1`, and the check, apply and return-to-defaults scripts for a running Windows.
The hand-written answer file v0.2 the catalog grew from is kept in the documentation appendices as the reference.

## 2. What to read first

| Task of the agent | Start with |
|---|---|
| Understand the toolkit and its tools | `README.md` in the root, then `docs/README.md` |
| Understand what the answer file does | `docs/appendices/B-autounattend-v0.2/README.md` (Russian), then `docs/technical/reference/00-architecture.md` |
| Find a parameter and its registry keys | `docs/technical/reference/README.md` (index by parameter) |
| Change installation behaviour | a rule in `WinKickOff/rules/` (v0.2 in Appendix B is frozen); Setup limits in `docs/technical/reference/00-architecture.md` section 3 |
| Understand why something differs from UnattendedWinstall | `docs/appendices/C-critical-review/01-critical-review.md` (Russian) |
| Work on the editor | `docs/technical/editor/README.md`, then `docs/technical/editor/todo/README.md`, then `WinKickOff/README.md` |
| Understand why the editor is built on rules, not on `$Config` | `docs/technical/editor/06-critical-review-v0.1.md` |
| Add or change an installation rule | `docs/technical/editor/03-data-model.md`, a file `WinKickOff/rules/NN-*.toml`, then `python -m unittest` in `WinKickOff/` |
| Write or update user documentation | `docs/user/README.md`, the Russian source in `docs/user/ru/`, then the same change in `uk` and `en` |
| Build or release | `.github/workflows/build.yml`, `WinKickOff/tools/build.ps1`, section 5 of this file |
| See what the critic checked in v0.2 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` (Word, at the customer's request) |

## 3. Folder structure

```
(repository root)
├── AGENTS.md                      this file
├── README.md                      the toolkit: purpose, tools, quick start, user docs, builds
├── Start-WinKickOff.cmd           starts the editor from the sources (py launcher, Python 3.14+, no console)
├── .gitignore, .gitattributes     what is not versioned; files are stored byte for byte (CRLF)
├── .github/workflows/build.yml    CI: tests, checker, portable build on every push; a tag v<version> publishes a release
├── tools/
│   └── Validate-Unattend.ps1      answer file checker (36 checks), read-only; without -Path it checks Appendix B
├── docs/
│   ├── README.md                  entry point to the documentation (three languages)
│   ├── technical/                 TECHNICAL DOCUMENTATION, English
│   │   ├── memstechtips-profile.md  generated report: the original of Appendix A mapped onto the catalog (issue #2)
│   │   ├── reference/             reference: a card for every installation parameter (20 files; 18 browsers, 19 more privacy)
│   │   └── editor/                WinKickOff specification: problem, architecture, data model, testing,
│   │       │                      plan (days, milestones), review of revision 0.1
│   │       └── todo/              tasks T01-T21 with status (README.md is the index)
│   ├── user/                      USER DOCUMENTATION: ru (source), uk, en; the same files in each language
│   ├── releases/                  release notes v<version>.md (ru, uk, en), used by the release job
│   └── appendices/                APPENDICES, frozen, Russian: README describes them
│       ├── A-unattendedwinstall/  original UnattendedWinstall answer file (MIT, SOURCE.md, LICENSE)
│       ├── B-autounattend-v0.2/   our hand-written answer file v0.2 (the reference) and its README: history, VM checklist
│       ├── C-critical-review/     review of the original and the critic's report on v0.2 (docx)
│       └── D-requirements-draft/  first requirements draft; section 6 holds open questions to the customer
└── WinKickOff/                    EDITOR 1.1.0-rc.4 AND RULE CATALOG 0.5
    ├── README.md                  developer README: run, test, structure; links to user docs
    ├── pyproject.toml             requires-python >= 3.14, no runtime dependencies
    ├── winkickoff/                package: app.py (start), core/ (paths, log, catalog, deps, profile, resources,
    │                              render, validate, verify, actions_parser, importer, pscheck, settings, i18n, themes,
    │                              apply, admx),
    │                              ui/ (main_window: tree, search, description, parameters, profiles, build;
    │                              data_forms: install, accounts, languages; checkimages: check box images;
    │                              winmenus: theme colours around drop-down menus)
    ├── rules/                     RULE CATALOG in English: groups.toml (36 groups), 00-16-*.toml (251 rules),
    │                              lang/ru.toml and lang/uk.toml (translations; a new file adds a language)
    ├── templates/                 runtime with slots: autounattend.template.xml, Setup-System, Setup-User, Post-OOBE,
    │                              Audit, Apply, Undo *.runtime.ps1, section-*.ps1; README lists the slots; VERSION = 0.5
    ├── resources/                 keyboards.json, timezones.json, strings.ru.json and strings.uk.json (interface
    │                              translations), themes/ (light, dark, latte, matrix colour themes)
    ├── profiles/                  presets Office (= catalog defaults), Strict, Laptop, memstechtips, README
    ├── tests/                     unittest: catalog, resolver, profile, render, build against v0.2, validation,
    │                              import, presets, PowerShell, settings, portability, window smoke test, docs,
    │                              translations, themes, ADMX import;
    │                              v02_actions.py holds the v0.2 reference profile (V02_DIFFERENCES)
    └── tools/                     make_presets.py, make_rule_docs.py, run-tests.ps1, build.ps1 (portable zip),
                                   make_browser_rules.py (generates rules/14-browsers.toml),
                                   memstechtips.py (maps Appendix A onto the catalog for make_presets.py)
```

Working folders `WinKickOff/output/`, `WinKickOff/logs/`, `WinKickOff/settings.json`, `__pycache__/` and
user profiles (all but `preset-*.json`) are not versioned.

## 4. Project rules (mandatory for every agent)

1. The customer's work PC is untouchable. Only reading is allowed there (registry, services, files,
   logs) and running tests that write only into temporary folders or inside the project folder.
   No "temporary" or "reversible" changes to the system: on 12.09.2026 such a test broke the keyboard
   layout switching. Anything that changes the system is done in a virtual machine or written down as
   instructions. The only exception is a separate, explicit command of the customer for a specific action.
   The portable build installs PyInstaller, so it runs in GitHub Actions or a VM, never on the customer's PC.
2. The em dash (U+2014) and the en dash (U+2013) are forbidden in every text we create, in any language:
   documents, code, data, comments, interface strings, commit messages. Number ranges use a hyphen
   (08:00-20:00, T01-T06). Checks: `WinKickOff/tests/test_sources.py` and `test_docs.py`, and the command in section 5.
3. Reports requested by the customer are written as Russian Markdown files in `docs/`; Word only when
   explicitly asked ("в Ворд").
4. Languages: communication with the customer and customer reports in Russian. Instructions and technical
   documentation (`docs/technical/`, this file, READMEs of code folders, code, comments) in English. User
   documentation in `docs/user/` in Russian (the source), Ukrainian and English with the same files and
   structure. The editor's source language is English (interface strings, rule catalog, preset names); Russian
   and Ukrainian are translation files (`WinKickOff/resources/strings.<code>.json`,
   `WinKickOff/rules/lang/<code>.toml`, task T18); other translations only on the customer's demand.
   Identifiers, parameter names and registry keys stay in English everywhere.
5. The starter accounts Admin and User without passwords are a deliberate decision of the customer:
   passwords and groups are assigned by a separate project after installation. Do not propose to "fix" it.
6. The Windows display language is never changed: `UILanguage` equals the ISO language (now uk-UA).
7. Files in `docs/appendices/` are frozen: v0.2 (Appendix B) is the reference the tests compare the catalog
   and builds with. Installation behaviour changes through rules in `WinKickOff/rules/`, observing
   `docs/technical/reference/00-architecture.md` section 3 (Path up to 259 characters, no comments inside
   components, exit 0); then the parameter card in the reference, the presets (`WinKickOff/tools/make_presets.py`),
   the generated rule list of the user documentation (`WinKickOff/tools/make_rule_docs.py`) and the tests. If the
   reference itself must change (customer decision), the file, its README, `test_coverage_v02.py` and the
   checksum in `docs/appendices/README.md` change together.
8. Editor: only the Python standard library in the application; tests on `unittest`; rules in TOML,
   profiles in JSON; rules contain no program logic. A change of the runtime templates needs a new
   `templates/VERSION`.
9. The agent's file writing tools turn escape sequences of the form backslash, `u`, four hex digits into real
   characters. Characters that must not appear in a file (such as dashes in regular expressions) are built in
   code with `chr(0x2013)` or `[char]0x2013`, never with an escape. Shell here-documents may also swallow
   doubled backslashes: edit files with backslashes through the editor tool or a script file.

## 5. Commands

Check an answer file (read-only, PowerShell 5.1); without `-Path` the v0.2 reference in Appendix B is checked:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

Editor tests (Python 3.14, standard library, nothing on the machine changes):

```powershell
cd WinKickOff
python -m unittest discover -s tests -v
```

Regenerate the presets and the rule lists of the user documentation after a catalog change
(`test_presets.py` and `test_docs.py` fail if you forget):

```powershell
cd WinKickOff
python tools/make_presets.py
python tools/make_rule_docs.py
```

Build and release (GitHub Actions, `.github/workflows/build.yml`): every push to `main` runs the tests, the
checker and `WinKickOff/tools/build.ps1`, the zip is an artifact of the run. A release: set `APP_VERSION` in
`WinKickOff/winkickoff/__init__.py` (and `version` in `pyproject.toml`), add `docs/releases/v<version>.md`
(`test_docs.py` checks it), push, then push the tag; the job publishes the release (a prerelease for `-rc`):

```bash
git tag -a v1.1.0-rc.4 -m "WinKickOff 1.1.0-rc.4"
git push origin v1.1.0-rc.4
```

Run the editor from sources (`Start-WinKickOff.cmd` in the root does the same with a double click, without a
console window; agents do not run it on the customer's PC, since it opens the window on the customer's screen):

```powershell
cd WinKickOff
python -m winkickoff
```

Find em and en dashes in the whole tree (PowerShell; an empty output means none):

```powershell
$d = "[$([char]0x2013)$([char]0x2014)]"; Get-ChildItem -Recurse -Include *.md,*.ps1,*.py,*.toml,*.json -File | Where-Object { $_.FullName -notmatch '\\(A-unattendedwinstall|\.git|__pycache__)\\' } | ForEach-Object { $n = ([regex]::Matches([IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8), $d)).Count; if ($n) { "$($_.FullName): $n" } }
```

Checks after an installation in a VM: the checklist in `docs/user/<lang>/install-and-check.md`.

## 6. Facts that are easy to lose

- The first installation of v0.1 (13.09.2026) failed in specialize with 0x80220005: two commands were
  longer than 259 characters. The limit is documented by Microsoft. Fixed in v0.2.
- Target ISO: Ukrainian Windows 11 Pro (setupact.log: Language uk-ua, Region UA), build 26200 (25H2).
- "Russian (Ukraine)" (`ru-UA`) has no LCID; the XML gets plain Russian `0419:00000419` and `Setup-User.ps1`
  replaces it at first sign-in (Windows assigns the transient id `2000:00000419`).
- Windows 11 24H2 leaves copies of the answer file in `C:\Windows\Panther`; `Post-OOBE.ps1` deletes them.
- `auditpol` on the Ukrainian image rejects English subcategory names; GUIDs are used.
- The scheduled task is created from XML so that it runs on battery; `Register-ScheduledTask` is unreliable in specialize.
- All three embedded scripts end with `exit 0`; command wrappers catch errors into `C:\Windows\Temp\ua.err`.
- Known inconsistencies of v0.2 are listed in `docs/technical/reference/17-cross-links.md`, section 3; in the
  editor catalog `MapsBroker` already belongs to the removal of Maps, not to Xbox.
- Of the 153 actions of the v0.2 script, 47 ran unconditionally; in the editor every action belongs to a
  rule (130 rules for v0.2: 47 baseline, 18 ASR, 33 apps and so on) and any rule can be disabled.
- Browser rules (issue #1) are generated: edit the table in `WinKickOff/tools/make_browser_rules.py` and rerun it,
  not `rules/14-browsers.toml`. Every policy name was checked against the vendors' definitions; several lines
  of the issue's scripts were invalid or obsolete (`docs/technical/reference/18-browsers.md`, corrections).
  `DEFAULT_ON` in the tool holds the browser rules that are on by default (commit d33fc41).
- Since 26.09.2026 the catalog defaults, and so the Office preset, differ from v0.2: browser policies,
  `apps.remove.onedrive` on; `update.other-microsoft-products`, `asr.usb-untrusted`, `uac.admin-always-notify`
  off (Task Manager opened by Admin must not ask for UAC). Tests that compare with v0.2 use `reference_profile()`
  of `WinKickOff/tests/v02_actions.py`; a new rule that is on by default goes into `V02_DIFFERENCES` as off.
  Presets are generated: change defaults in the rules or the preset functions of `WinKickOff/tools/make_presets.py`,
  never by hand in `profiles/preset-*.json` (a hand edit is overwritten by the next generation).
- Return to Windows defaults (context menu, `core/apply.py` `plan_revert`) uses the action field `default`; a
  value under `SOFTWARE\Policies` needs none. Write a default only when it is certain for the target Windows 11
  24H2/25H2, otherwise `"unknown"` (the SMB signing defaults changed in 24H2, for example).
- Customer lists of registry values (issue #1, MoreOptions of 28.09.2026) are checked value by value against
  Microsoft Learn, the ADMX of 26200 and read-only registry queries before they become rules. Documented values and
  undocumented values of a Settings switch become rules; values that do not exist, internal state that Windows
  rewrites, obsolete ones and wrong paths are replaced by the documented equivalent or left out, and each case is
  listed in the "Corrections" section of the card (18 for browsers, 19 for the rest).
- Most Edge AI policies do not apply to a profile signed in with a personal Microsoft account, so `edge.signin-off`
  is on by default. Office settings are per user: WinKickOff writes them into the default profile (DU), so only
  accounts created after installation get them.
- This PC folders (`thispc.*`): Windows 11 24H2+ hides all 11 `MyComputer\NameSpace` entries with
  `HiddenByDefault=1`; the rules show them (0) in the 64-bit and WOW6432Node views and are off by default. Each
  folder has a Local entry (shown by Windows 10) and a classic one; showing both may duplicate the folder.
- The memstechtips preset (issue #2) is computed, not hand-made: a rule is on when the original of Appendix A has at
  least one of its actions and none of them contradicts the original; `EQUIVALENT` in `WinKickOff/tools/memstechtips.py` lists
  values with the same effect on Pro (`AllowTelemetry` 0 acts as 1). A catalog change can change the preset and
  `docs/technical/memstechtips-profile.md`: rerun `python tools/make_presets.py` and read the report diff.
  The report shows that the original weakens protection (administrators elevate without a UAC prompt, no secure
  desktop, Win+L disabled).
- GitHub rejects a push with a personal e-mail in the commit author; this repository has the local address
  `265459095+stanislavperec-ua@users.noreply.github.com` (`git config user.email`, this folder only).
  Files are stored byte for byte (`.gitattributes`: `* -text`), CRLF.
- The work PC has Python 3.14.3 with tkinter 8.6 and tomllib; pytest is absent and is not installed.
  PyInstaller is not installed either: installing a package changes the PC, so the exe (T12) is built by
  GitHub Actions, in a VM or on a separate command of the customer.
- A WinKickOff build matches v0.2 in meaning, not byte for byte: `test_build.py` compares the actions of
  `Setup-System.ps1`, the pass commands, International-Core, OOBE, accounts and the time zone.
  `tools/Validate-Unattend.ps1` accepts both styles (the `$Config` block of v0.2 or `# [rule.id]` markers).
- Everything the generator writes (header, markers, embedded profile) is ASCII; the profile is embedded in
  `Extensions/Profile` as JSON with escaped national characters, so "Open profile from autounattend.xml"
  restores the settings from a built file. A file without a profile
  (v0.2) is imported by its actions: `core/actions_parser.py` reads `$Config` from the file itself and
  evaluates the conditions; importing v0.2 gives exactly the v0.2 reference profile (`test_importer.py`).
- tkinter's Treeview does not lay out rows in a hidden window; the window smoke test shows it fully
  transparent outside the screen. Tree check boxes are images (`identify_element` returns `image`), the "+"
  is `Treeitem.indicator`: a click on "+" only expands the branch. Text tag bindings in a Text widget follow
  the "current" mark, so a synthetic click needs a preceding `<Motion>` event.
- Interface translations (T18, 30.09.2026): the English source text is the key; wrap every user-facing string
  in `tr()` (or `N_()` at module level) and add its ru and uk translation to
  `WinKickOff/resources/strings.<code>.json`, otherwise `tests/test_i18n.py` fails. Rule texts, extra search tags
  and group titles are translated in `WinKickOff/rules/lang/<code>.toml`. A language exists when one of its files
  exists (the native name is the field `_language`); there is no `strings.en.json` or `lang/en.toml`, and every
  gap falls back to English. The setting `language` `""` follows the Windows interface language. The Russian
  UI of this PC used to hide missing translations: window tests set `i18n.set_language("en", ...)` and
  `Settings(language="en", theme="light")` explicitly and reset the language in `tearDown`.
- Code, comments, rule texts and tool tables are English (`test_sources.py` fails on Cyrillic);
  `WinKickOff/tools/make_rule_docs.py` keeps the words of the three user documentation languages as data.
  The technical documentation quotes editor elements by their English text in double quotes ("Office", "This PC",
  "Check rule catalog"), as in `tr()` and the rule titles; guillemets with Russian or Ukrainian text are kept only
  for Windows' own labels and other data (`test_docs.py` allows Cyrillic only there and in code).
- Colour themes (T18): `WinKickOff/resources/themes/<id>.json` with `base` (`native` or `clam`), `dark`, `font` and
  `colors` (keys of `LIGHT_COLORS` in `core/themes.py`); a new file adds a theme. The setting `theme` `""`
  follows the Windows light or dark mode: `core/themes.py` is the only module allowed to read the registry
  (`AppsUseLightTheme`, read only), no module may write it. A language or theme change rebuilds the window
  with the open profile. Windows paints the native menu bar in system colours only: coloured themes (`clam`) get
  a row of menu buttons, and `ui/winmenus.py` repaints the margin of drop-down menus through a WinEvent hook of
  this thread; the title bar, its text and the window border take the theme colours on Windows 11
  (DwmSetWindowAttribute 34-36, keys `title_bar`, `title_text`, `border`); everything is per window and per
  process, system-wide calls are forbidden by `test_sources.py`.
- T15 scripts: tests only generate and parse Apply, Undo and Audit scripts; `run_audit` is exercised with a harmless
  script and `launch_elevated` is always mocked. Never run an apply or an audit on the customer's PC from an agent.
- Catalog 0.3: the country moved into the parameters of rule `default-user.region` (string `"241"`), the field
  `iso_language` was removed; old profiles are migrated on load with a warning.
- Nothing in the repository depends on the name of the local folder of a clone.
- Imported policy templates (T19, 1.1.0): `core/admx.py` turns ADMX policies into rules `admx.<namespace>.<policy>`
  kept in `admx/<id>/` next to the program (runtime folder, not versioned). The prefix `admx.` is reserved; such a rule
  without a check mark is "not configured": not written to the profile, not validated, not reverted by an apply,
  and its group check box only switches off. Template files are untrusted input (no DTD, size limits, unsafe
  characters refused, `ps_quote` doubles typographic single quotes). Tests read the templates of this Windows
  (`C:\Windows\PolicyDefinitions`) read-only; nothing is written outside temporary folders.
- Several imports (T20): a policy is one rule, owned by the first loaded import; later trees show it as an alias
  (`Catalog.aliases`, `placements()`), with the tree item id `r:<rule>@<group>`. Code that takes a rule from a tree
  item uses `rule_of()` of `ui/main_window.py`, never `item[2:]`, and This PC gets canonical `r:<rule>` items.
  `import.json` `renamed: true` keeps a name given by the user when the import is updated in place.
- Built-in rules and imported policies (T21, `core/linked.py`): a policy whose registry writes an enabled built-in
  rule already covers is shown checked (tag `linked`) but stays off in the profile; the window uses `_rule_on()`
  for images and group counts, never `profile.is_enabled()` alone. An equal policy switches the built-in rule.
- Lists of values (1.1.0-rc.2, catalog 0.5): a `list` element becomes a parameter of type `list` and a `reg-list`
  action, a `multiText` element a `list` parameter in a `reg` action of kind MultiString. `Set-RegList` gets names and
  values as two arrays that pair up by position (the generator computes the names: items, prefix and number, or
  `name=value`), uses the .NET registry API because value names such as `https://*.example.com` must be literal, and
  without `-Additive` deletes the other values of the key first; so the list actions of a rule come before its other
  values, and the Disabled rule of a policy clears the keys of its lists. The apply script saves every value of the
  key before the change; `Undo.runtime.ps1` needed no new code. Imports of format 1 (rc.1) still load, without lists.

## 7. Work status

| Area | State | Date | Where |
|---|---|---|---|
| Answer file v0.2 | Reference, frozen; checked by the validator and the critic | 13.09.2026 | `docs/appendices/B-autounattend-v0.2/` |
| Review of the original | Done | 12.09.2026 | `docs/appendices/C-critical-review/01-critical-review.md` |
| Critic's report and fixes | Done (9 accepted, 3 rejected) | 13.09.2026 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` |
| Parameter reference | Done, 19 files, English | 25.09.2026 | `docs/technical/reference/` |
| Answer file checker | Done, 36 checks, 0 errors on v0.2 | 25.09.2026 | `tools/Validate-Unattend.ps1` |
| GitHub repository | Renamed to WinKickOff; the local clone and `origin/main` match; CI in GitHub Actions | 26.09.2026 | https://github.com/supakov/WinKickOff |
| Editor specification | Revision 0.2, English | 25.09.2026 | `docs/technical/editor/` |
| Editor tasks | T01-T12, T14, T16-T21 done (the build runs in GitHub Actions); T13 blocked on the acceptance checklist; T15 implemented with return to defaults, acceptance in a VM pending | 30.09.2026 | `docs/technical/editor/todo/` |
| Rule catalog | 0.5: 251 rules, 36 groups (130 carry v0.2; browsers 64; list MoreOptions: AI, telemetry, advertising, search, speech, Office, OneDrive, drivers; File Explorer 15), Windows defaults for return, integrity and v0.2 coverage confirmed by tests; 0.5 adds the parameter type `list` and the action `reg-list` (runtime Set-RegList, Test-RegList), the rules themselves are those of 0.4 | 30.09.2026 | `WinKickOff/rules/` |
| Editor code | 1.1.0-rc.4 (import of ADMX templates with lists of values, T19; Back and Forward, shared imports, T20; links to built-in rules, T21): generator, profile, XML and catalog checks, import of built files and of v0.2, PowerShell check, four presets, window with check boxes, parameters, forms, profiles, comparison, recent files and build; English source with Russian and Ukrainian translation files, languages and colour themes (Light, Dark, Latte, Matrix, as in Windows) found from files; 236 tests | 30.09.2026 | `WinKickOff/` |
| Installation from a WinKickOff build | Confirmed by the customer on real hardware (accounts, languages, minimal questions) | 26.09.2026 | release 1.0.0-rc.1 |
| Applying rules to a running Windows | T15: read-only audit, apply (rules on are applied, rules off return to Windows defaults) and return to Windows defaults with backup and undo, through UAC after a one-time permission; acceptance in a VM pending | 29.09.2026 | `WinKickOff/winkickoff/core/apply.py`, `docs/user/*/this-pc.md` |
| Repository layout | T17 done; 26.09.2026 the repository was renamed to WinKickOff, the old umbrella name is gone | 26.09.2026 | `README.md`, `docs/appendices/` |
| Documentation split | T16 done: technical in English, user documentation in ru, uk, en; since T18 the catalog is English with complete ru and uk translations | 30.09.2026 | `docs/technical/`, `docs/user/`, `WinKickOff/rules/lang/` |
| GitHub issues | #1 "Web Browsers debloat" done: section "Browsers" (Edge, Chrome, Brave), 46 rules off by default, card 18. #2 "memstechtips profile" done: preset of 60 rules computed from Appendix A, report of what is added, contradicted and not transferable. The customer closes issues | 25.09.2026 | `WinKickOff/rules/14-browsers.toml`, `docs/technical/reference/18-browsers.md`, `WinKickOff/profiles/preset-memstechtips.json`, `docs/technical/memstechtips-profile.md` |
| Release candidate | 1.1.0-rc.4 (imported policies follow the built-in rules), after 1.1.0-rc.3 (Back and Forward, shared imports), 1.1.0-rc.2 (lists of values), 1.1.0-rc.1 (import of ADMX templates) and 1.0.0-rc.1 to rc.4 of 26.09-30.09.2026: tag and GitHub release built by CI | 30.09.2026 | `docs/releases/v1.1.0-rc.4.md` |
| Imported ADMX templates | T19 done: ADMX menu, store `admx/` next to the program, policies as rules with parameters, links to built-in rules; since 1.1.0-rc.2 list and multi-line elements too (20 of 3552 policies of this Windows skipped); acceptance of lists on This PC in a VM pending; T20 (1.1.0-rc.3): an import of an imported folder asks to update it or add a tree, a policy in several trees has one check mark, trees can be renamed; Back and Forward in the window; T21 (1.1.0-rc.4): an imported policy follows the built-in rule that sets the same values | 30.09.2026 | `WinKickOff/winkickoff/core/admx.py`, `docs/user/*/admx.md` |
| Customer list MoreOptions | Done: BitLocker off in every preset; 57 rules on by default (AI, telemetry, advertising, search, speech, Office, OneDrive, drivers, Edge AI and sign-in, Gallery hidden), This PC folders as options off by default; corrections in card 19 | 28.09.2026 | `docs/technical/reference/19-more-privacy.md` |
| Tuning of preset defaults | Awaited from the customer | | `WinKickOff/tools/make_presets.py`, rule defaults |

Open questions to the customer: `docs/appendices/D-requirements-draft/02-constructor-requirements-draft.md`,
section 6; whether Appendix D should get a sample WinKickOff build.

## 8. How to update this file

- The folder structure changed: section 3.
- A run or check command appeared: section 5.
- A task was finished or started: section 7 and `docs/technical/editor/todo/README.md`.
- A fact that affects future changes was found: section 6.
- The date in the header on every change.
