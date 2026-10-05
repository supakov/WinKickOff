# WinKickOff

The editor of the WinKickOff toolkit (installing and configuring Windows 11 Pro in workgroups without a
domain). It shows every installation rule in one tree with check boxes and search, disables dependent rules
automatically, keeps the selection in a JSON profile and assembles `autounattend.xml` from the selected rules
only; its This PC menu checks, applies and returns rules to Windows defaults on a running Windows.
The answer file checker is `../tools/Validate-Unattend.ps1`.

User documentation (how to work with the program): [Русский](../docs/user/ru/README.md),
[Українська](../docs/user/uk/README.md), [English](../docs/user/en/README.md).
Specification, architecture, data model and plan: [`../docs/technical/editor/`](../docs/technical/editor/README.md).

State on 04.10.2026: version 1.3.0-rc.1. New in 1.3: the rule catalog is strict JSON in a canonical layout (task
T23); the "ADMX" menu exports imported templates as catalog files and imports catalog files and the catalogs of the
program (`catalogs/`, none shipped yet), checks every record of them and of the saved imports, and takes a policy
that two imports share from the most trusted source; the account can be asked and the edition chosen during
installation; parameters are filled in only in values, never in registry paths or value names; the tree root
"Unknown rules and policies" shows the choices of the profile for rules the loaded catalog does not have, and the
choices of imported policies held back because only a less trusted import has the policy now. Since 1.2:
the MCP server (stdio and HTTP on 127.0.0.1, read-only by default) and the skill `skills/winkickoff` for assistants
that use it. Since 1.1: import of ADMX templates, including policies with lists of values and multi-line text; Back
and Forward; imported policies follow the built-in rules. The catalog 0.6 (278 rules, 40 groups) carries every action
of the hand-written answer file v0.2, the Edge, Chrome and Brave policies, the AI, telemetry, Office and OneDrive rules
of the customer's list, the File Explorer namespaces and desktop icons and the keys that switch the input language;
the generator, the checks, four presets, profiles, data forms, import, the build from the window and the This PC menu
work. The source language is English; languages and colour themes are files (see "Languages and themes" below).
The Office preset equals the catalog defaults; a build passes `tools/Validate-Unattend.ps1` (36 of
36), and installation from a built file has been confirmed by the customer on real hardware. Test every new
answer file in a VM first. Open tasks: `../docs/technical/editor/todo/`.

## Requirements

- Python 3.14 (standard library only: tkinter, json, lzma and zlib for compressed catalog files, xml.etree, logging).
- Windows 10 1809+ or Windows 11.

## Commands

Run from sources (or double-click `../Start-WinKickOff.cmd`, which checks for Python 3.14 with tkinter and
starts the window without a console); `python -m winkickoff --mcp stdio` runs the MCP server without a window,
`python -m winkickoff --mcp-config stdio` prints the client configuration:

```powershell
cd WinKickOff
python -m winkickoff
```

Tests (write only into temporary folders; every window they open is fully transparent and has no taskbar button,
`tests/quiet_tk.py`):

```powershell
cd WinKickOff
python -m unittest discover -s tests -v
```

After a change of the rule catalog, bring its files to the canonical layout (two spaces of indent, an object or array
on one line when it fits in 120 columns, CRLF; `--check` only lists the files that differ, and
`tests/test_catalog_format.py` fails on them), then regenerate the presets and the rule lists of the user
documentation:

```powershell
cd WinKickOff
python tools/format_catalog.py
python tools/make_presets.py
python tools/make_rule_docs.py
```

A catalog of the program is made from a folder of ADMX and ADML files (read like "Import templates from a folder...",
with the ADML of every language of the program); read `catalogs/README.md` first, because the license of the templates
must allow shipping them:

```powershell
cd WinKickOff
python tools/make_admx_catalogs.py <templates folder> catalogs/<name>.json --name "<tree name>" --windows 10.0.26200
```

What the build tests check: the output is deterministic and ASCII only; a disabled rule leaves no trace;
phases without rules add no scripts or tasks; every `Setup-System.ps1` action of v0.2 is present in the build
of the v0.2 reference profile (`tests/v02_actions.py`); commands, International-Core, OOBE, accounts and the
time zone equal v0.2; importing v0.2 gives the reference profile; `tools/Validate-Unattend.ps1` accepts the
built file.

The portable zip is built by GitHub Actions (`../.github/workflows/build.yml`) with `tools/build.ps1`; it needs
PyInstaller from the internet, so it never runs on the customer's work PC. The build checks every
`catalogs/<name>.json`, writes it as `_internal/catalogs/<name>.json.xz` and reads it back (`tools/pack_catalogs.py`);
it fails when a catalog does not pass the check, reads back different from its JSON or is missing from the build, and
when two files would get the same import id.

## Where things are stored

| What | Where | Versioned |
|---|---|---|
| Presets Office, Strict, Laptop, Home | `profiles/preset-*.json` | yes; generated by `tools/make_presets.py` |
| User profiles | `profiles/<name>.json` | no |
| Built answer files | `output/` (default) | no |
| Program log | `logs/winkickoff.log` | no |
| Settings: window size, last profile, recent files, language, theme, imported templates shown, MCP port, access token and autostart | `settings.json` | no |
| Logs of MCP servers started without a window | `logs/mcp-stdio-<pid>.log`, `logs/mcp-http-<pid>.log` | no |
| Imported policy templates (ADMX menu; ids `system-*`, `folder-*`, `package-*`, `bundled-*`) | `admx/<id>/` | no |
| Catalogs of the program ("Import a catalog of the program") | `catalogs/<name>.json`; in the portable build `_internal/catalogs/<name>.json.xz` | yes (none yet) |
| Catalog files exported by the user ("Export imported templates") | wherever the user saves them | no |

The program writes nothing outside its folder, except the files the user saves elsewhere through a file dialog, and
never connects to the internet. The optional MCP server accepts
connections only from this computer, on 127.0.0.1, when the user starts it, and is read-only by default (menu MCP,
`docs/user/<lang>/mcp.md`). The PowerShell syntax check runs
`powershell.exe` only to parse files in the temporary folder `logs/tmp/`.

## Structure

```
WinKickOff/
  winkickoff/        code: core (logic without UI), ui (tkinter: window, forms, check boxes)
  rules/             rule catalog (strict JSON, English, canonical layout): groups.json, NN-<area>.json,
                     lang/<code>.json (translations)
  catalogs/          catalogs of the program: packages <name>.json of imported ADMX templates for the menu "ADMX"
                     (none yet, see catalogs/README.md); the build ships them compressed with xz
  templates/         runtime XML and PowerShell with slots (see templates/README.md)
  resources/         keyboard layouts, time zones, strings.<code>.json (interface translations), themes/
  profiles/          presets (generated from the catalog, see profiles/README.md)
  skills/            winkickoff/: the Agent Skill for AI agents that use WinKickOff over MCP (see skills/README.md);
                     shipped next to the exe in the portable build
  tests/             unittest
  tools/             make_presets.py, make_rule_docs.py, make_browser_rules.py (generates rules/14-browsers.json),
                     make_shell_rules.py (generates rules/17-shell.json), format_catalog.py (canonical layout of the
                     catalog files), make_admx_catalogs.py (a catalog of the program from ADMX templates),
                     pack_catalogs.py (xz for the build), run-tests.ps1, build.ps1 (T12)
```

The working folders `output/`, `logs/` and `settings.json` are created next to the program on first use
and are not versioned.

## Languages and themes

English is the source language of the code, the interface and the catalog. A translation is a pair of files:
`resources/strings.<code>.json` (`{"_language": "<native name>", "<English text>": "<translation>"}`) and
`rules/lang/<code>.json` (`_language`; rule, parameter and option texts and extra search tags under the rule id;
group texts under `_groups`). Either file alone adds the language to the "Language" menu; anything missing is shown
in English. Bundled: `ru`, `uk`.
A colour theme is `resources/themes/<id>.json` (`name`, `base` `native` or `clam`, `dark`, `font`, `colors`);
bundled: `light`, `dark`, `latte`, `matrix`. The empty setting (the menu item "As in Windows") follows the Windows
interface language and the Windows light or dark mode. Details: `../docs/technical/editor/03-data-model.md`,
section 3.

## Project rules

- No dependencies beyond the standard library in the application.
- No writes outside the program folder, except a file the user saves through a file dialog; no network access except
  the MCP listener on 127.0.0.1 (`winkickoff/mcp/httpserver.py`) that the user starts.
- No em or en dashes in code, data, strings or documents (the vendor texts of the templates in `catalogs/` are kept as
  written).
- Code, comments and catalog texts in English; a new interface string needs its ru and uk translation.
- Catalog and template changes are checked with `python -m unittest` before a commit.
