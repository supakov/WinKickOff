# autounattend.xml v0.2 settings reference

Documentation for the answer file `autounattend.xml` (version 0.2 of 13.09.2026, located in
[Appendix B](../../appendices/B-autounattend-v0.2/README.md)); WinKickOff rules link to these cards. Every area
and every parameter is described: what exactly is written, by what method, what effect is expected, what it affects
in other subsystems, how the behavior differs across Windows versions, how to verify it and how to roll it back.

## How to read a parameter card

Every parameter is described using the same scheme:

| Field | Contents |
|---|---|
| Default value | What is set in `$Config` (or in the XML) in version 0.2 |
| Where applied | Setup pass, script and script section, the account it runs as |
| What it does | Exact registry keys, values, commands, including unconditional actions of the same section |
| Expected effect | What the user or administrator will see |
| Cross-links | Other parameters and Windows subsystems that this affects or depends on |
| Version differences | Windows 10, Windows 11 21H2/22H2/23H2/24H2/25H2, Home/Pro/Enterprise editions |
| Verification | A command that confirms the setting was applied |
| Rollback | A command or key that restores the default Windows behavior |

Registry paths are abbreviated: `HKLM` = `HKEY_LOCAL_MACHINE`, `Pol` = `HKLM\SOFTWARE\Policies\Microsoft\Windows`,
`Sys` = `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System`,
`Def` = `HKLM\SOFTWARE\Policies\Microsoft\Windows Defender`, `DU` = the default profile hive
(`C:\Users\Default\NTUSER.DAT`, mounted as `HKU\UnattendDefault` while settings are applied).

## Sections

| File | Area | Parameters |
|---|---|---|
| [00-architecture.md](00-architecture.md) | File structure: passes, order, application mechanisms, Setup constraints, logs, overall cross-link map | none |
| [01-windows-pe.md](01-windows-pe.md) | windowsPE pass: key, edition, license, hardware check bypass | ProductKey, WillShowUI, AcceptEula, LabConfig |
| [02-specialize-xml.md](02-specialize-xml.md) | specialize pass in XML: script extraction, BypassNRO, launching Setup-System.ps1, time zone | Order 1..3, TimeZone |
| [03-oobe-accounts-languages.md](03-oobe-accounts-languages.md) | oobeSystem pass: languages and region, OOBE screens, starter accounts | InputLocale, SystemLocale, UILanguage, UserLocale, OOBE, LocalAccounts |
| [04-users-and-media.md](04-users-and-media.md) | Accounts in `$Config`, .NET 3.5 from the installation media | AdminAccount, UserAccount, PasswordNeverExpires, EnableNetFx3 |
| [05-printing.md](05-printing.md) | Printing | EnsurePrintSpooler, RestrictPrinterDriverInstallToAdmins |
| [06-windows-update.md](06-windows-update.md) | Windows updates and Delivery Optimization | WindowsUpdateAutomatic, UpdateOtherMicrosoftProducts, DeferFeatureUpdatesDays, DeliveryOptimizationLANOnly |
| [07-defender.md](07-defender.md) | Microsoft Defender, ASR rules, SmartScreen | DefenderCloudProtection, DefenderPUAProtection, DefenderNetworkProtection, DefenderASRRules, ControlledFolderAccess, SmartScreenLevel |
| [08-accounts-uac-lsa-remote.md](08-accounts-uac-lsa-remote.md) | UAC, credential protection, lockout, remote access, BitLocker | UACAlwaysNotify, LSAProtection, AccountLockout, InactivityLockSeconds, NTLMv2Only, DisableRemoteAssistance, DisableRemoteDesktopInbound, DisableRemoteRegistry, PreventAutoDeviceEncryption |
| [09-network-smb-firewall.md](09-network-smb-firewall.md) | SMB, name resolution, firewall | DisableSMB1, RequireSMBSigning, DisableLLMNR, DisableNetBIOS, FirewallOnWithLogging |
| [10-removable-scripts-browser.md](10-removable-scripts-browser.md) | Removable media, script files, Edge | DisableAutoRun, ScriptFilesOpenInNotepad, RemoveVBScript, EdgeSmartScreenLocked |
| [11-logging-audit.md](11-logging-audit.md) | Logging for investigations | AuditLogging, PowerShellLogging, DisablePowerShellV2 |
| [12-telemetry-consumer-ai.md](12-telemetry-consumer-ai.md) | Telemetry, advertising, Copilot and Recall, widgets, web search | MinimalTelemetry, DisableConsumerContent, DisableCopilotAndRecall, DisableWidgetsAndNews, DisableWebSearchInStart |
| [13-services-apps.md](13-services-apps.md) | Services and app removal | RemoveBloatApps ($AppsToRemove), RemoveQuickAssist, RemoveXboxServices |
| [14-default-user-profile.md](14-default-user-profile.md) | Default user profile (inherited by all accounts) | DU hive values |
| [15-per-user-script.md](15-per-user-script.md) | Active Setup and Setup-User.ps1: input languages for each user | no parameters, mechanism |
| [16-post-oobe.md](16-post-oobe.md) | Scheduled task and Post-OOBE.ps1: cleanup after OOBE | no parameters, mechanism |
| [17-cross-links.md](17-cross-links.md) | Summary cross-link matrix and known inconsistencies of version 0.2 | none |
| [18-browsers.md](18-browsers.md) | Browser policies for Microsoft Edge, Google Chrome and Brave (issue #1), corrections to the issue scripts | WinKickOff rules only, not in v0.2 |

## Windows version conventions

The file targets Windows 11 Pro 24H2 and later (tested on the Ukrainian 25H2 ISO, build 26200).
The cards mention:

- Windows 10 (1809 and later): the file is formally compatible but has not been tested; differences are noted.
- Windows 11 21H2, 22H2, 23H2: differences are noted where a setting was introduced or changed.
- Windows 11 24H2 and 25H2: the baseline version; where 24H2 changed the default behavior, this is stated explicitly.
- Editions: Home is not supported (no policies, some components are missing). Pro is the main edition. Enterprise/Education:
  some policies that Pro ignores work there; this is noted in the cards.

## Sources

Microsoft Learn documentation (Unattended Windows Setup Reference, Group Policy reference, Defender ASR reference),
results of the 13.09.2026 installation (setupact.log, setuperr.log), verification on build 26200, the report of the independent
critic ([Appendix C](../../appendices/C-critical-review/03-critic-report-v0.2.docx)).
