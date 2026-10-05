# 05. Work plan

Revision 0.2 of 25.09.2026, updated 04.10.2026 (stages 7-9 of the tasks added after the plan, T19-T23).

## 1. Stages

| Stage | Content | Result | Tasks |
|---|---|---|---|
| 0. Skeleton | `WinKickOff/` structure, paths, log, entry point, test infrastructure on `unittest` | Skeleton in the repository, tests run | T01 |
| 1. Catalog | Rule format, groups, full transfer of v0.2 actions into the catalog files `rules/*` (TOML until 1.3.0, JSON since T23), loader and integrity verification, semantic golden | Catalog 0.2 passes integrity and v0.2 coverage | T02 |
| 2. Logic | Dependency resolver, profile and presets, runtime templates, generator | The "Office" preset builds into XML that passes the validator | T03, T04, T05, T06 |
| 3. Verification | Validator, import (embedded profile and v0.2), PowerShell verification | All bad profiles are caught; importing v0.2 yields "Office" | T07, T08 |
| 4. Interface | Tree with check boxes and search, description and parameters panel, data forms, build from the window | The "find, disable, build" path in 4 actions | T09, T10, T11 |
| 5. Release | Root as a toolkit and XML appendices; documentation split (technical in English, user documentation in three languages); build, portability, acceptance in a VM | zip, documentation, acceptance report | T17, T16, T12, T13 |
| 6. Additional | uk localization, profile comparison, "Laptop" preset; applying a rule or branch to a running Windows | As needed | T14, T15 |
| 7. Imported templates | ADMX and ADML import as rules, several imports, links to built-in rules (added after the plan) | Releases 1.1.0-rc.1 to rc.4 | T19, T20, T21 |
| 8. MCP server | stdio and HTTP on 127.0.0.1, read-only by default (added after the plan) | Release 1.2.0-rc.1 | T22 |
| 9. Catalog files | The catalog in JSON instead of TOML; export and import of catalog files of imported templates; catalogs of the program (added after the plan) | Version 1.3.0-rc.1 | T23 |

## 2. Order and dependencies

```
T01 ──> T02 ──┬──> T03 ──┬──> T06 ──┬──> T07 ──> T08 ──┐
              ├──> T04 ──┤          │                   ├──> T11 ──> T12 ──> T13 ──> T14
              └──> T05 ──┘          └──> T09 ──> T10 ───┘
```

- T02 (catalog) blocks everything: without data, neither the resolver nor the interface can be tested at real scale.
- T03, T04, T05 are independent of each other after T02.
- T09 (tree) starts after T03 (resolver) and T04 (profile); T10 after T09.
- T15 (applying to a running system) starts after T11 and does not depend on T12-T14.
- T17 (moving the XML and the new root) does not depend on code and is done before T16, so that translation already happens in the new locations.
- T16 (documentation split) replaces the user documentation part of T13: it is written in three languages from the start.

## 3. Estimate

| Task | Days |
|---|---|
| T01 Skeleton, paths, log, tests | 1 |
| T02 Rule catalog: format, loader, integrity, full transfer of v0.2, golden | 4 |
| T03 Dependency resolver and application order | 1.5 |
| T04 Profile, presets, migration, comparison | 1.5 |
| T05 Runtime templates (XML skeleton, three PowerShell runtimes) | 1.5 |
| T06 Generator | 2.5 |
| T07 Validator | 2 |
| T08 Import and PowerShell verification | 1.5 |
| T09 Tree, check boxes, search, description panel | 3 |
| T10 Parameters, data forms (installation, accounts, languages) | 2.5 |
| T11 Build from the window, verification, export, recent files, settings | 2 |
| T12 PyInstaller build and portability | 1.5 |
| T13 Documentation and AGENTS.md, acceptance | 1.5 |
| T14 Localization, profile comparison, "Laptop" preset | 2 |
| T15 Applying to a running Windows: audit, application, rollback | 4 |
| T16 Documentation split, translation of the technical documentation into English, user documentation in three languages | 6 |
| T17 Root as a toolkit, XML in documentation appendices | 1 |
| Total | 39 |

Reserve 20 %. About 10 weeks at half-time workload.

## 4. Definition of done for a task

1. Code and data are written; `python -m unittest discover -s tests` is green.
2. The catalog integrity verification and the semantic golden pass (for T02 and all subsequent tasks).
3. The task file in `todo/` is updated: status, date, deviations.
4. `AGENTS.md` is updated if the structure, commands or state have changed.
5. No em dashes or en dashes in code, data and documents.
6. Nothing was run on the customer's work PC except reading and tests in temporary folders.

## 5. Milestones

| Milestone | Criterion | Target |
|---|---|---|
| M1 "Catalog" | T01, T02: catalog 0.2 passes integrity and v0.2 coverage | week 2 |
| M2 "Generator" | T03-T06: the "Office" preset builds and passes `Validate-Unattend.ps1` | week 3 |
| M3 "Verification" | T07, T08 | week 4 |
| M4 "Interface" | T09-T11: full cycle through the window | week 6 |
| M5 "Release 1.0" | T12, T13: zip, checklists, acceptance in a VM | week 7 |
