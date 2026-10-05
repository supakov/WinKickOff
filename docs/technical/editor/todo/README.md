# WinKickOff plan tasks

Revision 0.2 of 25.09.2026 (reworked for the rule model, see `../06-critical-review-v0.1.md`); statuses of 04.10.2026.
One file per task. Statuses: `todo`, `in-progress`, `done`, `blocked`. When a status changes,
update this index and the root `AGENTS.md` (the "Work status" section).

Code: `../../../WinKickOff/`. Tests: `python -m unittest discover -s tests` in the `WinKickOff/` folder (787 tests).

| Task | Title | Stage | Depends on | Status |
|---|---|---|---|---|
| [T01](T01-project-skeleton-and-paths.md) | Project skeleton, portable paths, log, tests | 0 | none | done (skeleton, paths, log, test run) |
| [T02](T02-rules-catalog.md) | Rule catalog: format, loader, integrity, v0.2 transfer, semantic golden | 1 | T01 | done (format, v0.2 transfer, loader, semantic golden) |
| [T03](T03-dependency-resolver.md) | Dependency resolver and application order | 2 | T02 | done (cascade, groups, application order as in v0.2) |
| [T04](T04-profile-and-presets.md) | JSON profile, presets, migration, comparison | 2 | T02 | done (profile, "Office" and "Strict" presets) |
| [T05](T05-runtime-templates.md) | XML and PowerShell runtime templates | 2 | T02 | done (templates with slots, VERSION 0.3) |
| [T06](T06-generator.md) | Generator of scripts and XML from enabled rules | 2 | T03, T04, T05 | done (the "Office" build covers v0.2, validator 36 of 36) |
| [T07](T07-validator.md) | Validator for the catalog, profile and XML | 3 | T06 | done (profile, XML, catalog; bad profiles in tests) |
| [T08](T08-importer-and-pscheck.md) | Profile import from XML and v0.2; PowerShell verification | 3 | T06 | done (embedded profile and v0.2 import by actions, PowerShell verification) |
| [T09](T09-ui-tree-search-details.md) | Tree with check boxes, search, description panel | 4 | T03, T04 | done (tree, search, description with links, verification and rollback for every rule) |
| [T10](T10-ui-params-and-data-forms.md) | Rule parameters, data forms (installation, accounts, languages) | 4 | T09 | done (parameters with change marks, three data forms) |
| [T11](T11-ui-build-and-settings.md) | Build from the window, verification, export, recent files, settings | 4 | T07, T08, T10 | done (build with background verification, recent files, settings.json, portability) |
| [T12](T12-packaging-portability.md) | PyInstaller build and portability verification | 5 | T11 | done (GitHub Actions builds the zip on every push; release 1.0.0-rc.1) |
| [T13](T13-docs-and-agents.md) | User documentation, AGENTS.md, acceptance | 5 | T12 | blocked (documentation done; acceptance needs a VM of the customer) |
| [T14](T14-localization-and-diff.md) | uk localization, profile comparison, "Laptop" preset | 6 | T13 | done (uk and en interface, language menu, profile comparison, Laptop preset) |
| [T15](T15-apply-to-running-system.md) | Applying the selected rule or branch to a running Windows: audit, application, rollback, return to Windows defaults | 6 | T06, T08, T11 | blocked (implemented and tested; acceptance needs a VM) |
| [T16](T16-docs-split-technical-user.md) | Documentation split: technical in English, user documentation in Ukrainian, English, Russian | 5 | T17 | done (technical docs in English, user docs in ru, uk, en, generated rule lists) |
| [T17](T17-repo-toolkit-and-appendices.md) | Repository root as a toolkit, with WinKickOff as the first one; XML of v0.2 in documentation appendices | 5 | none | done (root as a toolkit, XML and the critic's report in `docs/appendices/`) |
| [T18](T18-english-source-languages-themes.md) | English source language; languages and colour themes as files | 6 | T14 | done (English code and catalog, ru and uk files, Light, Dark, Latte, Matrix, as in Windows) |
| [T19](T19-admx-import.md) | Import of policy templates (ADMX, ADML) as a subtree of selectable rules | 7 | T18 | done (1.1.0-rc.1: menu ADMX, store admx/, rules, links to built-in rules; 1.1.0-rc.2: list and multiText elements) |
| [T20](T20-navigation-and-shared-imports.md) | Back and Forward; rename, update and shared policies of imported templates | 7 | T19 | done (1.1.0-rc.3) |
| [T21](T21-linked-built-in-rules.md) | Imported policies follow the built-in rules that set the same values | 7 | T20 | done (1.1.0-rc.4) |
| [T22](T22-mcp-server.md) | MCP server inside the editor: stdio and HTTP, read-only by default | 8 | T21 | done in code (30.09.2026, 1.2.0-rc.1; 43 findings of an adversarial review fixed 01.10.2026); acceptance with real clients in a VM pending |
| [T23](T23-catalog-json.md) | Catalog in JSON; catalog files of imported templates: export, import, catalogs of the program | 9 | T19, T20 | done in code (04.10.2026, 1.3.0-rc.1); catalogs of the program wait for the license check |

Rules for the implementer of any task:

1. Change nothing on the customer's work PC; tests only in temporary folders, acceptance in a VM.
2. No em dashes or en dashes in code, data, strings and documents.
3. Only the Python standard library in the application; tests with `unittest`.
4. After a task, update its file, this index and `AGENTS.md`; commit and push.
5. Tests stay invisible on the customer's screen: a test module that opens a window imports `tests/quiet_tk.py`
   first (`../04-testing.md`, `AGENTS.md` section 4, rule 12).
