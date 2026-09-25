# 12. Telemetry, advertising and preinstalled apps, Copilot and Recall, widgets, web search

Section 8 of `Setup-System.ps1` plus the related values in the default user profile (section 14).
This is not cosmetics: each item either reduces the data sent outside or removes a channel through
which unwanted apps and links appear on the PC.

## MinimalTelemetry

- Value: `$true`.
- What it does:

| Key | Value | Effect |
|---|---|---|
| `Pol\DataCollection\AllowTelemetry` | 1 | Diagnostic data level «Обязательные» (Required), the minimum for Pro; 0 «Выкл» (Off) works only on Enterprise/Education |
| `Pol\DataCollection\DoNotShowFeedbackNotifications` | 1 | Windows does not ask you to rate the system |
| `Pol\DataCollection\AllowDeviceNameInDiagnosticData` | 0 | The PC name is not sent |
| `Pol\AdvertisingInfo\DisabledByGroupPolicy` | 1 | The advertising ID is disabled for all users |
| `Pol\Windows Error Reporting\Disabled` | 1 | Crash reports are not sent to Microsoft; local events 1000/1001 in the Application log remain |
| `Pol\System\PublishUserActivities` | 0 | Activity history (Timeline) is not collected |
| `Pol\System\UploadUserActivities` | 0 | Nor is it uploaded |
| service `DiagTrack` | Start = 3 (manual) | Not disabled (4): the service is needed by the compatibility appraisal for feature updates and by Defender reports on blocked threats |
| scheduled tasks | disabled | `Customer Experience Improvement Program\Consolidator`, `...\UsbCeip`, `Feedback\Siuf\DmClient`, `...\DmClientOnScenarioDownload` |

- Expected effect: the minimum level of data sending available on Pro, without harming
  updates and Defender. The «Необязательные диагностические данные» (Optional diagnostic data) switch in Settings is grayed out.
- Cross-links:
  - The original file disabled DiagTrack (4) and the Application Experience tasks (Compatibility Appraiser),
    which interfered with feature update offers; here they are kept for the sake of `DeferFeatureUpdatesDays`
    (section 06). The critic confirmed that the Appraiser tasks are absent under their old names on build 26200.
  - Windows Error Reporting is disabled: developer dumps (`LocalDumps`) are not affected; the
    «Программа перестала работать» (Program has stopped working) window appears, but the report is not sent.
- Version differences: the value `AllowTelemetry=0` on Windows 10/11 Pro is treated as 1. In Windows 11
  the level names are: 1 «Обязательные», 3 «Необязательные» (Optional). CEIP tasks are present in 24H2, but
  `Consolidator` may be missing on some builds (a WARN in the log is expected).
- Verification: Settings → Privacy → Diagnostics: «управляется организацией» (managed by your organization);
  `Get-Service DiagTrack | Select StartType` → Manual; `schtasks /Query /TN "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip"` → Disabled.
- Rollback: delete the values; `Set-Service DiagTrack -StartupType Automatic`; `schtasks /Change /Enable`.

## DisableConsumerContent

- Value: `$true`.
- What it does: in `Pol\CloudContent`: `DisableWindowsConsumerFeatures = 1`, `DisableSoftLanding = 1`,
  `DisableCloudOptimizedContent = 1`, `DisableConsumerAccountStateContent = 1`,
  `DisableThirdPartySuggestions = 1`; `Pol\Windows Chat\ChatIcon = 3` (hidden);
  `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Communications\ConfigureChatAutoInstall = 0`.
  Plus 17 `ContentDeliveryManager` values and five more in the default user profile (section 14).
- Expected effect: the Store does not silently install TikTok, Candy Crush and the like; the Start menu and the lock
  screen show no ads and no "tips"; no automatic installation of (personal) Teams; no
  «Завершим настройку устройства» (Let's finish setting up your device) after sign-in.
- Cross-links: on Pro the main working mechanism is the `ContentDeliveryManager` values in the user
  profile (section 14), not the policies. The policies `DisableWindowsConsumerFeatures`,
  `DisableSoftLanding`, `DisableThirdPartySuggestions` work only on Enterprise/Education and are ignored on Pro;
  they are kept as harmless in case of other editions.
  `DisableCloudOptimizedContent` (Windows 10 20H2+/Windows 11) and `DisableConsumerAccountStateContent`
  (Windows 11 22H2+) work on Pro.
- Version differences: `Windows Chat` and `ConfigureChatAutoInstall` apply to Windows 11 21H2-22H2
  (the Teams chat icon); in 23H2+ it no longer exists, and the values are harmless. No changes in 24H2.
- Verification: after installation the Start menu has no pinned third-party apps; Settings →
  Personalization → Lock screen without "fun facts".
- Rollback: delete the values; the preinstalled apps will return the next time the Store contacts the subscription channel.

## DisableCopilotAndRecall

- Value: `$true`.
- What it does:
  - `Pol\WindowsCopilot\TurnOffWindowsCopilot = 1` (machine copy; effective only on 23H2 with Copilot
    Preview) and the same policy in the default user profile (section 14), where it actually applies;
  - `Pol\WindowsAI\DisableAIDataAnalysis = 1`: Recall (screenshots for the PC's "memory") is off;
  - `Pol\WindowsAI\AllowRecallEnablement = 0`: the user cannot enable Recall on their own;
  - `Pol\WindowsAI\DisableClickToDo = 1`: Click to Do (actions on screen content) is off;
  - `Disable-WindowsOptionalFeature -FeatureName Recall`, if the component is enabled;
  - the Copilot app (`Microsoft.Copilot`, `Microsoft.Windows.Ai.Copilot.Provider`) is removed
    through `$AppsToRemove` (section 13); the taskbar button is hidden in the default user profile.
- Expected effect: no AI component takes screenshots or sends document content
  to the cloud; there is no Copilot button.
- Cross-links: Recall and Click to Do exist only on Copilot+ PCs (NPU) since 24H2; on ordinary PCs
  the policies are harmless and protect in advance against these features appearing after an update. The user can reverse
  the removal of the Copilot app through the Store (the Store is kept).
- Version differences: `TurnOffWindowsCopilot` appeared in 23H2 and was declared deprecated in 24H2 (Copilot became
  a regular app). `DisableAIDataAnalysis` since 24H2, `AllowRecallEnablement` and `DisableClickToDo`
  since the 2025 updates. The `Recall` component exists only in 24H2+.
- Verification: `Get-WindowsOptionalFeature -Online -FeatureName Recall` → Disabled or absent;
  `Get-AppxPackage -AllUsers Microsoft.Copilot` is empty.
- Rollback: delete the values; install Copilot from the Store.

## DisableWidgetsAndNews

- Value: `$true`.
- What it does: `HKLM\SOFTWARE\Policies\Microsoft\Dsh\AllowNewsAndInterests = 0` (Windows 11 widgets);
  `Pol\Windows Feeds\EnableFeeds = 0` (the Windows 10 «Новости и интересы» (News and interests) feed); in the default user profile
  `Explorer\Advanced\TaskbarDa = 0` (the widgets button is hidden).
- Expected effect: no widgets button and no panel with news, weather and MSN ads; the background
  process `Widgets.exe` does not start.
- Cross-links: the widgets panel is WebView2 with MSN content, that is, a permanently open web page
  with ads on every PC. Disabling it also removes a delivery channel for malicious advertising (malvertising).
  The `MicrosoftWindows.Client.WebExperience` package is not removed (it is a system package).
- Version differences: the `Dsh` policy since Windows 11 21H2, works on Pro. `Windows Feeds` for
  Windows 10 20H1+. No changes in 24H2.
- Verification: Settings → Personalization → Taskbar: «Виджеты» (Widgets) is grayed out and off.
- Rollback: delete the values.

## DisableWebSearchInStart

- Value: `$true`.
- What it does: `Pol\Explorer\DisableSearchBoxSuggestions = 1` (no Bing results in Start menu search);
  `Pol\Windows Search\AllowCortana = 0`; `Pol\Windows Search\DisableWebSearch = 1`.
- Expected effect: Start menu search looks only for apps, files and settings; nothing is
  sent to Bing on every keystroke; no "recommended" web results.
- Cross-links: Cortana was removed from Windows 11 (2023), so the policy is harmless. File Explorer search and
  indexing (`WSearch`) are not affected: the original file switched the indexing service to
  manual mode, which broke search in Outlook; here it is left untouched.
- Version differences: `DisableSearchBoxSuggestions` since Windows 10 2004, works on Pro. `DisableWebSearch`
  comes from the old Windows 8.1/10 set; on 11 it partially duplicates the first one. No changes in 24H2.
- Verification: searching Start for the word "weather" shows no web results.
- Rollback: delete the values.

## LongPathsEnabled (unconditional)

- What it does: `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`.
- Effect: programs with a `longPathAware` manifest (PowerShell 7, Git, modern archivers) work
  with paths longer than 260 characters. File Explorer and old programs keep the limit.
- Version differences: Windows 10 1607+. Harmless.
- Rollback: value 0.
