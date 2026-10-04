# WinKickOff: user guide

WinKickOff builds an `autounattend.xml` file for unattended installation of Windows 11 Pro. The file is
placed on a USB drive with the Windows installation image; Windows Setup finds it on its own and configures
the computer: security, updates, accounts, languages, removal of unneeded apps. All a person has to do is
choose the disk (and, when the profile says so, type the product key, pick the edition or enter the account).

The program is designed for small organizations without a Windows domain, where there is no dedicated
administrator for each computer. Settings are grouped into ready-made sets (presets), and you can change
them without knowing the registry.

## What you will need

- A computer with Windows 10 or 11 to run WinKickOff. The program does not need administrator
  rights, changes nothing on that computer and writes files only to its own folder.
- An official Windows 11 ISO image from the Microsoft website and a USB drive of 8 GB or more.
- For the first test: a virtual machine (Hyper-V or VirtualBox). A new file is tested on a virtual
  machine first, and only then on work computers.

## How to start the program

If you received the program as a folder containing `WinKickOff.exe`, run that file. If you received the
source code, you need Python 3.14 for Windows: double-click `Start-WinKickOff.cmd` in the root of the project
folder, or in the `WinKickOff` folder run:

```powershell
python -m winkickoff
```

The links in the description of a rule lead to other rules; the "Back" and "Forward" buttons above the
description (or Alt+Left and Alt+Right) go along the history of these jumps, as in a browser. The history keeps
jumps by links, by messages at the bottom of the window and clicks in the tree.

## Language and appearance

The main language of the program is English; the Russian and Ukrainian translations are separate files, and
the program finds every available language by itself. By default it uses the Windows language when there is a
translation for it, otherwise English. The language is changed in the "Language" menu, the colour scheme in
the "Theme" menu: "As in Windows" (light or dark, as set in Windows), "Light", "Dark", the beige and coffee
"Latte" and the playful "Matrix".
The program remembers the choice and keeps the open profile when switching.

Adding a language needs no change to the program: a file `strings.<code>.json` in the `resources` folder (for
example `strings.pl.json` with the field `"_language": "Polski"`) and a file `<code>.toml` with the rule
translations in `rules\lang`. Use the Russian or Ukrainian files as a sample. Untranslated strings are shown in
English. A colour scheme of your own: a file `resources\themes\<name>.json` modelled on `dark.json`. In the
portable build these folders are inside `_internal`.

## Documents

| Document | What it covers |
|---|---|
| [Quick start](quick-start.md) | Seven steps from starting the program to a USB drive with the finished file |
| [Profiles and presets](profiles.md) | Ready-made sets of settings, your own profiles, moving to another computer, restoring from a finished file |
| [Installation and checks](install-and-check.md) | Preparing the USB drive, what Windows Setup will ask, how to check the result and where to find the logs |
| [Safety](safety.md) | What you must do before using the file on work computers, and which decisions were made deliberately |
| [This PC](this-pc.md) | Checking an already installed Windows and applying selected rules without reinstalling, rollback |
| [Policy templates (ADMX)](admx.md) | Importing the administrative templates of Windows, Edge, Chrome, Office and building any of their policies |
| [MCP server](mcp.md) | Access of AI assistants (Claude Code, Claude Desktop) to the catalog and the open profile: modes, token, connection, monitor |
| [Rule list](rules.md) | All installation rules by group: what each one does, whether it is enabled in "Office", risks |

## In short

1. Select the "Preset: Office" profile.
2. If needed, turn off or adjust rules in the tree on the left.
3. Click "Build autounattend.xml" (F9) and save the file.
4. Copy the file to the root of the USB drive with the Windows 11 image and install Windows on a virtual machine.
5. Check the result using the list in the "Installation and checks" document, then use the file on work computers.
