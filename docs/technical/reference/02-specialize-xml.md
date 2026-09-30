# 02. specialize pass in XML: extraction, BypassNRO, script launch, time zone

The specialize pass runs at the first boot of the installed system, as SYSTEM,
before any screens appear, without user profiles and, as a rule, without a network (network adapter
drivers may still be installing). At this stage the registry, DISM, services and
Task Scheduler via `schtasks.exe` work. Unreliable: WMI/CIM (which is why `Register-ScheduledTask` is not used),
networking cmdlets, anything that requires an interactive session.

Component `Microsoft-Windows-Deployment` (amd64 and arm64), three synchronous commands.

## Order 1. Extracting the embedded scripts

```
powershell.exe -NoProfile -WindowStyle Hidden -Command "try{$x=[xml]::new();$x.Load('C:\Windows\Panther\unattend.xml');$s=[scriptblock]::Create($x.unattend.Extensions.ExtractScript);icm $s -Args $x}catch{$_>C:\Windows\Temp\ua.err};exit 0"
```

- Length 238 characters (limit 259).
- What it does: loads the copy of the answer file from Panther, takes the text of the `Extensions/ExtractScript` element,
  turns it into a script block and runs it with the XML itself as the argument. `ExtractScript` creates
  the `C:\ProgramData\Unattend\Scripts` and `...\Logs` folders and writes each `<File path="...">`
  to a file encoded as UTF-8 with BOM (the BOM is needed so that PowerShell 5.1 reads the Cyrillic text in the scripts correctly).
- Error handling: any exception is written to `C:\Windows\Temp\ua.err`, the return code is always 0.
- Cross-links: without this step the Order 3 command will not find the script and will write "no script" to the same file;
  Post-OOBE.ps1 carries the contents of `ua.err` over into its log. The path `C:\Windows\Panther\unattend.xml`
  is fixed by Setup for all versions from Windows 7 onward.
- Version differences: none. The method (scripts inside the XML) is taken from the practice of the Schneegans generator and
  UnattendedWinstall; it works on Windows 10 and 11.
- Verification: after installation three files exist in `C:\ProgramData\Unattend\Scripts`.
- Rollback: not required.

## Order 2. BypassNRO

```
reg.exe add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE" /v BypassNRO /t REG_DWORD /d 1 /f
```

- What it does: allows OOBE to finish without an internet connection and without a Microsoft account
  (NRO = Network Required OOBE). Shows the «У меня нет интернета» (I don't have internet) option if the network screen appears anyway.
- Expected effect: in our file the accounts are created from the XML, and the network and account screens are
  hidden (`HideOnlineAccountScreens`, `HideWirelessSetupInOOBE`), so the key serves as insurance in
  case Microsoft changes the behavior of OOBE.
- Cross-links: related to `HideOnlineAccountScreens` and `LocalAccounts` (section 03). When the file contains
  local accounts, OOBE requires neither a network nor a Microsoft account, regardless of the key.
- Version differences: not needed on Windows 10 (OOBE allows a local account). Works on Windows 11
  21H2+. In 2025 Microsoft announced the removal of NRO bypasses in Insider builds
  (first the `oobe\bypassnro.cmd` script, then the registry key as well). On the released 24H2/25H2 the key
  works; if it stops working in future builds, our file will not be affected thanks to `LocalAccounts`.
- Verification: `Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE -Name BypassNRO`.
- Rollback: delete the value; it does not affect the installed system.

## Order 3. Launching Setup-System.ps1

```
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "try{$p='C:\ProgramData\Unattend\Scripts\Setup-System.ps1';if(Test-Path $p){& $p}else{'no script'>C:\Windows\Temp\ua.err}}catch{$_>C:\Windows\Temp\ua.err};exit 0"
```

- Length 241 characters.
- What it does: runs the machine settings script if it has been extracted. `-ExecutionPolicy Bypass` is needed
  because the default execution policy on client Windows forbids running scripts.
  `-WindowStyle Hidden` hides the console window, which would otherwise hang over the «Подготовка» (Getting ready) screen
  for several minutes (removing apps takes time).
- Error handling: three levels. The wrapper catches an exception at launch; inside the script `trap { ...; continue }`
  logs any unhandled error and continues with the next line; each call is wrapped in try/catch
  or in `Set-Reg`/`Invoke-Exe`, which write OK/WARN/ERROR themselves. The script ends with `exit 0`.
- Run time: 2-6 minutes depending on the disk (most of the time goes to removing 33 apps and DISM).
- Cross-links: the entire content of the script is described in sections 04-14.
- Version differences: `powershell.exe` is Windows PowerShell 5.1, built into all versions of Windows 10/11.
  PowerShell 7 is neither used nor required.
- Verification: `C:\ProgramData\Unattend\Logs\Setup-System.log` contains the "started" and "finished" lines.
- Rollback: not applicable.

## TimeZone

Component `Microsoft-Windows-Shell-Setup` in specialize.

- Value: `FLE Standard Time` (Kyiv, UTC+2, daylight saving time under EU rules).
- What it does: sets the system time zone before OOBE; otherwise Windows determines it from the region
  or via the time service.
- Expected effect: correct time right after installation; in Settings the zone is «(UTC+02:00) Киев» (Kyiv).
- Cross-links: does not depend on `UserLocale`. Time synchronization (`W32Time`) stays enabled
  and corrects the clock via `time.windows.com` once a network is available. Correct time is critical for audit logs:
  events with the wrong time are hard to correlate during an investigation.
- Version differences: the identifier is the same in all versions; list: `tzutil /l`.
- Verification: `tzutil /g`.
- Rollback: `tzutil /s "<other time zone>"`.
