# T06. Generator of scripts and XML from enabled rules

Status: done (25.09.2026: `Renderer.build`, tests in `test_build.py`: determinism, a disabled rule
leaves no trace, phases without rules have no scripts, match with v0.2, external `Validate-Unattend.ps1`). Stage 2.
Dependencies: T03, T04, T05. Milestone M2. Deviation from the steps: the block marker is `# [id]` without the rule title,
because everything the generator writes is ASCII only.

## Goal

Implement `core/render.py`: a deterministic build of the XML and the three scripts from enabled rules only.

## Steps

1. `render_action(action, params) -> str` for each type (`02-architecture.md`, section 6);
   escaping of PowerShell strings; substitution of `{param}` with type conversion; `DU:` → `$du`.
2. `render_block(rule, state) -> str`: the line `# [id] title` plus the actions, indented.
3. Build by phase via `Resolver.apply_order`; phase infrastructure depending on the presence of rules.
4. XML: windowsPE and specialize commands with `Order`; OOBE elements; International-Core from the profile;
   accounts; key and `WillShowUI` by mode; time zone; header with versions and profile name;
   embedded profile in `Extensions/Profile`.
5. `build(profile) -> BuildResult(xml, scripts, rule_ids, warnings)`; CRLF, no BOM.
6. `tests/test_render.py` per `04-testing.md`; the build of the «Офис» (Office) preset passes `Validate-Unattend.ps1`
   (external test).

## Acceptance criteria

- A disabled rule is completely absent from the output.
- All `Path` values are no longer than 259; the XML parses; the profile reads back.
- Two calls produce identical bytes.

## Implementer notes
