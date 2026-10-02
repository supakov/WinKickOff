# 05. Printing

Section 1 of `Setup-System.ps1`. Customer requirement: printing must work right after installation.
With the print spooler on manual start, printing does not work until the service is started
manually.

## EnsurePrintSpooler

- Value: `$true`.
- Where applied: specialize, SYSTEM.
- What it does:
  1. `HKLM\SYSTEM\CurrentControlSet\Services\Spooler\Start = 2` (Automatic) via the registry;
  2. `Set-Service -Name Spooler -StartupType Automatic` (duplicates it through the Service Control Manager, in case
     the registry value gets overwritten);
  3. `HKLM\SYSTEM\CurrentControlSet\Services\PrintNotify\Start = 3` (Manual, the Windows default).
- Expected effect: the «Диспетчер печати» (Print Spooler) service is running after every boot; USB and network printers
  connect normally; «Печать в PDF» (Microsoft Print to PDF) and «XPS» are available.
- Cross-links:
  - The print spooler has historically been the main source of remote code execution vulnerabilities
    (PrintNightmare 2021). Mitigation: `RestrictPrinterDriverInstallToAdmins` below, and inbound
    connections are blocked by the firewall by default (section 09); printer sharing
    opens port 445 only through the «Общий доступ к файлам и принтерам» (File and Printer Sharing) rule in the private profile.
  - The `PrintNotify` service is needed for print notifications; manual start is the standard mode.
- Version differences: in Windows 11 22H2+ Microsoft is moving printing to IPP and "Windows Protected Print
  Mode" (WPP, 24H2): in this mode third-party drivers are not used, only the universal class driver.
  WPP is off by default; the file does not enable it because old host-based (GDI) printers
  require their own drivers.
- Verification: `Get-Service Spooler | Select Status, StartType` → Running, Automatic.
- Rollback: `Set-Service Spooler -StartupType Manual`.

## RestrictPrinterDriverInstallToAdmins

- Value: `$true`.
- Where applied: specialize, policy in the registry.
- What it does: key `HKLM\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint`:
  - `RestrictDriverInstallationToAdministrators = 1`: printer drivers can be installed only by administrators;
  - `NoWarningNoElevationOnInstall = 0`: when connecting to a print server, show a warning
    and require elevation;
  - `UpdatePromptSettings = 0`: the same when a driver is updated.
- Expected effect: the standard user User cannot install a printer driver. A network printer
  with a new driver is connected by Admin. Connecting a printer whose driver is already
  on the system (class drivers, previously installed drivers) works for everyone.
- Cross-links:
  - This has been the Windows default since August 2021 (KB5005652); the file enforces it with a policy
    so that nobody weakens it.
  - For networks with a print server or a shared printer on another PC of the workgroup: on the first
    connection User will see a prompt for administrator credentials; with Admin's empty password the prompt
    will fail (section 03). Solution: Admin connects the printer under their own account once
    for each user, or the users project assigns passwords.
  - A future constructor parameter: a list of trusted print servers
    (`PackagePointAndPrintServerList`) for which installation is allowed for everyone.
- Version differences: the policy applies to Windows 10 1507+ and Windows 11 after KB5005652;
  on older builds the value is ignored.
- Verification: `Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint'`.
- Rollback: `RestrictDriverInstallationToAdministrators = 0` (not recommended: it reopens the PrintNightmare vector).
