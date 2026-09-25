# 16. Scheduled task and Post-OOBE.ps1: cleanup after OOBE

Section 12 of `Setup-System.ps1` creates the task; the script is embedded in the XML as
`C:\ProgramData\Unattend\Scripts\Post-OOBE.ps1`.

## Why a separate stage

Some actions are impossible in specialize: the Admin and User accounts do not exist yet (they are created by
oobeSystem), and the files `C:\Windows\Panther\unattend*.xml` are still needed by Setup. Therefore they
run after OOBE completes, as a scheduled task running as SYSTEM.

## The Unattend-PostOOBE task

- Creation: `schtasks.exe /Create /F /TN Unattend-PostOOBE /XML C:\ProgramData\Unattend\Scripts\Post-OOBE.task.xml`.
  The script writes the XML definition in UTF-16 (the format that schtasks requires).
- Why not `Register-ScheduledTask`: the cmdlet works through CIM/WMI, which is unreliable in specialize
  (a documented source of 0x8004100a errors).
- Why XML rather than `/SC ONSTART`: a task created with the `/SC` switches keeps the defaults
  "do not start on battery" and "stop when switching to battery". On a laptop that was unplugged from the mains after
  installation, the task would never run. The XML sets:

| Parameter | Value | Meaning |
|---|---|---|
| Trigger | BootTrigger | At every boot |
| Principal | S-1-5-18 (SYSTEM), HighestAvailable | Rights to delete files in Panther and to manage accounts |
| DisallowStartIfOnBatteries | false | Runs on battery |
| StopIfGoingOnBatteries | false | Not interrupted when unplugged from the mains |
| StartWhenAvailable | true | If the boot moment was missed, starts as soon as possible |
| MultipleInstancesPolicy | IgnoreNew | A single instance |
| ExecutionTimeLimit | PT6H | Maximum 6 hours (the script waits for OOBE for up to 5 hours) |
| Hidden | false | Visible in Task Scheduler so that the administrator understands what it is |

- Version differences: the Task Scheduler 1.2 format has been the same since Windows Vista. No changes in 24H2.
- Verification: `schtasks /Query /TN Unattend-PostOOBE /V /FO LIST` (before the first successful run);
  after it the task is absent, and the log contains the line `task removed (exit 0)`.

## What Post-OOBE.ps1 does

Log: `C:\ProgramData\Unattend\Logs\Post-OOBE.log`.

1. Waiting for OOBE to complete: every 30 seconds the script reads
   `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Setup\State\ImageState`; `IMAGE_STATE_COMPLETE` is required.
   The limit is 5 hours; if the state is not reached, `exit 0` and a retry at the next boot (the task remains).
   Usually the first boot after specialize is OOBE itself; the state becomes COMPLETE a
   minute after the sign-in screen appears.
2. A 2-minute pause after COMPLETE: so that the user's first sign-in (if it is already happening) does not
   compete for the disk and the registry.
3. Reading `C:\ProgramData\Unattend\config.json`: account names and the `PasswordNeverExpires` flag.
   If the file is unreadable, the names `Admin` and `User` are used.
4. For each account: `Set-LocalUser -PasswordNeverExpires $true` (if the flag is on).
   A missing account is logged and skipped.
5. Built-in accounts by SID: all local users with RID 500 (Administrator) and 501 (Guest)
   are disabled if they are enabled. The lookup is by SID rather than by name, because on the Ukrainian image they
   are named «Адміністратор» (Administrator) and «Гість» (Guest).
6. Carrying over specialize errors: if `C:\Windows\Temp\ua.err` exists (it is written by the command wrappers of
   Order 1 and 3, section 02), each line goes to the log marked `SPECIALIZE ERROR`, and the file is deleted.
   This is the only way to learn that the machine script was not extracted or crashed at startup.
7. Removing copies of the answer file: `C:\Windows\Panther\unattend.xml`, `C:\Windows\Panther\unattend-original.xml`,
   `C:\Windows\Panther\Unattend\unattend.xml`, `C:\Windows\System32\Sysprep\unattend.xml`,
   `C:\unattend.xml`, `C:\autounattend.xml`. Existing ones are deleted, the others are skipped.
8. Removing the task: `schtasks.exe /Delete /TN Unattend-PostOOBE /F`.
9. `exit 0`.

- Expected effect: a few minutes after the sign-in screen first appears (even if nobody
  has signed in), there are no files describing the accounts on the disk, the empty passwords no longer expire,
  the built-in accounts are disabled, and the task has disappeared from Task Scheduler.
- Cross-links:
  - Windows 11 24H2 keeps a full copy of the file in `unattend-original.xml`, including passwords in plain
    text if they were set. The passwords are empty now, but the constructor may set them in the future:
    removal is mandatory.
  - The scripts in `C:\ProgramData\Unattend` are not removed: they contain no secrets and serve as
    documentation of what was applied.
  - If an image capture with Sysprep is planned after installation, the absence of `unattend.xml` in Panther
    is not a problem: Sysprep uses its own file.
  - `PasswordNeverExpires` is duplicated in specialize through `net accounts /maxpwage:unlimited`
    (section 04), so even if this task fails, password expiration will not kick in.
- Version differences: `ImageState` and its values have been the same since Windows Vista. `Set-LocalUser`,
  `Get-LocalUser -SID`, `Disable-LocalUser -SID` since Windows 10 1607. No changes in 24H2.
- Verification: `Test-Path C:\Windows\Panther\unattend.xml` → False; `Get-LocalUser | Where { $_.SID -match '-50[01]$' } | Select Name, Enabled`
  → both False; the log ends with the line `Post-OOBE.ps1 finished`.
- Rollback: not required. Rerunning it as administrator is safe.
