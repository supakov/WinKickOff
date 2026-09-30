# 14. Default user profile

Section 10 of `Setup-System.ps1`. Mechanism: the hive `C:\Users\Default\NTUSER.DAT` is mounted with
`reg.exe load HKU\UnattendDefault`, values are written into it, then the hive is unloaded
(`reg.exe unload`, with a retry after 3 seconds if it is busy). Windows copies this hive into the `HKCU`
of every new profile at first sign-in. Admin and User are created in oobeSystem, and their profiles at
first sign-in, that is, after specialize: they inherit everything listed here.

Specifics of the method:

- These are the user's personal settings, not policies: the user can change them in Settings,
  and nothing is greyed out. For non-professionals these are the right defaults, not a prohibition.
- Profiles that already exist (when the script is rerun on a configured system) are not affected.
- If `reg load` fails (the hive is busy), the section is skipped entirely with ERROR in the log; the other
  sections do not depend on it.
- The `[gc]::Collect()` line before unloading releases PowerShell's registry handles; otherwise
  `reg unload` returns "access denied".

The notation `DU` = `HKU\UnattendDefault` (after sign-in: `HKCU`).

## Unconditional values

| Key (relative to DU) | Value | Effect | Version differences |
|---|---|---|---|
| `Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\HideFileExt` | 0 | File extensions are visible: `счёт.pdf.exe` will not pass itself off as a PDF. The main security setting of this section | All versions; default is 1 |
| `...\Explorer\Advanced\ShowSyncProviderNotifications` | 0 | No OneDrive and Microsoft 365 advertising in File Explorer | Win10 1607+ |
| `Control Panel\International\Geo\Nation` | 241 | Region "Ukraine" (GeoID) | All |
| `Control Panel\International\Geo\Name` | UA | Same, two-letter code (Windows 10 1803+ reads it first) | 1803+ |
| `Control Panel\International\User Profile\HttpAcceptLanguageOptOut` | 1 | Browsers do not report the user's language list to websites (reduces the fingerprint) | Win10+ |

The region affects the Store (which apps and prices to show), the format in «Погода» (Weather) and content
suggestions. It does not change the display language and is not related to the time zone.

## Values under the DisableConsumerContent condition

| Key | Value | Effect |
|---|---|---|
| `...\ContentDeliveryManager\ContentDeliveryAllowed` | 0 | The content delivery channel is off |
| `...\FeatureManagementEnabled` | 0 | No feature "experiments" |
| `...\OemPreInstalledAppsEnabled` | 0 | No OEM preinstalled apps |
| `...\PreInstalledAppsEnabled` | 0 | No Microsoft preinstalled apps |
| `...\PreInstalledAppsEverEnabled` | 0 | The "already installed" flag is reset |
| `...\SilentInstalledAppsEnabled` | 0 | The Store does not install apps silently (the main value) |
| `...\SoftLandingEnabled` | 0 | No "tips" after updates |
| `...\SystemPaneSuggestionsEnabled` | 0 | No recommendations in the Start menu |
| `...\RotatingLockScreenOverlayEnabled` | 0 | No "fun facts" on the lock screen |
| `...\SubscribedContent-310093Enabled` | 0 | No "What's new" after updates |
| `...\SubscribedContent-338387Enabled` | 0 | No facts on the lock screen |
| `...\SubscribedContent-338388Enabled` | 0 | No app suggestions in Start |
| `...\SubscribedContent-338389Enabled` | 0 | No tips and suggestions |
| `...\SubscribedContent-338393Enabled`, `-353694Enabled`, `-353696Enabled` | 0 | No suggestions in Settings |
| `...\SubscribedContent-353698Enabled` | 0 | No suggestions on Timeline |
| `...\UserProfileEngagement\ScoobeSystemSettingEnabled` | 0 | No «Завершим настройку устройства» (Let's finish setting up your device) screen after sign-in |
| `...\Explorer\Advanced\Start_IrisRecommendations` | 0 | No recommendations in Start (Windows 11 22H2+) |
| `...\Explorer\Advanced\Start_AccountNotifications` | 0 | No Microsoft account reminders in Start (23H2+) |
| `...\AdvertisingInfo\Enabled` | 0 | The advertising ID is off for the user |
| `...\Privacy\TailoredExperiencesWithDiagnosticDataEnabled` | 0 | No "personalized suggestions" based on diagnostic data |

Cross-links: it is exactly these values that do on Pro what the `DisableWindowsConsumerFeatures` policy
does on Enterprise. The «Рекомендации» (Recommended) section of the Windows 11 Start menu remains (files and recent
documents), but without app advertising.

## Values under other conditions

| Condition | Key | Value | Effect |
|---|---|---|---|
| DisableWidgetsAndNews | `...\Explorer\Advanced\TaskbarDa` | 0 | The widgets button is hidden (duplicates the Dsh policy) |
| DisableCopilotAndRecall | `...\Explorer\Advanced\ShowCopilotButton` | 0 | The Copilot button is hidden (23H2) |
| DisableCopilotAndRecall | `Software\Policies\Microsoft\Windows\WindowsCopilot\TurnOffWindowsCopilot` | 1 | User policy that turns off Copilot: the only level where it takes effect |
| DisableAutoRun | `...\Explorer\AutoplayHandlers\DisableAutoplay` | 1 | No AutoPlay dialog for media |

## What is intentionally not set

Theme (dark/light), wallpaper, taskbar alignment, the classic context menu, showing
hidden files, disabling animations: all of this is a matter of the user's taste, not of the base image.
If needed, it is added as a separate profile "Cosmetics".

## Verification and rollback

- Verification before sign-in: `reg load HKU\Test C:\Users\Default\NTUSER.DAT`, inspect the values, `reg unload HKU\Test`.
- Verification after sign-in: `Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced -Name HideFileExt`.
- Rollback for a user: Settings or `Set-ItemProperty` in HKCU; for future users: the same
  keys in the Default hive.
