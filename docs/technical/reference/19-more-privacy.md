# 19. More privacy options: AI, telemetry, advertising, search, speech, Office, OneDrive, drivers, Explorer

Rules from the customer's list of 28.09.2026 (file MoreOptions: "AI and telemetry must be off; the whole list is
on by default everywhere except memstechtips"). Every value was checked on 28.09.2026 against Microsoft Learn
(Policy CSP, ADMX reference, "Manage connections from Windows operating system components to Microsoft
services", Microsoft 365 Apps privacy controls, OneDrive Group Policy), the ADMX templates shipped with Windows 11
25H2 (26200) and read-only registry queries on a 26200 PC. Where the list had a wrong path, an internal value,
a value that does not exist or an obsolete one, the catalog uses the documented equivalent or leaves the item
out; the section "Corrections to the list" names each case.

All rules below are on by default, so they are in the «Офис» (Office), «Строгий» (Strict) and «Ноутбук» (Laptop)
presets; the memstechtips preset takes a rule only when the original file has its actions. Per-user values are
written into the default user profile (phase default-user), so every account created during and after the
installation gets them; accounts that already exist on a running PC keep their own values.

Status column: D documented by Microsoft; P preview policy (in the 26200 ADMX, not yet confirmed for Pro);
U undocumented value of a Settings switch (community sources), harmless.

## Windows AI

| Rule | Values | Effect | Status |
|---|---|---|---|
| `privacy.copilot-recall-off` (v0.2) | `HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsAI` DisableAIDataAnalysis=1, AllowRecallEnablement=0, DisableClickToDo=1; `...\WindowsCopilot` TurnOffWindowsCopilot=1 | Recall, snapshots and Click to Do off; the machine copy of TurnOffWindowsCopilot is not documented (the user copy is) | D |
| `default-user.copilot-off` (v0.2) | `HKCU\Software\Policies\Microsoft\Windows\WindowsCopilot` TurnOffWindowsCopilot=1 and the taskbar button | Old Copilot sidebar off; deprecated in 24H2, the Copilot app itself is removed by `apps.remove.copilot` | D |
| `ai.recall-user-off` | `HKCU\Software\Policies\Microsoft\Windows\WindowsAI` DisableAIDataAnalysis=1, DisableClickToDo=1 | User copies of the Recall and Click to Do policies | D |
| `ai.settings-agent-off` | `...\WindowsAI` DisableSettingsAgent=1 | No AI agent in the Settings search | P |
| `ai.agent-connectors-off` | `...\WindowsAI` ConfigureAgentConnectors=2 | Agent connectors (MCP servers for AI agents) forced off | P |
| `ai.apps-generative-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy` LetAppsAccessSystemAIModels=2 | Apps cannot use the Windows text and image generation models; the Settings switch is locked | D (ADMX) |
| `ai.copilot-microphone-off` | `...\AppPrivacy` LetAppsAccessMicrophone=0, LetAppsAccessMicrophone_ForceDenyTheseApps = Microsoft.Copilot_8wekyb3d8bbwe, Microsoft.MicrosoftOfficeHub_8wekyb3d8bbwe | The two Copilot apps never get the microphone; other apps ask the user as usual | D |
| `ai.paint-off` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint` DisableImageCreator, DisableCocreator, DisableGenerativeFill = 1 (D); DisableGenerativeErase, DisableRemoveBackground = 1 (U, from the list) | Paint AI features hidden | D and U |
| `ai.notepad-off` | `HKLM\SOFTWARE\Policies\WindowsNotepad` DisableAIFeatures=1 | Copilot features of Notepad off (Notepad 11.2503.16.0+) | D |
| `ai.copilot-pin-screen-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\CloudContent` DisableCopilotPinScreen=1 | No Microsoft 365 Copilot setup screen at sign-in | P |
| `ai.typing-insights-off` | `HKCU\Software\Microsoft\Input\Settings` InsightsEnabled=0 | No local typing statistics; not AI and not telemetry, kept because it is on the list | U |

## Telemetry and feedback

| Rule | Values | Effect | Status |
|---|---|---|---|
| `privacy.telemetry-minimal` (v0.2) | `HKLM\SOFTWARE\Policies\Microsoft\Windows\DataCollection` AllowTelemetry = parameter `level`, default 1; feedback, advertising ID, WER, activity history, DiagTrack, CEIP tasks | Since 28.09.2026 the level is a parameter: 1 (Required) or 0 (Security). Pro treats 0 as 1; on Enterprise or Education 0 really stops the data, which Microsoft advises against for PCs updated by Windows Update (compatibility data for safeguard holds). The default stays 1, the lowest level Pro sends | D |
| `telemetry.settings-state` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\DataCollection` AllowTelemetry=1, MaxTelemetryAllowed=1 | State of the Settings page «Диагностика и отзывы» (Diagnostics & feedback): Required, no higher level offered. Not a policy; the policy above decides | U |
| `telemetry.user-policy` | `HKCU\Software\Policies\Microsoft\Windows\DataCollection` AllowTelemetry=1 | User copy of the policy; when both exist the more restrictive applies | D |
| `telemetry.change-notification-off` | `...\DataCollection` DisableTelemetryOptInChangeNotification=1 | No toast about the diagnostic data level; documented replacement of ShowedToastAtLevel | D |
| `telemetry.limit-logs-dumps` | `...\DataCollection` LimitDiagnosticLogCollection=1, LimitDumpCollection=1 | No extra logs, only minidumps; takes effect only if Optional data is ever turned on | D |
| `telemetry.app-telemetry-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\AppCompat` AITEnable=0 | Application Telemetry engine off. DisableInventory, which touches compatibility data, is not set | D |
| `telemetry.steps-recorder-off` | `...\AppCompat` DisableUAR=1 | Steps Recorder off (deprecated tool, used by "tech support" scammers) | D |
| `telemetry.app-diagnostics-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy` LetAppsGetDiagnosticInfo=2 | Apps cannot read diagnostic data of other apps | D |
| `telemetry.feedback-user-off` | `HKCU\Software\Microsoft\Siuf\Rules` NumberOfSIUFInPeriod=0 | Feedback frequency "Never"; the machine policy DoNotShowFeedbackNotifications is in `privacy.telemetry-minimal` | D |

## Advertising and suggestions

| Rule | Values | Effect | Status |
|---|---|---|---|
| `privacy.consumer-content`, `privacy.widgets-off`, `default-user.no-consumer-content`, `default-user.no-sync-provider-ads`, `default-user.http-accept-language-optout` (v0.2 and 25.09) | cards 12 and 14 | Moved into this subsection; ContentDeliveryAllowed, SubscribedContent-338393/353694/353696Enabled, AdvertisingInfo Enabled, HttpAcceptLanguageOptOut and DisableConsumerAccountStateContent of the list are already there | D and U |
| `ads.lock-screen-spotlight-off` | `HKCU\...\ContentDeliveryManager` RotatingLockScreenEnabled=0, SubscribedContentEnabled=0 | No Spotlight pictures on the lock screen; the meaning of SubscribedContentEnabled is not documented | U |
| `ads.suggestions-user-policies` | `HKCU\Software\Policies\Microsoft\Windows\CloudContent` DisableTailoredExperiencesWithDiagnosticData=1, DisableThirdPartySuggestions=1 | No tailored tips, no third-party app suggestions (user policies, Pro supported) | D |
| `ads.account-notifications-off` | `HKCU\...\SystemSettings\AccountNotifications` EnableAccountNotifications=0 | No account and service prompts in Settings | U |
| `ads.advertising-id-user-off` | `HKCU\...\CPSS\Store\AdvertisingInfo` Value=0 | Advertising ID switch of the newer Settings store | U |

The desktop Spotlight wallpaper that Windows 11 uses by default since late 2024 is not governed by these
values, and its policy is Enterprise/Education only; a fixed wallpaper is a separate decision.

## Search and Start

| Rule | Values | Effect | Status |
|---|---|---|---|
| `privacy.web-search-off` (v0.2) | card 12 | No Bing results in Start search | D |
| `search.cloud-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\Windows Search` AllowCloudSearch=0, EnableDynamicContentInWSB=0, AllowSearchToUseLocation=0 | No cloud content, no search highlights, no location in search | D |
| `search.user-cloud-off` | `HKCU\...\SearchSettings` IsAADCloudSearchEnabled, IsMSACloudSearchEnabled, IsDynamicSearchBoxEnabled, IsDeviceSearchHistoryEnabled = 0 | The same switches in the user profile and no local search history | U |
| `search.start-track-off` | `HKCU\...\Explorer\Advanced` Start_TrackProgs=0 | App launches are not tracked for Start and search | D |

## Speech and input

| Rule | Values | Effect | Status |
|---|---|---|---|
| `speech.online-off` | `HKLM\SOFTWARE\Policies\Microsoft\InputPersonalization` AllowInputPersonalization=0; `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\TextInput` AllowLinguisticDataCollection=0 | Online speech recognition cannot be enabled; inking and typing data are not sent | D |
| `speech.online-user-off` | `HKCU\...\Speech_OneCore\Settings\OnlineSpeechPrivacy` HasAccepted=0; `HKCU\Software\Microsoft\InputPersonalization` RestrictImplicitInkCollection=1, RestrictImplicitTextCollection=1; `...\TrainedDataStore` HarvestContacts=0; `HKCU\Software\Microsoft\Personalization\Settings` AcceptedPrivacyPolicy=0 | Online speech and the personal inking and typing dictionary off | D and U |
| `speech.narrator-online-off` | `HKCU\Software\Microsoft\Narrator\NoRoam` OnlineServicesEnabled=0 | Narrator sends no images to the cloud for descriptions | U |
| `speech.narrator-extensions-off` | `...\Narrator\NoRoam` ScriptingEnabled=0 | Narrator extensions (Excel, Outlook) off. From the list; it is an accessibility feature, not telemetry: blind users lose part of Narrator | U |

## Microsoft Office

Per-user policies of Microsoft 365 Apps 1904+, Office 2021 and 2024 (retail and LTSC), written into the default
profile before Office is installed. For the privacy values 2 means Disabled.

| Rule | Values | Effect | Status |
|---|---|---|---|
| `office.connected-ai-off` | `HKCU\Software\Policies\Microsoft\office\16.0\common\privacy` usercontentdisabled=2 | "Connected experiences that analyze content" off: the only documented switch that removes Copilot from Word, Excel, PowerPoint, Outlook and OneNote for every account type; also dictation, Translator, cloud Editor, Designer, text predictions | D |
| `office.optional-connected-off` | `...\privacy` controllerconnectedservicesenabled=2 | Optional connected experiences (Bing-based: Smart Lookup, Researcher, online pictures, Copilot web search) off | D |
| `office.download-content-off` (off by default) | `...\privacy` downloadcontentdisabled=2 | No online templates, icons, pictures, fonts, help; not AI | D |
| `office.telemetry-off` | `HKCU\Software\Policies\Microsoft\office\common\clienttelemetry` sendtelemetry=3 | Diagnostic data level "Neither" (note: no 16.0 in the path) | D |
| `office.feedback-off` | `...\16.0\common\feedback` enabled=0, surveyenabled=0 | No feedback and surveys, so no screenshots, logs or Copilot prompts in feedback | D |
| `office.copilot-checkbox-off` | `HKCU\Software\Microsoft\Office\16.0\Word\Options`, `...\Excel\Options` EnableCopilot=0; `...\OneNote\Options\Other` EnableCopilot, EnableCopilotNotebooks, EnableCopilotSkittle = 0 | Values of the list behind the "Enable Copilot" check box, which exists only with a personal Microsoft account; not locked, the user can re-enable | U |

`disconnectedstate=2` is deliberately not offered: it also switches off co-authoring, OneDrive and SharePoint
saving, Safe Links and Safe Documents.

## OneDrive policies

| Rule | Values | Effect | Status |
|---|---|---|---|
| `apps.remove.onedrive` (26.09) | card 13 | OneDrive is not installed for new users | D |
| `onedrive.kfm-block` | `HKLM\SOFTWARE\Policies\Microsoft\OneDrive` KFMBlockOptIn=1 | Desktop, Documents and Pictures cannot be moved to any OneDrive; needed on non-domain PCs | D |
| `onedrive.no-traffic-before-signin` | `...\OneDrive` PreventNetworkTrafficPreUserSignIn=1 | No OneDrive traffic before a user signs in to OneDrive (stays in effect after removal of the policy) | D |
| `onedrive.feedback-off` | `...\OneDrive` EnableSendFeedback=0, EnableSurveyCampaigns=0, EnableContactSupport=0 | No feedback, surveys or support contact | D |
| `onedrive.block` (off by default) | `HKLM\SOFTWARE\Policies\Microsoft\Windows\OneDrive` DisableFileSyncNGSC=1 | OneDrive cannot be used at all; an organisational decision | D |
| `onedrive.personal-sync-off` (off by default) | `HKCU\Software\Policies\Microsoft\OneDrive` DisablePersonalSync=1 | No personal (Microsoft account) OneDrive | D |

## Drivers and devices

| Rule | Values | Effect | Status |
|---|---|---|---|
| `drivers.coinstallers-off` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Device Installer` DisableCoInstallers=1 | Legacy INF co-installers do not run as SYSTEM during device installation (Razer Synapse case, 2021); drivers still install. Vendor utilities of old printers and scanners must be installed by hand: test with the organisation's devices | U (widely used) |
| `drivers.metadata-off` | `HKLM\SOFTWARE\Policies\Microsoft\Windows\Device Metadata` PreventDeviceMetadataFromNetwork=1 | No apps and icons of devices from the internet | D |

Neither value blocks drivers from Windows Update; `ExcludeWUDriversInQualityUpdate` and `SearchOrderConfig` are
never set.

## This PC folders

From the customer's file `enable_namespaces_in_mypc.reg` (28.09.2026): "add every Explorer namespace, also the
missing ones; by default the icons are not shown". Read-only inspection of a 26200 PC: `HKLM\SOFTWARE\Microsoft\
Windows\CurrentVersion\Explorer\MyComputer\NameSpace` and its WOW6432Node twin hold 11 entries, each with
`HiddenByDefault=1` (1 hides, 0 shows; since 22H2, without the feature gate `HideIfEnabled` since 24H2). The file
of the customer unhides the five Local entries and leaves the rest hidden; it touches only the 64-bit view.

Every rule writes both views (32-bit programs use the WOW6432Node view in their Open and Save dialogs). All
«Показывать ...» (Show ...) rules are off by default, so This PC shows only drives, as Windows 11 does.

| Rule | Entry (GUID, internal name) | Points to | Remarks |
|---|---|---|---|
| `thispc.desktop` | {B4BFCC3A-DB2C-424C-B029-7FE99A87C641} ThisPCDesktopRegFolder | FOLDERID_Desktop | Shown by Windows 10; no second entry |
| `thispc.documents` | {d3162b92-9365-467a-956b-92703aca08af} ThisPCLocalDocumentsRegFolder | FOLDERID_LocalDocuments | Shown by Windows 10 (ThisPCPolicy Show) |
| `thispc.downloads` | {088e3905-0323-4b02-9826-5d99428e115f} ThisPCLocalDownloadsRegFolder | FOLDERID_LocalDownloads | Same |
| `thispc.music` | {3dfdf296-dbec-4fb4-81d1-6a3438bcf4de} ThisPCLocalMusicRegFolder | FOLDERID_LocalMusic | Same |
| `thispc.pictures` | {24ad3ad4-a569-4530-98e1-ab02f9417aa8} ThisPCLocalPicturesRegFolder | FOLDERID_LocalPictures | Same |
| `thispc.videos` | {f86fa3ab-70d2-4fc7-9c99-fcbf05467f3a} ThisPCLocalVideosRegFolder | FOLDERID_LocalVideos | Same |
| `thispc.documents-extra` | {A8CDFF1C-4878-43be-B5FD-F8091C1C60D0} ThisPCDocumentsRegFolder | FOLDERID_Documents | Second entry of the same folder (ThisPCPolicy Hide); showing both can duplicate the folder |
| `thispc.downloads-extra` | {374DE290-123F-4565-9164-39C4925E467B} ThisPCDownloadsRegFolder | FOLDERID_Downloads | Same |
| `thispc.music-extra` | {1CF1260C-4DD0-4ebb-811F-33C572699FDE} ThisPCMyMusicRegFolder | FOLDERID_Music | Same |
| `thispc.pictures-extra` | {3ADD1653-EB32-4cb0-BBD7-DFA0ABB5ACCA} ThisPCMyPicturesRegFolder | FOLDERID_Pictures | Same |
| `thispc.videos-extra` | {A0953C92-50DC-43bf-BE83-3742FED03C9C} ThisPCMyVideosRegFolder | FOLDERID_Videos | Same |
| `thispc.3d-objects` | {0DB7E03F-FC29-4DC6-9020-FF41B59E513A} 3D Objects | FOLDERID_3DObjects | Missing from the file: the entry was removed in Windows 11 (the known folder remains, PreCreate=0); the rule creates it with `HiddenByDefault=0`. Its return to defaults is manual (delete the key) |

The Local and the classic known folders resolve to the same profile folder; "Local" does not mean "outside
OneDrive" (with OneDrive folder backup both are redirected). The return-to-defaults value of `HiddenByDefault`
is 1, the state of 24H2 and 25H2; Windows 10 does not have the value.

Navigation pane (`...\Explorer\Desktop\NameSpace`, both views), also missing from the file:

| Rule | Entry | Default | Remarks |
|---|---|---|---|
| `nav.gallery-hidden` | {e88865ea-0e1c-4e20-9aa6-edcd0212c87c} «Галерея» (Gallery) | on | `HiddenByDefault=1`; no side effects known |
| `nav.home-hidden` | {f874310e-b6b7-47dc-bc84-b9e6b38f5903} «Главная» (Home), CLSID_MSGraphHomeFolder | off | Requires `nav.launch-to-this-pc` (`LaunchTo=1` in the default profile), because Explorer opens on Home. With the This PC folders hidden, users would lose the quick way to Documents; reports say Quick access pins disappear with Home |
| `nav.launch-to-this-pc` | `HKCU\...\Explorer\Advanced` LaunchTo=1 | off | Explorer opens on This PC |

Not generated: Network, Libraries, OneDrive and Linux entries of the navigation pane (Libraries are hidden by
default, OneDrive is not installed, Linux appears only with WSL, Network is needed for shared folders);
`ThisPCPolicy` of `FolderDescriptions` (on 22H2 and later `HiddenByDefault` decides; whether ThisPCPolicy still
hides is unverified); the `DelegateFolders` of This PC (portable devices and similar data sources).

Verification: open This PC and press F5; after a feature update Windows may restore its defaults, and the
«Этот ПК» (This PC) menu applies the rules again.

## Corrections to the list

| Item of the list | Finding | In WinKickOff |
|---|---|---|
| WindowsAI TurnOffSavingSnapshots | Not a value: it is the display name of the DisableAIDataAnalysis policy | DisableAIDataAnalysis (machine and user) |
| WindowsAI DisableAgentConnectors, DisableAgentWorkspaces, DisableRemoteAgentConnectors | Not defined by Microsoft (ADMX, CSP, preview list) | ConfigureAgentConnectors=2; the agent workspace is only switched on by an administrator in Settings |
| WindowsAI SetCopilotHardwareKey | Lives in `HKCU\...\CopilotKey`; takes an app ID, has no "off" value | Not generated |
| WindowsAI AllowCopilotRuntime, IsCopilotAvailable, IsUserEligible | Internal shell state that Windows rewrites | Not generated |
| ConsentStore generativeAI Value, systemAIModels Value and RecordUsageData, AppPrivacy LetAppsAccessGenerativeAI | generativeAI is absent on 26200 (old Insider name), the others are internal state or the old policy name | LetAppsAccessSystemAIModels=2 |
| ConsentStore microphone for Microsoft.Copilot and Microsoft.MicrosoftOfficeHub | Internal per-app state | LetAppsAccessMicrophone_ForceDenyTheseApps with both apps |
| `HKLM\SOFTWARE\Policies\Microsoft\Paint` | Wrong path | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Paint` |
| Explorer\Advanced ShowCopilotNudges | Not present on 26200 and not documented | Not generated |
| Edge CopilotCDPPageContext | Obsolete after Edge 132 | EdgeEntraCopilotPageContext |
| Edge DevToolsGenAiSettings | Not an Edge policy (Chrome only) | Kept for Chrome (`chrome.devtools-genai-off`) |
| Edge CopilotPageContext, EdgeEntraCopilotPageContext, Microsoft365CopilotChatIconEnabled, ComposeInlineEnabled, ShareBrowsingHistoryWithCopilotSearchAllowed | Apply only to Microsoft Entra ID profiles | Generated and on as the list asks, marked "Entra ID profiles"; no effect with local accounts |
| Office common\ai\training optionalconnectedexperiencesenabled, common\ai contentsafetyserviceenabled | Not found in any Microsoft source; the content safety policies moderate AI, they do not turn it off | Not generated; usercontentdisabled and controllerconnectedservicesenabled cover the intent |
| OneDrive KFMBlockOptIn in HKCU | Documented for the machine only | HKLM value only |
| Diagnostics\DiagTrack ShowedToastAtLevel | State written by Windows | DisableTelemetryOptInChangeNotification=1 |
| `HKCU\...\CurrentVersion\Policies\DataCollection` AllowTelemetry, MaxTelemetryAllowed | Written by tweak tools; Windows reads the machine copy | HKLM copy (`telemetry.settings-state`) and the user policy (`telemetry.user-policy`) |
| AllowTelemetry = 0 | Pro treats 0 as 1; 0 matters only on Enterprise and Education and there hurts the update safeguards | Parameter of `privacy.telemetry-minimal`, default 1 |
| `HKCU\...\Policies\Microsoft\Windows\DataCollection` DoNotShowFeedbackNotifications, `HKCU\...\AppCompat` AITEnable, `HKCU\...\AdvertisingInfo` DisabledByGroupPolicy, `HKCU\...\InputPersonalization` AllowInputPersonalization | No user-scope policy exists | Machine policies, plus the per-user Settings values where they exist |
| PolicyManager\default\WiFi AllowWiFiHotSpotReporting, AllowAutoConnectToWiFiSenseHotspots | Wi-Fi Sense was removed in Windows 10 1803 | Not generated |
| ConsentStore appDiagnostics Value | Internal state of the Settings switch | LetAppsGetDiagnosticInfo=2 |

Values that were considered and left out on purpose: `DisableOneSettingsDownloads` (Microsoft asks not to block
that endpoint, it keeps safeguard-hold data current), `DisableInventory` (touches compatibility data),
`DisableDiagnosticDataViewer` (no privacy gain), `DisableWindowsSpotlightFeatures` and `ConnectedSearchUseWeb`
(not supported on Pro), `RemoveMicrosoftCopilotApp` (conditional; the app removal rule is more reliable).

## Verification and rollback

- Verification: `reg query` of the keys above; Settings pages show "Some settings are managed by your
  organization"; `edge://policy` for Edge; in Office, File, Account, Account Privacy. The «Этот ПК» (This PC) menu
  of WinKickOff checks every rule on a running PC.
- Rollback: every rule has a Windows default for «Вернуть выбранное к умолчаниям Windows» (Return the selection to
  Windows defaults): policies are removed, per-user values return to «нет значения».

## Sources

- Policy CSP: WindowsAI, Privacy, Experience, System, Search, AppCompat (ADMX), TextInput, DeviceInstallation,
  learn.microsoft.com/windows/client-management/mdm/.
- Manage Copilot, Recall, Click to Do and Notepad, learn.microsoft.com/windows/client-management/.
- Configure Windows diagnostic data; Manage connections from Windows components to Microsoft services,
  learn.microsoft.com/windows/privacy/.
- Microsoft 365 Apps privacy controls, learn.microsoft.com/microsoft-365-apps/privacy/.
- OneDrive Group Policy, learn.microsoft.com/sharepoint/use-group-policy.
- ADMX templates of Windows 11 25H2 (26200) in `C:\Windows\PolicyDefinitions` (read only).
