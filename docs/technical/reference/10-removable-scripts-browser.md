# 10. Removable media, script files, Microsoft Edge

Section 6 of `Setup-System.ps1`. The three vectors through which a non-professional user most often
runs malicious code: a USB flash drive, a script attachment, a downloaded file.

## DisableAutoRun

- Value: `$true`.
- What it does:
  - `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer\NoDriveTypeAutoRun = 255 (0xFF)`:
    AutoRun is disabled for all drive types (removable, fixed, network, CD, RAM);
  - `...\Policies\Explorer\NoAutorun = 1`: `autorun.inf` files are not processed, even for CDs;
  - `Pol\Explorer\NoAutoplayfornonVolume = 1`: AutoPlay is off for devices without a drive
    letter (cameras, phones over MTP);
  - in the default user profile (section 14) `Explorer\AutoplayHandlers\DisableAutoplay = 1`: the
    «Что делать с этим носителем?» (Choose what to do with this device?) dialog is turned off.
- Expected effect: connecting a flash drive, a disk or a phone launches nothing and asks nothing.
  The content is opened only manually through File Explorer.
- Cross-links: manually launching a file from a flash drive remains possible; it is covered by the ASR rule
  "untrusted processes from USB" (section 07) and by cloud protection. The option in Settings → Devices →
  AutoPlay becomes grayed out.
- Version differences: since Windows 7 (after update KB971029) `autorun.inf` on USB is always ignored;
  for CD/DVD it still works, so `NoAutorun` is needed. No changes in 24H2.
- Verification: `Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer`.
- Rollback: delete the three values.

## ScriptFilesOpenInNotepad

- Value: `$true`.
- What it does: for the ProgIds `JSFile`, `JSEFile`, `VBSFile`, `VBEFile`, `WSFFile`, `WSHFile`, `htafile`
  the default value of the key `HKLM\SOFTWARE\Classes\<ProgId>\Shell\Open\Command` is replaced with
  `"%SystemRoot%\System32\notepad.exe" "%1"` (type REG_EXPAND_SZ).
- Expected effect: double-clicking a `.js`, `.jse`, `.vbs`, `.vbe`, `.wsf`, `.wsh`, `.hta` file
  (including one disguised as a document: `счёт.pdf.js`) opens its text in Notepad instead of
  running it. This closes the classic "archive with a script inside" phishing scenario.
- Cross-links:
  - `cscript.exe file.vbs`, `wscript.exe file.vbs`, `mshta.exe file.hta` from the command line and from
    programs still work: only the shell association is changed. Installers that launch `.vbs`
    via `ShellExecute` (rare) will open Notepad; for them a rollback for the specific ProgId is needed.
  - An association in HKCU (`Software\Classes\...`) overrides HKLM: a user who "restored" the
    association through «Открыть с помощью» (Open with) cancels the protection for themselves.
  - The ASR rule "JavaScript/VBScript launch downloaded content" (section 07) and `RemoveVBScript` below
    cover launching through the engine directly.
  - Showing file extensions in the default user profile (section 14) gives the user a chance to notice `.js`.
- Version differences: the ProgIds have been the same since Windows XP. In Windows 11 24H2 VBScript became an
  optional feature (see below), but it is still installed by default, and the associations exist.
- Verification: `(Get-ItemProperty 'HKLM:\SOFTWARE\Classes\VBSFile\Shell\Open\Command').'(default)'`.
- Rollback: restore the default values, for example for VBS:
  `"%SystemRoot%\System32\WScript.exe" "%1" %*`; for JS the same with `WScript.exe`; for HTA
  `"%SystemRoot%\System32\mshta.exe" "%1" %*`.

## RemoveVBScript

- Value: `$false` (the engine is kept).
- What it does with `$true`: `Remove-WindowsCapability -Online -Name VBSCRIPT~~~~` (all versions).
- Expected effect with `$true`: the VBScript interpreter is removed; neither `.vbs` files, nor VBScript macros
  in old programs, nor the `MSScriptControl` component work.
- Why it is off: installers of programs from the 2000s, some printer drivers and old
  corporate applications use VBScript; on 24H2 the engine is also still needed by system components of
  third-party vendors. The Notepad association (above) gives most of the protection without breaking anything.
- Cross-links: JScript cannot be removed (it is not a component); it is covered by the associations and ASR.
- Version differences: the `VBSCRIPT~~~~` capability exists only in Windows 11 24H2 and later; on 23H2 and
  Windows 10 the engine is inseparable, so the command will log WARN and do nothing. Microsoft plans to remove
  VBScript from the image in future versions.
- Verification: `Get-WindowsCapability -Online -Name 'VBSCRIPT*'`.
- Rollback: `Add-WindowsCapability -Online -Name VBSCRIPT~~~~` (requires internet access or a source).

## EdgeSmartScreenLocked and unconditional Edge policies

Edge is kept as an "emergency" browser: without it, no other browser can be downloaded after installation.
Policies are in `HKLM\SOFTWARE\Policies\Microsoft\Edge`.

| Policy | Value | Condition | Effect |
|---|---|---|---|
| SmartScreenEnabled | 1 | EdgeSmartScreenLocked | Reputation checks for sites and downloads |
| SmartScreenPuaEnabled | 1 | EdgeSmartScreenLocked | Blocking of unwanted downloads |
| PreventSmartScreenPromptOverride | 1 | EdgeSmartScreenLocked | The user cannot «перейти на сайт» (continue to the site) after a warning |
| PreventSmartScreenPromptOverrideForFiles | 1 | EdgeSmartScreenLocked | The user cannot «сохранить всё равно» (keep anyway) a blocked file |
| HideFirstRunExperience | 1 | always | No first-run wizard and no import offers |
| ShowRecommendationsEnabled | 0 | always | No promotional tips in the interface |
| PersonalizationReportingEnabled | 0 | always | Browsing data is not sent for ad personalization |
| StartupBoostEnabled | 0 | always | Edge does not stay in memory after it is closed |
| BackgroundModeEnabled | 0 | always | No Edge background processes |

- Expected effect: Edge protects against phishing and malicious downloads without the option to bypass
  a warning with one click; shows no ads; takes no memory in the background.
- Cross-links: Edge SmartScreen does not replace shell SmartScreen (section 07): the first works
  on download, the second when a file is launched. Other browsers (Chrome, Firefox) are not managed by these
  policies; Defender network protection (section 07) covers them as well. The policies gray out the corresponding
  items in `edge://settings`.
- Version differences: Edge policies are supported since Edge 77+ (2019) and are updated together with the browser,
  independently of the Windows version. `PreventSmartScreenPromptOverrideForFiles` since Edge 79.
- Verification: `edge://policy` shows all nine with the source «Machine».
- Rollback: delete the values from the policy key.
