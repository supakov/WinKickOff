# 03. oobeSystem pass: languages and region, OOBE screens, starter accounts

## Microsoft-Windows-International-Core component

All four values are set. According to the "Automate OOBE" documentation, the language and region selection screen
is skipped only if all four are set; otherwise OOBE asks for whatever is missing.

### InputLocale

- Value: `0409:00000409;0422:00020422;0419:00000419`.
- What it does: the list of input languages for the sign-in screen and the default user profile, in this order:
  1. `0409:00000409` English (United States), US keyboard layout;
  2. `0422:00020422` Ukrainian, «Украинская (расширенная)» (Ukrainian (Enhanced)) keyboard layout (with the apostrophe and the letter `Ґ` on regular keys);
  3. `0419:00000419` Russian, «Русская» (Russian) keyboard layout.
  The first one in the list becomes the default input language.
- Expected effect: on the sign-in screen the languages switch ENG → UKR → RUS. New users get the same list.
- Cross-links: "Russian (Ukraine)" (`ru-UA`) cannot be written here: it has no numeric language code
  (LCID 0x1000, a temporary identifier is assigned by the system). It is substituted by `Setup-User.ps1` at
  each user's first sign-in (section 15). Until then the user has the plain "Russian".
- Version differences: the `LCID:KLID` format is the same for Windows 7 and later. The `00020422` keyboard layout exists
  in Windows 8 and later. At first sign-in Windows 11 may add the language of the region (`uk-UA` is already present).
- Verification: the language indicator on the sign-in screen; in the system, `Get-WinUserLanguageList` for a new user.
- Rollback: Settings → Time & language → Language & region, or `Set-WinUserLanguageList`.

### SystemLocale

- Value: `uk-UA`.
- What it does: the language for non-Unicode programs (ANSI code page 1251, OEM 866).
- Expected effect: legacy programs (1C 7.7, old accounting systems, console utilities) display
  Cyrillic instead of "mojibake". Code page 1251 is shared by Ukrainian and Russian, so
  choosing `uk-UA` also covers legacy Russian-language programs.
- Cross-links: does not affect the display language or input. Changing it requires a reboot. The
  «Бета: использовать Юникод UTF-8» (Beta: Use Unicode UTF-8) option is not enabled (it breaks some legacy programs).
- Version differences: none.
- Verification: `Get-WinSystemLocale`.
- Rollback: `Set-WinSystemLocale ru-RU` (or another value) and a reboot.

### UILanguage

- Value: `uk-UA`.
- What it does: the system display language. It must match the ISO language: a value that is not present in the
  image is ignored, and a missing value causes the language selection screen to appear in OOBE.
- Expected effect: the interface is in the ISO language, the language screen in OOBE is not shown. The customer's requirement
  "do not change the display language" is met: the value equals the image language rather than changing it.
- Cross-links: `Setup-User.ps1` additionally pins the display language via
  `Set-WinUILanguageOverride`, so that reordering the input languages does not switch the interface.
  If the ISO is replaced with an English one, the value must be changed to `en-US` (a constructor parameter,
  derived from the ISO).
- Version differences: in Windows 11 22H2 and later, language packs are installed as LXPs via the Store;
  if a language that is not in the image is specified, the system stays in the image language without an error.
- Verification: `Get-WinSystemLocale`, `dism /online /get-intl`, `[CultureInfo]::InstalledUICulture`.
- Rollback: Settings → Language & region → Windows display language.

### UserLocale

- Value: `uk-UA`.
- What it does: the regional format: dates `дд.мм.рррр`, 24-hour time, comma as the decimal separator,
  currency ₴, Monday as the first day of the week.
- Expected effect: Excel, accounting programs and File Explorer show dates and numbers in the Ukrainian format.
- Cross-links: the region (country) is set separately in the default profile (`Geo\Nation=241`, section 14).
  The format affects CSV parsing and data import in accounting programs: the list separator is ";".
- Version differences: none.
- Verification: `Get-Culture`.
- Rollback: Settings → Language & region → Regional format.

## Microsoft-Windows-Shell-Setup / OOBE component

| Element | Value | What it hides or sets | Note |
|---|---|---|---|
| HideEULAPage | true | The license screen in OOBE | In Setup the license is accepted via `AcceptEula` |
| HideOEMRegistrationScreen | true | The manufacturer registration screen | Appears only on OEM images |
| HideOnlineAccountScreens | true | The screens for signing in with a Microsoft account and for creating a local account | Works because the accounts are defined in `LocalAccounts` |
| HideWirelessSetupInOOBE | true | The «Подключитесь к сети» (Connect to a network) screen | The screen is skipped anyway on a wired connection; here it is always hidden |
| ProtectYourPC | 3 | The privacy settings screen | 3 = turn off all «экспресс-параметры» (express settings): data sending, advertising, location detection. SmartScreen and Defender are not affected: they are enabled separately in `Setup-System.ps1` |

- Expected effect: after specialize the system shows only the preparation animation and then goes straight to the sign-in
  screen with two accounts. Not a single question.
- Cross-links: the language screen is hidden via International-Core; the keyboard layout screen is hidden via `InputLocale`;
  the network and account screens via `HideOnlineAccountScreens` + `LocalAccounts` + `BypassNRO`.
  The screens that Windows 11 shows after sign-in («Завершим настройку устройства» (Let's finish setting up your device)) are disabled
  in the default profile (`ScoobeSystemSettingEnabled=0`, section 14).
- Version differences: `ProtectYourPC=3` works on Windows 11 24H2; `HideLocalAccountScreen` is not
  used (it is needed only for autologon of the built-in administrator). Windows 10 has the same elements.
- Verification: installation proceeds without a single screen after disk selection.
- Rollback: not applicable.

## UserAccounts / LocalAccounts

Two accounts; the order of the child elements follows the example in the Microsoft documentation
(Password, Description, DisplayName, Group, Name).

| Field | Admin | User |
|---|---|---|
| Name | Admin | User |
| DisplayName | Admin | User |
| Description | Local administrator (starter account) | Standard user (starter account) |
| Group | Administrators | Users |
| Password/Value | empty | empty |
| Password/PlainText | true | true |

- What it does: OOBE creates both accounts before the first sign-in. The profiles (the `C:\Users\Admin`,
  `C:\Users\User` folders) are created at each account's first sign-in, so they inherit the default user profile
  modified in specialize (section 14).
- Expected effect: two tiles on the sign-in screen, sign-in without a password with a single click.
- Cross-links:
  - Blank password and `LimitBlankPasswordUse=1` (Windows default): network sign-in, RDP, `runas` and UAC
    confirmation with Admin credentials are impossible until passwords are assigned. The standard user User
    cannot elevate (error 1327). Until passwords are assigned, programs are installed under Admin.
  - `PasswordNeverExpires` (section 04) prevents a password change from being required after 42 days.
  - The names `Admin` and `User` are duplicated in `$Config.AdminAccount` and `$Config.UserAccount`:
    they are used by `Post-OOBE.ps1`. They must be changed in both places (the constructor will do this from a single field).
  - The `Administrators` group is specified by its English name; on localized images Setup
    maps the built-in groups correctly (check after installation with the command below).
  - The built-in `Administrator` (RID 500) and `Guest` (RID 501) remain disabled; Post-OOBE.ps1
    checks this by SID.
- Version differences: Windows 11 24H2 keeps a copy of the file with the names (and the passwords, if there were any)
  in `C:\Windows\Panther\unattend.xml` and `unattend-original.xml`; Post-OOBE.ps1 deletes them. Windows 10
  kept only one copy. In 24H2, with a blank password, Windows does not require security questions
  (they appear only when an account is created through the OOBE screen).
- Verification:
  ```powershell
  Get-LocalUser Admin, User | Select-Object Name, Enabled, PasswordRequired, PasswordExpires
  Get-LocalGroupMember -SID S-1-5-32-544   # Administrators
  Get-LocalGroupMember -SID S-1-5-32-545   # Users
  ```
- Rollback: `Remove-LocalUser`, or renaming via `Rename-LocalUser`. Profiles are deleted via
  System Properties → User Profiles.

## FirstLogonCommands component

Not used. In the original it re-enabled the network adapters after OOBE; in our design the adapters
are not disabled, and the first sign-in actions are performed by Active Setup (section 15), which fires
for every user, not only for the first one to sign in.
