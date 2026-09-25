# 17. Summary cross-link matrix and known inconsistencies

## 1. Matrix "parameter → what it affects"

| Parameter | Depends on | Affects | Conflicts with |
|---|---|---|---|
| ProductKey | edition in the ISO | activation, WillShowUI | ISO without Pro |
| LabConfig bypass | none | PreventAutoDeviceEncryption (redundant without TPM), LSAProtection (value 2 for PCs without UEFI) | the POPCNT/SSE4.2 requirement in 24H2 (cannot be bypassed) |
| UILanguage | ISO language | OOBE language screen, Setup-User (override) | ISO in another language |
| InputLocale | none | sign-in screen, default user profile | ru-UA (no LCID, only through Setup-User) |
| LocalAccounts (empty passwords) | none | LimitBlankPasswordUse (network sign-in blocked), ConsentPromptBehaviorUser (UAC prompt for User cannot succeed), PasswordNeverExpires, AccountLockout, InactivityLockSeconds, RestrictPrinterDriverInstallToAdmins (User cannot connect a printer) | users project (will assign passwords, lift the restrictions) |
| AdminAccount / UserAccount | LocalAccounts (same names) | Post-OOBE | name mismatch |
| PasswordNeverExpires | LocalAccounts | net accounts, Post-OOBE | password policy of the users project |
| EnableNetFx3 | media attached in specialize | old programs, PowerShell 2.0 (unrelated) | stripped-down ISOs |
| EnsurePrintSpooler | none | printing | RestrictPrinterDriverInstallToAdmins (who installs drivers) |
| RestrictPrinterDriverInstallToAdmins | none | users connecting network printers | empty Admin password (UAC prompt cannot succeed) |
| WindowsUpdateAutomatic | none | restarts outside 08:00-20:00 | PCs that work at night (time window parameter) |
| UpdateOtherMicrosoftProducts | none | Office MSI, .NET 3.5 | none |
| DeferFeatureUpdatesDays | DiagTrack Manual, Appraiser tasks | Windows version across the fleet | disabling telemetry completely |
| DeliveryOptimizationLANOnly | port 7680 between PCs | traffic | none |
| DefenderCloudProtection | internet | ASR (prevalence, ransomware, obfuscated), false positives on rare programs | isolated network (does not work, but does not interfere) |
| DefenderPUAProtection | none | bundled installers, remote access utilities | legitimate PUA-class utilities |
| DefenderNetworkProtection | Defender as the primary antivirus | all browsers, VPN clients with filters | third-party antivirus (Defender is passive) |
| DefenderASRRules | cloud protection for three rules, Office in the standard path | Office macros, scripts, USB, PsExec (audit) | in-house programs without reputation (rule in audit mode), remote administration through PsExec/WMI (audit) |
| ControlledFolderAccess (0) | none | at 1: accounting programs that write to Documents | 1C, M.E.Doc, old Office |
| SmartScreenLevel | Mark of the Web | launching downloaded programs | Block breaks installation of rare programs |
| UACAlwaysNotify | none | prompts on system changes | none |
| InactivityLockSeconds | passwords | screen lock | empty passwords (Enter unlocks) |
| LSAProtection | signed LSA plug-ins | e-signature tokens, third-party sign-in providers | unsigned smart card drivers |
| NTLMv2Only | none | old NAS, MFPs | devices with NTLMv1 |
| AccountLockout | passwords | brute force over the network | none |
| DisableRemoteAssistance | none | msra | remote support (a dedicated tool is needed) |
| DisableRemoteDesktopInbound | none | inbound RDP | remote administration |
| DisableRemoteRegistry | none | remote registry | old inventory agents |
| PreventAutoDeviceEncryption | TPM | 24H2 automatic encryption, cloning, recovery | protection of laptops against theft (enable separately, with a key) |
| DisableSMB1 | none | old MFPs and NAS | SMB1-only devices |
| RequireSMBSigning | none | old MFPs and NAS, NTLM relay | devices without SMB2 signing |
| DisableLLMNR | NetBIOS or mDNS for names | responder attacks | none |
| DisableNetBIOS (off) | mDNS, DNS | when enabled: `\\ИМЯ` without DNS | old shortcuts to shared folders |
| FirewallOnWithLogging | network profile | inbound by default, log | file sharing requires the private profile (not set) |
| DisableAutoRun | none | USB flash drives, discs, phones | none |
| ScriptFilesOpenInNotepad | not overridden by HKCU | .js/.vbs/.hta on double-click | installers that launch .vbs through the shell |
| RemoveVBScript (off) | 24H2+ (component) | when enabled: old installers, macros | old software |
| EdgeSmartScreenLocked | Edge | downloads in Edge | none |
| AuditLogging | correct time | 256 MB on disk, noise from removable media | none |
| PowerShellLogging | log size | secrets on the command line end up in the log | none |
| DisablePowerShellV2 | presence of the component (absent in 24H2+) | downgrade attacks | none |
| MinimalTelemetry | none | DeferFeatureUpdates (DiagTrack left as Manual), WER | none |
| DisableConsumerContent | default user profile (the main mechanism on Pro) | preinstalled apps, advertising | none |
| DisableCopilotAndRecall | 24H2, Copilot+ PC | Copilot, Recall, Click to Do | none |
| DisableWidgetsAndNews | none | widgets panel, malvertising | none |
| DisableWebSearchInStart | none | search in Start | none |
| RemoveBloatApps | Store kept | 33 apps, MapsBroker | a feature update may bring some of them back |
| RemoveQuickAssist | none | "tech support" scams | remote support (a dedicated tool is needed) |
| RemoveXboxServices | none | Game Bar, Xbox Live | Store games |
| TimeZone | none | audit logs (event times) | none |

## 2. Chains to keep in mind when changing a single parameter

1. Starter accounts and passwords: `LocalAccounts` → `LimitBlankPasswordUse` → `ConsentPromptBehaviorUser`
   → `RestrictPrinterDriverInstallToAdmins` → `PasswordNeverExpires` → users project.
   Assigning passwords lifts all restrictions of this chain.
2. Legacy network protocols: `DisableSMB1` + `RequireSMBSigning` + `NTLMv2Only` + `DisableLLMNR`.
   Relax them only together with an inventory of old devices (MFPs, NAS).
3. Cloud protection: `DefenderCloudProtection` → three ASR rules → `SmartScreenLevel` → `DefenderNetworkProtection`.
   Without internet, only local signatures and rules without a cloud dependency work.
4. Feature updates: `DeferFeatureUpdatesDays` → `MinimalTelemetry` (DiagTrack Manual, Appraiser is not touched)
   → `WindowsUpdateAutomatic`. Disabling DiagTrack "for privacy" breaks the first item.
5. Languages: `UILanguage` (= ISO) → `InputLocale` → default user profile → `Setup-User.ps1` (display language
   override, `ru-UA`). Changing the ISO requires changing `UILanguage`; `SystemLocale` and `UserLocale` can stay.
6. Remote administration: `DisableRemoteAssistance` + `DisableRemoteDesktopInbound` +
   `DisableRemoteRegistry` + `RemoveQuickAssist` + ASR rule PsExec/WMI (audit) + firewall.
   The organization must choose a support tool before deployment.
7. Credentials: `LSAProtection` + `WDigest` + `NoLMHash` + `NTLMv2Only` + `LocalAccountTokenFilterPolicy`
   + `AccountLockout`. Together they make a stolen hash or password of little use.
8. Default user profile: everything in section 14 applies only to profiles created after specialize.
   Rerunning the script on a configured system does not change existing profiles.

## 3. Known inconsistencies and assumptions of version 0.2

| What | Where | Consequence | Plan |
|---|---|---|---|
| `MapsBroker` is disabled under the `RemoveXboxServices` condition inside `RemoveBloatApps` | Setup-System.ps1 section 9 | With non-default values the service may remain without the app (harmless) | Bind it to the Maps removal in the constructor |
| The policies `DisableWindowsConsumerFeatures`, `DisableSoftLanding`, `DisableThirdPartySuggestions` have no effect on Pro | Section 8 | Harmless; the real work is done by the default user profile | Keep them, mark them in the constructor schema as "Enterprise only" |
| `TurnOffWindowsCopilot` in HKLM has no effect | Section 8 | Harmless; the copy in the default user profile and the app removal take effect | Keep |
| `AllowCortana`, `Windows Chat`, `ConfigureChatAutoInstall` relate to past versions | Section 8 | Harmless | Mark as "obsolete" in the schema |
| The network profile (private/public) is not set | oobeSystem | Windows asks at the first connection or assigns public; shared folders will require switching | Constructor parameter |
| The Setup language (WinPE) is not set | windowsPE | The first Setup screen remains | Constructor parameter, derived from the ISO |
| Passwords in the answer file, if they appear, are stored in plain text | oobeSystem | Post-OOBE.ps1 deletes the copies; the media with the file must be kept as a secret | Requirement for the constructor: a warning when a password is set |
| ASR rules for Office do not work if Office is not installed in Program Files | Section 3 | No protection against Office macros | Document it in the Office installation instructions |
| The critic's report pointed to `DisableLockWorkstation` in Winlogon | Section 4 | Fixed in 0.2: the value is removed from both places | Closed |
| Cleanup task on a laptop running on battery | Section 12 | Fixed in 0.2: task XML | Closed |
| auditpol with English names on the Ukrainian image | Section 7 | Fixed in 0.2: GUIDs | Closed |
