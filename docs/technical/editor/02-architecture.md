# 02. WinKickOff architecture

Revision 0.2 of 25.09.2026.

## 1. Principles

1. The rule catalog (`rules/*.toml`) is the single source of truth about what the installation
   can do. The interface, generator, validator, descriptions and tests read it; the code contains no rules.
2. The runtime is separate from the rules: immutable PowerShell and XML fragments live in `templates/`.
3. Logic without the interface: `core/` does not import tkinter and is tested with `unittest`.
4. A single path function `app_paths()`; nobody builds paths on their own.
5. No dependencies outside the standard library in the application itself.
6. Any data error (rule, profile, template) turns into a message naming the file and the
   identifier; the application does not crash.

## 2. Structure of the `WinKickOff/` directory

```
WinKickOff/
  README.md                  how to run from sources, tests, build
  pyproject.toml             metadata, requires-python >= 3.14, ruff/mypy settings
  winkickoff/
    __init__.py              APP_VERSION
    __main__.py              python -m winkickoff
    app.py                   startup: paths, log, catalog, window
    core/
      paths.py               AppPaths, app_paths()
      log.py                 logging to logs/
      catalog.py             Rule, Action, Group, Param models; TOML loading; integrity verification
      deps.py                Resolver: enable/disable with cascade, application order
      profile.py             Profile: rule and parameter state, installation data; JSON
      render.py              building scripts and XML from the runtime and the enabled rules
      validate.py            profile and XML verification; Issue
      importer.py            profile from XML (embedded) or from the v0.2 file (action parsing)
      pscheck.py             syntax verification via powershell.exe, if available
      i18n.py                translations: languages found from files, English fallback
      themes.py              colour themes from resources/themes, following the Windows light or dark mode
      admx.py                policy templates (ADMX, ADML) imported into admx/<id>/ and turned into rules
      linked.py              imported policies that follow a built-in rule with the same registry values
      startup.py             the profile a session starts with (shared by the window and the headless MCP server)
    mcp/                     MCP server (task T22, see 07-mcp-server.md): jsonrpc, schema, redact, journal,
                             workspace, bridge, tools, resources, protocol, stdio, httpserver (the only listener,
                             127.0.0.1), service, cli
    __main__.py              dispatcher: --mcp, --mcp-config and --version run without tkinter
    mcp_main.py              console entry of WinKickOff-mcp.exe (a stdio server)
    ui/
      main_window.py         window, menu, three areas, hotkeys
      rule_tree.py           tree with check boxes, search, filter
      detail_panel.py        rule description, action table, parameter editor
      data_forms.py          data node forms: installation, accounts, languages
      dialogs.py             about, profile comparison, cascade list
  rules/
    groups.toml              group tree
    NN-<area>.toml           rules by area (English), file order = application order
    lang/<code>.toml         translations of rule strings (ru, uk; a new file adds a language)
  templates/
    autounattend.template.xml      skeleton with slot markers
    Setup-System.runtime.ps1       functions, trap, header, hive mounting
    Setup-User.runtime.ps1         header and log of the first sign-in script
    Post-OOBE.runtime.ps1          waiting for OOBE, reading the profile, completion
    VERSION                        catalog and runtime version (0.3)
  resources/
    strings.<code>.json                interface translations keyed by the English text (ru, uk)
    themes/<id>.json                   colour themes (light, dark, latte, matrix)
    keyboards.json, timezones.json     reference data
  profiles/
    preset-office.json, preset-strict.json
  tests/
    test_catalog.py, test_deps.py, test_profile.py, test_render.py, test_validate.py,
    test_coverage_v02.py (semantic golden), test_ui_smoke.py
  tools/
    build.ps1, run-tests.ps1
```

## 3. In-memory data model

```
Catalog
  groups: dict[id, Group(id, parent, title, order, summary)]
  rules:  dict[id, Rule]
  order:  list[id]              order by file and position
Rule
  id, group, phase, title, level, default, requires[], conflicts[], tags[]
  summary, effect, risk, versions, verify, rollback, doc
  params: dict[name, Param(type, default, min, max, values, title)]
  actions: list[Action(type, fields...)]
Profile
  meta: format_version, catalog_version, name, author, created, modified, comment
  install: edition, product_key_mode, product_key, time_zone
  languages: ui_language, system_locale, user_locale, input[]  (country: parameters geo_id and geo_name of the rule default-user.region)
  accounts: [Account(name, display_name, group, description, password)]
  rules: dict[id, RuleState(enabled, params: dict)]
  unknown: dict
Resolver(catalog)
  disable(profile, id) -> list[Change]
  enable(profile, id)  -> list[Change]
  set_group(profile, group_id, enabled) -> list[Change]
  apply_order(enabled_ids) -> list[id]    phase, file, topological sort by requires
Renderer(catalog, templates)
  build(profile) -> BuildResult(xml_text, scripts: dict[name, text], rule_ids: list)
Validator
  catalog(catalog) -> list[Issue]
  profile(profile, catalog) -> list[Issue]
  xml(text) -> list[Issue]
```

## 4. Portable paths

```python
# core/paths.py
import sys
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class AppPaths:
    root: Path      # exe folder (build) or WinKickOff/ (sources)
    data: Path      # rules/, templates/, resources/ (in the build: root/_internal)
    profiles: Path
    output: Path
    logs: Path

def app_paths() -> AppPaths:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        data = Path(getattr(sys, "_MEIPASS", root / "_internal"))
    else:
        root = Path(__file__).resolve().parents[2]
        data = root
    paths = AppPaths(root, data, root / "profiles", root / "output", root / "logs")
    for p in (paths.profiles, paths.output, paths.logs):
        p.mkdir(parents=True, exist_ok=True)
    return paths
```

The rules are the same as in 0.1: no `os.getcwd()`, `%APPDATA%`, `%TEMP%`; temporary files go to
`logs/tmp/`; `settings.json` next to the exe.

## 5. Data flow

```
rules/*.toml ──> Catalog ──┬──> Validator.catalog
                           ├──> Resolver
profiles/*.json ──> Profile┴──> Renderer ──> XML + scripts ──> Validator.xml ──> file
templates/* ───────────────────────┘                 └──> pscheck (optional)
```

1. Startup: loading the catalog and integrity verification; on error, a window with a message and exit.
2. Profile: from a preset or a file; unknown rules go to `unknown`, new ones get `default`.
3. The tree is built by groups; states come from the profile; search filters using a string index built
   when the catalog is loaded (identifier, title, tags, summary, action strings).
4. Check box change: `Resolver.disable/enable` → list of changes → update of the tree nodes and
   the status bar; the profile is marked as modified.
5. Build: `Validator.profile` → stop on errors; `Renderer.build` → `Validator.xml` →
   `pscheck` (background) → writing the file.

## 6. Generator

Rule order: `Resolver.apply_order` returns the enabled rules sorted by phase,
then by position in the catalog, with a stable topological correction: a rule never comes before its `requires`.

Build by phase:

| Phase | Where it goes | Infrastructure (included when the phase has rules) |
|---|---|---|
| windowspe | `RunSynchronous` in the Setup component (both architectures) | none |
| specialize-xml | `RunSynchronous` in Deployment, after the extraction command, before the script is run | script extraction and running `Setup-System.ps1` (always, if there are specialize or default-user rules) |
| specialize | blocks in `Setup-System.ps1` | runtime: functions, trap, log |
| default-user | blocks inside `reg load`/`reg unload` of the hive in `Setup-System.ps1` | hive mounting |
| user-first-logon | blocks in `Setup-User.ps1` | Active Setup registration in `Setup-System.ps1` |
| post-oobe | blocks in `Post-OOBE.ps1` | scheduled task from `Setup-System.ps1`; waiting for OOBE in the runtime |
| oobe-xml | `OOBE` and International-Core elements, accounts | none |

Converting actions to PowerShell (phases specialize, default-user, user-first-logon, post-oobe):

| Type | Line |
|---|---|
| reg | `Set-Reg -Path '<path>' -Name '<name>' -Type <kind> -Value <value> -Why '<why>'` (for `DU:` the path goes through `$du`) |
| reg-remove | `Remove-Reg -Path '<path>' -Name '<name>'` |
| service | `Set-ServiceStart -Name '<name>' -Start <n>` |
| exe | `Invoke-Exe '<file>' @('<arg>', ...)` |
| feature | `Set-Feature -Name '<name>' -State <Enabled|Disabled>` (wrapper around DISM in the runtime) |
| capability | `Remove-Capability -Pattern '<pattern>'` |
| appx | `Remove-Apps @('<name>', ...)` |
| ps | text as is, indented |

Each block starts with the line `# [<rule.id>]` (without the title: everything the generator writes is ASCII only,
and the rule title is visible in the editor by its identifier); parameter values are substituted by name
`{param}` with type conversion. Strings are escaped for PowerShell (single quotes are doubled).

XML actions: `xml-pe-command` and `xml-specialize-command` add a `RunSynchronousCommand` with
sequential `Order`; `xml-oobe` adds an element with a name and a value to the `OOBE` block. Profile
data (key, time zone, languages, accounts) is substituted into fixed slots.

The profile is embedded in `Extensions/Profile` as JSON inside CDATA. The validator computes `Path` lengths
on the unpacked text.

## 7. Dependency resolver

- `required_by` is built once at load time (reverse index of `requires`).
- `disable(id)`: breadth-first traversal over `required_by`, disabling each enabled rule; result:
  `[Change(id, enabled=False, reason="requires <id>")]`.
- `enable(id)`: traversal over `requires`, enabling; then, for each enabled rule, disabling
  its `conflicts` with traversal over `required_by`.
- Group: sequential application to the rules of the group; the changes are merged.
- All operations are pure with respect to the catalog and change only the profile.

## 8. Interface

- A horizontal `ttk.PanedWindow`: on the left a `Frame` with the search field and a `ttk.Treeview` (a single column
  `#0` with a check box image before the title, `ui/checkimages.py`: on, off, partial for a group); on the right
  a `Frame` with a scrollable `Text` (description) and a parameter panel; at the bottom a `ttk.Treeview` of messages.
- A click on the check box image, or Space: toggling through the resolver; the changed nodes
  are redrawn; the status bar shows the number of cascade changes, a click expands the list.
- Search: on input (with a 150 ms delay) the tree is rebuilt from the filtered list;
  an empty query restores the full tree, preserving the expansion state.
- The description is built from the rule data and the action table; the "Reference entry" link under "More details" opens
  the reference card (`os.startfile`) if the file is in the build.
- Parameters: widgets by type (Spinbox, Combobox, Entry) below the description; a change goes straight into the profile.
- Data nodes: "Installation: edition, key, time zone", "Accounts", "Languages and region" open forms in the right panel.
- DPI: `SetProcessDpiAwareness(1)` before Tk is created; theme `vista`.

## 9. Build

PyInstaller onedir, `--noconsole`, data `rules`, `templates`, `resources`, `profiles`, and
`docs/technical/reference` and `docs/user` from the repository root for the "More details" links. Output: `dist/WinKickOff/`.
