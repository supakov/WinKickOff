# 00. Answer file structure and application mechanisms

## 1. What the answer file is and where Setup finds it

`autounattend.xml` sits in the root of the USB media. Windows Setup searches all removable drives for it at startup
(the 13.09.2026 log: `UnattendSearchExplicitPath: Found unattend file at [E:\autounattend.xml]`).
After copying the files, Setup saves it as `C:\Windows\Panther\unattend.xml` and reads it from there in
subsequent passes. This is the path the script extraction command uses.

A single file contains two parts:

1. The actual answers to Setup: elements in the `urn:schemas-microsoft-com:unattend` namespace,
   split by pass (`<settings pass="...">`).
2. The `<Extensions xmlns="urn:workgroup-unattend">` section: a namespace of its own, which Setup neither
   parses nor validates. It holds three PowerShell scripts in CDATA blocks and the extraction script.

## 2. Setup passes and what happens in them

| Pass | When | Runs as | What our file does |
|---|---|---|---|
| windowsPE | In the Setup environment, before files are copied | SYSTEM in WinPE | Product key (edition selection), license acceptance, hardware check bypass via `HKLM\SYSTEM\Setup\LabConfig` |
| offlineServicing | Applied to the image before the first boot | not used | Empty (the section is absent from the file, which is allowed) |
| specialize | First boot of the installed system, before OOBE, with no network and no users | SYSTEM | Script extraction, `BypassNRO`, launching `Setup-System.ps1`, time zone |
| oobeSystem | OOBE (the out-of-box experience screens) | SYSTEM, then account creation | Languages and region, hiding OOBE screens, creating Admin and User |
| after OOBE | First sign-in of each user | the user | Active Setup runs `Setup-User.ps1` |
| after OOBE | Every boot until its work is done | SYSTEM | The `Unattend-PostOOBE` scheduled task runs `Post-OOBE.ps1`, then deletes itself |

Within specialize the order strictly follows `<Order>`: 1 extraction, 2 BypassNRO, 3 script launch.
All three commands are wrapped so that they return code 0 on any error, because a non-zero code from
any synchronous command aborts the installation (WillReboot documentation: "Other codes: the command failed,
installation terminated").

## 3. Hard constraints of Windows Setup

Violating any of them stops the installation with the message "The provided unattend file is not valid"
(code 0x80220005). The first of them is what caused the failure on 13.09.2026.

| Constraint | Source | How it is met |
|---|---|---|
| `RunSynchronousCommand/Path` length at most 259 characters | Path documentation | Commands shortened, heavy logic moved into the script; the maximum in 0.2 is 241 characters |
| `Description` length at most 259 characters | Description documentation | Maximum 111 |
| XML comments inside `<component>` are not allowed | Observation (the SMI validator rejects them) | The only comment is in the file header |
| A synchronous command must return 0 | WillReboot documentation | `try{...}catch{...};exit 0` wrappers, `trap` inside the script, `exit 0` at the end of each script |
| All four International-Core values must be set, otherwise OOBE shows the language screen | Automate OOBE | InputLocale, SystemLocale, UILanguage, UserLocale are set |
| `Path` cannot be empty | Path documentation | None are empty |

## 4. Methods of applying settings

The file uses seven ways of changing the system. The method determines when a setting takes effect,
whether the user can change it and how to roll it back.

| Method | What it looks like in the script | When it takes effect | Can the user change it in Settings | Rollback |
|---|---|---|---|---|
| Registry policy (`Policies\...`) | `Set-Reg -Path "$Pol\..."` | Immediately or after a reboot, like a GPO | No: the item is greyed out, labelled «управляется организацией» (managed by your organization) | Delete the value |
| Ordinary HKLM registry value | `Set-Reg -Path 'HKLM:\SYSTEM\...'` | Usually after a reboot | Yes, if the UI has an item for it | Restore the default value |
| Value in the default profile (DU) | `Set-Reg -Path ($du + '\...')` | When each new profile is created | Yes, it is the user's personal setting | Change it in HKCU or in the Default hive |
| Service startup type | `Set-ServiceStart` (writes `Start` to the registry) | After a reboot | Yes, via services.msc | `sc config <name> start= <type>` |
| Command-line utilities | `Invoke-Exe 'auditpol.exe' ...`, `net.exe`, `wevtutil.exe`, `schtasks.exe`, `dism.exe` | Immediately | Depends on the utility | The reverse command |
| DISM and Appx cmdlets | `Disable-WindowsOptionalFeature`, `Remove-WindowsCapability`, `Remove-AppxProvisionedPackage` | Immediately (some after a reboot) | Via «Дополнительные компоненты» (Optional features) and the Store | Install it back |
| Active Setup | Key `HKLM\...\Active Setup\Installed Components\{GUID}` | Once, at each user's first sign-in | No | Delete the key (new users), delete the HKCU copy (to run again) |

Why policies and not just ordinary values: in a workgroup without a domain, a registry policy
is the only way to make a setting "tamper-proof" against a non-expert user.
The downside: the administrator also sees greyed-out items and has to know where the key is. All keys
are listed in the cards.

## 5. Files after installation

| Path | What it is | Who can access it |
|---|---|---|
| `C:\ProgramData\Unattend\Scripts\Setup-System.ps1` | Machine settings script, run once in specialize | Read for everyone, write for administrators |
| `C:\ProgramData\Unattend\Scripts\Setup-User.ps1` | First sign-in script, run by Active Setup for each user | Same |
| `C:\ProgramData\Unattend\Scripts\Post-OOBE.ps1` | Cleanup after OOBE | Same |
| `C:\ProgramData\Unattend\Scripts\Post-OOBE.task.xml` | Scheduled task definition | Same |
| `C:\ProgramData\Unattend\config.json` | Snapshot of `$Config` for Post-OOBE.ps1 and for auditing | Same |
| `C:\ProgramData\Unattend\Logs\Setup-System.log` | Machine log: every registry write with an OK/WARN/ERROR result | Same |
| `C:\ProgramData\Unattend\Logs\Setup-User.<name>.log` | First sign-in log, one file per user | Same |
| `C:\ProgramData\Unattend\Logs\Post-OOBE.log` | Cleanup log, including errors carried over from specialize | Same |
| `C:\Windows\Temp\ua.err` | Temporary error file of the specialize wrappers; deleted by Post-OOBE.ps1 | until cleanup |
| `C:\Windows\Panther\unattend.xml`, `unattend-original.xml` | Copies of the answer file left by Setup; deleted by Post-OOBE.ps1 | until cleanup |

The scripts are left on disk on purpose: they show exactly what was applied. They contain no passwords.

## 6. Logging levels in Setup-System.log

| Level | Meaning |
|---|---|
| OK | The value was written, the command returned 0 |
| INFO | Informational message (a missing service was skipped, installation media was found) |
| WARN | The command returned a non-zero code or the component is missing; installation continues |
| ERROR | Exception while writing; installation continues thanks to `trap` |
| UNHANDLED | An error caught by `trap` outside try blocks |

After installation there must be no `ERROR` or `UNHANDLED` lines; `WARN` lines are acceptable for components
that are absent from the given build (for example SMB1, PowerShell 2.0 on 24H2).

## 7. Overall cross-link map

The detailed matrix is in [17-cross-links.md](17-cross-links.md). The main chains:

1. Starter accounts without a password → `LimitBlankPasswordUse` (Windows default) → network sign-in and UAC prompts
   for User are unavailable until passwords are assigned → `PasswordNeverExpires` prevents Windows from demanding a change
   of the blank password → a separate user management project assigns passwords and groups.
2. `UILanguage` = ISO language → all four language values are set → OOBE does not show the language screen →
   `Setup-User.ps1` pins the display language and reorders the input languages.
3. `LSAProtection` → the ASR rule for LSASS is not needed → digital signature token drivers must be signed
   (otherwise they will not load into LSA; for them the rollback is `RunAsPPL`).
4. `DisableSMB1` + `RequireSMBSigning` + `NTLMv2Only` → old multifunction printers with scan-to-network-folder and
   old NAS devices may fail to connect → firmware with SMB 2/3 and signing is needed, or the parameters must be disabled.
5. `DisableLLMNR` (enabled) + `DisableNetBIOS` (disabled) → computer names in the workgroup
   are resolved via NetBIOS and mDNS → turning NetBIOS off leaves only mDNS.
6. `MinimalTelemetry` leaves DiagTrack in manual mode and does not touch compatibility appraisal →
   `DeferFeatureUpdatesDays` and feature update offers keep working.
7. `PreventAutoDeviceEncryption` → on 24H2 the disk is not encrypted automatically → data is recoverable
   without a key, disk cloning works; protection against laptop theft is enabled deliberately.
8. `RemoveBloatApps` does not touch the Store and winget → apps and components get updated →
   `DisableConsumerContent` in the default profile prevents the Store from silently installing promotional apps.

## 8. What happens when the scripts are run again

All three scripts are idempotent: rerunning `Setup-System.ps1` as an administrator rewrites the same
values and does not break the system. The only difference: the default profile hive is mounted again,
and apps that were already removed are simply not found. `Setup-User.ps1` can be run manually as the
user to set the input languages again. `Post-OOBE.ps1` deletes its task after the first successful run,
but the script itself can be run again as an administrator.
