# WinKickOff: user guide

WinKickOff builds an `autounattend.xml` file for unattended installation of Windows 11 Pro. The file is
placed on a USB drive with the Windows installation image; Windows Setup finds it on its own and configures
the computer: security, updates, accounts, languages, removal of unneeded apps. All a person has to do is
choose the disk.

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
source code, you need Python 3.14 for Windows; in the `WinKickOff` folder, run:

```powershell
python -m winkickoff
```

The interface language (English, Ukrainian or Russian) is chosen in the "Language" menu; the program
remembers the choice and keeps the open profile when switching.

## Documents

| Document | What it covers |
|---|---|
| [Quick start](quick-start.md) | Seven steps from starting the program to a USB drive with the finished file |
| [Profiles and presets](profiles.md) | Ready-made sets of settings, your own profiles, moving to another computer, restoring from a finished file |
| [Installation and checks](install-and-check.md) | Preparing the USB drive, what Windows Setup will ask, how to check the result and where to find the logs |
| [Safety](safety.md) | What you must do before using the file on work computers, and which decisions were made deliberately |
| [Rule list](rules.md) | All installation rules by group: what each one does, whether it is enabled in "Office", risks |

## In short

1. Select the "Preset: Office" profile.
2. If needed, turn off or adjust rules in the tree on the left.
3. Click "Build autounattend.xml" (F9) and save the file.
4. Copy the file to the root of the USB drive with the Windows 11 image and install Windows on a virtual machine.
5. Check the result using the list in the "Installation and checks" document, then use the file on work computers.
