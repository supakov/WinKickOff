# AGENTS.md: map of the WinKickOff repository

For agents and developers: where things are, what to read first, which rules apply, the state of the
work. Updated with every change of structure, commands or task status.
Last update: 08.10.2026 (version 1.3.0-rc.2, task T24: the computer name of the form "Installation" (a name or a template) and the account texts outside ASCII set after OOBE, catalog and runtime 0.7, profile format 4; before it 1.3.0-rc.1, published on 08.10.2026: the customer's commits of 05.10.2026, 14 editions of the generic key and `HiddenByDefault` 1 as the Windows default of every `thispc.*` rule, and the fixes of the last review of T23: a profile saved through a temporary file, held choices at every start, a policy named Off; before it task T23: the rule catalog in JSON instead of TOML, export and import of catalog files, catalogs of the program, and the fixes of its adversarial reviews: profiles read strictly, the provenance of imported choices, safe keys and characters, the ids of policies that share one; before it the customer requests of 04.10.2026: File Explorer namespaces and desktop icons, the account asked during installation, the switch keys of the input language, the edition chosen during installation, a security fix of placeholders in paths, catalog and runtime 0.6, profile format 3).

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
`tools/Validate-Unattend.ps1`, the check, apply and return-to-defaults scripts for a running Windows, and since 1.2 an
MCP server (stdio and HTTP on 127.0.0.1, read-only by default) through which AI clients read the catalog and the profile.
The hand-written answer file v0.2 the catalog grew from is kept in the documentation appendices as the reference.
`pi-agent/` holds a Podman image of the pi agent with a local model that analyses and changes WinKickOff profiles
only through the MCP server, without a cloud model and without any file of the project.

## 2. What to read first

| Task of the agent | Start with |
|---|---|
| Understand the toolkit and its tools | `README.md` in the root, then `docs/README.md` |
| Understand what the answer file does | `docs/appendices/B-autounattend-v0.2/README.md` (Russian), then `docs/technical/reference/00-architecture.md` |
| Find a parameter and its registry keys | `docs/technical/reference/README.md` (index by parameter) |
| Change installation behaviour | a rule in `WinKickOff/rules/` (v0.2 in Appendix B is frozen); Setup limits in `docs/technical/reference/00-architecture.md` section 3 |
| Work on the editor | `docs/technical/editor/README.md`, then `docs/technical/editor/todo/README.md`, then `WinKickOff/README.md` |
| Understand why the editor is built on rules, not on `$Config` | `docs/technical/editor/06-critical-review-v0.1.md` |
| Add or change an installation rule | `docs/technical/editor/03-data-model.md`, a file `WinKickOff/rules/NN-*.json`, then `python tools/format_catalog.py` and `python -m unittest` in `WinKickOff/` |
| Work on catalog files, their export and import, or the catalogs of the program | `docs/technical/editor/03-data-model.md` sections 8 and 10, `WinKickOff/winkickoff/core/package.py`, `admx.check_templates` in `WinKickOff/winkickoff/core/admx.py`, `WinKickOff/winkickoff/core/jsonfile.py`, `WinKickOff/catalogs/README.md` |
| Write or update user documentation | `docs/user/README.md`, the Russian source in `docs/user/ru/`, then the same change in `uk` and `en` |
| Build or release | `.github/workflows/build.yml`, `WinKickOff/tools/build.ps1`, section 5 of this file |
| Change the skill for AI agents that use WinKickOff over MCP | `WinKickOff/skills/README.md`, then `WinKickOff/skills/winkickoff/SKILL.md` and its `references/`; `WinKickOff/tests/test_skill.py` ties it to the server |
| Change the pi agent container | `pi-agent/README.md`, then `pi-agent/AGENTS.md` (the instructions the agent works by; no word about the project may enter `pi-agent/`, `tests/test_pi_agent.py` checks it), `.github/scripts/check_pi_agent.py` |
| See what the critic checked in v0.2 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` (Word, at the customer's request) |

## 3. Folder structure

```
(repository root)
├── AGENTS.md                      this file
├── README.md                      the toolkit: purpose, tools, quick start, user docs, builds
├── Start-WinKickOff.cmd           starts the editor from the sources (py launcher, Python 3.14+, no console)
├── .gitignore, .gitattributes     what is not versioned; files are stored byte for byte (CRLF)
├── .github/workflows/build.yml    CI: tests, checker, portable build on every push; a tag v<version> publishes a release;
│                                  a Linux job builds pi-agent/ and checks it (.github/scripts/check_pi_agent.py)
├── pi-agent/                      Podman image of the WinKickOff assistant (pi with its defaults and a local model;
│                                  WinKickOff only over MCP, from codemode scripts):
│                                  Dockerfile, AGENTS.md (its instructions, copied into the image), README.md (setup);
│                                  nothing about the project itself
├── tools/
│   └── Validate-Unattend.ps1      answer file checker (37 checks), read-only; without -Path it checks Appendix B
├── docs/
│   ├── README.md                  entry point to the documentation (three languages)
│   ├── technical/                 TECHNICAL DOCUMENTATION, English
│   │   ├── reference/             reference: a card for every installation parameter (21 files; 18 browsers, 19 more privacy, 20 File Explorer namespaces)
│   │   └── editor/                WinKickOff specification: problem, architecture, data model, testing,
│   │       │                      plan (days, milestones), review of revision 0.1
│   │       └── todo/              tasks T01-T24 with status (README.md is the index)
│   ├── user/                      USER DOCUMENTATION: ru (source), uk, en; the same files in each language
│   ├── releases/                  release notes v<version>.md (ru, uk, en), used by the release job
│   ├── reports/                   reports to the customer, Russian (README.md lists them)
│   └── appendices/                APPENDICES, frozen, Russian: README describes them
│       ├── B-autounattend-v0.2/   our hand-written answer file v0.2 (the reference) and its README: history, VM checklist
│       ├── C-critical-review/     the critic's report on v0.2 (docx)
│       └── D-requirements-draft/  first requirements draft; section 6 holds open questions to the customer
└── WinKickOff/                    EDITOR 1.3.0-rc.2 AND RULE CATALOG 0.7
    ├── README.md                  developer README: run, test, structure; links to user docs
    ├── pyproject.toml             requires-python >= 3.14, no runtime dependencies
    ├── winkickoff/                package: __main__.py (dispatcher: window or headless MCP), app.py (window start,
    │                              owns the MCP service), mcp_main.py (console entry of WinKickOff-mcp.exe),
    │                              core/ (paths, log, catalog, deps, profile, resources, render, validate, verify,
    │                              actions_parser, importer, pscheck, settings, i18n, themes, apply, admx, linked, startup,
    │                              computername: names and templates of the computer name,
    │                              jsonfile: strict JSON, gzip and xz, canonical layout; package: catalog files),
    │                              mcp/ (MCP server: jsonrpc, schema, redact, journal, workspace, bridge, tools, resources,
    │                              protocol, stdio, httpserver, service, cli; errors),
    │                              ui/ (main_window: tree, search, description, parameters, profiles, build, MCP menu;
    │                              data_forms: install, accounts, languages; checkimages: check box images;
    │                              winmenus: theme colours around drop-down menus; mcp_workspace: the window as the MCP
    │                              workspace; mcp_window: the MCP monitor; clipboard: the token kept out of the
    │                              clipboard history)
    ├── rules/                     RULE CATALOG in English, strict JSON: groups.json (40 groups), 00-17-*.json (278 rules),
    │                              lang/ru.json and lang/uk.json (translations; a new file adds a language)
    ├── catalogs/                  catalogs of the program (catalog files of imported ADMX templates, <name>.json;
    │                              README.md); none committed until the license check; the build ships them as xz
    ├── templates/                 runtime with slots: autounattend.template.xml, Setup-System, Setup-User, Post-OOBE,
    │                              Audit, Apply, Undo *.runtime.ps1, section-*.ps1; README lists the slots; VERSION = 0.7
    ├── resources/                 keyboards.json, timezones.json, strings.ru.json and strings.uk.json (interface
    │                              translations), themes/ (light, dark, latte, matrix colour themes)
    ├── profiles/                  presets Office (= catalog defaults), Strict, Laptop, Home, README
    ├── skills/                    winkickoff/: the Agent Skill for AI agents that use WinKickOff over MCP (SKILL.md,
    │                              references/tools.md, workflows.md, concepts.md); README.md: how to install it;
    │                              shipped next to the exe in the portable build
    ├── tests/                     unittest: catalog, resolver, profile, render, build against v0.2, validation,
    │                              import, presets, PowerShell, settings, portability, window smoke test, docs,
    │                              translations, themes, ADMX import, catalog files and packages (test_catalog_format.py,
    │                              test_package.py), MCP server (test_mcp_*.py);
    │                              v02_actions.py holds the v0.2 reference profile (V02_DIFFERENCES); quiet_tk.py keeps
    │                              every window of the tests invisible (imported first by each window test module)
    └── tools/                     make_presets.py, make_rule_docs.py, run-tests.ps1, build.ps1 (portable zip,
                                   two executables from WinKickOff.spec),
                                   make_browser_rules.py (generates rules/14-browsers.json),
                                   make_shell_rules.py (generates rules/17-shell.json),
                                   format_catalog.py (canonical layout of the catalog JSON),
                                   make_admx_catalogs.py (a catalog of the program from a folder of ADMX templates),
                                   pack_catalogs.py (xz of catalogs/ for the build)
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
   The same holds for the image of `pi-agent/`: building and running it pulls images and packages, so a person does
   it on their own machine; an agent never runs podman, docker or WSL commands on the customer's PC.
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
   `WinKickOff/rules/lang/<code>.json`, task T18); other translations only on the customer's demand.
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
8. Editor: only the Python standard library in the application; tests on `unittest`; rules, translations, profiles
   and catalog files in JSON (since 1.3.0, task T23; TOML is gone); rules contain no program logic. The catalog files
   are strict JSON in the canonical layout: after a hand edit run `python tools/format_catalog.py` in `WinKickOff/`
   (`test_catalog_format.py` fails otherwise). A change of the runtime templates needs a new `templates/VERSION`.
   Policy templates, catalog files (packages) and the saved imports in `admx/<id>/` are untrusted input: their keys,
   value names and values reach PowerShell scripts and an answer file that runs as SYSTEM. Read them only through
   `core/jsonfile.py` (size, memory and nesting limits) and `admx.check_templates` (the safe characters, kinds and
   ranges of the template parser), never let a text leave a single-quoted PowerShell string or a CDATA section, and
   turn every defect into a short message (a broken import is left out, the program still starts), never a crash or a
   hang of the window.
9. The agent's file writing tools turn escape sequences of the form backslash, `u`, four hex digits into real
   characters. Characters that must not appear in a file (such as dashes in regular expressions) are built in
   code with `chr(0x2013)` or `[char]0x2013`, never with an escape. Shell here-documents may also swallow
   doubled backslashes: edit files with backslashes through the editor tool or a script file. Registry paths in the
   catalog JSON have doubled backslashes (`"HKLM:\\SOFTWARE\\..."`), so the same care applies to them. `sed -i` of
   Git Bash writes LF: convert the file back to CRLF or edit it another way.
10. Text files are UTF-8 without a byte order mark and use CRLF line endings; `.gitattributes` (`* -text`) stores
    them as they are, so a file written on Linux with LF reaches the repository like that. `test_docs.py` checks the
    line endings of every tracked or new text file outside `docs/appendices/` (the frozen originals keep their bytes).
    `*.ps1`, `*.cmd`, `WinKickOff/templates/*` and `WinKickOff/rules/*.json` (not `rules/lang/`) are pure ASCII,
    because Windows PowerShell 5.1 reads a file without a byte order mark in the ANSI code page and the catalog source
    is English; Russian and Ukrainian texts live in the translation files and in `docs/user/`. `WinKickOff/catalogs/`
    keeps the texts of the templates as the vendor wrote them, so it is outside the dash check (customer decision of
    04.10.2026).
11. The skill `WinKickOff/skills/winkickoff` tells AI agents that use WinKickOff how the MCP tools, error kinds,
    modes, presets and rules behave. A change of any of them updates the skill in the same commit;
    `WinKickOff/tests/test_skill.py` fails on a tool, error kind, rule, group or resource the skill names wrongly or
    misses, but not on a changed behaviour, so read the skill when the behaviour changes.
12. Tests and checks on the customer's PC run in the background and stay invisible on the customer's screen: no
    window, console, dialog or taskbar button may appear (customer rule of 04.10.2026, after the window tests flashed
    the editor for a moment). Every test module that opens a window imports `WinKickOff/tests/quiet_tk.py` before its
    first `tk.Tk()` (every Tk root and Toplevel is transparent and a tool window from its creation, so the tests that
    need a mapped window still work); subprocesses get `CREATE_NO_WINDOW`; message boxes and file dialogs are mocked;
    a throwaway script that needs Tk (only in a temporary folder outside the repository) imports
    `WinKickOff/tests/quiet_tk.py` first or sets `-alpha 0` and `-toolwindow` right after `tk.Tk()`, before any update;
    `docs/technical/editor/04-testing.md` describes the module. When a check cannot
    run invisibly, say so and propose a VM or CI; a visible run only on the customer's direct instruction.

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
(`test_presets.py` and `test_docs.py` fail if you forget); after a hand edit of a catalog file bring it into the
canonical layout (`test_catalog_format.py` fails otherwise; `--check` only lists the files and exits with 1 when
there are any; a file that cannot be read is named, left as it is, and the exit code is 2):

```powershell
cd WinKickOff
python tools/format_catalog.py
python tools/make_presets.py
python tools/make_rule_docs.py
```

A catalog of the program from a folder of ADMX templates (only reading of the templates; the target is a plain
`.json`, which the tool reads back as the program will; commit a package only after the license check,
`WinKickOff/catalogs/README.md`). The build packs `catalogs/*.json` with `WinKickOff/tools/pack_catalogs.py`,
which `WinKickOff/tools/build.ps1` calls with the folder `dist\WinKickOff\_internal\catalogs`:

```powershell
cd WinKickOff
python tools/make_admx_catalogs.py <folder with the ADMX and ADML files of the target build> "catalogs\<name>.json" --name "<tree name>" --windows <version of those templates>
```

The templates must be those of the Windows build that the name and `--windows` give (this PC has build 26300, the
target ISO is 26200); the tool checks `--windows` and the whole package before it writes anything.

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

MCP server without a window (task T22; the stdio server needs `python.exe`, never `pythonw.exe`; agents never start a
server on the customer's PC outside `unittest`, the tests bind only 127.0.0.1 port 0):

```powershell
cd WinKickOff
python -m winkickoff --mcp stdio --mode read --profile office
python -m winkickoff --mcp http --port 0 --token <32 to 64 characters>
python -m winkickoff --mcp-config stdio
python -m winkickoff --version
```

Find em and en dashes in the whole tree (PowerShell; an empty output means none):

```powershell
$d = "[$([char]0x2013)$([char]0x2014)]"; Get-ChildItem -Recurse -Include *.md,*.ps1,*.py,*.toml,*.json -File | Where-Object { $_.FullName -notmatch '\\(\.git|__pycache__|catalogs)\\' } | ForEach-Object { $n = ([regex]::Matches([IO.File]::ReadAllText($_.FullName, [Text.Encoding]::UTF8), $d)).Count; if ($n) { "$($_.FullName): $n" } }
```

Checks after an installation in a VM: the checklist in `docs/user/<lang>/install-and-check.md`.

The pi agent container (`pi-agent/README.md`; a person runs these on their own machine, an agent never runs them on
the customer's PC; nothing of the repository is mounted):

```bash
podman build -t winkickoff-pi:local ./pi-agent/
podman run -it --rm --name winkickoff-pi -v pi-winkickoff:/home/pi/.pi --network=host winkickoff-pi:local
```

The same checks as CI, on a Linux machine with Podman and Python 3.14, from the repository root:
`python .github/scripts/check_pi_agent.py winkickoff-pi:local`.

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
  not `rules/14-browsers.json`. Every policy name was checked against the vendors' definitions; several lines
  of the issue's scripts were invalid or obsolete (`docs/technical/reference/18-browsers.md`, corrections).
  `DEFAULT_ON` in the tool holds the browser rules that are on by default (commit d33fc41).
- File Explorer namespaces and desktop icons (customer request 1 of 04.10.2026, catalog 0.6) are generated: edit the
  tables in `WinKickOff/tools/make_shell_rules.py` and rerun it, not `rules/17-shell.json`. Every entry is off by
  default; card 20 lists what was checked (registry of 26300, ADMX, Microsoft Learn) and what only third parties report.
  Groups: `system.explorer` ("File Explorer and the desktop") with `.thispc`, `.nav`, `.desktop` and
  `.desktop.folders`; the `thispc.*` and `nav.*` rules of `16-explorer.json` moved into them, their ids are unchanged.
  Navigation pane pins (`System.IsPinnedToNameSpaceTree`) go to `HKCU\Software\Classes` at the first sign-in: the
  machine registration belongs to TrustedInstaller and `UsrClass.dat` is not the default profile. Desktop icons are
  `DU:` values of `HideDesktopIcons`. `desktop.gallery` and `desktop.home` conflict with `nav.gallery-hidden` and
  `nav.home-hidden` both ways. Pending in a VM: whether `HiddenByDefault` under `Desktop\NameSpace` (which
  `nav.gallery-hidden`, on by default, relies on) works at all; Windows uses it only under `MyComputer\NameSpace`.
- The catalog in JSON (T23, 1.3.0-rc.1, 04.10.2026): `core/catalog.py` and `core/i18n.py` read `rules/*.json` and
  `rules/lang/*.json` through `core/jsonfile.py` (a duplicate key, null, NaN, nesting deeper than 32 levels or a byte
  order mark is an error; unknown keys of a file, rule, group, parameter, option or action are a CatalogError, so a
  misspelt field is no longer ignored; a parameter takes only the keys of its type, `PARAM_TYPE_KEYS`; a field of a
  type no check foresaw is a CatalogError naming the file and the rule, never a crash). A translation file of a wrong
  shape (`i18n.language_file_problem`) is not used: the window and the MCP server (`ToolRegistry.texts`) log it and
  show English. Former TOML comments became `"comment"` of a file and `"note"` of a rule; a
  script of several lines is a list of lines without a trailing line break. The move was proved by a snapshot: the
  four presets and a profile with every rule on gave byte-identical builds, the catalog objects and translations were
  equal (nine scripts lost a trailing line break the build drops anyway). The catalog version stayed 0.6. Test
  fixtures are Python dicts written as JSON, not TOML strings.
- Catalog files (T23, `core/package.py`): an envelope `{"format": "winkickoff-catalog", "version": 1, "kind": "admx",
  "name", "windows", "created", "comment", "templates"}` around the records of `admx/<id>/policies.json`; plain, gzip
  or xz (first bytes), 64 MB stored and unpacked, at most 1 000 000 values counted before parsing, 128 MB for the xz
  decoder; null is allowed only there, in a saved `policies.json` and in profiles, which older versions may have
  written with it (`jsonfile.read(nulls=True)`); lone surrogates and non-finite numbers are refused everywhere. Saved
  imports are read the same way (`import.json` at most 64 KB with every field of its type, `admx._info`, and its id
  must be the folder name: `load_import` refuses another, since the kind of an import, so its trust, and its group ids
  come from the folder): a damaged `import.json` or `policies.json` is reported by `with_imports` (which never raises)
  and left out, the program starts without it. `store_import` encodes both files before it creates the folder, so a
  failed import leaves nothing; names are at most 120 characters (`save_import` cuts a long folder name so that the
  date stays, `admx.fit_name` a longer name of an older version on export).
  `admx.check_templates` checks every record of a package and of every saved import on load (the program folder is
  writable): known fields, the safe names and values of the parser, kinds, ranges, unique parameters, counts. Registry
  branches are not limited, because the templates of Windows write outside the policy branches too. Import ids
  `package-<date>-<time>` and `bundled-<name>`; when two imports hold the same policy, `admx.trust_order` gives it to
  bundled, then system, then folder, then package imports (before, the first loaded won). The window's ADMX menu
  imports and exports them; MCP never does. The window reads a catalog file in a background thread
  (`_read_catalog`); while it is busy, the other imports, show or hide, rename, delete and the language and theme
  changes do nothing, and errors are cut by `error_text` for the message box. `WinKickOff/catalogs/` holds only its
  README until the license check; the build packs it with `WinKickOff/tools/pack_catalogs.py` into
  `_internal/catalogs/*.json.xz` (two files with the same import id stop it).
- Records of imports are conformed, catalog files are not (T23, 04.10.2026): `admx.conform` brings the records of the
  template parser (`read_templates` calls it) and of an import saved by an older version (`load_import`, before
  `check_templates`) into the shape the check accepts: texts lose control characters (DEL included) and keys that are
  not culture names (a culture is 2 or 3 letters and at most 4 subtags; `adml_cultures` ignores a folder such as
  `en-US - Copy`), a chain of categories longer than `MAX_CATEGORY_DEPTH` (32) or a cycle is cut, problems lose the
  quoted paths of this computer (`without_paths`, also on export: single- or double-quoted drive or UNC paths, a
  pattern without nested repetition that runs in linear time, after each problem is cut to 4096 characters; an earlier
  pattern was quadratic on a quote that never closes and could hang the start), and every policy the check would
  refuse (class `machine`, an empty name, a check box with equal values, a key of backslashes only or with a `..`
  segment, `]]>` in a name) becomes a skipped policy (`unsafe` or `broken`) instead of refusing the whole import.
  `conform` checks each policy once; `load_import` then calls `check_templates(data, policies=False)`, which checks
  only the sections. A catalog file is refused as it is. `check_templates` refuses a deeper chain of parent categories
  or a cycle, and `safe_name` refuses `]]>`. A new check of the records needs the same rule in `conform`, otherwise an
  odd policy of the templates of Windows stops an import.
- Keys and characters of imported policies (05.10.2026): C1 controls (0x80-0x9F), U+FFFE and U+FFFF are unsafe in
  keys, value names and string values (`admx._NOT_XML`: an XML document cannot hold U+FFFE and U+FFFF at all, and the
  C1 controls are control characters that XML 1.0 discourages and XML 1.1 allows only as character references), and
  `admx.safe_key` refuses a key with an empty, `.` or `..` segment between backslashes or slashes: PowerShell resolves
  `..` even with `-LiteralPath`, so the key `..\.DEFAULT\Control Panel` of a user policy would write `HKU:\.DEFAULT`
  instead of the default profile. The parser, `conform` and `check_templates` use the same functions; texts by culture
  (titles, explanations) are checked separately and may hold C1 characters.
- Rule ids of an import (`admx._rule_ids`): policies with the same id are numbered (`<id>-2`, ...) by their English
  titles in lower case (`pick(title, "en")`, else the name), then by their position: the order 1.2 used for an English
  interface, so the ids English users saved stay; 1.2 took the titles of the interface language, and now a profile
  saved with the Russian interface names the same policies with the English one. Never number by another field
  without a migration: profiles keep these ids. A counter per base id keeps it linear (5000 equal ids load in
  seconds); every id reserves its `<id>.off`, so an id is never the `<id>.off` of another policy's Disabled rule.
  `catalog_part` never lets a rule replace a rule of another import: a policy whose Disabled rule `<id>.off` is
  already a rule (a policy named `Off` of an import made into rules before it) is left out and logged, and so is a
  policy named `Off` whose id is the Disabled rule of an earlier import (`with_imports` passes the ids of the Disabled
  rules as `disabled`, `ImportedPart.disabled`); an alias of `<id>.off` is made only for a Disabled rule.
  `catalog_part.group_for` remembers the group of each category, and `with_imports` reads and converts each import
  (`load_import` and `catalog_part`) in one `try`, so it never raises.
- Fixed string values of imported policies are literal: `admx._action` marks the action `"literal": True`, and
  `render.substitute_fields` (used by the build, apply, audit, the importer and `core/linked.py`) returns its fields
  unchanged without the mark, so `https://example.com/{id}` stays text. The mark cannot appear in `rules/*.json` (an
  unknown action field). "Check" (F7), "Build autounattend.xml" (F9) and the MCP tools that build (`check_profile`,
  `preview_build`, `write_answer_file`, through `mcp/workspace.check_and_build` or the window's checks) report a
  `KeyError`, `ValueError` or `TypeError` of the build as a build issue.
- Provenance of imported choices (T23): `RuleState.source` is a kind of import, the source of a choice of a policy
  (`catalog.IMPORT_KINDS`: bundled, system, folder, package, most trusted first; `import_kind`, `import_rank` and
  `RuleOrigin.kind` live in `core/catalog.py`, and `core/admx.py` and `core/profile.py` import them), written as
  `"source"` of the rule entry of an imported policy only. It is the most trusted kind the choice has been in effect
  in: `from_dict` and `to_dict(catalog)` keep the more trusted of the saved kind and the kind of the owner now, so a
  choice made in a catalog file and used later with the templates of this Windows is saved as `system`.
  `Profile.from_dict` holds a choice (kept unchanged in `unknown`, the policy off, one warning) when its policy now
  comes from a less trusted kind, and gives it back when an import of that kind or a more trusted one is shown again,
  so a catalog file never takes over a choice made in the templates of this Windows. An entry without `source` was
  saved before 1.3 and counts as `folder` (`profile.LEGACY_SOURCE`), since catalog files did not exist then, and so
  does an entry with an unknown kind: it is held when only a catalog file has the policy and used as before with a
  folder, system or bundled import. The window describes a held choice under the root of unknown rules
  (`UNKNOWN_HELD`, `KIND_TITLES`, `_held_source`). For every kept choice of a policy, held or not loaded at all, it
  offers "Show ..." and the import commands only for imports of the kind of the choice (`_kept_source`) or a more
  trusted one, since a less trusted import would hold it again, and names a held choice that no hidden import brings
  back. `Profile.held(catalog)` lists the held choices (entries of `unknown` whose rule is loaded), and
  `app.create_app` puts `profile.held_warning` into the message list at every start, after a restart of the window
  and at the first start alike, not only into the log. The profile format stays 3.
- Profiles of a wrong shape (T23): `Profile.load` reads strictly through `jsonfile.read` (16 MB, `PROFILE_MAX_BYTES`;
  `null` allowed for older files; a duplicate key, `NaN`, a lone surrogate or nesting deeper than 32 levels refused),
  and the embedded profile of an answer file through `jsonfile.loads` (`core/importer.py`); before 05.10.2026 both used
  the `json` module. `Profile.from_dict` checks the depth of an object given directly (`jsonfile.check_depth`) and
  raises only `ValueError` (a profile that is not an object, or any `TypeError`, `AttributeError`, `KeyError` or
  `RecursionError` while reading); a field of a wrong type falls back to its default (`format_version`, `install`,
  `languages`, accounts, rule entries, `enabled`, parameter values by type through `profile._fits`), with a warning for
  the format, rule entries, `enabled`, values of `install` and `languages`, parameter values and skipped accounts;
  `"install": 5` loads. `enabled` 0 or 1 is false or true, as 1.2 took it; a boolean that MCP of 1.2 saved for an enum
  becomes the option it equals (`profile._as_option`), and the MCP `set_param` refuses a boolean for an enum
  (`True == 1` in Python). `profile.one_line` keeps the name and the author on one line, and `apply._label` writes the
  label line of the Apply, Audit and Undo scripts through `render.ascii_text`, so a name with line breaks (also CR and
  U+2028) stays on that comment line. `Profile.save` encodes the text before it opens a file and writes a temporary
  `<name>.tmp` that `os.replace` puts in place, so a failed save leaves the old file whole; a lone surrogate (half of an
  emoji that a Tk entry keeps after a Backspace) is saved as U+FFFD (`jsonfile.without_surrogates`), since before
  08.10.2026 `write_text` failed on it after emptying the file. The check of the profile reports such a text as an
  error at its field (`validate.half_characters`, `HALF_CHARACTER`), so the build never writes it.
- Runtime 0.6 (`templates/VERSION`): `Setup-User.ps1` and `Post-OOBE.ps1` define `Set-Reg` and `Remove-Reg`; before, a
  `reg` action of the phases user-first-logon or post-oobe failed with "Set-Reg is not recognized". These phases may use
  only `reg`, `reg-remove` and `ps` (`PHASE_ACTION_TYPES` in `core/catalog.py`, checked against the runtimes by
  `tests/test_render.py`). `HKU:\.DEFAULT\` (the sign-in screen) is a registry prefix of the phases specialize and
  default-user, scope `signin` in `registry_values()`; the audit reads it as `Registry::HKEY_USERS\...`. An enum
  parameter may name `differs_from` another enum of the rule with `same_allowed` values; the check of the profile
  reports a clash (`default-user.input-switch-keys`: language and layout switch keys, Win+Space cannot change).
- Computer name and account texts (task T24, 08.10.2026, catalog and runtime 0.7, profile format 4):
  `install.computer_name_mode` `random` (no `ComputerName`, the default), `fixed` or `template`, `install.computer_name`
  the name or the template; `core/computername.py` holds the rules (15 characters, Latin letters, digits and hyphens,
  not only digits, `{serial}`, `{mac}`, `{random}` with lengths). A template: `ComputerName` `WINKICKOFF-TMP` and
  `templates/section-computer-name.ps1` at the start of `Setup-System.ps1` (slot `computer_name_section`), which
  starts a hidden PowerShell process that writes the name to the three registry values every 50 ms until the restart
  after specialize, the technique of the Schneegans generator (card 02); nothing on the customer's PC may run it.
  Windows Setup 24H2 and later turns the characters of a `LocalAccount` outside ASCII into question marks (the
  customer's Cyrillic description of 08.10.2026): `render.account_xml_texts` writes ASCII only, and
  `render.account_text_lines` adds `Set-AccountText` calls (ADSI, the text as UTF-8 in Base64 through `ps_text`, so the
  answer file stays ASCII) to `Post-OOBE.ps1`, which the build then creates with its task even without post-oobe rules.
  An account name or a password outside ASCII is a check error (`validate.NOT_ASCII`), and both XML checks refuse such
  texts. The other paths of Cyrillic were checked and keep it (T24 lists them). Acceptance in a VM pending.
- Accounts asked during installation (customer request 2 of 04.10.2026): profile format 3 adds `install.account_mode`
  (`file` or `ask`). In `ask` the answer file has no `UserAccounts` (`Profile.answer_file_accounts()` is empty, also for
  Post-OOBE and Apply), so Windows Setup asks for one account and makes it an administrator; the accounts stay in the
  profile. The check warns when `oobe.hide-online-account` or `install.bypass-nro` is off in that mode, and
  `tools/Validate-Unattend.ps1` accepts a file without any `LocalAccount`. Format 2 profiles load as `file` without a
  warning. The edition is chosen during installation in the existing key mode `ask` (request 4): the form disables the
  edition list outside `generic`, and the check adds an info about Home.
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
  folder has a Local entry (shown by Windows 10) and a classic one; showing both may duplicate the folder. Since the
  customer's commits of 05.10.2026 the Windows default of every `thispc.*` action is 1, also of the three entries
  Windows does not ship (`thispc.3d-objects`, `thispc.recycle-bin`, `thispc.control-panel`; the last two come from
  `WinKickOff/tools/make_shell_rules.py`): an apply of a profile with them off and "Return the selection to Windows defaults now..."
  create their keys with value 1, which should hide them (card 20, VM check 6). Keep this decision.
- Editions of the generic key (customer commit 036b364 of 05.10.2026): `render.EDITION_KEYS` names 14 editions, the
  keys aligned in columns by the customer. Pro and Education have generic installation keys; the other twelve are the
  KMS client keys (GVLK) of the Microsoft Learn table "Key Management Services (KMS) client activation and product
  keys", compared key by key on 08.10.2026: without a KMS host such a Windows stays unactivated until the key of the
  licence is typed. The form sizes the edition list to the longest name and says so under it; card 01 lists them. The
  file `skills/winkickoff/references/concepts.md` is 9 bytes below the pi limit of 20 KB (`test_skill.py`; 08.10.2026,
  after the computer name): shorten something before adding text there.
- The Home preset is an allowlist: `HOME_RULES` in `WinKickOff/tools/make_presets.py` names its 70 rules (the hardware
  check bypasses and OOBE screens of Office, removal of extra apps, ads, Copilot and user privacy, File Explorer opens
  This PC), with Delivery Optimization `mode` 99, telemetry `level` 0 and the product key asked. A new catalog rule
  stays off in Home until it is added to the list. Home leaves out the WinKickOff protection set: of the UAC, LSA,
  Defender, ASR, SmartScreen, network, logging, update, browser and post-installation rules only
  `defender.notifications` and `update.delivery-optimization-lan` are on, the rest write nothing, so Windows keeps its
  defaults. Also off: `install.netfx3`, `printing.spooler-automatic`, `default-user.region`,
  `user-logon.input-languages`, `user-logon.pin-ui-language`, `removable.autorun-off` and the AI rules of Notepad,
  Paint, Office and Edge; the check shows 13 baseline warnings. It does not turn UAC prompts, the secure desktop, Win+L or
  real-time protection off; it only stops enforcing them. Home is not the Windows Home edition: its key mode `ask`
  lets the person choose the edition during Setup, and Pro is the better choice for the WinKickOff protection.
- GitHub rejects a push with a personal e-mail in the commit author; this repository has the local address
  `265459095+stanislavperec-ua@users.noreply.github.com` (`git config user.email`, this folder only).
  Files are stored byte for byte (`.gitattributes`: `* -text`), CRLF.
- The work PC has Python 3.14.3 with tkinter 8.6; pytest is absent and is not installed.
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
  and group titles are translated in `WinKickOff/rules/lang/<code>.json`. A language exists when one of its files
  exists (the native name is the field `_language`); there is no `strings.en.json` or `lang/en.json`, and every
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
  characters refused, also C1 controls and U+FFFE and U+FFFF since 05.10.2026, keys with an empty, `.` or `..` segment
  refused by `admx.safe_key`, `ps_quote` doubles typographic single quotes). Tests read the templates of this Windows
  (`C:\Windows\PolicyDefinitions`) read-only; nothing is written outside temporary folders.
- Several imports (T20): a policy is one rule, owned by the most trusted import (`admx.trust_order`, T23; before 1.3
  the first loaded); the other trees show it as an alias
  (`Catalog.aliases`, `placements()`), with the tree item id `r:<rule>@<group>`. Code that takes a rule from a tree
  item uses `rule_of()` of `ui/main_window.py`, never `item[2:]`, and This PC gets canonical `r:<rule>` items.
  An alias needs the same rule id; a rule of one import never replaces a rule of another (`catalog_part` leaves out a
  policy whose Disabled rule `<id>.off` another import already holds as a policy named `Off`, and logs it).
  `import.json` `renamed: true` keeps a name given by the user when the import is updated in place.
- Unknown choices (02.10.2026, after 1.2.0-rc.4): `Profile.unknown` holds the states of rules the loaded catalog does
  not have (policies of hidden or deleted imports, rules of another catalog version); they are never built, validated
  or applied. The window lists them under the last root `unknown` with items `u:<rule id>` (`Profile.unknown_entries()`),
  only while there are any; they cannot be toggled, search matches their ids, and the MCP `show_item` pattern does not
  accept them. The description names the hidden saved imports that have the policy (`admx.policy_ids()`, the ids
  `catalog_part` gives, read once per window) and offers "Show ..." (`show_templates(id, True, "r:<rule>")`) or the
  import commands of the ADMX menu. Since T23 the root also lists choices held by their `source` (the policy is loaded,
  but only from a less trusted kind of import; see the provenance fact above): status "held: a less trusted source
  holds the policy now", description `UNKNOWN_HELD`, "Show ..." only for imports of the kind of the choice or a more
  trusted one.
- MCP server (T22, `winkickoff/mcp/`, design in `docs/technical/editor/todo/T22-mcp-server.md`, description in
  `docs/technical/editor/07-mcp-server.md`): protocol 2025-06-18 on JSON-RPC 2.0, hand-written on the standard library;
  the HTTP listener binds the literal 127.0.0.1 (`tests/test_sources.py` allows `http.server` in `mcp/httpserver.py`
  only), needs the bearer token of `settings.mcp_token`, checks Host and Origin and answers every request with JSON.
  The mode (`read`, `edit`, `files`) is never persisted: every start is `read`. Nothing through MCP ever runs
  PowerShell, applies, audits, deletes, replaces or imports; passwords and product keys are redacted, and
  `tests/test_mcp_tools.py` proves both. Threads: server threads never touch tkinter or the Profile; every call goes
  through `mcp/bridge.py`, pumped by the window from an `after()` timer; dialogs are counted by `MainWindow._dialog()`
  so writes are refused with `window_busy` while a dialog is open. The window's settings object is the only writer of
  `settings.json` (the service saves the token through `window.save_settings`); headless processes never write it and
  log into `logs/mcp-<transport>-<pid>.log`. `winkickoff/__main__.py` dispatches `--mcp` before importing `app.py`, so a
  stdio server never loads tkinter. The portable build has a console `WinKickOff-mcp.exe` for stdio next to
  `WinKickOff.exe` (`WinKickOff/tools/WinKickOff.spec`, CI only). After the adversarial review of rc.1 (01.10.2026):
  the journal shows only identifier-like keys declared by the tool schema, URIs and client names (free text by size);
  a profile outside the program folder is reported by file name only; `set_param` with the current value and
  `set_profile_info` without a change keep the profile clean; `save_profile` refuses the preset ids; file errors are
  the tool error `write_failed`; `fit_text` cuts a preview by its serialised size; HTTP refuses a signed
  `Content-Length`, caps handler threads (`MAX_CONNECTIONS`) and drains at most 64 KB for an unauthenticated request;
  `service.stop()` marks the `McpServer` closed and closes the bridge; the token is copied through
  `ui/clipboard.py` with the Windows exclusion formats and never as a plain copy on Windows (a busy clipboard means
  nothing is copied; while waiting it delivers the messages sent to the thread, because Tk renders its own clipboard
  text on request and a viewer such as the clipboard history waits for that); HTTP tests bind loopback port 0 on every
  run (no gate).
- The pi agent container (`pi-agent/`, by a team member on 01.10.2026, reworked on 02.10.2026 at the customer's
  request): an assistant with a local model that analyses and changes profiles, reaching WinKickOff only through its
  MCP server. The customer's rule: the folder `pi-agent/` holds no information about the project (an agent that reads
  about the source code starts exploring it), so the repository is not mounted and the image holds `/work/AGENTS.md`
  (a copy of `pi-agent/AGENTS.md`) and nothing else of the project. pi runs with its defaults: its own tools `read`,
  `bash`, `edit`, `write`, the built-in MCP support with exposure `codemode` (the model calls
  `tools.mcp__winkickoff__<tool>({...})` and the resource tools from JavaScript run by the `codemode` tool;
  `"defaultTools": ["+codemode"]` in the volume's settings keeps it on even without a server entry; pi turns it on at
  session start for the codemode entry anyway), its default system prompt with `/work/AGENTS.md` as the context file.
  Later on 02.10.2026 the customer removed the wrapper
  `/usr/local/bin/pi` of rc.3 and rc.4 (`--no-builtin-tools`, an allowlist `--tools`, `--system-prompt`, exposure
  direct): it took away the additional tools and codemode, which works better, and replaced the system instructions,
  so the whole agent worked worse. Never bring the wrapper or tool restrictions back unless the customer asks;
  `test_pi_agent.py` fails on a wrapper, a restricting flag, a baked prompt file or an exposure in the setup. The
  instructions of `pi-agent/AGENTS.md` keep the agent away from WinKickOff files, `~/.pi` and the token, and ask for
  one awaited call at a time (a script could start calls together; a fifth concurrent call gets our 503 and pi never
  retries). Node.js comes from the official archive with a pinned SHA-256 (the NodeSource package needs python3); pi is
  pinned to 1.0.0 (commit ef52d8e; the facts below were checked with 0.99.2, recheck them with 1.0.0). Facts of pi:
  a codemode script gets the whole `CallToolResult` (`isError`, `content`, `structuredContent`) and its returned
  output is cut above about 10,000 tokens; a direct call shows the model only the
  error text (hence the kind at the start of that text) and cuts any MCP text above 20 KB (hence every skill file stays
  below, checked by `test_skill.py`); the system prompt names a codemode server with at most the first 250 characters
  of the first line of its instructions (not the skill sentence at their end), once it has connected. Networking: `--network=host` reaches the window only where the container's loopback is the host's (on
  Windows only with WSL mirrored networking, a system setting). The CI job `pi-agent-container` builds the image with
  Podman, starts a headless WinKickOff HTTP server from the checkout on the runner and runs
  `.github/scripts/check_pi_agent.py`: the image contents (plain pi, no wrapper, no baked prompt files), `pi mcp list`
  (codemode, 18 tools), and with a stub OpenAI-compatible server instead of a model the tools and the prompt pi sends
  and a `codemode` script of the stub that calls WinKickOff tools. `WinKickOff/tests/test_pi_agent.py` keeps project
  markers out of `pi-agent/` and ties its AGENTS.md to the server (tools, script calls, error kinds, ids, resources,
  labels).
  Portability fixes of 01.10.2026 stay: the reserved device names are a fixed list (`os.path.isreserved` exists only on
  Windows), the `pythonw.exe` test runs only on Windows, `McpHttpServer.allow_reuse_port` is False, `test_docs.py` skips
  `.claude`, `.venv`, `venv`, `node_modules`, `build` and `dist`.
- The PowerShell syntax check of the embedded scripts runs only in the window's "Build autounattend.xml" (F9);
  "Check" (F7) and the MCP tools `check_profile` and `write_answer_file` skip it. Since 01.10.2026 the note that
  `write_answer_file` returns says so (it used to send people to Check). The Office preset turns on 16 ASR rules,
  Strict 17 (`asr.usb-untrusted`).
- The skill `WinKickOff/skills/winkickoff` (01.10.2026) was written by a workflow: research of the Agent Skills format
  and of the clients (Claude Code `~/.claude/skills`, Claude Desktop and claude.ai ZIP upload with a description of at
  most 200 characters, pi `~/.pi/agent/skills` and `/skill:winkickoff`), the MCP surface from the code, the domain;
  then three reviews (accuracy, usability with a small local model, safety) and fixes. It names tools bare
  (`get_status`) and explains the client prefixes; it is not for editing WinKickOff code (that is this file).
- Built-in rules and imported policies (T21, `core/linked.py`): a policy whose registry writes an enabled built-in
  rule already covers is shown checked (tag `linked`) but stays off in the profile; the window uses `_rule_on()`
  for images and group counts, never `profile.is_enabled()` alone. An equal policy switches the built-in rule.
- Placeholders and paths (security fix of 04.10.2026): `{param}` is filled in only in the action fields
  `PLACEHOLDER_FIELDS` (`value`, `args`, `script`, `command`) through `render.substitute_fields`; a key, a value name
  or a file is always literal, and the catalog refuses a placeholder elsewhere. A DU path is rendered as `($du +
  '\...')`, a single-quoted literal, never as the double-quoted `"$du\..."` of older builds, which PowerShell
  expanded: an imported template could put a key with `{e1}` and an enum value `$(...)` into the answer file.
  `actions_parser` reads both forms, so older builds still import.
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
| Critic's report and fixes | Done (9 accepted, 3 rejected) | 13.09.2026 | `docs/appendices/C-critical-review/03-critic-report-v0.2.docx` |
| Parameter reference | Done, 21 cards (00-20) and the index, English; card 20 (File Explorer namespaces) added for catalog 0.6 | 04.10.2026 | `docs/technical/reference/` |
| Answer file checker | Done, 37 checks, 0 errors on v0.2 (since 08.10.2026: computer name, account texts in ASCII) | 08.10.2026 | `tools/Validate-Unattend.ps1` |
| GitHub repository | Renamed to WinKickOff; the local clone and `origin/main` match; CI in GitHub Actions | 26.09.2026 | https://github.com/supakov/WinKickOff |
| Editor specification | Revision 0.2, English | 25.09.2026 | `docs/technical/editor/` |
| Editor tasks | T01-T12, T14, T16-T24 done (the build runs in GitHub Actions; T23: the catalogs of the program wait for the license check); T13 blocked on the acceptance checklist; T15 implemented with return to defaults, acceptance in a VM pending | 04.10.2026 | `docs/technical/editor/todo/` |
| Rule catalog | 0.6: 278 rules, 40 groups (130 carry v0.2; browsers 64; list MoreOptions: AI, telemetry, advertising, search, speech, Office, OneDrive, drivers; File Explorer and the desktop 41; keys that switch the input language), Windows defaults for return, integrity and v0.2 coverage confirmed by tests; 0.6 adds the File Explorer namespaces and desktop icons (generated), the switch keys of the sign-in screen and new accounts, registry functions of the per-user and post-OOBE scripts; since 1.3.0 (T23) strict JSON in a canonical layout instead of TOML, the same content | 04.10.2026 | `WinKickOff/rules/` |
| Editor code | 1.3.0-rc.2 (T24: the computer name, a name or a template, and account texts outside ASCII; T23: the catalog in JSON, export and import of catalog files, catalogs of the program, saved imports checked and conformed on load, trust order of imports and the provenance of imported choices; the tree root of unknown rules and policies, the account asked during installation, File Explorer namespaces and desktop icons, the switch keys of the input language, a security fix of placeholders; Home preset; customer specifics removed; skill for agents that use WinKickOff, also served over MCP; error kinds in tool error texts; MCP server, T22; import of ADMX templates with lists of values, T19; Back and Forward, shared imports, T20; links to built-in rules, T21): generator, profile, XML and catalog checks, import of built files and of v0.2, PowerShell check, four presets, window with check boxes, parameters, forms, profiles, comparison, recent files and build; English source with Russian and Ukrainian translation files, languages and colour themes (Light, Dark, Latte, Matrix, as in Windows) found from files; 799 tests | 08.10.2026 | `WinKickOff/` |
| Installation from a WinKickOff build | Confirmed by the customer on real hardware (accounts, languages, minimal questions) | 26.09.2026 | release 1.0.0-rc.1 |
| Applying rules to a running Windows | T15: read-only audit, apply (rules on are applied, rules off return to Windows defaults) and return to Windows defaults with backup and undo, through UAC after a one-time permission; acceptance in a VM pending | 29.09.2026 | `WinKickOff/winkickoff/core/apply.py`, `docs/user/*/this-pc.md` |
| Repository layout | T17 done; 26.09.2026 the repository was renamed to WinKickOff, the old umbrella name is gone | 26.09.2026 | `README.md`, `docs/appendices/` |
| Documentation split | T16 done: technical in English, user documentation in ru, uk, en; since T18 the catalog is English with complete ru and uk translations | 30.09.2026 | `docs/technical/`, `docs/user/`, `WinKickOff/rules/lang/` |
| GitHub issues | #1 "Web Browsers debloat" done: section "Browsers" (Edge, Chrome, Brave), 46 rules off by default, card 18. The customer closes issues | 25.09.2026 | `WinKickOff/rules/14-browsers.json`, `docs/technical/reference/18-browsers.md` |
| Release candidate | 1.3.0-rc.2 in the code with its notes, not tagged yet (a tag only on the customer's command); 1.3.0-rc.1 published on 08.10.2026 (tag on 7e25d20, prerelease built by CI); 1.2.0-rc.4 published (Home preset with its own list of rules, customer specifics removed, Appendix A and the review of the original deleted); earlier 1.2.0-rc.3 (the skill served over MCP, error kinds in tool error texts, pi-agent an MCP-only assistant), 1.2.0-rc.2 (skill `skills/winkickoff` in the build, clipboard fix, F9 hint), 1.2.0-rc.1 (MCP server, after the review fixes of 01.10.2026), 1.1.0-rc.4 (imported policies follow the built-in rules), 1.1.0-rc.3 (Back and Forward, shared imports), 1.1.0-rc.2 (lists of values), 1.1.0-rc.1 (import of ADMX templates) and 1.0.0-rc.1 to rc.4 of 26.09-30.09.2026: tag and GitHub release built by CI | 04.10.2026 | `docs/releases/v1.2.0-rc.4.md`, `docs/releases/v1.3.0-rc.1.md` |
| Imported ADMX templates | T19 done: ADMX menu, store `admx/` next to the program, policies as rules with parameters, links to built-in rules; since 1.1.0-rc.2 list and multi-line elements too (20 of 3552 policies of this Windows skipped); acceptance of lists on This PC in a VM pending; T20 (1.1.0-rc.3): an import of an imported folder asks to update it or add a tree, a policy in several trees has one check mark, trees can be renamed; Back and Forward in the window; T21 (1.1.0-rc.4): an imported policy follows the built-in rule that sets the same values; T23 (1.3.0-rc.1): export and import of catalog files, catalogs of the program (none shipped until the license check), the trust order of imports, saved imports checked on load | 04.10.2026 | `WinKickOff/winkickoff/core/admx.py`, `docs/user/*/admx.md` |
| Customer list MoreOptions | Done: BitLocker off in every preset; 57 rules on by default (AI, telemetry, advertising, search, speech, Office, OneDrive, drivers, Edge AI and sign-in, Gallery hidden), This PC folders as options off by default; corrections in card 19 | 28.09.2026 | `docs/technical/reference/19-more-privacy.md` |
| MCP server | T22 done in code: stdio and HTTP transports, 18 tools, resources, modes read/edit/files, monitor, second executable in CI; acceptance with real clients (Claude Code, Claude Desktop) in a VM pending | 30.09.2026 | `WinKickOff/winkickoff/mcp/`, `docs/user/*/mcp.md` |
| pi agent container | An assistant that reaches WinKickOff only over MCP (no project files or information in the image); since the customer's decision of 02.10.2026 pi runs with its defaults and codemode, without the wrapper of rc.3 and rc.4; CI job `pi-agent-container` checks the image, the connection, the tools and prompt given to the model and a codemode script that calls WinKickOff; acceptance with the window and the local model (README) pending | 02.10.2026 | `pi-agent/` |
| Skill for agents that use WinKickOff | `WinKickOff/skills/winkickoff` (SKILL.md, references tools, workflows, concepts) and its install README; shipped in the portable build; `test_skill.py`; user page `mcp.md` section on the skill (ru, uk, en); not yet tried with a model, Claude Desktop upload untested | 01.10.2026 | `WinKickOff/skills/` |
| Tuning of preset defaults | Awaited from the customer | | `WinKickOff/tools/make_presets.py`, rule defaults |

Awaited from the customer: the decision on the catalogs of the program after the license report
`docs/reports/2026-10-08-admx-license.md` (it recommends shipping none made from Microsoft templates).

Open questions to the customer: `docs/appendices/D-requirements-draft/02-constructor-requirements-draft.md`,
section 6; whether Appendix D should get a sample WinKickOff build.

## 8. How to update this file

- The folder structure changed: section 3.
- A run or check command appeared: section 5.
- A task was finished or started: section 7 and `docs/technical/editor/todo/README.md`.
- A fact that affects future changes was found: section 6.
- The MCP tools, their errors, the presets or the catalog changed: the skill (`WinKickOff/skills/winkickoff`).
- The pi agent container changed (`pi-agent/`): its README, its AGENTS.md when the agent's environment or rules
  change, and the "pi agent container" row of section 7.
- The date in the header on every change.
