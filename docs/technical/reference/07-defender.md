# 07. Microsoft Defender, attack surface reduction rules, SmartScreen

Section 3 of `Setup-System.ps1`. Customer requirement: the built-in antivirus must work. The file does not weaken
anything in Defender; it only enables additional layers that are off by default on Pro.

All settings are written as policies to `Def` = `HKLM\SOFTWARE\Policies\Microsoft\Windows Defender`.
This is the same path that Group Policy uses; Defender reads it directly, without a running
service, so the method is reliable in specialize. Side effect: the corresponding toggles in
«Безопасности Windows» (Windows Security) become greyed out with the caption "managed by your administrator", which is
desirable for non-professional users.

Tamper Protection is enabled by default and does not allow protection to be weakened through
the registry; it does not block enabling additional layers.

## Unconditional actions of the section

| Key | Action | Meaning |
|---|---|---|
| `Def\DisableAntiSpyware`, `Def\DisableAntiVirus` | deleted | The only values third-party scripts use to disable Defender |
| `Def\Real-Time Protection\DisableRealtimeMonitoring` | deleted, then = 0 | Real-time protection is on |
| `Def\Real-Time Protection\DisableBehaviorMonitoring` | 0 | Behavior monitoring is on |
| `Def\Real-Time Protection\DisableIOAVProtection` | 0 | Scanning of downloaded files and attachments is on |
| `Def\Real-Time Protection\DisableScriptScanning` | 0 | Script scanning (AMSI) is on |
| `Def\Windows Defender Exploit Guard\Controlled Folder Access\EnableControlledFolderAccess` | the `ControlledFolderAccess` value | See below |
| `HKLM\SOFTWARE\Policies\Microsoft\Windows Defender Security Center\Notifications\DisableNotifications` | 0 | Windows Security notifications are visible |
| `...\Notifications\DisableEnhancedNotifications` | 0 | Enhanced notifications are visible |
| `Pol\System\EnableSmartScreen` | 1 | SmartScreen for apps and files is on |
| `Pol\System\ShellSmartScreenLevel` | the `SmartScreenLevel` value | See below |

## DefenderCloudProtection

- Value: `$true`.
- What it does:
  - `Def\Spynet\SpynetReporting = 2`: MAPS membership at the «Расширенный» (Advanced) level (cloud protection);
  - `Def\Spynet\SubmitSamplesConsent = 1`: automatic submission of safe samples
    (no documents; files with personal data are not sent without a prompt);
  - `Def\MpEngine\MpCloudBlockLevel = 2`: cloud blocking level «Высокий» (High);
  - `Def\MpEngine\MpBafsExtendedTimeout = 50`: up to 50 seconds of additional waiting for the cloud
    verdict on a suspicious file (the default is 10).
- Expected effect: new malicious files that are not yet in the signatures are blocked by cloud
  reputation within seconds. A file that the cloud considers suspicious is held for up to a minute
  before its first run.
- Cross-links:
  - The ASR rules "block executable files based on prevalence", "ransomware protection"
    and "obfuscated scripts" require cloud protection to be on; without it they do not work.
  - The «Высокий» level increases the share of false positives on rare in-house programs
    (for example internal accounting utilities). Solution: Defender exclusions for specific files
    or lowering the level to 0 (the default).
  - Internet access is required; in an isolated network cloud protection simply does not respond, and local signatures keep working.
- Version differences: the values are available since Windows 10 1607 (blocking level) and 1703 (timeout).
  Unchanged on Windows 11 24H2. `MpCloudBlockLevel=4` («Высокий плюс» (High+)) and 6 («Нулевая терпимость» (Zero tolerance))
  were not chosen because of false positives.
- Verification: `Get-MpPreference | Select MAPSReporting, SubmitSamplesConsent, CloudBlockLevel, CloudExtendedTimeout`
  → 2, 1, 2, 50.
- Rollback: delete the four values; Defender returns to the defaults (advanced MAPS, level 0).

## DefenderPUAProtection

- Value: `$true`.
- What it does: `Def\PUAProtection = 1`: blocking of potentially unwanted applications (adware,
  bundling installers, miners, "optimizers", torrent clients with ads).
- Expected effect: when such a program is downloaded or run, Defender blocks it and shows
  a notification. For non-professionals this closes the most common infection channel: "a free program
  from a website with a Download button".
- Cross-links: complemented by `SmartScreenPuaEnabled` in Edge (section 10). Legitimate programs that are flagged
  as PUA (for example some remote access utilities) require an exclusion.
- Version differences: the policy exists since Windows 10 1607; the toggle appeared in Settings in 2004.
  Unchanged on 24H2.
- Verification: `Get-MpPreference | Select PUAProtection` → 1.
- Rollback: delete the value (the default on Pro: 0, off, but Edge SmartScreen PUA is on).

## DefenderNetworkProtection

- Value: `$true`.
- What it does: `Def\Windows Defender Exploit Guard\Network Protection\EnableNetworkProtection = 1`.
- Expected effect: no application (not only Edge) can connect to domains and addresses with
  a bad reputation according to SmartScreen: phishing, command-and-control servers, exploit kits. The user
  sees a "Connection blocked" notification.
- Cross-links:
  - Works through a filter driver; on Windows 11 24H2 it requires Defender to be the primary
    antivirus (when a third-party antivirus is installed, Defender switches to passive mode and network
    protection turns off).
  - May conflict with VPN clients that use their own filters; in that case audit
    mode (2) gives a log without blocking.
  - Does not replace DNS filtering; it complements it.
- Version differences: Windows 10 1709+. On Windows 11 24H2 it also works partially for QUIC/HTTP3.
- Verification: `Get-MpPreference | Select EnableNetworkProtection` → 1; the test
  `https://smartscreentestratings2.net` must be blocked.
- Rollback: value 0 or 2 (audit).

## DefenderASRRules

- Value: `$true`. The set of rules is in `$AsrRules`.
- What it does: `Def\Windows Defender Exploit Guard\ASR\ExploitGuard_ASR_Rules = 1` enables the mechanism;
  for each rule, the string value `Def\...\ASR\Rules\<GUID>` = `1` (block),
  `2` (audit: only an event in the log), `6` (warn: the user can allow).
- Expected effect: typical infection techniques through Office, email, scripts and USB are blocked,
  which Defender as a signature-based antivirus does not catch.
- Cross-links: ASR rules are available on all editions with Defender (including Home), but they are managed only through
  policies or PowerShell; they are not in Settings. Events: log
  `Microsoft-Windows-Windows Defender/Operational`, ID 1121 (block), 1122 (audit), 1125/1126 (network protection).
  The Office rules require Office in `%ProgramFiles%` or `%ProgramFiles(x86)%`.
- Version differences: minimum builds are in the table. On 24H2/25H2 all 17 rules are supported.

### Rules table

| GUID | Rule | Mode | What it blocks | False positive risk | Minimum version |
|---|---|---|---|---|---|
| 56a863a9-875e-4185-98a7-b882c64b5ce5 | Abuse of vulnerable signed drivers | 1 | Installation of drivers from the Microsoft list of vulnerable drivers (BYOVD attacks to disable the antivirus) | Low; old RGB lighting and overclocking drivers | Win10 1709 |
| e6db77e5-3df2-4cf1-b95a-636979351e5b | Persistence through WMI subscriptions | 1 | Fileless persistence of malicious code in the WMI repository | Low; SCCM client (not used) | Win10 1903 |
| 7674ba52-37eb-4a4f-a9a1-f0f9a1619a2c | Adobe Reader: child processes | 1 | Launching anything from a PDF (Reader exploits) | Low | Win10 1809 |
| d4f940ab-401b-4efc-aadc-ad5f3c50688a | Office: child processes | 1 | Macros that launch cmd/PowerShell/installers | Medium: add-ins that launch external programs | Win10 1709 |
| be9ba2d9-53ea-4cdc-84e5-9b1eeee46550 | Executable content from email and webmail | 1 | Launching .exe/.js/.zip saved from Outlook and webmail | Low | Win10 1709 |
| 5beb7efe-fd9a-4556-801d-275e5ffc04cc | Obfuscated scripts | 1 | Running PowerShell/JS/VBS with signs of obfuscation | Medium: installers of some programs | Win10 1709, requires cloud protection |
| d3e037e1-3eb8-44c8-a917-57927947596d | JavaScript/VBScript launch downloaded content | 1 | A downloader script that launches a downloaded file | Low | Win10 1709 |
| 3b576869-a4ec-4529-8536-b80a7769e899 | Office creates executable content | 1 | Macros that write .exe/.dll/.vbs to disk | Low | Win10 1709 |
| 75668c1f-73b5-4cf0-bb93-3ecf5cb7cc84 | Office injects code into processes | 1 | Injections from Word/Excel/PowerPoint/OneNote | Low; incompatible with BeyondTrust, Heimdal | Win10 1709 |
| 26190899-1602-49e8-8b27-eb1d0a1ce869 | Outlook: child processes | 1 | Exploits of Outlook rules and forms | Low | Win10 1709 |
| b2b3f03d-6a65-4f7b-a9c7-1c7ef74a9ba4 | Untrusted processes from USB | 1 | Running unsigned .exe files directly from a USB drive or SD card | Medium: unsigned portable utilities. In WinKickOff (`asr.usb-untrusted`) off by default since 26.09.2026 (commit d33fc41), on in "Strict" | Win10 1709 |
| 92e97fa1-2edf-4476-bdd6-9dd0b4dddc7b | Win32 API from Office macros | 1 | Shellcode from VBA | Low | Win10 1709 |
| c1db55ab-c21a-4637-bb3f-a12568109d35 | Advanced ransomware protection | 1 | Files that look like ransomware according to cloud heuristics | Medium: rare in-house programs until they build up reputation | Win10 1803, requires cloud protection |
| 33ddedf1-c6e0-47cb-833e-de6133960387 | Reboot into Safe Mode | 1 | `bcdedit /set safeboot` from malicious code (antivirus bypass) | Low; Safe Mode is available from the recovery environment | Win10 1709 |
| c0033c00-d16d-4114-a5a0-dc9b3a7d2ceb | Copied or impersonated system utilities | 6 (warn) | Copies of system32 utilities from other folders | Elevated: heuristic; hence the warn mode | Win10 1709 |
| 01443614-cd74-433a-b99e-2ecdc07bfc25 | Executable files without reputation (prevalence, age) | 2 (audit) | Running rare or new .exe files | High: would block internal programs; enable in the "Strict" preset | Win10 1803, requires cloud protection |
| d1e49aac-8f56-4280-b9ba-993a6d77406c | Processes from PsExec and WMI | 2 (audit) | Remote execution via PsExec/WMI (lateral movement) | High for remote administration by your own admin | Win10 1803 |

Not enabled: `9e6c4e1f-7d60-472f-ba1a-a39ef669e4b2` "Credential theft from LSASS". It duplicates
`LSAProtection` (section 08) and creates a lot of noise in the log; Microsoft marks it as not applicable
when LSA protection is enabled.

- Verification:
  ```powershell
  $p = Get-MpPreference; $p.AttackSurfaceReductionRules_Ids.Count      # 17
  $p.AttackSurfaceReductionRules_Ids | % { "$_ = " + $p.AttackSurfaceReductionRules_Actions[[array]::IndexOf($p.AttackSurfaceReductionRules_Ids,$_)] }
  ```
- Rollback: delete `Def\...\ASR\Rules\<GUID>` for a specific rule, or the whole `ASR` key.
  Exclusions for individual files: `Add-MpPreference -AttackSurfaceReductionOnlyExclusions <path>`.

## ControlledFolderAccess

- Value: `0` (off). Allowed: `1` block, `2` audit.
- What it does: `Def\Windows Defender Exploit Guard\Controlled Folder Access\EnableControlledFolderAccess = <value>`.
- Expected effect with 1: writing to Documents, Pictures, Desktop and other protected folders
  is allowed only to applications on the Microsoft trusted list or added manually. Ransomware
  launched by the user cannot damage the documents.
- Why it is off by default: accounting and banking programs, old versions of Office
  and any in-house programs that write to Documents will be blocked, and a non-professional
  user will not understand what is happening. Enabling it requires maintaining a list of allowed applications
  (`Add-MpPreference -ControlledFolderAccessAllowedApplications`). Recommended path: audit mode (2)
  for a month, review of events 1123/1124, then blocking.
- Cross-links: the ASR rule "ransomware protection" partially covers the same threat
  without an application list. Backups remain the main protection against ransomware.
- Version differences: Windows 10 1709+. Unchanged on 24H2.
- Verification: `Get-MpPreference | Select EnableControlledFolderAccess`.
- Rollback: value 0.

## SmartScreenLevel

- Value: `'Warn'`. `'Block'` is allowed.
- What it does: `Pol\System\EnableSmartScreen = 1` and `Pol\System\ShellSmartScreenLevel = Warn|Block`.
- Expected effect with Warn: running an app without reputation that was downloaded from the internet shows
  the blue "Windows protected your PC" window with the «Выполнить в любом случае» (Run anyway) button.
  With Block there is no button and the app cannot be run.
- Why Warn: Block would prevent installing any low-prevalence program (including the same accounting programs
  from developers' websites). Warn leaves the decision to the administrator, who knows what they are installing.
- Cross-links: it works by the internet zone mark (Mark of the Web) on the file; files from USB drives and from
  the local network have no mark and are not checked by SmartScreen (they are covered by the USB ASR rule and
  cloud protection). Edge has its own SmartScreen (section 10).
- Version differences: the `ShellSmartScreenLevel` policy exists since Windows 10 1703. Unchanged on 24H2.
- Verification: Windows Security → App & browser control → «Проверка приложений и файлов» (Check apps and files)
  shows «Предупреждать» (Warn) and "managed by your administrator".
- Rollback: delete `ShellSmartScreenLevel` (the default Warn remains, but the user will be able to turn it off).
