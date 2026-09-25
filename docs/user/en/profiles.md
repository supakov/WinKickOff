# Profiles and presets

A profile stores everything you have selected in the program: which rules are enabled, parameter values,
the edition and key, the time zone, languages and accounts. A profile is a `.json` file in the `profiles`
folder next to the program.

## Presets

| Preset | Purpose |
|---|---|
| "Office" | Ordinary work computers. Reproduces the tested v0.2 answer file: Defender with cloud-delivered protection and ASR rules, Windows Update, printing, network protection, logs for investigating incidents, removal of advertising and gaming apps |
| "Strict" | Computers at higher risk. "Office" plus ransomware protection for folders in block mode, blocking programs without a reputation from starting (SmartScreen), blocking rare executable files, NetBIOS turned off, the VBScript engine removed. Older programs may stop working: test on one computer first |
| "Laptop" | Laptops. "Office", but the screen locks after 10 minutes of inactivity and automatic device encryption is allowed. Right after installation save the BitLocker recovery key separately from the laptop: `manage-bde -protectors -get C:` |

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
