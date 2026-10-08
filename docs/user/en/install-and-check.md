# Installation and checks

## Preparing the USB drive

1. Download the latest Windows 11 image from the Microsoft website.
2. Write the image to the USB drive (Rufus or Media Creation Tool).
3. Copy the built `autounattend.xml` to the root of the USB drive.

With Ventoy, the file is placed next to the image and connected through the Auto Install plugin.

## What Windows Setup will ask

1. The Setup language and keyboard layout on the first screen (depends on the image).
2. The disk and partition to install to. Automatic partitioning is deliberately not configured: it erases
   the disk without asking, which is dangerous for work computers.

3. Only if the key mode "Choose the edition during installation" is selected in the "Installation" node: the product
   key page. Type the key from the sticker, or click "I don't have a product key" and pick the edition from the list
   (on a laptop that came with Windows Home pick Home, otherwise Windows does not activate).
4. Only if "Ask for the account during installation" is selected in the "Accounts" node: the account name (it becomes
   an administrator) and its password. The password may stay empty; if one is typed, Windows also asks three security
   questions. Install without a network cable.

Everything else happens without anyone's involvement: the license, the initial setup screens, and also the key, the
edition and the accounts unless the forms ask for them as in items 3 and 4. After installation, the desktop opens.

## Checking the file before installation

In the program window: "Check" (F7); "Build autounattend.xml" (F9) also checks the PowerShell syntax of the
embedded scripts. From the project folder you can also run the validation utility; it only reads the file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

## Checking after installation (on a virtual machine)

Sign in as Admin and run in PowerShell:

```powershell
Get-Content C:\ProgramData\Unattend\Logs\Setup-System.log | Select-String 'ERROR|WARN'
Get-ChildItem C:\ProgramData\Unattend\Logs\Setup-User.*.log | Get-Content
Get-Content C:\ProgramData\Unattend\Logs\Post-OOBE.log
Get-Service Spooler | Select-Object Status, StartType
Get-LocalUser Admin, User | Select-Object Name, FullName, Description, Enabled, PasswordExpires
$env:COMPUTERNAME
Get-WinUserLanguageList | Select-Object LanguageTag, InputMethodTips
Get-MpPreference | Select-Object PUAProtection, MAPSReporting, EnableNetworkProtection, AttackSurfaceReductionRules_Ids
Test-Path C:\Windows\Panther\unattend.xml
```

Expected result for the "Office" preset: no ERROR in the logs; the Print Spooler service is running
and starts automatically; the Admin and User passwords never expire; the input languages are en-US, uk-UA,
ru-UA; protection against potentially unwanted apps and network protection are turned on; there are 16 ASR
rules (17 in the "Strict" preset); there is no `unattend.xml` file in Panther. The display names and
descriptions of the accounts are those of the "Accounts" form (`Post-OOBE.ps1` sets the Cyrillic ones, see
`Post-OOBE.log`), and the computer name is the one the "Installation" form sets: the name, a name from the
template or a random `DESKTOP-...`.

For every rule, the program has a "Check after installation" section with the
exact command.

## Logs

| Log | What it contains |
|---|---|
| `C:\ProgramData\Unattend\Logs\Setup-System.log` | Computer configuration at the first startup: each rule and its result |
| `C:\ProgramData\Unattend\Logs\Setup-User.<name>.log` | Configuration at each user's first sign-in (input languages) |
| `C:\ProgramData\Unattend\Logs\Post-OOBE.log` | Actions after the initial setup, errors from the first startup marked SPECIALIZE ERROR |
| `C:\Windows\Panther\setuperr.log` | Errors of Windows Setup itself |

## If something goes wrong

- Windows Setup reports that the answer file is invalid: check the file with the "Check" button and
  with the validation utility; send `C:\Windows\Panther\setuperr.log` and `setupact.log` from the installed system.
- After the first sign-in there is no "Russian (Ukraine)": sometimes it appears only after the second
  sign-in, and until then plain "Russian" is set. What was applied is shown in `Setup-User.<name>.log`.
- A program stopped working after installation with the "Strict" preset: in WinKickOff, open the
  rules for folder protection, SmartScreen and ASR; the "Rollback" section of each one describes
  how to restore the previous behavior.
