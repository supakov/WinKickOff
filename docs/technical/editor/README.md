# WinKickOff: installation configuration editor. Project documents

Status: specification and plan at revision 0.2 (25.09.2026). Code and rule catalog: `../../../WinKickOff/`.

What it is: a Windows desktop program that shows all Windows 11 Pro installation configuration rules
in a single tree with check boxes and search, lets you disable any rule with automatic
disabling of dependent rules, stores the selection in a JSON profile and builds `autounattend.xml` only from what is selected.

| Document | Contents |
|---|---|
| [01-problem-statement.md](01-problem-statement.md) | Specification: goal, scenarios, requirements for the catalog, dependencies, generation, interface; acceptance criteria; risks |
| [02-architecture.md](02-architecture.md) | Architecture: `WinKickOff/` structure, in-memory model, data flows, per-phase generator, resolver, interface, build |
| [03-data-model.md](03-data-model.md) | Format of TOML rules, groups, translations; JSON profile; reference data; embedded profile in XML |
| [04-testing.md](04-testing.md) | `unittest`, semantic golden against v0.2, per-module tests, checklists |
| [05-plan.md](05-plan.md) | Stages, dependencies, estimate, milestones |
| [06-critical-review-v0.1.md](06-critical-review-v0.1.md) | Why revision 0.1 did not meet the requirements and what was changed |
| [todo/](todo/README.md) | Tasks T01-T17 with statuses |

Technologies fixed by the customer: Python 3.14, tkinter from the standard library, Windows
only, a portable application without installation and without ties to system paths.

Related documents: parameter reference `../reference/` (source of rule descriptions and
of "More details" links), first draft `../../appendices/D-requirements-draft/02-constructor-requirements-draft.md` (historical).
