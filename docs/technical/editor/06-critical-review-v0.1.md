# 06. Critical review of draft 0.1 and the move to the rule model

Date: 25.09.2026. Subject: documents 01-05 in revision 0.1 (morning of 25.09.2026) against the
customer's refined requirements: disabling any rule through the interface, with all dependent rules
deactivated; building the file only from what is selected; a settings tree with fast search and a
minimum of clicks; a description of every option with technical details; data in external files.

Conclusion: draft 0.1 is not worked out thoroughly enough. It repeats the structure of the v0.2 file
(a monolithic script with a `$Config` block) and provides none of the four properties in full.
Documents 01-05 have been rewritten in revision 0.2; below is the list of flaws and the decisions taken.

## 1. "Disable any rule": the `$Config` model does not allow it

Facts about the v0.2 file (counted in the text of `Setup-System.ps1`):

| What | How many |
|---|---|
| `$Config` keys (switches) | 45 |
| `Set-Reg` calls | 124 |
| `Remove-Reg`, `Set-ServiceStart`, `Invoke-Exe` calls | 12, 5, 12 |
| Top-level calls, without any condition | 47 |

47 actions (the baseline values for UAC, LSA, WDigest, SEHOP, NLA, Defender notifications, SmartScreen,
Edge policies, `LongPathsEnabled`, `RetailDemo`, `BlockAADWorkplaceJoin`, the whole baseline set of the
default profile, Active Setup registration, the Post-OOBE task) always run. A `$Config` switch covers
a group of actions as a whole: you cannot keep `RequireSMBSigning` for the server but drop it for the
client; you cannot disable one Edge policy out of nine.

Decision: the unit of configuration is the rule, not a `$Config` key. Each rule has its own list of
actions and can be disabled. Everything that was unconditional in v0.2 becomes rules of the "baseline"
level, enabled by default. In this model the v0.2 file is one of the profiles (the "Office"
preset), not a code template.

## 2. Dependencies: 0.1 has only visibility, no cascade

The `depends` field in the 0.1 schema controlled widget availability. The customer's requirement is
different: disabling rule A must disable all rules that are meaningless or dangerous without A. Examples
from v0.2 where such links exist but are not recorded anywhere:

- 17 ASR rules require the ASR mechanism to be enabled; three of them require Defender cloud protection;
- PowerShell logging requires an enlarged log, otherwise it is useless after a week;
- deferring feature updates requires that DiagTrack is not disabled;
- the first sign-in script requires Active Setup registration; rules of the post-oobe phase require the scheduled task;
- `PasswordNeverExpires` requires the starter accounts to exist;
- "Remove Quick Assist" and "Remote Assistance turned off" are logically paired but independent.

Decision: a rule has the fields `requires` (hard dependencies) and `conflicts` (mutually exclusive).
Resolver: disabling a rule cascades to disable every rule that requires it (transitively); enabling
cascades to enable the required ones; enabling disables the conflicting ones. Each operation returns
the list of affected rules, and the interface shows it immediately, without a dialog. The phase
mechanics (Active Setup, the Post-OOBE task, mounting the default profile hive) are not rules but
infrastructure: the generator includes it automatically if the phase has at least one enabled rule.

## 3. Generation: what is disabled must disappear from the file

In 0.1 the generator substituted values into a fixed script; a disabled switch left an
`if ($Config.X) { ... }` block with dead code in the file. The customer asks for "generation that
respects the selection": the file must contain only what is selected. This is shorter (less chance of
hitting Setup limits), auditable (the script shows what was applied), and safer (no code that could
"accidentally" turn on).

Decision: the scripts are assembled from an immutable "runtime" (the functions `Write-Log`, `Set-Reg`, `Invoke-Exe`,
`trap`, hive mounting) and the blocks of enabled rules, by phase, in the order defined by the catalog and
the dependencies. Each block is marked with the rule identifier: the setup log and the script read as a
list of rules.

## 4. Interface: tabs and forms mean many clicks and no overview

In 0.1: a group tree on the left, a `Notebook` with a form on the right, dialogs for tables. To find and
disable a single policy, you need to know the group, open a tab, find the field, open the hint. There is no search.

Decision: one window, three areas. On the left, a tree of all rules with check boxes directly in the
nodes (group → rule), toggled with one click or the space bar; a group check box toggles the whole group.
Above the tree, a search field: filtering by identifier, title, tags, description text and even by registry keys
("PUAProtection" finds the rule); results are expanded, the rest is hidden. On the right, the
description panel of the selected node, which is also where the rule parameters are edited (number, list, string).
At the bottom, a status bar with the last cascade ("Disabled rules: 1; 3 more changed automatically outside the
selection (list below)"). Data that are not rules (accounts, languages, key, time zone) are nodes of the same tree
with a form in the right panel.
Zero modal dialogs in the main loop.

## 5. Descriptions: a one-sentence hint is not enough

In 0.1 a parameter has a one-sentence `hint` and a link to the Markdown reference. The customer asks for
a technical description of every option in the tool itself.

Decision: a rule description consists of two parts. The manual part in the rule file: a short summary,
effect, risk and side effects, differences between Windows versions, verification command, rollback method, link
to the reference card. The automatic part is built from the list of actions: a table "registry key,
name, type, value", or "service, start type", or "command, arguments". This way the technical details
never diverge from what actually goes into the file.

## 6. Data: JSON is inconvenient for rules, TOML is in the standard library

Rules contain multi-line descriptions, author comments, backslashes in paths. In JSON this
turns into unreadable strings with escaping. Python 3.11+ reads TOML with the standard module
`tomllib` without dependencies; TOML literal strings (`'HKLM:\SOFTWARE\...'`) need no escaping,
and multi-line literals keep PowerShell fragments as they are.

Decision: the rule catalog in `rules/*.toml` (one file per area; the order within the file sets the
application order within a phase), tree groups in `rules/groups.toml`, translations in `rules/lang/uk.toml`.
Profiles written by the program are in JSON (the standard library has no TOML writer).
The keyboard layout and time zone reference data are in JSON, as planned.

## 7. A byte-for-byte golden test hinders rather than helps

A byte-for-byte match with v0.2 would lock in the script structure we are abandoning.

Decision: a semantic golden. The set of actions is extracted from the v0.2 file by parsing `Set-Reg`, `Remove-Reg`, `Set-ServiceStart`,
`Invoke-Exe`; the test requires that the rule catalog with the "Office" profile
yields a superset of these actions (every v0.2 action is present, with the same value). Second
level: the built file passes `tools/Validate-Unattend.ps1` and PowerShell 5.1 parsing. Third:
an acceptance installation in a VM. Bytes are compared only inside the generator (determinism:
two runs on the same profile produce the same file).

## 8. The application order was not modelled

In v0.2 the order matters in places: removing the blocking update policies before setting new ones;
`RunAsPPL` after the verifications; the default profile hive is mounted once; `.NET 3.5` first,
while the media is still connected. In 0.1 the order was determined by the order of the schema parameters, which is unrelated to the order of actions.

Decision: phases with a fixed order (windowspe, specialize-xml, specialize, default-user,
user-first-logon, post-oobe, oobe-xml); within a phase, the order of files and rules in the catalog, with
a stable topological sort by `requires` on top of it (the required rule before the requiring one).

## 9. Other

- Presets were code (`presets.py`): they become `profiles/preset-*.json` files.
- Import by parsing the `$Config` block from PowerShell is fragile: the generator embeds the JSON profile in the XML
  (the `Extensions/Profile` section), and import reads it back without parsing code. A v0.2 file without such a
  section is imported by parsing actions, with the same code as the semantic golden.
- Verification: `pytest` is absent on the machine and must not be installed on the work PC; tests are written with
  `unittest` from the standard library and are compatible with pytest if it appears in the VM.
- Project name: WinKickOff. The code is in `WinKickOff/` at the repository root; the specification documents stay
  here and reference the code.

## 10. What was kept from 0.1

Portable paths through a single function, separation of logic from tkinter, PyInstaller onedir, no
writes outside the application folder, no internet access, portability and acceptance checklists,
the rule "no changes on the customer's work PC".
