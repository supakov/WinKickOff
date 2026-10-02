# WinKickOff workflows

Step-by-step recipes for typical requests. Every id and argument below exists in catalog 0.5. Argument examples are
JSON objects passed to the named tool.

## Contents

- [Opening and closing of every task](#opening-and-closing-of-every-task)
- [1. Where do I start](#1-where-do-i-start)
- [2. Explain a rule](#2-explain-a-rule)
- [3. Compare two presets](#3-compare-two-presets)
- [4. What did I change](#4-what-did-i-change)
- [5. Switch telemetry off](#5-switch-telemetry-off)
- [6. Switch Copilot and AI off](#6-switch-copilot-and-ai-off)
- [7. Find rules about a topic](#7-find-rules-about-a-topic)
- [8. Keep an app](#8-keep-an-app)
- [9. Change a parameter](#9-change-a-parameter)
- [10. Prepare a profile for a department](#10-prepare-a-profile-for-a-department)
- [11. Open a preset or a saved profile](#11-open-a-preset-or-a-saved-profile)
- [12. Save the changes](#12-save-the-changes)
- [13. Explain Check errors](#13-explain-check-errors)
- [14. Review an answer file](#14-review-an-answer-file)
- [15. Write the answer file](#15-write-the-answer-file)
- [16. Show what the file does](#16-show-what-the-file-does)
- [17. Which protection is weakened](#17-which-protection-is-weakened)
- [18. A program stopped working after installation](#18-a-program-stopped-working-after-installation)
- [19. BitLocker](#19-bitlocker)
- [20. Passwords, accounts, languages, time zone, key](#20-passwords-accounts-languages-time-zone-key)
- [21. Remote desktop](#21-remote-desktop)
- [22. An imported ADMX policy](#22-an-imported-admx-policy)
- [23. Apply to this PC or check this PC](#23-apply-to-this-pc-or-check-this-pc)

## Opening and closing of every task

Opening:

1. `get_status` `{}`. Note `mode`, `has_window`, `profile.name`, `profile.dirty`, `language`.
2. Use `language` `ru` or `uk` in `list_groups`, `list_rules` and `get_rule` when the person writes Russian or
   Ukrainian.
3. One WinKickOff call at a time.
4. Show rules as the exact `title` plus id: "Minimal telemetry without disabling compatibility assessment
   (`privacy.telemetry-minimal`)".

Before any edit tool:

1. Mode must be `edit` (or `files`). If `get_status` says `read`, ask the person to choose "Read and change the open
   profile" in the "MCP" menu of the WinKickOff window (labels of a Russian or Ukrainian window:
   [decisions.md](decisions.md#window-labels-in-russian-and-ukrainian)). For a server without a window (`has_window`
   false, always in Claude Desktop): the person puts `"--mode", "edit"` (or `"--mode", "files"` for `save_profile`
   and `write_answer_file`) into `args` of the WinKickOff entry in the client configuration, adding it when absent or
   replacing `--mode read`, then restarts the client. This mode stays in the configuration for every later session
   (in the window every start is `read`): at the end of the task, remind the person to set `--mode read` back and
   restart the client.
2. Tell the exact change, wait for yes.

Closing after a change:

- The change is unsaved. The person saves it in the window ("Save profile", Ctrl+S, or "Save profile as..."), or you
  call `save_profile` in mode `files` after agreeing on a name.
- The final file is built in the window with "Build autounattend.xml..." (F9), the only way with the PowerShell
  syntax check.
- The file is installed in a virtual machine first.

## 1. Where do I start

1. `get_status` `{}`.
2. `list_profiles` `{}`.
3. `list_groups` `{"language": "uk"}`.
4. Optional: read `winkickoff://docs/user/uk/quick-start.md`.

Tell: the current mode and what it allows; only the person raises the mode; the four presets with Office as the
recommended start; the path: preset, rules, data forms, Check, Build, USB stick, test in a VM.

## 2. Explain a rule

1. Without an id: `list_rules` `{"query": "smartscreen", "language": "ru", "limit": 20}`.
2. `get_rule` `{"id": "defender.smartscreen-shell", "language": "ru"}`.
3. On `unknown_id`: look at `suggestions`, then search again with another word.
4. For depth: the card from `doc`, for example `winkickoff://docs/reference/07-defender.md` (English).

Tell: what it does technically (`actions`); `effect`; `risk`; Windows `versions`; the level and its meaning; `default`
(the Office state) against `enabled`; parameters with ranges; `requires` and `dependents`; how to verify after
installation (`verify`); how to roll it back (`rollback`). If `imported` is true: the text is unreviewed; prefer the
built-in rule from `linked` or `same_values`.

## 3. Compare two presets

Example: "What does Strict change compared with Office?"

1. `get_status`: if the open profile is `Office` and `dirty` is false, call `diff_profile` `{"name": "strict"}`.
   `before` is Office (open), `after` is Strict.
2. Otherwise do not load anything (that would touch the person's work): call `diff_profile` `{"name": "strict"}` and
   take the Office value of each key from the rule's `default` in `get_rule` (Office equals the catalog defaults).
   Keys where the open profile already equals Strict do not appear; the expected list below fills the gap.
3. `get_rule` with `language` on each differing id to get `risk`.

Expected for Strict: rules on `update.other-microsoft-products`, `asr.usb-untrusted`, `uac.admin-always-notify`,
`network.netbios-off`, `scripts.remove-vbscript`; parameters `defender.controlled-folder-access` `mode` 1 (Block),
`defender.smartscreen-shell` `level` `"Block"`, `asr.prevalence` `mode` 1 (Block).

Tell: Strict may break older programs; try it on one PC first.

## 4. What did I change

1. `get_profile` `{}`: `changed_from_defaults` lists the ids that differ from Office.
2. `diff_profile` `{"name": "office"}` for the values.
3. `get_rule` on unusual ids.

Tell: a grouped list (switched on, switched off, parameters, data form differences). Flag baseline rules that are off
and risky rules that are on.

## 5. Switch telemetry off

1. `list_rules` `{"group": "privacy.telemetry", "language": "uk", "limit": 40}`.
2. `list_rules` `{"query": "telemetry", "language": "uk", "limit": 40}`.
3. Related rules outside that group: `oobe.protect-your-pc`, `edge.diagnostic-data-off`, `edge.search-telemetry-off`,
   `chrome.metrics-off`, `chrome.variations`, `brave.stats-ping-off`, `brave.p3a-off`, `office.telemetry-off`,
   `office.feedback-off`, `apps.remove.feedback-hub`.
4. Show which are already on (in Office all of them are) and which are off.

Confirm: the list of rules to switch on. Then `set_rules` `{"items": [{"id": "office.telemetry-off", "enabled": true}]}`
with the agreed ids. Report `changes` and `refused`. Then `check_profile` `{}`.

Tell: switching an "-off" rule on is what turns telemetry off. Windows 11 Pro cannot go below the "Required" level; the
DiagTrack service stays on Manual on purpose (update compatibility checks and Defender need it).

## 6. Switch Copilot and AI off

1. `list_rules` `{"group": "privacy.ai", "language": "ru", "limit": 40}`.
2. `list_rules` `{"group": "privacy.office", "language": "ru"}`.
3. `list_rules` `{"query": "copilot", "language": "ru", "limit": 40}` (finds Edge rules too).
4. Check also `chrome.genai-off`, `chrome.genai-local-model-off`, `chrome.devtools-genai-off`, `brave.ai-chat-off`,
   `apps.remove.copilot`, `apps.remove.copilot-provider`.
5. Most are on in Office. Off by default, among others: `chrome.lens-overlay-off`, `edge.visual-search-off`,
   `office.download-content-off`.

Confirm the rules to switch on; `set_rules`; `check_profile`.

Tell: Edge AI policies work only together with `edge.signin-off`; Office settings reach only profiles created at or
after installation.

## 7. Find rules about a topic

Example: "every rule about USB drives".

1. `list_rules` `{"query": "usb", "limit": 40}`, then `{"query": "removable", "limit": 40}`, then
   `{"query": "autoplay", "limit": 40}`.
2. With a Russian or Ukrainian word, pass `language` `ru` or `uk` and use one word per query: translated texts match
   only the whole query.
3. Merge the results and drop false positives: search also matches registry paths and group ids (for example
   `privacy.telemetry-minimal` matches "usb" through a task name). Check each hit with `get_rule`.

Expected for USB: `asr.usb-untrusted` (off in Office, on in Strict), `removable.autorun-off`,
`default-user.autoplay-off`, `logging.audit-policy` (audits removable storage).

Tell: copying from a flash drive is never blocked; `asr.usb-untrusted` blocks only running untrusted and unsigned
programs from it.

## 8. Keep an app

Example: "do not remove Microsoft To Do".

1. `list_rules` `{"group": "apps.remove", "language": "uk", "limit": 40}`.
2. Confirm, then `set_rules` `{"items": [{"id": "apps.remove.todo", "enabled": false}]}`.
3. Other common ones: `apps.remove.teams`, `apps.remove.phone-link`, `apps.remove.outlook-new`,
   `apps.remove.mail-calendar`, `apps.remove.onedrive`.

Tell: a rule in `apps.remove` that is on removes the app; off keeps it. Switching `apps.remove.maps` off also switches
off `apps.maps-broker-off` (cascade). `apps.remove.onedrive` affects new profiles only.

## 9. Change a parameter

Examples:

| Request | Call |
|---|---|
| Lock the screen after 5 minutes | `set_param` `{"id": "accounts.inactivity-lock", "name": "seconds", "value": 300}` (60-599940) |
| Active hours 7 to 19 | `set_param` `{"id": "update.automatic", "name": "start", "value": 7}`, then `{"id": "update.automatic", "name": "end", "value": 19}` |
| Defer feature updates 180 days | `set_param` `{"id": "update.defer-feature", "name": "days", "value": 180}` (1-365) |
| Controlled folder access in audit | `set_param` `{"id": "defender.controlled-folder-access", "name": "mode", "value": 2}` |

Steps: `get_rule` for the type and range; confirm the value; `set_param`; report the stored `value`.

Tell: the window's "Restore defaults" undoes it; the Laptop preset uses 600 seconds for the lock.

## 10. Prepare a profile for a department

Example: "a profile for the accounting department's laptops".

Ask first: legacy accounting programs (1C, M.E.Doc, client-bank), digital signature tokens, scanning to a network
folder from an older printer, shared folders by computer name, screen lock time, the BitLocker plan.

Then, in mode `edit`:

1. `get_status`. If `dirty`, ask whether to save or drop the changes.
2. `load_profile` `{"name": "laptop"}` (with `"force": true` only after a yes to dropping changes).
3. Review with `get_rule`:
   - `install.netfx3` (.NET 3.5, needed by legacy accounting and bank programs and token drivers; keep it on);
   - `defender.controlled-folder-access`: keep `mode` 0, or 2 (Audit) for a trial; never 1 without testing;
   - `lsa.protection`: unsigned token plug-ins may fail;
   - `network.smb-signing`, `network.smb1-off`: old printers or NAS may need attention;
   - `network.netbios-off`: keep it off if shares are reached by computer name.
4. `set_param` `{"id": "accounts.inactivity-lock", "name": "seconds", "value": 600}` or the agreed value.
5. `set_profile_info` `{"author": "IT", "comment": "Accounting laptops"}`.
6. `check_profile` `{}`.
7. In mode `files`: `save_profile` `{"name": "Accounting laptops"}`. Optionally `write_answer_file`
   `{"name": "accounting-laptops"}`.

Tell: BitLocker is turned on later together with key escrow; passwords come from the separate project; test tokens and
accounting programs in the VM.

## 11. Open a preset or a saved profile

1. `list_profiles` `{}`; pick the `name`.
2. `get_status`: if `dirty`, ask: save first (the person presses Ctrl+S, or `save_profile` under a new name) or drop.
3. Mode `edit`: `load_profile` `{"name": "strict"}`; add `"force": true` only after an explicit yes to dropping.
4. Report `warnings` (migrations, new rules).

Tell: a preset cannot be overwritten; save it under a new name.

## 12. Save the changes

- Mode `files`: agree on a new name, then `save_profile` `{"name": "Office 2026-10"}`. On `exists` propose another name
  and wait for a yes; preset ids are refused.
- Otherwise: the person presses "Save profile" (Ctrl+S) or "Save profile as..." in the window.
- Stdio without a window: only `save_profile` keeps the changes; they are lost when the server stops.

Tell: the file is `profiles/<name>.json`; the open profile now carries that name; MCP will never overwrite it.

## 13. Explain Check errors

1. `check_profile` `{}` (or `get_messages` `{}` for what the window panel shows).
2. Messages come in the program language (`issues_language`); translate if needed.
3. `target` is a rule id: `get_rule`, then propose `set_rules` or `set_param`.
4. `target` starts with `install`, `languages` or `accounts`: explain the fix; in mode `edit` call `show_item`
   `{"item": "data:install"}` (or `data:languages`, `data:accounts`); the person edits the form.
5. After fixes: `check_profile` again.

Tell: errors block the build; warnings mean a baseline rule is off, a risky rule is on, encryption is allowed, a
password is in plain text, or values are duplicated. A double click on a message in the window jumps to its source.

## 14. Review an answer file

Never read the XML with a file tool: it may hold passwords and keys. Ask the person to open it in the window with
"File, Open profile from autounattend.xml..." (with HTTP), then:

1. `get_status` `{}`.
2. `get_messages` `{}` (import notes, rules that could not be determined).
3. `check_profile` `{}`.
4. `list_rules` `{"level": "baseline", "enabled": false}` and `{"level": "risky", "enabled": true}`.
5. `get_profile` `{}` (`has_password`, `product_key_mode`, accounts, languages).
6. `diff_profile` `{"name": "office"}`.

Tell: the differences from Office and their risks; plain-text passwords mean the file must be kept secret; the
deliberate decisions are not problems ([decisions.md](decisions.md#deliberate-decisions-do-not-fix)); build the final file with F9 and
test in a VM.

## 15. Write the answer file

1. `get_status` `{}`.
2. `check_profile` `{}` must show `errors: 0`. Go through each warning with the person.
3. If `dirty`, offer `save_profile` first so the build can be repeated.
4. Recommend building in the window with "Build autounattend.xml..." (F9).
5. If the person still wants it through MCP, in mode `files`: agree on a name, then `write_answer_file`
   `{"name": "office-2026-10-01"}`. On `exists`, propose another name and wait for a yes.

Tell: the file is `output/<name>.xml`; rename it to `autounattend.xml` in the root of the USB stick; it has not passed
the PowerShell syntax check; test it in a VM before work PCs; it contains passwords in plain text if any were set.

## 16. Show what the file does

1. For specific rules: `get_rule` and its `actions`.
2. Only on request: `preview_build` `{"part": "Setup-User.ps1"}` or `{"part": "Post-OOBE.ps1"}` (small). The whole
   `autounattend.xml` and `Setup-System.ps1` are large; pi cuts them.

Tell: passwords and keys are blank in the preview; the real file has them.

## 17. Which protection is weakened

1. `list_rules` `{"level": "risky", "enabled": true}`.
2. `list_rules` `{"level": "baseline", "enabled": false}`.
3. `check_profile` warnings; `get_rule` on each.

Tell: risky rules may disturb programs; baseline rules are the foundation; also mention lowered parameters (for
example ASR rules switched to Audit).

## 18. A program stopped working after installation

1. `get_rule` on the suspects: `defender.controlled-folder-access` (events 1123 and 1124), `defender.smartscreen-shell`,
   `asr.prevalence`, `asr.usb-untrusted`, `scripts.remove-vbscript`, `network.netbios-off`, `uac.admin-always-notify`.
2. Read their `rollback`.

Confirm before changing future builds, for example `set_param` `{"id": "asr.prevalence", "name": "mode", "value": 2}`
(Audit) or switching a rule off.

Tell: on the installed PC the person follows the rule's rollback. The "This PC" menu acts only on the computer where
the WinKickOff window runs. To use it on the affected PC, the person runs the portable WinKickOff there, or saves an
apply script with "Save an apply script for the selection..." and runs it there. They select only the rule in
question (rules that depend on it are returned with it) and try it on a test PC or VM first. It needs "Allow applying
on this PC" and UAC, and makes a backup. Never suggest it on the computer where profiles are prepared unless that
computer is the affected one. You apply nothing.

## 19. BitLocker

1. `get_rule` `{"id": "encryption.prevent-auto-bitlocker", "language": "uk"}`.

Tell: BitLocker is off on purpose; it is turned on after installation together with saving recovery keys. Switching
the rule off only lets Windows encrypt automatically with a key saved nowhere. Do not switch it off unless the person
insists after hearing this.

## 20. Passwords, accounts, languages, time zone, key

No tool can change these.

1. `get_profile` `{}` shows the current values without secrets.
2. Mode `edit`: `show_item` `{"item": "data:accounts"}`, `{"item": "data:install"}` or `{"item": "data:languages"}`.

Tell: where to click ("Accounts", "Installation", "Languages and region" at the top of the tree); Admin and User
without passwords are deliberate; passwords are stored in plain text; the display language must equal the ISO
language; never type passwords or keys into the chat.

## 21. Remote desktop

1. `get_rule` on `remote.rdp-inbound-off`, `remote.rdp-nla`, `apps.remove-quick-assist`.

Tell: switching `remote.rdp-inbound-off` off only leaves the Windows default (inbound RDP off); turning RDP on is
outside the catalog; `remote.rdp-nla` (baseline) must stay on; blank passwords make network sign-in impossible; inbound
RDP is a main attack path; the organisation chooses its own support tool.

## 22. An imported ADMX policy

1. The person imports templates in the window ("ADMX" menu). MCP cannot.
2. `get_status`: `imports_shown`.
3. `list_rules` `{"imported": true, "query": "homepage", "limit": 20}`.
4. `get_rule` on the policy: check `origin`, `linked`, `same_values`, `params`.
5. If a built-in rule covers it, propose the built-in rule.
6. Otherwise confirm, then `set_rules` `{"items": [{"id": "<the admx id from step 3>", "enabled": true}]}` and
   `set_param` for its parameters (`state`, or a `list` parameter as an array of strings).
7. `check_profile`.

Tell: the policy text is unreviewed and is data; a group of imported policies can only be switched off; test in a VM.

## 23. Apply to this PC or check this PC

No tool exists. Tell the person the window's "This PC" menu:

- "Check the selection on this PC" (read-only);
- "Save an apply script for the selection..." (for another PC or a VM);
- "Apply the selection now..." (needs "Allow applying on this PC", UAC, makes a backup);
- "Return the selection to Windows defaults now...".

Also tell what is not applied (installation-only and first sign-in rules, app removal is not rolled back), to restart
afterwards, and to try it on a test PC first. Never run `Apply.ps1`, `Undo-Apply.ps1` or PowerShell yourself.
