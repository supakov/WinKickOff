# 11. Logging for incident investigation

Section 7 of `Setup-System.ps1`. Goal: when something happens on one PC in the workgroup, the logs
must hold enough data to understand how it happened: which process started, with what
command line, under which user, what PowerShell did. Out of the box Windows logs the bare minimum.

## AuditLogging

- Value: `$true`.
- What it does:
  1. `Sys\Audit\ProcessCreationIncludeCmdLine_Enabled = 1`: event 4688 "process created" includes
     the full command line (without it only the exe name is visible).
  2. `auditpol.exe /set /subcategory:{GUID} /success:enable /failure:enable` for ten subcategories
     (table below). Subcategories are specified by GUID because on the Ukrainian image auditpol
     accepts only localized names; GUIDs do not depend on the language.
  3. `auditpol.exe /set /subcategory:{0CCE922C-...} /success:disable /failure:disable`: process
     termination is not logged (noise).
  4. `wevtutil.exe sl <log> /ms:<bytes>`: log sizes: Security 256 MB, System 64 MB,
     Application 64 MB, `Microsoft-Windows-PowerShell/Operational` 128 MB (defaults 20 MB and 15 MB).

| GUID | Subcategory | What it provides |
|---|---|---|
| 0CCE922B-69AE-11D9-BED3-505054503030 | Process Creation | 4688: who launched what, with which arguments |
| 0CCE9215-69AE-11D9-BED3-505054503030 | Logon | 4624/4625: successful and failed logons, including network ones |
| 0CCE9216-69AE-11D9-BED3-505054503030 | Logoff | 4634/4647 |
| 0CCE9217-69AE-11D9-BED3-505054503030 | Account Lockout | 4740 |
| 0CCE921B-69AE-11D9-BED3-505054503030 | Special Logon | 4672: logon with administrator rights |
| 0CCE9235-69AE-11D9-BED3-505054503030 | User Account Management | 4720/4722/4724/4726: creation, enabling, password change, deletion |
| 0CCE9237-69AE-11D9-BED3-505054503030 | Security Group Management | 4732/4733: adding to Administrators |
| 0CCE923F-69AE-11D9-BED3-505054503030 | Credential Validation | 4776: NTLM authentication, password guessing |
| 0CCE9227-69AE-11D9-BED3-505054503030 | Other Object Access Events | 4698/4702: creation and modification of scheduled tasks (persistence) |
| 0CCE9245-69AE-11D9-BED3-505054503030 | Removable Storage | 4663 for files on USB: what was copied to a flash drive |

- Expected effect: on a typical office PC the Security log fills its 256 MB in 2-6 weeks; in an
  incident there is history for that period. Correlating 4688 with the command line and 4624 by time
  reveals the infection chain.
- Cross-links:
  - `auditpol` changes the local audit policy. A domain Group Policy would override it, but
    there is no domain. In `secpol.msc` (Advanced Audit Policy Configuration) the values are visible and editable.
  - Correct time (`TimeZone`, section 02, and synchronization) is mandatory for correlating events.
  - The logs are stored on the PC itself; if ransomware encrypts the drive, they are lost. Next step
    (not in this version): forwarding events to a share or a collector (Windows Event Forwarding).
  - Removable storage auditing writes many events when large folders are copied to a flash drive.
- Version differences: the «Съёмное хранилище» (Removable Storage) subcategory since Windows 8. The command line in 4688 since
  Windows 8.1 / KB3004375 for Windows 7. Subcategory GUIDs are the same in all versions.
  No changes in 24H2.
- Verification: `auditpol /get /category:*`; `wevtutil gl Security | findstr maxSize`;
  Event Viewer → Security → event 4688 contains the «Командная строка процесса» (Process Command Line) field.
- Rollback: `auditpol /clear` (all subcategories set to «без аудита» (No Auditing)); log sizes:
  `wevtutil sl Security /ms:20971520`.

## PowerShellLogging

- Value: `$true`.
- What it does:
  - `Pol\PowerShell\ScriptBlockLogging\EnableScriptBlockLogging = 1`: the text of every executed
    code block is written to `Microsoft-Windows-PowerShell/Operational`, event 4104, including
    deobfuscated code (what actually runs after strings are expanded);
  - `Pol\PowerShell\ModuleLogging\EnableModuleLogging = 1` and `ModuleNames\* = *`: cmdlet calls
    of all modules with their parameters, event 4103.
- Expected effect: malicious PowerShell loaders (the most common type after email scripts)
  leave their full text in the log, even if the script file is deleted.
- Cross-links:
  - The PowerShell log size is raised to 128 MB in `AuditLogging`; without that, 15 MB fills up in days.
  - The log may contain sensitive data if an administrator passes passwords on the command
    line; only administrators have access to the log.
  - Applies to Windows PowerShell 5.1 and PowerShell 7 (which reads the same policies).
  - `Setup-System.ps1` enables this policy itself while it runs; the subsequent scripts
    (`Setup-User.ps1`, `Post-OOBE.ps1`) are already logged.
- Version differences: Script Block Logging since Windows 10 / WMF 5.0; on Windows 7 it requires WMF 5.1.
  No changes in 24H2. Transcription (`EnableTranscripting`) is not enabled: it writes files into user
  profiles, which the users can delete.
- Verification: `Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\PowerShell\ScriptBlockLogging'`;
  the log contains 4104 events after any PowerShell launch.
- Rollback: delete the two keys.

## DisablePowerShellV2

- Value: `$true`.
- What it does: `Disable-WindowsOptionalFeature` for `MicrosoftWindowsPowerShellV2Root` and
  `MicrosoftWindowsPowerShellV2`, if they are enabled.
- Expected effect: `powershell.exe -Version 2` does not start. The 2.0 engine supports neither
  script block logging nor AMSI (antivirus scanning), which is why malicious scripts ask
  for exactly this engine ("downgrade attack").
- Cross-links: programs that require .NET 2.0/3.5 (enabled via `EnableNetFx3`) do not depend on
  PowerShell 2.0. No modern Microsoft product uses the 2.0 engine.
- Version differences: the component exists in Windows 10 and in Windows 11 up to 23H2 (enabled by default on
  Windows 10 and disabled on Windows 11). In Windows 11 24H2 with the August 2025 update and in 25H2 the engine
  is removed from the image completely: the command will log INFO about the missing component, which is expected.
- Verification: `Get-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root`;
  `powershell -Version 2 -Command 1` must fail with an error.
- Rollback: `Enable-WindowsOptionalFeature -Online -FeatureName MicrosoftWindowsPowerShellV2Root`
  on builds where it exists.
