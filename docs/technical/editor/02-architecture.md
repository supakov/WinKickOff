# 02. WinKickOff architecture

Revision 0.2 of 25.09.2026, updated 04.10.2026 (T23: the catalog in JSON, catalog files).

## 1. Principles

1. The rule catalog (`rules/*.json`) is the single source of truth about what the installation
   can do. The interface, generator, validator, descriptions and tests read it; the code contains no rules.
2. The runtime is separate from the rules: immutable PowerShell and XML fragments live in `templates/`.
3. Logic without the interface: `core/` does not import tkinter and is tested with `unittest`.
4. A single path function `app_paths()`; nobody builds paths on their own.
5. No dependencies outside the standard library in the application itself.
6. Any data error (rule, profile, template, catalog file, saved import of templates) turns into a message naming the
   file and the identifier; the application does not crash. Imported templates and catalog files are untrusted input:
   they are read with limits of size, memory and nesting, every record is checked, and nothing of them runs.

## 2. Structure of the `WinKickOff/` directory

```
WinKickOff/
  README.md                  how to run from sources, tests, build
  pyproject.toml             metadata, requires-python >= 3.14, ruff/mypy settings
  winkickoff/
    __init__.py              APP_VERSION
    __main__.py              python -m winkickoff; dispatcher: --mcp, --mcp-config and --version run without tkinter
    app.py                   startup: paths, log, catalog, saved imports of templates, window
    core/
      paths.py               AppPaths, app_paths()
      log.py                 logging to logs/
      catalog.py             Rule, Action, Group, Param models; loading of the JSON files with known fields only;
                             integrity verification
      jsonfile.py            strict JSON reading (no duplicate keys, null, NaN, numbers too large, lone surrogates,
                             deep nesting, more than 1 000 000 values, BOM), gzip and xz unpacking with size and
                             memory limits, the canonical layout writer
      deps.py                Resolver: enable/disable with cascade, application order
      profile.py             Profile: rule and parameter state, installation data; JSON
      render.py              building scripts and XML from the runtime and the enabled rules
      validate.py            profile and XML verification; Issue
      importer.py            profile from XML (embedded) or from the v0.2 file (action parsing)
      pscheck.py             syntax verification via powershell.exe, if available
      i18n.py                translations: languages found from files, English fallback
      themes.py              colour themes from resources/themes, following the Windows light or dark mode
      admx.py                policy templates (ADMX, ADML) imported into admx/<id>/ and turned into rules; the check
                             of stored records (check_templates), strict reading of saved imports, the trust order
                             of imports (trust_order)
      package.py             catalog files: envelope, export and import of imported templates, the catalogs of the
                             program (bundled_catalogs, import_bundled)
      linked.py              imported policies that follow a built-in rule with the same registry values
      startup.py             the profile a session starts with (shared by the window and the headless MCP server)
    mcp/                     MCP server (task T22, see 07-mcp-server.md): jsonrpc, schema, redact, journal,
                             workspace, bridge, tools, resources, protocol, stdio, httpserver (the only listener,
                             127.0.0.1), service, cli
    mcp_main.py              console entry of WinKickOff-mcp.exe (a stdio server)
    ui/
      main_window.py         window, menus (the ADMX menu with catalog files), three areas, hotkeys; tree with
                             check boxes, search, description, action table, parameter editor, dialogs
      data_forms.py          data node forms: installation, accounts, languages
      checkimages.py         check box images of the tree
      winmenus.py            theme colours around the drop-down menus
      mcp_workspace.py, mcp_window.py   the window as the MCP workspace; the MCP monitor
      clipboard.py           the MCP token kept out of the clipboard history
  rules/
    groups.json              group tree
    NN-<area>.json           rules by area (English, ASCII), file order = application order
    lang/<code>.json         translations of rule strings (ru, uk; a new file adds a language)
  catalogs/
    README.md                catalogs of the program: packages <name>.json of imported templates (none committed yet)
  templates/
    autounattend.template.xml      skeleton with slot markers
    Setup-System.runtime.ps1       functions, trap, header, hive mounting
    Setup-User.runtime.ps1         header and log of the first sign-in script
    Post-OOBE.runtime.ps1          waiting for OOBE, reading the profile, completion
    VERSION                        catalog and runtime version (0.6)
  resources/
    strings.<code>.json                interface translations keyed by the English text (ru, uk)
    themes/<id>.json                   colour themes (light, dark, latte, matrix)
    keyboards.json, timezones.json     reference data
  profiles/
    preset-office.json, preset-strict.json, preset-laptop.json, preset-home.json
  tests/
    test_catalog.py, test_catalog_format.py, test_deps.py, test_profile.py, test_render.py, test_validate.py,
    test_coverage_v02.py (semantic golden), test_package.py, test_ui_smoke.py, ...
    quiet_tk.py              imported first by every test module that opens a window: the windows stay invisible
  tools/
    build.ps1, run-tests.ps1
    format_catalog.py        rewrites the catalog files in the canonical layout (--check only lists them)
    make_browser_rules.py    generates rules/14-browsers.json
    make_shell_rules.py      generates rules/17-shell.json
    make_presets.py, make_rule_docs.py   presets and the rule lists of the user documentation
    make_admx_catalogs.py    makes a catalog of the program from a folder of ADMX templates
    pack_catalogs.py         compresses catalogs/*.json with xz for the portable build
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
    root: Path       # exe folder (build) or WinKickOff/ (sources)
    data: Path       # rules/, templates/, resources/, catalogs/ (in the build: root/_internal)
    docs_root: Path  # docs/technical/reference and docs/user (in the build: data; from sources: the repository root)
    profiles: Path
    output: Path
    logs: Path
    # properties: rules, templates, resources, catalogs (data/...: read only), settings_file and admx (root/...)

def app_paths(*, create: bool = True) -> AppPaths:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        data = Path(getattr(sys, "_MEIPASS", root / "_internal"))
        docs_root = data
    else:
        root = Path(__file__).resolve().parents[2]
        data = root
        docs_root = root.parent
    paths = AppPaths(root, data, docs_root, root / "profiles", root / "output", root / "logs")
    if create:
        for p in (paths.profiles, paths.output, paths.logs):
            p.mkdir(parents=True, exist_ok=True)
    return paths
```

`catalogs` is `data/catalogs` (the catalogs of the program, `03-data-model.md` section 10); `admx` is `root/admx`,
the saved imports of templates, created on the first import next to `settings.json`.

The rules are the same as in 0.1: no `os.getcwd()`, `%APPDATA%`, `%TEMP%`; temporary files go to
`logs/tmp/`; `settings.json` next to the exe.

## 5. Data flow

```
rules/*.json ──> Catalog ──┬──> Validator.catalog
admx/<id>/ ──> with_imports┤
                           ├──> Resolver
profiles/*.json ──> Profile┴──> Renderer ──> XML + scripts ──> Validator.xml ──> file
templates/* ───────────────────────┘                 └──> pscheck (optional)
```

1. Startup: loading the catalog and integrity verification; on error, a window with a message and exit. Then the
   saved imports of templates listed in `settings.json` (`admx/<id>/`) are read, checked and merged into the catalog
   (`admx.with_imports`, in the trust order of `03-data-model.md` section 8); an import that fails the check is left
   out and named in the messages, and the program starts without it.
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
- "Unknown rules and policies": the last root, only while the profile keeps choices in `unknown`: for rules the
  catalog does not have (policies of imported templates that are not loaded, rules of another version) and, since
  1.3.0, choices held back by their `source` because only a less trusted import holds the policy now
  (`03-data-model.md` section 4). Its items show the kept state and parameters, cannot be toggled and offer to show
  the hidden import that has the policy (for a held choice, only an import of its kind or a more trusted one).
- Menu "ADMX": import the templates of this Windows or of a folder, a catalog file or a catalog of the program; show
  or hide, rename, export and delete the saved imports. Templates and catalog files are read in a background thread;
  meanwhile the window is busy, and the commands that would rebuild it (other imports, show or hide, rename, delete,
  language, theme) do nothing. A change of the imports rebuilds the window with the open profile.
- DPI: `SetProcessDpiAwareness(1)` before Tk is created; theme `vista`.

## 9. Build

PyInstaller onedir, `--noconsole`, data `rules`, `templates`, `resources`, `profiles`, and
`docs/technical/reference` and `docs/user` from the repository root for the "More details" links. Output: `dist/WinKickOff/`.
Since 1.3.0 the catalogs of the program (`catalogs/<name>.json`) are written into `_internal/catalogs` compressed
with xz by `tools/pack_catalogs.py`, which `tools/build.ps1` runs after PyInstaller (`03-data-model.md`, section 10);
the rule catalog is copied as it is.
