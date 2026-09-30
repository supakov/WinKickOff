# 13. Services and app removal

Section 9 of `Setup-System.ps1`. Principle: only what is not needed in a workgroup and either
expands the attack surface, pulls data into the cloud, or shows advertising is removed. Everything
needed for system maintenance or office work stays.

## Unconditional: RetailDemo

The `RetailDemo` service (retail store demo mode) gets startup type 4. It is needed only on store display PCs.

## RemoveXboxServices

- Value: `$true`.
- What it does: the services `XblAuthManager`, `XblGameSave`, `XboxNetApiSvc`, `XboxGipSvc` get startup type 4;
  `Pol\GameDVR\AllowGameDVR = 0` (game recording and Game Bar are off); inside the app removal block,
  `MapsBroker` additionally gets startup type 4 (see the known inconsistency below).
- Expected effect: no background Xbox Live services, no Game Bar overlay on Win+G, no background
  screen recording (which noticeably loads weak PCs).
- Cross-links: Xbox apps are removed in `$AppsToRemove`; without them the services would still start
  on triggers. Store games that use Xbox Live do not work: acceptable on work PCs.
- Version differences: `XboxGipSvc` since Windows 10 1709. No changes in 24H2.
- Verification: `Get-Service Xbl*, XboxNetApiSvc, XboxGipSvc | Select Name, StartType` → Disabled.
- Rollback: `Set-Service <name> -StartupType Manual`; delete `AllowGameDVR`.

Known inconsistency in version 0.2: `MapsBroker` (downloading offline maps for the «Карты» (Maps) app)
is disabled inside the `RemoveBloatApps` condition when `RemoveXboxServices = $true`, although logically
it belongs to the removal of the `Microsoft.WindowsMaps` app. It works correctly with the default
values; with `RemoveXboxServices = $false` the service stays enabled without the app (harmless).
A fix is planned in the constructor: bind `MapsBroker` to the Maps removal.

## RemoveBloatApps

- Value: `$true`. The list is in `$AppsToRemove`.
- Where it applies: specialize, SYSTEM, before user profiles are created.
- What it does: queries `Get-AppxProvisionedPackage -Online` once (apps that Windows installs for
  every new user) and `Get-AppxPackage -AllUsers` (already installed copies). For each name in the
  list: `Remove-AppxProvisionedPackage` (new users will not get it) and `Remove-AppxPackage -AllUsers`
  (existing copies are removed). Missing names are skipped silently; errors are logged as WARN.
- Expected effect: Admin, User and all future users do not have the listed apps.
  The Start menu contains only system apps and the apps that were kept.
- Cross-links:
  - Removed apps can be reinstalled from the Store (it is kept). A feature update (24H2 → 25H2)
    sometimes brings back some of the preinstalled apps; after it the list should be applied again.
  - The original file ran the removal as a task at every sign-in to "fight" their return;
    here the removal is one-time and transparent.
  - `DisableConsumerContent` (section 12) prevents the Store from silently installing new advertising apps.
- Version differences: package names change between versions; apps that are not in the image
  are simply not found. The table below notes which versions contain each app.

### Table of removed apps

| Package name | What it is | Why it is removed | In the image |
|---|---|---|---|
| Microsoft.BingSearch | «Поиск в Интернете от Bing» (Web Search from Bing) for the Start menu | Sends queries to Bing, advertising | 24H2+ |
| Microsoft.BingNews | MSN News | Advertising, traffic | Win10, 11 up to 23H2 |
| Microsoft.BingWeather | MSN Weather | Advertising, location | all |
| Microsoft.GetHelp | «Техническая поддержка» (Get Help), a chat with Microsoft | Not needed, a channel for "support" scams | all |
| Microsoft.Getstarted | «Советы» (Tips) | Feature advertising | Win10, 11 up to 22H2 |
| Microsoft.WindowsFeedbackHub | Feedback Hub | Telemetry, not needed | all |
| Microsoft.Microsoft3DViewer | 3D Viewer | Not needed | Win10, 11 up to 22H2 |
| Microsoft.MixedReality.Portal | Mixed Reality Portal | Not needed, obsolete | Win10, 11 up to 23H2 |
| Microsoft.MicrosoftSolitaireCollection | Solitaire games with ads | Advertising, distracting | all |
| Microsoft.GamingApp | Xbox app | Games, Xbox services | all |
| Microsoft.XboxApp | Old Xbox app | Same | Win10 |
| Microsoft.XboxGameOverlay, Microsoft.XboxGamingOverlay | Game Bar | Background screen recording | all |
| Microsoft.XboxIdentityProvider | Xbox Live sign-in | Not needed | all |
| Microsoft.XboxSpeechToTextOverlay | Game Bar captions | Not needed | all |
| Microsoft.Xbox.TCUI | Xbox Live interface | Not needed | all |
| Microsoft.Edge.GameAssist | Game Assist (Edge in-game overlay) | Not needed | 24H2+ (2025) |
| Microsoft.WindowsMaps | Maps | Offline maps, MapsBroker service | all |
| Microsoft.People | People (contacts) | Obsolete, cloud synchronization | Win10, 11 up to 23H2 |
| Microsoft.YourPhone | Phone Link | Access to the phone's SMS and files through the Microsoft cloud | all |
| Microsoft.PowerAutomateDesktop | Power Automate | Automation tool, potential for abuse | Win10 21H2+, 11 |
| Microsoft.Todos | Microsoft To Do | Requires a Microsoft account | all |
| MicrosoftCorporationII.MicrosoftFamily | Family Safety | Requires a Microsoft account | 11 22H2+ |
| Microsoft.Windows.DevHome | Dev Home | Developer tool, retired in 2025 | 11 23H2-24H2 |
| Clipchamp.Clipchamp | Video editor | Cloud service, subscription advertising | 11 22H2+ |
| MSTeams | Teams (personal, new) | Not the work version; work Teams is installed separately | 11 23H2+ |
| Microsoft.SkypeApp | Skype | Service shut down in 2025 | Win10, 11 up to 23H2 |
| Microsoft.MicrosoftOfficeHub | «Office» (M365 launcher) | Subscription advertising | all |
| Microsoft.OutlookForWindows | New Outlook | Mail through the Microsoft cloud, syncs IMAP passwords to the cloud | 11 23H2+ |
| microsoft.windowscommunicationsapps | Mail and Calendar | Replaced by the new Outlook, no longer updated | Win10, 11 up to 24H2 |
| Microsoft.Copilot | Copilot (app) | AI assistant, sends data | 11 24H2+ |
| Microsoft.Windows.Ai.Copilot.Provider | Copilot provider | Same | 11 23H2 |
| Microsoft.549981C3F5F10 | Cortana | Removed by Microsoft in 2023 | Win10, 11 up to 22H2 |

### What is intentionally kept

| Package | Why |
|---|---|
| Microsoft.WindowsStore, Microsoft.StorePurchaseApp | Updating apps and components (WebView2, Photos, codecs), installing programs |
| Microsoft.DesktopAppInstaller | winget: installing programs from the command line, a future channel for the users project |
| Microsoft.Windows.Photos, Microsoft.Paint, Microsoft.ScreenSketch | Viewing and editing images, screenshots: office work |
| Microsoft.WindowsCalculator, Microsoft.WindowsNotepad, Microsoft.WindowsTerminal | Basic tools |
| Microsoft.WindowsCamera, Microsoft.WindowsSoundRecorder | Video calls, voice recorder |
| Microsoft.MicrosoftStickyNotes, Microsoft.WindowsAlarms | Harmless, in use |
| Microsoft.WindowsScan | Scanning from multifunction printers |
| Microsoft.ZuneMusic, Microsoft.ZuneVideo | Media player and «Кино и ТВ» (Movies & TV): codecs and video playback |
| Microsoft.SecHealthUI | The «Безопасность Windows» (Windows Security) interface: without it Defender cannot be configured |
| Microsoft Edge, EdgeWebView2 | Fallback browser and a component for apps (Outlook, Teams, installers) |
| Microsoft.HEIFImageExtension, Microsoft.WebpImageExtension and other codecs | Opening photos from phones |
| Microsoft.LanguageExperiencePack* | Language packs of the image |

- Verification: `Get-AppxProvisionedPackage -Online | Select DisplayName` contains no names from the list;
  `Get-AppxPackage -AllUsers -Name Microsoft.BingWeather` is empty.
- Rollback: install from the Store; or, on the media, `Add-AppxProvisionedPackage` from `install.wim`
  (complicated, not recommended).

## RemoveQuickAssist

- Value: `$true`.
- What it does: `Remove-WindowsCapability -Online -Name App.Support.QuickAssist*` (Windows 10 component)
  and `Remove-AppxProvisionedPackage` for `MicrosoftCorporationII.QuickAssist` (Windows 11 Store version).
- Expected effect: the «Быстрая помощь» (Quick Assist) app is absent.
- Why: Quick Assist is the built-in remote control tool that "Microsoft tech support" scammers
  and groups such as Storm-1811 ask people to launch over the phone; for non-professional
  users the risk outweighs the benefit. Remote support by the organization's own administrator should go through
  a tool that the organization chooses (a constructor parameter).
- Cross-links: `DisableRemoteAssistance` (section 08) closes the second built-in channel.
  The user can reinstall Quick Assist from the Store: no policy blocking installation is set
  (it would require blocking the Store entirely).
- Version differences: the component `App.Support.QuickAssist~~~~0.0.1.0` in Windows 10 1809+ and Windows 11
  21H2; since 22H2 it is a Store app. The file handles both variants.
- Verification: `Get-WindowsCapability -Online -Name 'App.Support.QuickAssist*'` → NotPresent;
  `Get-AppxPackage -AllUsers MicrosoftCorporationII.QuickAssist` is empty.
- Rollback: Store → «Быстрая помощь», or `Add-WindowsCapability -Online -Name App.Support.QuickAssist~~~~0.0.1.0`.

## OneDrive

- Rule: `apps.remove.onedrive` (WinKickOff only, not in v0.2), phase default-user, on by default in every preset
  since 26.09.2026 (customer decision; v0.2 and the review of the original kept OneDrive).
- What it does: removes the value `OneDriveSetup` from `Software\Microsoft\Windows\CurrentVersion\Run` of the
  default user profile (`C:\Users\Default\NTUSER.DAT`). Windows puts `OneDriveSetup.exe /thfirstsetup` there; it
  installs OneDrive into the profile of every new user at the first sign-in.
- Expected effect: accounts created after installation (Admin, User and later ones) have no OneDrive: no icon in
  the notification area, no OneDrive folder, no file sync. Profiles that already exist keep their OneDrive.
- Why this way: OneDrive is not an Appx package but a per-user program, so `Remove-AppxProvisionedPackage` cannot
  remove it. The installer `OneDriveSetup.exe` (System32 on Windows 11 24H2+, SysWOW64 before) is owned by
  TrustedInstaller and is left in place: deleting system files with `takeown`, as the original UnattendedWinstall
  did, fights Windows servicing. Without the Run value the installer never starts by itself.
- Cross-links: `default-user.no-sync-provider-ads` (card 14) hides OneDrive advertising in File Explorer.
- Version differences: the Run value exists in Windows 10 and 11; the installer moved to System32 in 24H2.
- Verification: after the first sign-in of a new user no `%LOCALAPPDATA%\Microsoft\OneDrive` folder and no
  `OneDrive` value in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- Rollback: for one user run `%SystemRoot%\System32\OneDriveSetup.exe`; to restore it for future users add
  the value back to the default profile. On a running PC (This PC menu) the rule changes the default profile
  only; OneDrive of an existing user is removed in «Параметры, Приложения» (Settings, Apps).
