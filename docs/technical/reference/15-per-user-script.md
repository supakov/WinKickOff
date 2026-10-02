# 15. Active Setup and Setup-User.ps1: first sign-in settings for each user

Section 11 of `Setup-System.ps1` registers the mechanism; the script itself is embedded in the XML as
`C:\ProgramData\Unattend\Scripts\Setup-User.ps1`.

## The Active Setup mechanism

- Key: `HKLM\SOFTWARE\Microsoft\Active Setup\Installed Components\{7A6C3F5E-2B1D-4C8E-9F0A-5D3E6B7C8D91}`.
- Values: `(Default) = Workgroup per-user setup`, `StubPath = powershell.exe -NoProfile
  -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\ProgramData\Unattend\Scripts\Setup-User.ps1"`,
  `Version = 1,0,0,0`, `IsInstalled = 1`.
- How it works: when a user signs in, Windows compares `Version` in HKLM with the copy in
  `HKCU\Software\Microsoft\Active Setup\Installed Components\{GUID}`. If there is no copy or its version is older,
  `StubPath` runs as the user, synchronously, before File Explorer starts, and then the version is
  copied to HKCU. It does not run again for the same user.
- Expected effect: the first sign-in of each user (Admin, User, any user created later)
  is delayed by 3-10 seconds while the script rearranges the input languages. No window is shown.
- Why not FirstLogonCommands and not a scheduled task: FirstLogonCommands run once
  for the first user who signs in; a task running as SYSTEM has no access to the HKCU of the right user without
  complex token substitution. Active Setup has been a standard mechanism since Windows 98 and works
  in all versions of Windows 10/11.
- Cross-links: `-ExecutionPolicy Bypass` is mandatory (the default policy is Restricted).
  The script runs without elevation: everything it does concerns the current user's HKCU.
  By changing `Version` to `1,0,0,1`, the administrator makes the script run again for everyone
  at their next sign-in (a way to deliver a new version of the settings).
- Version differences: none.
- Verification: `Get-ItemProperty 'HKCU:\Software\Microsoft\Active Setup\Installed Components\{7A6C3F5E-2B1D-4C8E-9F0A-5D3E6B7C8D91}'`
  after sign-in; log `C:\ProgramData\Unattend\Logs\Setup-User.<name>.log`.
- Rollback: delete the key in HKLM (new users will not get it); delete the copy in HKCU (to run it again).

## What Setup-User.ps1 does

Log: `C:\ProgramData\Unattend\Logs\Setup-User.<user name>.log`. A separate file for each user,
because a file created in ProgramData by the first user does not give write access to the second one.

### Step 1. Pinning the display language

`Set-WinUILanguageOverride -Language <InstalledUICulture>`: the display language is explicitly pinned to
the image language. Without this, Windows derives the display language from the first language in the preference list, and
the reordering of the list below (English first) would switch the interface to English after the
next sign-in. The customer's requirement "do not change the display language" rests on this line.

- Version differences: the cmdlet exists since Windows 8. On Windows 11 22H2+ the «Язык и регион» (Language & region) page shows
  «Язык интерфейса Windows» (Windows display language) separately from the language list; the override corresponds to this.
- Rollback: `Set-WinUILanguageOverride` without a parameter removes the pinning.

### Step 2. Input language list

1. A list is created: `en-US`, then `uk-UA`, then `ru-UA` ("Russian (Ukraine)").
2. `Set-WinUserLanguageList -Force`: applied without a prompt.
3. Verification: `Get-WinUserLanguageList` must contain `ru-UA` with a non-empty `InputMethodTips`.
   On build 26200 Windows assigns it the temporary identifier `2000:00000419`, that is, the Russian
   keyboard layout under a temporary language code (in the registry, `Keyboard Layout\Preload` gets `00002000`
   with the substitution `Substitutes\00002000 = 00000419`).
4. If `ru-UA` is missing or has no keyboard layout, or any command failed: the fallback list `en-US`,
   `uk-UA`, `ru` (plain "Russian"), also with `-Force`.

- Expected effect: the user's language switcher shows ENG, «УКР» (UKR), «РУС» (RUS); the last one is displayed as
  "Russian (Ukraine)" and is listed in Settings with the region Ukraine. The order matches the sign-in screen.
- Cross-links:
  - The sign-in screen and the default user profile received the list from `InputLocale` (section 03) with plain
    Russian; the script changes only the current user's list. The mismatch (sign-in screen "Russian",
    user "Russian (Ukraine)") is expected and harmless.
  - The Ukrainian keyboard layout in the user's list: `0422:00020422` (extended), same as in the XML.
  - Language packs for `ru-UA` are not needed: it is an input language, not a display language; Windows does not try
    to download an LXP.
  - Changes the user makes to the list in Settings persist: the script does not run again.
  - A test on the customer's work PC on 12.09.2026 showed that `Set-WinUserLanguageList` changes the live
    session not fully in sync with the registry; for a new user at first sign-in this does not
    show up, because the session is only being created.
- Version differences: `ru-UA` as an input language is supported in Windows 10 1803+ and Windows 11 (the
  CLDR list); on older builds the fallback applies. The cmdlets of the International module
  exist in all versions.
- Verification: `Get-WinUserLanguageList | Select LanguageTag, InputMethodTips` under the user's
  account; the log contains the line `applied: en-US[0409:00000409] uk-UA[0422:00020422] ru-UA[2000:00000419]`.
- Rollback: Settings → Language & region, or `Set-WinUserLanguageList` with the required list.

### Completion

`exit 0`. Active Setup does not analyze the exit code, but consistency with the other scripts is kept.
