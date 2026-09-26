# T15. Applying a selected rule or branch to a running Windows

Status: blocked (25.09.2026: implemented and tested without touching the computer; step 7, the acceptance
in a VM, needs a virtual machine that only the customer can run). Stage 6. Dependencies: T06, T08, T11.

## Goal

From the WinKickOff window, apply a selected rule or an entire tree branch to an already installed Windows,
without reinstalling: for example, to finish configuring a PC installed before the rule appeared, or to restore
a setting that the user broke. Before applying, show what is already in effect; after
applying, have an automatic rollback wherever it is possible.

## Feasibility

Possible, but not for all rules and not as a default action. Review by catalog phase:

| Rule phase | Applicable to a running system | How |
|---|---|---|
| `specialize` (HKLM, services, commands, features, apps for all users) | Yes | The same actions as in `Setup-System.ps1`; administrator rights are required; some changes take effect after a reboot |
| `default-user` (default profile hive) | Yes, for new users | Mounting `C:\Users\Default\NTUSER.DAT`; for the current user, optionally, the same values in `HKCU` |
| `user-first-logon` (input languages and other per-user settings) | Only for the current user and only with a separate confirmation | Input language rules change keyboard layouts: on 12.09.2026 exactly such a change broke layout switching. Excluded by default |
| `post-oobe` (accounts, built-in accounts, answer file copies) | Yes | The same actions as in `Post-OOBE.ps1` |
| `windowspe`, `specialize-xml`, `oobe-xml` | No | Effective only during installation; marked «только при установке» (installation only) in the window |

Rollback: for `reg`, `reg-remove` and `service` actions, the script saves the previous
value before the change and can restore it. For `feature` and `capability`, rollback is done with the reverse command.
For `appx` (app removal) and `ps`, `exe` there is no automatic rollback: the `rollback` text
from the catalog is shown, and such rules are marked as irreversible before applying.

Conflict with the specification requirements: the editor itself runs without administrator rights and does not change the
machine (`01-problem-statement.md`, sections 4 and 5). This is preserved: applying is done by a separate
PowerShell process, launched through a UAC prompt only on an explicit user action.
Tests never apply anything; functional verification is done only in a virtual machine.

## Steps

1. `core/apply.py`: `plan_apply(catalog, profile, item_ids) -> ApplyPlan` for a rule or a branch:
   applicable rules with dependencies taken into account (enabled required rules are added to the plan),
   excluded rules with a reason (installation phase, input languages, turned off in the profile), and the
   "reboot required" and "irreversible" flags.
2. Read-only verification mode (audit): the `Audit-*.ps1` script compares the current values of the
   registry, services, features and apps with the rule values and writes a JSON report: for each
   rule "in effect", "not in effect", "partial", "not verified" (for `ps` and `exe`). Administrator
   rights are not required. In the window: «Проверить на этом ПК» (Check on this PC) for a rule or a branch, the result shown in the tree
   as icons and in the list at the bottom.
3. Apply script `Apply-*.ps1`: the `Setup-System.runtime.ps1` runtime in apply mode
   (`Set-Reg`, `Remove-Reg`, `Set-ServiceStart` write the previous value to `backup-<время>.json`
   before the change), only the blocks from the plan, a log in a folder next to the script, `exit 0` as in the installation.
4. Rollback script `Undo-Apply.ps1`: restoring from a `backup-*.json` file; a fixed runtime
   in `templates/`, without rule logic.
5. Window: three actions in the context menu of a rule and of a group, and on the description panel:
   «Проверить на этом ПК» (read-only), «Сохранить скрипт применения...» (Save apply script...; puts Apply, Undo, README into
   the chosen folder to run on another PC), «Применить сейчас...» (Apply now...). The last one is disabled by
   default and is enabled in the program settings; before launch a dialog shows the computer name,
   the list of changes, the irreversible items and the reboot requirement; launch through UAC
   (`Start-Process powershell -Verb RunAs`), the result is read from the log and the report.
6. Tests: classification of the plan by phases and exclusion reasons; dependencies get into the plan; the
   Audit, Apply, Undo scripts are parsed by Windows PowerShell 5.1 (`pscheck`); launching the apply is forbidden in tests
   (the launch function is substituted with one that fails when called).
7. Acceptance in a VM: a clean installation from the «Офис» (Office) preset with the Defender branch turned off; the audit shows "not
   in effect"; applying the branch; the audit shows "in effect"; rollback; the audit shows "not in effect" again; reboot
   without errors; a log without ERROR.

## Acceptance criteria

- The audit changes nothing in the system and works without administrator rights.
- Applying is possible only through explicit confirmation and UAC; it is never executed in tests.
- For every changed registry value and service, rollback restores the previous state (verified in a VM).
- Rules of the installation phases and of input languages are not applied silently: they are visible in the plan with a reason.

## Risks

- Applying on a work PC without verification in a VM can disrupt its operation (example of 12.09.2026). That is why
  «Применить сейчас» is disabled by default, and the documentation requires an audit and a VM first.
- Some policies take effect only after a reboot or `gpupdate`; an audit right after applying
  may show "in effect" while programs still behave the old way.
- App removal and disabling of features cannot be rolled back instantly.

## Implementer notes

25.09.2026, implemented (steps 1-6):
- `core/apply.py`: `plan_apply` (selected rules and groups, enabled requirements added, install-only phases
  and the first sign-in phase excluded with the reason, flags "not rolled back automatically" for appx,
  capability, ps and exe actions and "restart" for services, components and `HKLM:\SYSTEM` values);
  `render_audit`, `render_apply`, `render_undo`; `parse_audit_report`; `run_audit` (powershell.exe, read-only
  script, report in `logs/tmp`); `launch_elevated` (ShellExecute "runas", the UAC prompt).
- Templates `Audit.runtime.ps1` (only reads; without administrator rights components and other users' apps
  are "unknown"; default user values are checked in HKCU), `Apply.runtime.ps1` (administrator check,
  `Save-RegState` before every registry change, feature states, removed apps and capabilities listed;
  `backup-*.json` and `apply-*.log` next to the script), `Undo.runtime.ps1`.
- Window: menu «Этот ПК» (This PC) and the tree context menu: «Проверить выбранное на этом ПК» (Check the
  selection on this PC), «Сохранить скрипт применения выбранного...» (Save an apply script: `Apply.ps1`,
  `Undo-Apply.ps1`, `README.txt`), «Применить выбранное сейчас...» (Apply now: off by default, enabled by
  «Разрешить применение на этом ПК» (Allow applying on this PC) with a warning, stored as `allow_apply` in
  `settings.json`; confirmation with the computer name, irreversible rules and restart; scripts in `logs/`).
- Tests: `tests/test_apply.py` (plan, flags, scripts parse in PowerShell 5.1, the audit contains no mutating
  command, report statuses, the runner with a harmless script in a temporary folder) and window tests with
  the audit runner and the elevation mocked. Nothing is applied and no audit runs on the customer's PC in tests.
- User documentation: `docs/user/{ru,uk,en}/this-pc.md`.

### 26.09.2026: return to Windows defaults, apply without a hidden switch

- Customer report: «Применить выбранное сейчас...» looked always disabled; its switch sat in another menu. Now
  the items are always available; the first apply or return asks the permission question of
  «Разрешить применение на этом ПК» (Allow applying on this PC) and remembers the answer.
- New item «Вернуть выбранное к умолчаниям Windows сейчас...» (Return the selection to Windows defaults now):
  `plan_revert` / `render_revert` in `core/apply.py` return the selected rules and the rules that require them to
  the values of a clean Windows, whatever the profile says. Data: the optional action field `default`
  (78 values in catalog 0.4); a missing policy is the default; unknown defaults are listed and left alone. The
  script is the apply script (same backup), so `Undo-Apply.ps1` in `logs/revert-*` undoes the return.
- Tests: `RevertTest` in `tests/test_apply.py`, window tests `test_apply_now_asks_for_permission_first` and
  `test_revert_now_returns_windows_defaults`.
