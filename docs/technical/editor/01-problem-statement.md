# 01. Specification: WinKickOff, a Windows installation configuration editor

Revision 0.2 of 25.09.2026 (replaces 0.1; the changes are justified in `06-critical-review-v0.1.md`).
Basis: answer file v0.2 and the reference `docs/technical/reference/`.

## 1. Goal

Give the administrator of a small organization a tool that:

1. shows all Windows 11 Pro configuration rules in a single tree with check boxes, search and a description
   of each rule, including technical details (registry keys, values, commands);
2. lets you disable any rule; the rules that depend on it are disabled automatically, and this is visible;
3. stores the selected set as a JSON profile;
4. builds from the profile an `autounattend.xml` that contains only what is selected;
5. checks the result, before it is written to media, against the rules whose violation stops Windows Setup;
6. runs from a flash drive on any Windows PC without installation and without administrator rights.

Outcome: changing the organization's policy means editing a profile in the tree, not editing PowerShell code;
the v0.2 file becomes a profile (the base of "Office") rather than the only template.

## 2. Users and scenarios

| Role | Who | Scenario |
|---|---|---|
| Organization administrator | An employee with basic Windows skills, no PowerShell | Opens the "Office" profile, disables "SMB signing required (server and client)" because of an old multifunction printer, sees that nothing dependent was disabled, builds the XML, copies it to a flash drive |
| Technical specialist | Serves several organizations | Maintains profiles per site, searches for the word "NetBIOS", compares profiles, updates the rule catalog when a new version is released |
| Catalog author (this project) | Maintains the rules and the runtime | Adds a rule to a TOML file; tests confirm catalog integrity and v0.2 coverage |

Scenarios:

1. New profile from the "Office" preset (the catalog defaults: v0.2 with the later changes) or from "Strict".
2. Find a rule by any word (title, tag, registry key), disable it with one click, see
   in the status bar what was disabled along with it.
3. Change a rule parameter (for example, minutes until lock) in the description panel.
4. Edit accounts, input languages, time zone, edition and key: nodes of the same tree.
5. Check the profile: a list of problems at the bottom, a double click leads to the rule.
6. Build the XML into `output/` or onto a flash drive; open the folder.
7. Import a profile from a previously built XML (the profile is embedded in the file) or from the v0.2 file.
8. Compare two profiles: a list of differences in rules and parameters.

## 3. Functional requirements

### 3.1 Rule catalog

- A rule is the unit of inclusion. Each action of the v0.2 file belongs to exactly one rule.
  Rules are described in external files `rules/*.toml`; the code contains no rules.
- A rule has: an identifier, a group in the tree, an application phase, a title, a level (baseline,
  recommended, optional, risky), a default state, dependencies `requires`,
  conflicts `conflicts`, tags, parameters with types and ranges, a list of actions, a description
  (summary, effect, risk, Windows versions, verification, rollback, link to the reference).
- Action types: registry value (set, remove), service startup type, running a utility,
  Windows feature (enable, disable), capability (remove), Appx apps (remove),
  a PowerShell fragment for complex cases, an XML command in windowsPE or specialize, an OOBE element.
- Phases: windowspe, specialize-xml, specialize, default-user, user-first-logon, post-oobe, oobe-xml.
- The catalog is consistent: identifiers are unique, `requires` and `conflicts` point to existing
  rules, there are no cycles, groups exist, each action has a valid type and the required fields,
  each rule has a summary, an effect and a reference link. This is verified by a test and by the "Check rule catalog" command.
- Coverage: with the v0.2 reference profile (the catalog defaults with the differences listed in
  `tests/v02_actions.py`), the set of catalog actions includes every action of the v0.2 file with the same
  values (semantic golden).

### 3.2 Dependencies

- Disabling a rule transitively disables all rules that have it in `requires`.
- Enabling a rule transitively enables all its `requires` and disables its `conflicts`.
- A group operation (group check box) applies the same to each rule of the group.
- Each operation returns a list of changed rules with the reason; the interface shows it immediately.
- Phase infrastructure (Active Setup registration, the Post-OOBE task, mounting the default user profile
  hive, extracting the scripts) is included by the generator automatically when the phase has rules
  and is not a rule.

### 3.3 JSON profile

- One file per profile, UTF-8, indent 2, Cyrillic without escaping, keys in a stable order.
- Contains: format version, catalog version, name, author, dates, comment; installation data
  (edition, key mode, key, time zone); languages (display language, formats, region, input list);
  accounts; the state of each rule (enabled or not) and parameter values.
- Loading a profile from an older catalog version: new rules get their default state,
  rules missing from the catalog are kept in the `unknown` section with a warning.
- Presets are files `profiles/preset-*.json`, not code.

### 3.4 Generation

- The runtime (functions, error handling, hive mounting, waiting for OOBE) is stored in
  `templates/` and is not changed by the profile.
- Scripts and XML are assembled only from enabled rules in the order: phase, catalog file, rule,
  with a topological correction by `requires`. Each block is marked with the rule identifier.
- The profile is embedded in the XML (section `Extensions/Profile`, JSON) for later import.
- Generation is deterministic: the same profile yields the same bytes.
- The output is UTF-8 without BOM, CRLF.

### 3.5 Validation

| Verification | Level | Response |
|---|---|---|
| Catalog integrity (see 3.1) | catalog | Error at startup, the interface shows the reason |
| The length of each `Path` is at most 259 characters | XML | Error, the build is blocked |
| No comments inside `<component>` | XML | Error |
| All four International-Core values are set | XML | Error |
| InputLocale format `LLLL:KKKKKKKK` | profile | Error |
| Account names are unique, not reserved, contain no forbidden characters, up to 20 characters | profile | Error |
| At least one account in Administrators (account mode "file") | profile | Error |
| Account mode "ask": the accounts of the form are not written, Windows Setup asks for one administrator | profile | Information |
| An unknown account mode | profile | Error |
| Parameter out of range | profile | Error |
| A rule of the "risky" level is enabled | profile | Warning with the risk text |
| A password is set | profile | Warning (plain text in the XML) |
| `UILanguage` does not match the ISO language | profile | Not checked: the editor does not see the ISO. The "Languages and region" form explains that the value equals the ISO language (decision of 25.09.2026) |
| A rule of the "baseline" level is disabled | profile | Warning |
| Syntax of the built scripts under PowerShell 5.1 | XML | Error (via `powershell.exe` if available; otherwise skipped with a note) |

### 3.6 Interface

- One window, three areas: tree (left), description and parameter panel (right), messages (bottom).
- Tree: groups and rules with check boxes in the nodes; clicking a check box or pressing Space toggles it; a group
  check box toggles the group; a partially enabled group is marked with a special sign; data nodes
  (Installation, Accounts, Languages) are in the same tree.
- Search: a field above the tree, filtering by identifier, title, tags, summary and action contents
  (registry keys, service names, commands); matches are expanded, the rest is hidden; Ctrl+F.
- Description panel: title, state, level, phase, summary, action table (built automatically
  from the data), effect, risk, Windows versions, dependencies (requires, required by, conflicts with),
  verification, rollback, reference link; the rule's parameters are edited right here.
- Status bar: the result of the last operation ("Disabled rules: 1; 3 more changed automatically outside the
  selection (list below)"); the list of messages gives the reasons.
- Menus: File (new from preset, open, save, save as, import from XML, recent),
  Profile (compare, reset group to preset), Build (check, build, open folder),
  Help (about, reference, check catalog).
- Hotkeys: Ctrl+F search, Space toggle, Ctrl+S save, F7 check, F9 build.
- Interface languages: Russian, Ukrainian (translations in external files).

## 4. Non-functional requirements

| Requirement | Value |
|---|---|
| Platform | Windows 10 1809+ and Windows 11, x64 |
| Language and libraries | Python 3.14; only the standard library in the application (tkinter, ttk, tomllib, json, xml.etree, logging); third-party packages only for the build (PyInstaller) |
| Tests | `unittest` from the standard library, run with `python -m unittest`; compatible with pytest |
| Portability | The folder can be copied anywhere; no writes to the registry, `%APPDATA%`, `%PROGRAMDATA%`; paths are relative to the executable's folder |
| Privileges | No administrator rights |
| Launch | One exe plus the `_internal` folder (onedir); startup within 2 seconds; the rule catalog is read at startup (up to 200 rules in 0.2 s) |
| Size | Up to 40 MB |
| Offline operation | No internet access; the optional MCP server (1.2) listens on 127.0.0.1 only, when the user starts it |
| Encodings | UTF-8; XML without BOM, CRLF; profiles in UTF-8 |
| Logs | `logs/winkickoff.log`, rotation at 1 MB, three files |
| Errors | Clear text for the user, stack trace to the log; the application does not crash because of a bad profile or rule |
| Quality | Type annotations; `ruff` and `mypy --strict` for `core` in a VM or on the developer's machine, not necessarily on the customer's work PC |
| Text style | No em or en dashes in any strings, documentation or comments |

## 5. Constraints and assumptions

- Target OS: Windows 11 Pro 24H2 and newer from the official ISO. The rule catalog version 0.2 reproduces
  the v0.2 file; new rules are added as separate tasks.
- Disk partitioning is not specified (a project decision): the installer asks for the disk.
- Passwords are in plain text in the XML (a format limitation); the editor warns about this.
- The editor does not run the installation and does not check the ISO.
- Applying rules to an already installed Windows (task T15) is done by a separate PowerShell process
  on an explicit user action and a UAC prompt; the editor itself stays without administrator rights.
- Windows only.
- No tests or runs change the state of the machine: they read project files and write only
  inside the application folder or the tests' `tmp_path`.

## 6. Acceptance criteria

1. The rule catalog passes the integrity verification; semantic golden: each v0.2 action
   is present in the catalog with the same value under the v0.2 reference profile.
2. Disabling any rule in the interface disables all dependent rules; enabling one enables the required ones;
   tests on the resolver and a UI smoke test.
3. A file built from the "Office" preset passes `tools/Validate-Unattend.ps1` and contains exactly
   the enabled rules (by the identifiers in the block comments).
4. A file built from a profile with half of the rules disabled contains none of their actions.
5. Search finds a rule by registry key and by tag; the path "find, disable, build" takes
   no more than 4 user actions.
6. The application starts from a flash drive on a clean Windows 11 without Python and writes nothing outside its folder.
7. An acceptance installation in a VM with a file from the "Office" preset completes without questions, except for disk selection.

## 7. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Errors when transferring 150+ v0.2 actions into the catalog | High | The semantic golden compares the catalog with v0.2 automatically |
| Incomplete or wrong dependencies in the catalog | Medium | Dependency overview in the description panel; cycle test; review of the catalog against the cross-links reference |
| A tree of 100+ rules renders slowly in tkinter | Low | `Treeview` handles thousands of nodes; search filters rather than rebuilds |
| Check boxes in `Treeview` are non-standard | Medium | A proven technique: symbols in the node text and handling clicks on the column; images as an alternative |
| A new Windows version changes unattend behavior | Medium | Catalog and runtime versions are separate from the application; acceptance test for each release |
| PyInstaller lags behind Python 3.14 | Medium | Building on 3.13 without code changes as a fallback |
| Defender/SmartScreen blocks the unsigned exe | Medium | Instructions; signing if a certificate is available |
