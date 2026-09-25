# AGENTS.md: map of the "Windows installer" project

For agents and developers: where things are, what to read first, which rules apply, the state of the
work. Updated with every change of structure, commands or task status.
Last update: 25.09.2026 (T16: technical documentation in English, user documentation in three languages).

Repository: https://github.com/supakov/WindowsInstaller (private, branch `main`). The local folder
`C:\Users\User\projects\Windows installer` and the repository must match: commit and push after every
finished task. Commit messages are in Russian (the customer reads the history), first line up to 72
characters, no em or en dashes, and a commit made by an agent ends with the line
`Co-Authored-By: <agent model> <noreply@anthropic.com>` (the model name of the current agent session,
for example `Claude Opus 5.5`).

## 1. The project in three sentences

A toolkit for automated installation and configuration of Windows 11 Pro in small workgroups without a
domain, where the PCs are used by non-professionals and the organisation is under constant cyber attack.
Priorities: security and updatability, no cosmetics and no third-party programs. The first tool, WinKickOff
(Python 3.14, tkinter, portable), shows every installation rule in a searchable tree, disables dependent
rules automatically and assembles `autounattend.xml` from the selection only; the hand-written answer
file v0.2 its catalog grew from is kept in the documentation appendices as the reference.

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
| See what the critic checked in v0.2 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` (Word, at the customer's request) |

## 3. Folder structure

```
Windows installer/
├── AGENTS.md                      this file
├── README.md                      THE TOOLKIT: purpose, tools (WinKickOff first), quick start, links to user docs
├── .gitignore, .gitattributes     what is not versioned; files are stored byte for byte (CRLF)
├── tools/
│   └── Validate-Unattend.ps1      answer file checker (36 checks), read-only; without -Path it checks Appendix B
├── docs/
│   ├── README.md                  entry point to the documentation (three languages)
│   ├── technical/                 TECHNICAL DOCUMENTATION, English
│   │   ├── reference/             reference: a card for every installation parameter (18 files)
│   │   └── editor/                WinKickOff specification: problem, architecture, data model, testing,
│   │       │                      plan (days, milestones), review of revision 0.1
│   │       └── todo/              tasks T01-T17 with status (README.md is the index)
│   ├── user/                      USER DOCUMENTATION: ru (source), uk, en; the same files in each language
│   └── appendices/                APPENDICES, frozen, Russian: README describes them
│       ├── A-unattendedwinstall/  original UnattendedWinstall answer file (MIT, SOURCE.md, LICENSE)
│       ├── B-autounattend-v0.2/   our hand-written answer file v0.2 (the reference) and its README: history, VM checklist
│       ├── C-critical-review/     review of the original and the critic's report on v0.2 (docx)
│       └── D-requirements-draft/  first requirements draft; section 6 holds open questions to the customer
└── WinKickOff/                    EDITOR 0.2.0 AND RULE CATALOG 0.3
    ├── README.md                  developer README: run, test, structure; links to user docs
    ├── pyproject.toml             requires-python >= 3.14, no runtime dependencies
    ├── winkickoff/                package: app.py (start), core/ (paths, log, catalog, deps, profile, resources,
    │                              render, validate, verify, actions_parser, importer, pscheck, settings, i18n, apply),
    │                              ui/ (main_window: tree, search, description, parameters, profiles, build;
    │                              data_forms: install, accounts, languages; checkimages: check box images)
    ├── rules/                     RULE CATALOG: groups.toml (24 groups), 00-13-*.toml (130 rules), lang/*.toml
    ├── templates/                 runtime with slots: autounattend.template.xml, Setup-System, Setup-User, Post-OOBE,
    │                              Audit, Apply, Undo *.runtime.ps1, section-*.ps1; README lists the slots; VERSION = 0.3
    ├── resources/                 keyboards.json, timezones.json, strings.uk.json, strings.en.json (interface translations)
    ├── profiles/                  presets «Офис» (equals v0.2), «Строгий» (Strict), «Ноутбук» (Laptop), README
    ├── tests/                     unittest: catalog, resolver, profile, render, build against v0.2, validation,
    │                              import, presets, PowerShell, settings, portability, window smoke test, docs
    └── tools/                     make_presets.py, make_rule_docs.py, run-tests.ps1
```

Working folders `WinKickOff/output/`, `WinKickOff/logs/`, `WinKickOff/settings.json`, `__pycache__/` and
user profiles (all but `preset-*.json`) are not versioned.

## 4. Project rules (mandatory for every agent)

1. The customer's work PC is untouchable. Only reading is allowed there (registry, services, files,
   logs) and running tests that write only into temporary folders or inside the project folder.
   No "temporary" or "reversible" changes to the system: on 12.09.2026 such a test broke the keyboard
   layout switching. Anything that changes the system is done in a virtual machine or written down as
   instructions. The only exception is a separate, explicit command of the customer for a specific action.
2. The em dash (U+2014) and the en dash (U+2013) are forbidden in every text we create, in any language:
   documents, code, data, comments, interface strings, commit messages. Number ranges use a hyphen
   (08:00-20:00, T01-T06). Checks: `WinKickOff/tests/test_sources.py` and `test_docs.py`, and the command in section 5.
3. Reports requested by the customer are written as Russian Markdown files in `docs/`; Word only when
   explicitly asked ("в Ворд").
4. Languages: communication with the customer and customer reports in Russian. Technical documentation
   (`docs/technical/`, this file, READMEs of code folders, code comments) in English. User documentation in
   `docs/user/` in Russian (the source), Ukrainian and English with the same files and structure. The editor's
   interface and rule texts are Russian with translations in `WinKickOff/rules/lang/` (task T14).
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

Run the editor from sources:

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
  rule (130 rules: 47 baseline, 18 ASR, 33 apps and so on) and any rule can be disabled.
- GitHub rejects a push with a personal e-mail in the commit author; this repository has the local address
  `265459095+stanislavperec-ua@users.noreply.github.com` (`git config user.email`, this folder only).
  Files are stored byte for byte (`.gitattributes`: `* -text`), CRLF.
- The work PC has Python 3.14.3 with tkinter 8.6 and tomllib; pytest is absent and is not installed.
  PyInstaller is not installed either: installing a package changes the PC, so building the exe (T12)
  happens only in a VM or on a separate command of the customer.
- A WinKickOff build matches v0.2 in meaning, not byte for byte: `test_build.py` compares the actions of
  `Setup-System.ps1`, the pass commands, International-Core, OOBE, accounts and the time zone.
  `tools/Validate-Unattend.ps1` accepts both styles (the `$Config` block of v0.2 or `# [rule.id]` markers).
- Everything the generator writes (header, markers, embedded profile) is ASCII; the profile is embedded in
  `Extensions/Profile` as JSON with escaped national characters, so «Открыть профиль из autounattend.xml»
  (Open profile from autounattend.xml) restores the settings from a built file. A file without a profile
  (v0.2) is imported by its actions: `core/actions_parser.py` reads `$Config` from the file itself and
  evaluates the conditions; importing v0.2 gives exactly the «Офис» (Office) preset (`test_importer.py`).
- tkinter's Treeview does not lay out rows in a hidden window; the window smoke test shows it fully
  transparent outside the screen. Tree check boxes are images (`identify_element` returns `image`), the "+"
  is `Treeitem.indicator`: a click on "+" only expands the branch. Text tag bindings in a Text widget follow
  the "current" mark, so a synthetic click needs a preceding `<Motion>` event.
- Interface translations: the Russian source text is the key; wrap every user-facing string in `tr()` (or
  `N_()` at module level) and add its uk and en translation to `WinKickOff/resources/strings.<lang>.json`,
  otherwise `tests/test_i18n.py` fails. Rule texts are translated in `WinKickOff/rules/lang/<lang>.toml`.
- T15 scripts: tests only generate and parse Apply, Undo and Audit scripts; `run_audit` is exercised with a harmless
  script and `launch_elevated` is always mocked. Never run an apply or an audit on the customer's PC from an agent.
- Catalog 0.3: the country moved into the parameters of rule `default-user.region` (string `"241"`), the field
  `iso_language` was removed; old profiles are migrated on load with a warning.

## 7. Work status

| Area | State | Date | Where |
|---|---|---|---|
| Answer file v0.2 | Reference, frozen; checked by the validator and the critic; acceptance install in a VM by the customer not yet confirmed | 13.09.2026 | `docs/appendices/B-autounattend-v0.2/` |
| Review of the original | Done | 12.09.2026 | `docs/appendices/C-critical-review/01-critical-review.md` |
| Critic's report and fixes | Done (9 accepted, 3 rejected) | 13.09.2026 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` |
| Parameter reference | Done, 18 files, English | 25.09.2026 | `docs/technical/reference/` |
| Answer file checker | Done, 36 checks, 0 errors on v0.2 | 25.09.2026 | `tools/Validate-Unattend.ps1` |
| GitHub repository | Connected, the local folder and `origin/main` match | 25.09.2026 | https://github.com/supakov/WindowsInstaller |
| Editor specification | Revision 0.2, English | 25.09.2026 | `docs/technical/editor/` |
| Editor tasks | T01-T11, T14, T16, T17 done (milestones M1-M4); T12 in progress (build script, the build only in a VM); T13 and T15 blocked (implemented, acceptance needs a VM) | 25.09.2026 | `docs/technical/editor/todo/` |
| Rule catalog | 0.3: 130 rules, 24 groups, integrity and v0.2 coverage confirmed by tests | 25.09.2026 | `WinKickOff/rules/` |
| Editor code | 0.2.0: generator, profile, XML and catalog checks, import of built files and of v0.2, PowerShell check, three presets, window in Russian, Ukrainian and English with check boxes, parameters, forms, profiles, comparison, recent files and build; 162 tests | 25.09.2026 | `WinKickOff/` |
| «Офис» build from the editor | Covers every v0.2 action, validator 36 of 36; installation in a VM not yet tested | 25.09.2026 | `WinKickOff/output/` (not versioned) |
| Applying rules to a running Windows | T15 implemented: read-only audit, apply scripts with backup, undo, apply through UAC (off by default); acceptance in a VM pending | 25.09.2026 | `WinKickOff/winkickoff/core/apply.py`, `docs/user/*/this-pc.md` |
| Repository layout | T17 done: the root describes the toolkit; XML files and reviews in `docs/appendices/` | 25.09.2026 | `README.md`, `docs/appendices/` |
| Documentation split | T16 done: technical in English, user documentation in ru, uk, en; complete catalog translations uk and en | 25.09.2026 | `docs/technical/`, `docs/user/`, `WinKickOff/rules/lang/` |
| Customer items for v0.3 | Awaited | | |

Open questions to the customer: `docs/appendices/D-requirements-draft/02-constructor-requirements-draft.md`,
section 6; the toolkit name in the root README is a working name (the repository name) awaiting a decision;
whether Appendix D should get a sample WinKickOff build.

## 8. How to update this file

- The folder structure changed: section 3.
- A run or check command appeared: section 5.
- A task was finished or started: section 7 and `docs/technical/editor/todo/README.md`.
- A fact that affects future changes was found: section 6.
- The date in the header on every change.
