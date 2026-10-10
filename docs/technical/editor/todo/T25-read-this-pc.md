# T25. Read the settings of this PC into a profile

Status: done in code (10.10.2026), version 1.4.0-rc.1; acceptance in a VM pending.
Stage 10. Dependencies: T15 (audit), T22 (MCP), T24.

## Goal

The customer's request of 10.10.2026: a menu command that reads the state of the settings of the running computer
into a profile, to clone a reference PC and to let an agent study damaged or infected systems. Through MCP the read is
protected by a separate option, "read the settings of the current PC". Version 1.4.0.

## Result

- `core/capture.py`: `render_capture` is the read-only audit (`apply.render_audit` with `read_system`) of every rule a
  running Windows can show (`capture_rules`, built-in and imported) plus the data forms
  (`templates/section-read-system.ps1`: edition, time zone, computer name, languages, local accounts and their groups;
  no passwords or keys). `capture_profile` turns its report into a copy of the open profile: in effect is on with the
  parameter values read (`read_rule`: a parameter written whole by a `reg` action, `"{seconds}"`, takes the value
  found when it is a valid value of its type and range), partly in effect is off and listed, not in effect is off, not
  readable and the rules no running Windows shows keep their state; an imported policy that an enabled built-in rule
  writes stays off; the edition (`EDITION_IDS`), time zone, locales, input languages (`_input_items`: tags when the
  layout is the first of the tag, else the pair; the transient 2000 ids become their tags) and accounts (with an
  administrator) are taken; the computer name never is. `summary_lines` lists the result for the message list.
- Window: "This PC", "Read the settings of this PC into a new profile..." (`MainWindow.read_this_pc`, a background
  thread with `apply.run_audit`, never elevated); the result opens unsaved (`adopt_profile`).
- MCP: the tool `read_this_pc` (mode read) with the option `read_pc` (`McpService.read_pc`, the MCP menu item "Allow
  reading the settings of this PC", `--read-pc` of the headless server, `ToolContext.read_pc`, `get_status.read_pc`):
  never saved, off at every start, `refused` without it; `load` (mode edit) opens the profile through
  `Workspace.open_profile`; failures are `read_failed`. The result holds the values found, untrusted data.
- Runtime 0.8: `Audit.runtime.ps1` reports `system` and serialises to depth 6. The customer's rule "nothing through
  MCP runs PowerShell" now has this one exception, behind the option.

## Acceptance criteria

- `python -m unittest discover -s tests` is green; the tests never run the read: they build its JSON report
  (`tests/test_capture.py`) and patch `mcp.tools.run_audit`; the script is only parsed by Windows PowerShell 5.1.
- In a VM: the read of a PC installed from the Office preset gives a profile that builds the same rules; a changed
  value (a screen lock of 600 s) comes back as the parameter; without administrator rights the features are not read.

## Open points

- The VM checks above; an elevated read (features, capabilities, the apps of all users) is not offered yet.
- The default user profile is read in the current user's HKCU, as the audit does.
