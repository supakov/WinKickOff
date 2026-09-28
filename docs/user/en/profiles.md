# Profiles and presets

A profile stores everything you have selected in the program: which rules are enabled, parameter values,
the edition and key, the time zone, languages and accounts. A profile is a `.json` file in the `profiles`
folder next to the program.

## Presets

| Preset | Purpose |
|---|---|
| "Office" | Ordinary work computers. Based on the tested v0.2 answer file: Defender with cloud-delivered protection and ASR rules, Windows Update, printing, network protection, logs for investigating incidents, removal of advertising and gaming apps. In addition: Edge, Chrome and Brave policies without telemetry, advertising and AI features, OneDrive is not installed, Task Manager and other Windows tools open for Admin without a UAC prompt. Since 28.09.2026 the AI features and telemetry of Windows, Edge and Office are off (Copilot, Recall, Paint, Notepad, online speech recognition), signing in to Edge is blocked, the drive is not encrypted |
| "Strict" | Computers at higher risk. "Office" plus ransomware protection for folders in block mode, blocking programs without a reputation from starting (SmartScreen), blocking rare executable files, blocking unsigned programs from USB drives, a UAC prompt for Admin on every elevation, updates for other Microsoft products (Office, .NET), NetBIOS turned off, the VBScript engine removed. Older programs may stop working: test on one computer first |
| "Laptop" | Laptops. "Office", but the screen locks after 10 minutes of inactivity. The drive is not encrypted, as in the other presets: BitLocker is turned on separately, together with saving the recovery keys and user passwords |
| "memstechtips" | Comparison and carrying over familiar settings. Reproduces the original UnattendedWinstall file (the memstechtips project, Appendix A) as far as the catalog allows: hardware check bypasses, app removal, no ads, Copilot or extra telemetry. Baseline protection rules that the original lacks or contradicts (UAC, real-time protection, NLA and others) are off, and the program warns about each of them. For work computers "Office" is the better choice. Detailed analysis: [memstechtips-profile.md](../../technical/memstechtips-profile.md) |

Presets do not change. If you modify a preset and click "Save", the program offers to save the
profile under a new name. The names `preset-*.json` are reserved.

## Your own profiles

- "Save as..." creates a new profile; the name you give it becomes the profile's name.
- The "Profile" field on the top bar switches between presets and saved profiles. If the current
  profile has been changed, the program asks whether to save the changes.
- "File, Recent" opens up to eight recent profiles and files.
- "File, Compare with profile..." shows how the current profile differs from another profile or preset:
  rule states, parameter values, installation data. A double click on a row leads to the rule.

## Moving to another computer

Copy the profile file from the `profiles` folder to the same folder of WinKickOff on the other computer. If
the profile contains passwords, keep the file secret: the passwords are stored in plain text.

## Restoring from a finished file

"File, Open profile from autounattend.xml" restores a profile:

- from a file built by WinKickOff: the profile is embedded in the file itself and is restored completely;
- from a hand-written v0.2 file or a file without an embedded profile: the profile is reconstructed from
  the actions in the file. Rules that cannot be determined unambiguously keep their catalog defaults and
  are listed at the bottom of the window. After restoring, click "Check" (F7).

Save the restored profile if you want to use it again.

## Profiles after a program update

A new version of the program opens profiles saved by an older one:

- rules present in the profile keep their states and parameters, even if their default changed in the new
  version;
- new catalog rules get their defaults; the program reports in one line how many there are and how many of
  them are on;
- rules no longer in the catalog are not lost: they are kept in the `unknown` section of the profile and come
  back if the rule reappears;
- outdated fields are migrated (the country of catalog 0.2, for example), with a message as well.

Presets always match their program version. To bring new recommendations into your profile, open a preset
and choose "File, Compare with profile...": the list shows every difference.
