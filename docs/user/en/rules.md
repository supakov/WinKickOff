# Rule list

Every rule of the WinKickOff catalog 0.3 by group, 176 in total. This file is generated from the catalog by `python tools/make_rule_docs.py` and is not edited by hand. In the program every rule also shows its technical details, the check after installation and the rollback.

Levels: baseline (the core of the protection, disabling is not recommended), recommended, optional, risky (may disturb programs, enable deliberately).

## Installation (windowsPE and specialize)

Bypassing compatibility checks, a local account without a network connection, .NET Framework 3.5 from the media.

- **Bypass the TPM 2.0 check** (`install.bypass-tpm`). Level: optional. "Office": enabled; "Strict": enabled.
  Setup does not require TPM 2.0. On PCs that have a TPM, the module stays enabled and in use.
  Effect: Installation proceeds on PCs without a TPM or with TPM 1.2, with no incompatibility message.
  Risk: Without a TPM, automatic device encryption and BitLocker without a startup password are unavailable. Microsoft does not guarantee updates for unsupported PCs.
- **Bypass the Secure Boot check** (`install.bypass-secureboot`). Level: optional. "Office": enabled; "Strict": enabled.
  Setup does not require Secure Boot to be enabled.
  Effect: Installation proceeds on PCs with BIOS/CSM or with Secure Boot turned off.
  Risk: Without Secure Boot, Credential Guard and some kernel protections do not work; LSA protection in this file is configured without a UEFI lock precisely for such PCs.
- **Bypass the processor check** (`install.bypass-cpu`). Level: optional. "Office": enabled; "Strict": enabled.
  Setup does not check the processor against the list of supported models.
  Effect: Installation proceeds on processors older than 8th generation Intel and Ryzen 2000.
  Risk: In 24H2 the POPCNT and SSE4.2 instruction requirement cannot be bypassed: installation is impossible on very old processors.
- **Bypass the memory check** (`install.bypass-ram`). Level: optional. "Office": enabled; "Strict": enabled.
  Setup does not require 4 GB of memory.
  Effect: Installation proceeds on PCs with less memory; the system will run slowly.
- **Bypass the disk size check** (`install.bypass-storage`). Level: optional. "Office": enabled; "Strict": enabled.
  Setup does not require 64 GB of disk space.
  Effect: Installation proceeds on small disks; free space for updates must be monitored.
- **Allow completing OOBE without internet access and a Microsoft account** (`install.bypass-nro`). Level: baseline. "Office": enabled; "Strict": enabled.
  BypassNRO key: the out-of-box experience does not require a network connection or a Microsoft account.
  Effect: A safeguard: accounts are created from the file, but if OOBE behavior changes, the key keeps setup from getting stuck on the network screen.
- **.NET Framework 3.5 from the installation media** (`install.netfx3`). Level: optional. "Office": enabled; "Strict": enabled.
  Searches connected drives for the sources\sxs folder and enables .NET Framework 3.5 (including 2.0 and 3.0) without internet access.
  Effect: Legacy accounting software, client-bank apps and drivers for digital signature keys work right after installation.
  Risk: The media must stay connected during the first restart; otherwise the component is not installed and a WARN entry is written to the log. It can be added later through Settings when internet access is available.

## Out-of-box experience (OOBE)

Which OOBE screens are hidden and how the privacy settings are set.

- **Hide the license agreement screen** (`oobe.hide-eula`). Level: baseline. "Office": enabled; "Strict": enabled.
  The license is accepted in Setup (AcceptEula), so the screen is not shown in OOBE.
  Effect: One screen fewer; the organization is responsible for accepting the terms.
- **Hide the manufacturer registration screen** (`oobe.hide-oem-registration`). Level: baseline. "Office": enabled; "Strict": enabled.
  The OEM registration screen is not shown (it appears only on manufacturer images).
  Effect: Harmless on Microsoft images; saves a screen on OEM images.
- **Hide the Microsoft account screens** (`oobe.hide-online-account`). Level: baseline. "Office": enabled; "Strict": enabled.
  The screens for signing in with a Microsoft account and creating a local account are not shown: accounts are defined in the file.
  Effect: After setup, the system goes straight to the sign-in screen with the initial accounts.
  Risk: Works only together with the accounts in the "Accounts" section; without them, OOBE will require creating an account.
- **Hide the network connection screen** (`oobe.hide-wireless`). Level: recommended. "Office": enabled; "Strict": enabled.
  The "Let's connect you to a network" screen is always hidden, not only on a wired connection.
  Effect: Setup does not stop on laptops without a network cable; Wi-Fi is configured after sign-in.
- **Privacy settings screen: turn off express settings** (`oobe.protect-your-pc`). Level: recommended. "Office": enabled; "Strict": enabled.
  The privacy screen is not shown; diagnostic data sending, advertising and location are turned off by default.
  Effect: SmartScreen and Defender are not affected: they are enabled by separate rules.

## Printing

Print Spooler and protection of printer driver installation.

- **Print Spooler starts automatically** (`printing.spooler-automatic`). Level: baseline. "Office": enabled; "Strict": enabled.
  The Spooler service is set to automatic startup (registry and Set-Service); PrintNotify stays manual.
  Effect: Printing works right after installation: USB and network printers, "Print to PDF". The original UnattendedWinstall file set the service to manual, and printing did not work.
  Risk: Print Spooler has historically been a source of vulnerabilities (PrintNightmare); this is mitigated by the rule that restricts driver installation to administrators and by the firewall.
- **Only administrators can install printer drivers** (`printing.point-and-print-admins`). Level: recommended. "Office": enabled; "Strict": enabled.
  Point and Print policy: installing and updating printer drivers requires administrator rights and shows a warning.
  Effect: A standard user cannot install a printer driver; drivers that are already installed and class drivers are available to everyone.
  Risk: An administrator must connect a network printer that needs a new driver. While Admin has a blank password, the credential prompt in a user session will not succeed.

## Windows Update

Automatic updates, other Microsoft products, feature update deferral, Delivery Optimization.

- **Remove all Windows Update blocks** (`update.unblock`). Level: baseline. "Office": enabled; "Strict": enabled.
  Removes policies that turn off updates, driver updates or Store automatic updates, and returns disabled update services to manual startup.
  Effect: Changes nothing on a clean image; removes leftovers of third-party "optimizers" and makes it safe to run the script again.
- **Automatic update installation and active hours** (`update.automatic`). Level: recommended. "Office": enabled; "Strict": enabled.
  Updates are downloaded and installed automatically; automatic restarts are not allowed during active hours.
  Effect: Restarts happen at night or before the workday starts; the user sees a notification and can postpone within the policy limits.
  Risk: Active hours cannot exceed 18 hours. PCs that run around the clock will restart outside active hours.
- **Updates for other Microsoft products (Office, .NET)** (`update.other-microsoft-products`). Level: recommended. "Office": enabled; "Strict": enabled.
  Opts in to Microsoft Update: fixes for Office (MSI), .NET and other products arrive together with Windows updates.
  Effect: The toggle in Settings is turned on and locked. Office 365 (Click-to-Run) updates independently through its own mechanism.
- **Defer feature updates** (`update.defer-feature`). Level: optional. "Office": enabled; "Strict": enabled.
  Annual version updates arrive with a delay; monthly security updates are not deferred.
  Effect: During the deferral period, Microsoft fixes the bugs of the first weeks and accounting software vendors release compatible versions.
  Risk: Requires working compatibility assessment: the minimal telemetry rule intentionally leaves DiagTrack on manual startup instead of disabling it.
- **Delivery Optimization: share updates only on the local network** (`update.delivery-optimization-lan`). Level: recommended. "Office": enabled; "Strict": enabled.
  PCs on the same network share downloaded update fragments with each other; nothing is uploaded outside the network.
  Effect: In an office with a dozen PCs, an update is downloaded from the internet only once. Port 7680 must be open between PCs (Windows creates the firewall rule itself).

## Microsoft Defender and SmartScreen

Real-time protection, cloud-delivered protection, PUA, network protection, ASR rules, SmartScreen.

- **Real-time protection enabled and enforced** (`defender.realtime`). Level: baseline. "Office": enabled; "Strict": enabled.
  Removes the values that third-party scripts use to disable Defender, and enforces real-time protection, behavior monitoring, and scanning of downloads and scripts.
  Effect: The antivirus cannot be turned off through the registry; the toggles in Windows Security are managed by policy.
- **Cloud protection: MAPS, sample submission, block level** (`defender.cloud`). Level: recommended. "Office": enabled; "Strict": enabled.
  MAPS membership at the "Advanced" level, automatic submission of safe samples, "High" cloud block level, and waiting up to 50 seconds for a verdict.
  Effect: New malicious files without signatures are blocked by cloud reputation within seconds; a suspicious file is held for up to a minute before its first run.
  Risk: The "High" level increases false positives on rare in-house programs; the fix is a file exclusion or level 0. Requires internet access.
- **Block potentially unwanted apps (PUA)** (`defender.pua`). Level: recommended. "Office": enabled; "Strict": enabled.
  Defender blocks adware, bundling installers, miners and "optimizers" on download and launch.
  Effect: Closes the most common infection channel for non-professional users: "a free program from a website with a Download button".
  Risk: Legitimate utilities flagged as PUA (some remote access tools) require an exclusion.
- **Network protection: block connections to dangerous addresses** (`defender.network-protection`). Level: recommended. "Office": enabled; "Strict": enabled.
  No app, not just Edge, can connect to domains that have a poor reputation according to SmartScreen.
  Effect: Phishing sites and command-and-control servers are blocked with a "Connection blocked" notification.
  Risk: Works only when Defender is the primary antivirus; may conflict with VPN clients that have their own filters (use audit mode in that case).
- **Attack surface reduction (ASR) rules engine enabled** (`defender.asr`). Level: recommended. "Office": enabled; "Strict": enabled.
  Enables the ASR engine; the rules themselves are listed in a subgroup and configured one by one.
  Effect: Without this rule, no ASR rule takes effect.
- **Controlled Folder Access (mode)** (`defender.controlled-folder-access`). Level: optional. "Office": enabled; "Strict": enabled.
  Sets the protection mode for the Documents, Pictures and Desktop folders. The default is 0 (off), set as a policy so the user cannot turn it on by accident.
  Effect: In block mode, only trusted apps can write to protected folders; ransomware launched by the user cannot damage documents.
  Risk: Mode 1 breaks accounting software (1C, M.E.Doc, client-bank apps), older versions of Office and any in-house programs that write to Documents. Recommended path: a month in audit mode (2), review of events 1123/1124, then block mode.
- **Windows Security notifications are shown** (`defender.notifications`). Level: baseline. "Office": enabled; "Strict": enabled.
  Security Center notification policies are enforced in the enabled state.
  Effect: The user sees messages about threats and scan results. The original UnattendedWinstall file turned off all notifications.
- **SmartScreen for downloaded programs and files** (`defender.smartscreen-shell`). Level: recommended. "Office": enabled; "Strict": enabled.
  Running a program downloaded from the internet that has no reputation shows a warning (Warn) or is blocked (Block).
  Effect: Works based on the Internet zone mark; files from USB flash drives and the local network are not checked (they are covered by the ASR rule for USB and by cloud protection).
  Risk: Block mode prevents installing any uncommon program, including accounting software from developer websites.

### Attack surface reduction (ASR) rules

Each rule blocks one attack technique through Office, email, scripts, USB or drivers. Mode: block, audit, warn.

- **ASR: block abuse of exploited vulnerable signed drivers** (`asr.vulnerable-drivers`). Level: recommended. "Office": enabled; "Strict": enabled.
  Prevents drivers from the Microsoft vulnerable driver list from being written to disk (the BYOVD technique used to disable antivirus).
  Effect: Drivers that are already installed are not affected.
  Risk: Low: old RGB lighting and overclocking utilities.
- **ASR: block persistence through WMI event subscriptions** (`asr.wmi-persistence`). Level: recommended. "Office": enabled; "Strict": enabled.
  Fileless malware cannot establish persistence in the WMI repository.
  Effect: Closes a hidden autostart technique.
  Risk: Low; interferes with the SCCM client, which is not present in a workgroup.
- **ASR: Adobe Reader cannot create child processes** (`asr.adobe-reader-child`). Level: recommended. "Office": enabled; "Strict": enabled.
  An exploit in a PDF cannot launch anything from Adobe Reader.
  Effect: Opening PDF files works as before.
  Risk: Low.
- **ASR: Office apps cannot create child processes** (`asr.office-child`). Level: recommended. "Office": enabled; "Strict": enabled.
  A macro in Word or Excel cannot launch cmd, PowerShell or an installer.
  Effect: Applies only if Office is installed in Program Files.
  Risk: Medium: add-ins that launch external programs.
- **ASR: block executable content from email client and webmail** (`asr.email-executable`). Level: recommended. "Office": enabled; "Strict": enabled.
  .exe, .js and .zip files saved from Outlook and webmail do not run.
  Effect: Stops attachments that act as downloaders.
  Risk: Low.
- **ASR: block execution of obfuscated scripts** (`asr.obfuscated-scripts`). Level: recommended. "Office": enabled; "Strict": enabled.
  PowerShell, JS and VBS scripts that show signs of obfuscation do not run. Requires cloud protection.
  Effect: Stops downloaders that hide their code from antivirus.
  Risk: Medium: some program installers use obfuscation.
- **ASR: JavaScript and VBScript cannot launch downloaded content** (`asr.script-download`). Level: recommended. "Office": enabled; "Strict": enabled.
  A downloader script cannot launch a file it has just downloaded.
  Effect: The typical "archive with a script inside" scheme stops working.
  Risk: Low.
- **ASR: Office cannot create executable files** (`asr.office-executable`). Level: recommended. "Office": enabled; "Strict": enabled.
  Macros cannot write .exe, .dll or .vbs files to disk.
  Effect: Closes persistence through documents.
  Risk: Low.
- **ASR: Office cannot inject code into other processes** (`asr.office-injection`). Level: recommended. "Office": enabled; "Strict": enabled.
  Word, Excel, PowerPoint and OneNote cannot inject code into other processes.
  Effect: There is no legitimate reason for such injection.
  Risk: Low; incompatible with BeyondTrust Privilege Guard and Heimdal. Warn mode is not supported.
- **ASR: Outlook cannot create child processes** (`asr.office-comm-child`). Level: recommended. "Office": enabled; "Strict": enabled.
  Protects against exploits of Outlook rules and forms when credentials have been stolen.
  Effect: Regular Outlook features keep working.
  Risk: Low.
- **ASR: block untrusted and unsigned programs from USB** (`asr.usb-untrusted`). Level: recommended. "Office": enabled; "Strict": enabled.
  Unsigned .exe, .dll and .scr files do not run directly from USB flash drives and SD cards.
  Effect: Copying files from a USB flash drive is not blocked, only running them.
  Risk: Medium: unsigned portable utilities.
- **ASR: block Win32 API calls from Office macros** (`asr.office-win32-api`). Level: recommended. "Office": enabled; "Strict": enabled.
  VBA macros cannot call the Win32 API (shellcode that is never written to disk).
  Effect: Regular macros do not need such calls.
  Risk: Low.
- **ASR: use advanced protection against ransomware** (`asr.ransomware`). Level: recommended. "Office": enabled; "Strict": enabled.
  Files that resemble ransomware according to cloud heuristics and have no positive reputation are blocked. Requires cloud protection.
  Effect: An additional layer on top of signatures and behavior monitoring.
  Risk: Medium: rare in-house programs are blocked until they build a reputation.
- **ASR: block programs from restarting the PC in safe mode** (`asr.safe-mode-reboot`). Level: recommended. "Office": enabled; "Strict": enabled.
  Malicious code cannot put the PC into safe mode, where the antivirus does not run.
  Effect: Safe mode is still available from the recovery environment.
  Risk: Low.
- **ASR: warn about copied or impersonated system tools** (`asr.copied-system-tools`). Level: recommended. "Office": enabled; "Strict": enabled.
  Copies of system32 utilities that run from other folders are blocked, with an option to allow them.
  Effect: Warn mode by default because the rule is heuristic.
  Risk: Elevated: legitimate programs that have system utility names and run from non-standard paths.
- **ASR: executable files without a reputation (audit)** (`asr.prevalence`). Level: optional. "Office": enabled; "Strict": enabled.
  Launches of rare or new .exe files are logged (audit). In block mode, the rule would shut out the organization's internal programs.
  Effect: Event 1122 in the Defender log shows what would have been blocked.
  Risk: High in block mode: in-house programs without a reputation. Enable it in the Strict profile after a month of auditing.
- **ASR: processes created by PsExec and WMI (audit)** (`asr.psexec-wmi`). Level: optional. "Office": enabled; "Strict": enabled.
  Remote execution through PsExec and WMI is logged. In block mode, the rule would interfere with remote administration by your own IT specialist.
  Effect: Auditing reveals attempts at lateral movement across the network.
  Risk: High in block mode if administration relies on PsExec/WMI.
- **ASR: block credential stealing from LSASS** (`asr.lsass`). Level: optional. "Office": disabled; "Strict": disabled.
  Duplicates the LSA protection rule (RunAsPPL) and produces a lot of noise in the log; off by default.
  Effect: Makes sense only where LSA protection cannot be enabled (unsigned smart card plug-ins).
  Risk: Many events from legitimate programs (the Chrome updater and others). Warn mode is not supported.

## Security

UAC, accounts, credential protection, remote access, encryption.

### User Account Control (UAC)

- **UAC enabled, prompts on the secure desktop, Win+L works** (`uac.baseline`). Level: baseline. "Office": enabled; "Strict": enabled.
  Baseline UAC values: enabled, prompts on the secure desktop, standard users enter administrator credentials, installers require elevation, the built-in Administrator runs in Admin Approval Mode, and network logons of local administrators get a filtered token. The ban on locking the screen is removed.
  Effect: The original UnattendedWinstall file blocked Win+L locking and removed UAC prompts; here it is the opposite.
- **UAC for administrators: always notify** (`uac.admin-always-notify`). Level: recommended. "Office": enabled; "Strict": enabled.
  The administrator sees a prompt for every elevation, including system components; this closes known UAC bypasses through trusted Windows programs.
  Effect: More "Yes/No" prompts for Admin; protection against automatic elevation by malicious code.
  Risk: With a blank password, a UAC prompt is just a "Yes" button: it protects against programs, not against the person at the keyboard.

### Accounts and sign-in

- **Lock the screen after inactivity** (`accounts.inactivity-lock`). Level: recommended. "Office": enabled; "Strict": enabled.
  After the specified number of seconds without input, the screen locks regardless of screen saver and power settings.
  Effect: The workstation is not left open; with a blank password, unlocking is just pressing Enter, so the rule becomes meaningful once passwords are assigned.
- **Lock out accounts after wrong passwords** (`accounts.lockout`). Level: recommended. "Office": enabled; "Strict": enabled.
  After the specified number of consecutive wrong passwords, the account is locked for the specified time.
  Effect: Password guessing over the network (SMB, RDP) becomes useless. Not relevant while passwords are blank; once passwords are assigned, it is the first line of defense.
- **Passwords never expire (initial accounts)** (`accounts.password-never-expires`). Level: recommended. "Office": enabled; "Strict": enabled.
  The maximum password age is removed for all local accounts (the default is 42 days).
  Effect: Windows will never show "Your password has expired" for the initial accounts with blank passwords. The user management project can restore password expiration when it assigns passwords.
- **No "Allow my organization to manage my device" prompt** (`accounts.block-aad-join`). Level: baseline. "Office": enabled; "Strict": enabled.
  When a user signs in to Office or Teams with a work account, Windows does not offer to join the device to Entra ID.
  Effect: A non-professional user cannot put the PC under someone else's cloud management with a single click.

### Credential protection (LSA, NTLM)

- **Basic credential protection: no LM hashes, no anonymous access, no WDigest, SEHOP** (`lsa.baseline`). Level: baseline. "Office": enabled; "Strict": enabled.
  LM hashes are not stored; accounts with blank passwords are limited to console logon; anonymous enumeration of shares and accounts is not allowed; passwords are not kept in memory in plain text (WDigest); Structured Exception Handler Overwrite Protection (SEHOP) is enabled.
  Effect: A stolen hash or memory dump becomes of little use.
  Risk: Very old devices (printers, NAS) that browse shares anonymously may not see them.
- **LSA protection (RunAsPPL): LSASS as a protected process** (`lsa.protection`). Level: recommended. "Office": enabled; "Strict": enabled.
  LSASS memory is inaccessible to other processes, even with administrator rights; hashes and passwords cannot be extracted.
  Effect: Mimikatz and dumps through Task Manager do not work. Value 2 has no UEFI lock, so it can be rolled back through the registry.
  Risk: Plug-ins loaded into LSA (digital signature token drivers, third-party sign-in providers) must be signed by Microsoft; unsigned ones will not load (events 3033/3063). Test the organization's digital signature keys before a broad rollout.
- **NTLMv2 only (refuse LM and NTLMv1)** (`lsa.ntlmv2-only`). Level: recommended. "Office": enabled; "Strict": enabled.
  The client and server use only NTLMv2 and refuse LM and NTLMv1.
  Effect: Intercepted hashes cannot be used in old NTLMv1 attacks; modern PCs and NAS devices are not affected.
  Risk: Very old NAS devices, printers with scan to folder, and embedded devices that use NTLMv1 will stop connecting. Relax it together with the SMB rules after an inventory.

### Remote access

- **Remote Assistance turned off** (`remote.assistance-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Remote Assistance invitations (msra.exe) and full remote control are not allowed.
  Effect: One of the built-in remote control channels is closed; support from your own administrator requires a tool chosen by the organization.
- **Inbound Remote Desktop turned off** (`remote.rdp-inbound-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Inbound RDP connections are not allowed (the Windows default, set explicitly); outbound connections to other PCs work.
  Effect: One of the main attack vectors against small networks is closed.
- **Network Level Authentication (NLA) for RDP** (`remote.rdp-nla`). Level: baseline. "Office": enabled; "Strict": enabled.
  If RDP is ever enabled, connections will require authentication before the sign-in screen is shown.
  Effect: Protects against attacks on the RDP sign-in screen (BlueKeep and similar).
- **Remote Registry service disabled** (`remote.registry-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Remote reading and writing of the registry is not possible.
  Effect: On client Windows the service is already disabled; the rule sets this explicitly. Old inventory agents may require it to be enabled.

### Drive encryption

- **Prevent automatic device encryption (BitLocker without a saved key)** (`encryption.prevent-auto-bitlocker`). Level: recommended. "Office": enabled; "Strict": enabled.
  Windows does not encrypt the system drive automatically. Without a domain or a Microsoft account, there is nowhere to store the recovery key.
  Effect: Disk cloning and restore work; data is not lost if the TPM fails. Protection of laptops against theft is turned on deliberately, with the key saved.
  Risk: Data on a stolen laptop is not protected by encryption until BitLocker is turned on manually.

## Network and sharing

SMB, signing, name resolution, firewall.

- **SMB1 disabled and removed** (`network.smb1-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The server does not respond over SMB1, the client driver is disabled, and the SMB1Protocol feature is removed if it is installed.
  Effect: The 1996 protocol through which WannaCry and NotPetya spread is completely absent.
  Risk: SMB1-only devices (multifunction printers with scan to network folder made before 2015, old NAS devices, Windows XP) will not connect. Solution: firmware with SMB2/3, scanning to FTP or e-mail.
- **SMB signing required (server and client)** (`network.smb-signing`). Level: recommended. "Office": enabled; "Strict": enabled.
  Every SMB packet is signed; NTLM relay and tampering with shared folder traffic are impossible.
  Effect: Workgroup PCs configured with this file are compatible with each other; performance on gigabit networks drops by a few percent.
  Risk: Old NAS devices and multifunction printers without SMB2 signing support will not connect. Relax it together with the SMB1 and NTLMv2 rules after an inventory.
- **LLMNR disabled (protection against name spoofing on the network)** (`network.llmnr-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  LLMNR multicast name queries are disabled; Responder-type tools do not get hashes from these PCs.
  Effect: Workgroup computer names continue to resolve through NetBIOS (left enabled) and mDNS.
- **NetBIOS over TCP/IP disabled** (`network.netbios-off`). Level: risky. "Office": disabled; "Strict": enabled.
  Closes the second name spoofing channel (NBT-NS) and ports 137-139 on all current interfaces.
  Effect: Without a domain and WINS, a name such as \\PC-BUH resolves only through mDNS (pc-buh.local) or the router's DNS; familiar shortcuts to shared folders may stop working.
  Risk: Interfaces added after installation (a new Wi-Fi adapter, VPN) get the default setting. Enable it only after testing on the specific network.
- **Firewall on for all profiles, inbound blocked, dropped packets logged** (`network.firewall`). Level: recommended. "Office": enabled; "Strict": enabled.
  Policy for the domain, private and public profiles: the firewall is on and cannot be turned off from Control Panel, inbound connections are blocked by default, outbound connections are allowed, dropped packets are written to a 16 MB file.
  Effect: Allow rules (file and printer sharing, Delivery Optimization, mDNS) keep working; during an investigation you can see who tried to connect to which ports.
  Risk: The network profile (private/public) is not set by the file; folder sharing requires the private profile.

## Removable media and scripts

AutoRun, script files, VBScript.

- **AutoRun and AutoPlay disabled for all media** (`removable.autorun-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  AutoRun is disabled for all drive types, autorun.inf files are ignored even on CDs, and AutoPlay is turned off for devices without a drive letter (phones, cameras).
  Effect: Connecting a USB flash drive, disk or phone launches nothing and asks nothing. Running a file manually is covered by the ASR rule for USB.

### Script files

- **Script files (.js .vbs .hta and others) open in Notepad** (`scripts.open-in-notepad`). Level: recommended. "Office": enabled; "Strict": enabled.
  Double-clicking a .js, .jse, .vbs, .vbe, .wsf, .wsh or .hta file shows its text in Notepad instead of running it.
  Effect: The classic "archive with a script inside" phishing (invoice.pdf.js) does not work. cscript, wscript and mshta still work from the command line and from programs.
  Risk: Installers that run .vbs files through the shell (rare) will open Notepad. A file association in the user profile (Open with) overrides this one.
- **Remove the VBScript engine** (`scripts.remove-vbscript`). Level: risky. "Office": disabled; "Strict": enabled.
  The VBScript interpreter is removed as an optional feature.
  Effect: Neither .vbs files, nor VBScript macros in old programs, nor the MSScriptControl component work.
  Risk: Program installers from the 2000s, some printer drivers and old business applications use VBScript. The Notepad association provides most of the protection without breaking anything.

## Browsers

Microsoft Edge, Google Chrome and Brave policies: security, telemetry, advertising, AI features. All rules except two Edge rules from v0.2 are off by default; policies for a browser that is not installed have no effect.

### Microsoft Edge

- **SmartScreen in Edge on, bypass not allowed** (`edge.smartscreen-locked`). Level: recommended. "Office": enabled; "Strict": enabled.
  Reputation checks for sites and downloads, blocking of potentially unwanted downloads; after a warning the user cannot "continue to the site" or "keep anyway".
  Effect: Edge protects against phishing and malicious downloads, and the warning cannot be bypassed with a single click.
- **Edge without first-run experience, ads and background processes** (`edge.baseline`). Level: baseline. "Office": enabled; "Strict": enabled.
  The first-run experience is hidden; recommendations, reporting for personalization, startup boost and background mode are turned off.
  Effect: Edge remains the emergency browser: without it you cannot download another browser. It shows no ads and uses no memory in the background.
- **Edge: do not send diagnostic data** (`edge.diagnostic-data-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not send required or optional diagnostic data about the browser to Microsoft.
  Effect: Information about browser usage and visited sites is not sent to Microsoft. Replaces the deprecated MetricsReportingEnabled and SendSiteInfoToImproveServices policies from the issue #1 script.
- **Edge: do not collect queries to third-party search engines** (`edge.search-telemetry-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not collect information about searches on third-party search engines (3P SERP telemetry).
  Effect: Queries to Google and other search engines are not included in Edge telemetry.
- **Edge: hide the sidebar** (`edge.sidebar-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Edge sidebar with apps and shortcuts is not shown.
  Effect: Fewer distracting elements. Before Edge 141, hiding the sidebar also hides the Copilot button; starting with version 141, the Copilot icon is controlled by a policy that applies only to Entra ID profiles.
- **Edge: turn off the shopping assistant** (`edge.shopping-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not show price comparisons, coupons or cashback on store websites.
  Effect: No pop-up offers on store pages, and the addresses of those pages are not sent to the shopping service.
- **Edge: hide Microsoft Rewards** (`edge.rewards-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Microsoft Rewards bonus program is not shown in Edge, and its switch in settings is turned off.
  Effect: No offers to earn points for searches and purchases.
- **Edge: no Edge Insider program promotion** (`edge.insider-promo-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not offer to install preview builds of the browser.
  Effect: Users do not install unstable versions of Edge in response to a promotional offer.
- **Edge: block sync** (`edge.sync-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Sync of Edge favorites, passwords, history and settings with a cloud account is turned off.
  Effect: Browser data does not go to the cloud and does not end up on employees' personal devices.
  Risk: Favorites and settings are not carried over between the user's computers.
- **Edge: do not offer page translation** (`edge.translate-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not offer to translate a page written in another language.
  Effect: Page text is not sent to a cloud translation service.
  Risk: Employees who read foreign-language websites lose built-in translation.
- **Edge: turn off Web Capture** (`edge.web-capture-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The feature for capturing a page or parts of it (Web Capture) is unavailable.
  Effect: Fewer built-in features that send page content to Microsoft services.
  Risk: Page screenshots have to be taken with Windows tools.
- **Edge: do not save addresses for autofill** (`edge.autofill-address-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not save addresses or fill them into forms.
  Effect: Employees' personal data is not stored in the browser profile.
- **Edge: no search suggestions** (`edge.search-suggest-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Edge address bar does not show search engine suggestions.
  Effect: Typed text is not sent to the search engine until Enter is pressed.
- **Edge: no feedback submission** (`edge.feedback-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The feedback button and sending feedback to Microsoft are disabled.
  Effect: Screenshots and problem descriptions are not sent from the browser to Microsoft.
- **Edge: block browser sign-in** (`edge.signin-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Signing in to Edge with a Microsoft account or a work account is blocked.
  Effect: The browser profile stays local and is not linked to a cloud account.
  Risk: Sync and features that require sign-in are unavailable. In the issue #1 script this line is commented out: enable it deliberately.
- **Edge: block password saving** (`edge.password-manager-off`). Level: risky. "Office": disabled; "Strict": disabled.
  The built-in Edge password manager does not offer to save passwords.
  Effect: Passwords are not stored in the browser profile.
  Risk: Without a password manager, users reuse passwords or write them down more often. Enable only if the organization has a separate password manager. In the issue #1 script this line is commented out: enable it deliberately.
- **Edge: do not save payment cards** (`edge.autofill-cards-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Edge does not save payment card details or fill them into forms.
  Effect: Card details are not stored in the browser profile.
  Risk: In the issue #1 script this line is commented out: enable it deliberately.

### Google Chrome

- **Chrome: do not send usage statistics and crash reports** (`chrome.metrics-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not send usage statistics and crash reports to Google.
  Effect: Information about browser operation is not sent to Google.
- **Chrome: limit field trials (variations)** (`chrome.variations`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not enable experimental features for the user that Google rolls out without a browser update.
  Effect: Browser behavior changes only with updates. Value 1 keeps urgent security fixes.
  Risk: Value 2 may delay critical security fixes: Google does not recommend it. The issue #1 script used the nonexistent name ChromeVariationsEnabled.
- **Chrome: sync with Google** (`chrome.sync`). Level: optional. "Office": disabled; "Strict": disabled.
  Sync of Chrome bookmarks, passwords, history and settings with a Google account is blocked (or left to the user's choice).
  Effect: Browser data does not go to the Google cloud and does not end up on employees' personal devices.
  Risk: The issue #1 script set 0, which leaves the choice to the user; here the default is to block it, as for Edge.
- **Chrome: do not run in the background after closing** (`chrome.background-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome and its apps do not keep running after the last window is closed.
  Effect: The browser does not use memory or network when it is not in use.
- **Chrome: turn off generative AI features** (`chrome.genai-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome generative AI features (writing help, tab organization, history search and others) are blocked by default.
  Effect: Page content and employees' texts are not sent to Google models.
- **Chrome: do not download the local AI model** (`chrome.genai-local-model-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not download a local generative AI model to the computer.
  Effect: A model several gigabytes in size does not appear on the disk, and no network traffic is spent.
- **Chrome: turn off AI in developer tools** (`chrome.devtools-genai-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Generative AI features in Chrome developer tools are blocked.
  Effect: Page code and data are not sent to Google models from DevTools.
- **Chrome: turn off Google Lens over the page** (`chrome.lens-overlay-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Google Lens search of screen content (Lens Overlay) is unavailable.
  Effect: Page screenshots are not sent to Google for visual search.
  Risk: The issue #1 script set 0, which allows the feature; here it is 1. Starting with Chrome 147, the policy is deprecated.
- **Chrome: do not offer page translation** (`chrome.translate-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not offer to translate a page written in another language.
  Effect: Page text is not sent to the Google cloud translation service.
  Risk: Employees who read foreign-language websites lose built-in translation.
- **Chrome: block browser sign-in** (`chrome.signin-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Signing in to Chrome with a Google account is blocked.
  Effect: The browser profile stays local and is not linked to a Google account.
  Risk: Sync and features that require sign-in are unavailable.
- **Chrome: no search suggestions** (`chrome.search-suggest-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Chrome address bar does not show search engine suggestions.
  Effect: Typed text is not sent to the search engine until Enter is pressed.
- **Chrome: Cast only on the local network** (`chrome.cast-private-only`). Level: optional. "Office": disabled; "Strict": disabled.
  Google Cast connects only to devices with private local network addresses.
  Effect: The screen cannot be cast to devices with public addresses.
- **Chrome: no promotional pages or campaigns** (`chrome.promotions-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not show Google promotional tabs and campaigns.
  Effect: Less advertising when the browser starts and updates. Replaces the deprecated PromotionalTabsEnabled policy from the issue #1 script.
- **Chrome: block password saving** (`chrome.password-manager-off`). Level: risky. "Office": disabled; "Strict": disabled.
  The built-in Chrome password manager does not offer to save passwords.
  Effect: Passwords are not stored in the browser profile.
  Risk: Without a password manager, users reuse passwords or write them down more often. Enable only if the organization has a separate password manager. In the issue #1 script this line is commented out: enable it deliberately.
- **Chrome: do not save addresses for autofill** (`chrome.autofill-address-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not save addresses or fill them into forms.
  Effect: Employees' personal data is not stored in the browser profile.
  Risk: In the issue #1 script this line is commented out: enable it deliberately.
- **Chrome: do not save payment cards** (`chrome.autofill-cards-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome does not save payment card details or fill them into forms.
  Effect: Card details are not stored in the browser profile.
  Risk: In the issue #1 script this line is commented out: enable it deliberately.
- **Chrome: Windows DNS instead of the built-in client** (`chrome.builtin-dns-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Chrome resolves names through the Windows DNS client rather than its own built-in one.
  Effect: The organization's DNS settings, the hosts file and filtering DNS, if any, take effect.
  Risk: In the issue #1 script this line is commented out: enable it deliberately.

### Brave

- **Brave: turn off Brave Rewards** (`brave.rewards-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Brave Rewards program, which rewards users for viewing ads, is unavailable.
  Effect: The browser does not show its own ads and does not award tokens.
- **Brave: turn off the crypto wallet** (`brave.wallet-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The built-in Brave Wallet cryptocurrency wallet is unavailable.
  Effect: Cryptocurrency wallets and extensions do not appear on work computers.
- **Brave: turn off Brave VPN** (`brave.vpn-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The paid Brave VPN is unavailable.
  Effect: Browser traffic does not go through a VPN, bypassing the organization's network rules.
- **Brave: turn off the Leo AI assistant** (`brave.ai-chat-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Leo AI assistant (AI Chat) in Brave is unavailable.
  Effect: Page content and employees' texts are not sent to AI models. The issue #1 script also used the nonexistent name BraveLeoEnabled.
- **Brave: no daily usage report** (`brave.stats-ping-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Brave does not send the daily anonymous usage signal (stats ping).
  Effect: Fewer browser connections to Brave servers. The issue #1 script also used the nonexistent name BraveStatsPingDisabled.
- **Brave: no product analytics (P3A)** (`brave.p3a-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Brave does not send anonymized P3A product analytics.
  Effect: Information about the use of browser features is not sent to Brave. The issue #1 script used the nonexistent name BraveP3ADisabled.
- **Brave: turn off Brave News** (`brave.news-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Brave News feed on the new tab page is unavailable.
  Effect: The new tab page has no news or promotional content.
- **Brave: turn off Brave Talk** (`brave.talk-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Brave Talk video calling service is unavailable.
  Effect: Video calls go only through services approved by the organization.
- **Brave: turn off Playlist** (`brave.playlist-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The feature for saving video and audio for offline viewing (Playlist) is unavailable.
  Effect: Media files do not accumulate in the browser profile.
- **Brave: turn off Speedreader** (`brave.speedreader-off`). Level: optional. "Office": disabled; "Strict": disabled.
  The Speedreader simplified reading mode is unavailable.
  Effect: Fewer built-in features that change how pages look.
- **Brave: no Wayback Machine prompts** (`brave.wayback-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Brave does not offer to open an archived copy of an unavailable page in the Wayback Machine.
  Effect: Addresses of unavailable pages are not sent to the internet archive.
- **Brave: turn off Web Discovery** (`brave.web-discovery-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Brave does not share information about visited pages to populate its search index.
  Effect: Addresses of visited sites are not sent to Brave Search.
- **Brave: do not offer page translation** (`brave.translate-off`). Level: optional. "Office": disabled; "Strict": disabled.
  Brave does not offer to translate a page written in another language.
  Effect: Page text is not sent to a cloud translation service.
  Risk: Employees who read foreign-language websites lose built-in translation.
- **Brave: block Tor windows** (`brave.tor-off`). Level: recommended. "Office": disabled; "Strict": disabled.
  Private windows connected to the Tor network are unavailable in Brave.
  Effect: Browser traffic does not go to the Tor network, bypassing the organization's filtering and logs.

## Logging for investigations

Auditing, log sizes, PowerShell logging, disabling PowerShell 2.0.

- **Larger event logs (Security 256 MB, System and Application 64 MB, PowerShell 128 MB)** (`logging.eventlog-sizes`). Level: recommended. "Office": enabled; "Strict": enabled.
  Log sizes are raised from 20 MB (15 MB for PowerShell) so that several weeks of history are not overwritten.
  Effect: Without this rule, auditing and PowerShell logging become useless within a few days.
- **Auditing: process creation with command line, logons, lockouts, accounts, removable storage** (`logging.audit-policy`). Level: recommended. "Office": enabled; "Strict": enabled.
  Event 4688 includes the full command line; the subcategories for logon, account lockout, user account and group management, credential validation, scheduled tasks and removable storage are enabled. Subcategories are specified by GUID: on the Ukrainian image auditpol does not accept English names.
  Effect: In an incident, the Security log lets you reconstruct the chain: which process, with which arguments, under which user.
  Risk: Removable storage auditing writes many events when large folders are copied to a USB flash drive.
- **PowerShell logging: script blocks and cmdlet invocations** (`logging.powershell`). Level: recommended. "Office": enabled; "Strict": enabled.
  The text of every executed script block (event 4104, including deobfuscated code) and the cmdlet invocations of all modules (4103) are written to the PowerShell log.
  Effect: Malicious PowerShell loaders leave their full text in the log even after the file is deleted.
  Risk: Secrets that an administrator passes on the command line end up in the log; only administrators have access to the log.
- **PowerShell 2.0 disabled** (`logging.powershell-v2-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The old engine, which supports neither logging nor antivirus scanning (AMSI), is disabled as a Windows feature.
  Effect: The powershell -Version 2 command does not work; downgrade attacks are impossible.

## Telemetry, ads, AI

Minimal data sending, disabling ads and preinstalled apps, Copilot and Recall, widgets, web search.

- **Minimal telemetry without disabling compatibility assessment** (`privacy.telemetry-minimal`). Level: recommended. "Office": enabled; "Strict": enabled.
  Diagnostic data level "Required" (the minimum for Pro), no feedback requests, no device name in the data, advertising ID off, error reports not sent, activity history not collected, the DiagTrack service set to Manual, the CEIP and Feedback tasks disabled.
  Effect: The minimum data sending available on Pro. DiagTrack is intentionally not disabled: compatibility assessment for feature updates and Defender reporting need it.
  Risk: Crash reports are not sent to Microsoft; local events 1000/1001 in the Application log remain.
- **No ads, preinstalled apps or automatic Teams installation (machine policies)** (`privacy.consumer-content`). Level: recommended. "Office": enabled; "Strict": enabled.
  CloudContent policies (some apply only to Enterprise/Education and are kept because they are harmless), the Teams Chat icon hidden, automatic installation of personal Teams disabled.
  Effect: On Pro the main working mechanism is the values in the default user profile (a separate rule in the profile group); this part enforces the same at the machine level.
- **Copilot, Recall and Click to Do turned off** (`privacy.copilot-recall-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Copilot and WindowsAI policies: Recall (screen snapshots) is off and cannot be turned on by the user, Click to Do is off; the Recall feature is disabled if present.
  Effect: No AI component takes screen snapshots or sends document contents. The Copilot app is removed by a separate rule in the apps group.
- **Widgets and news feed turned off** (`privacy.widgets-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The Windows 11 widgets board and the Windows 10 "News and interests" feed are disabled by policy.
  Effect: No widgets button and no constantly open MSN web page with ads; the Widgets.exe process does not start.
- **No Bing web results in Start menu search** (`privacy.web-search-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Start menu search finds only apps, files and settings; nothing is sent to Bing while typing.
  Effect: Indexing and search in File Explorer and Outlook are not affected (the WSearch service is left untouched).

## System

Other system settings.

- **Long path support (more than 260 characters)** (`system.long-paths`). Level: optional. "Office": enabled; "Strict": enabled.
  Programs with the longPathAware manifest (PowerShell 7, Git, modern archivers) work with paths longer than 260 characters.
  Effect: File Explorer and older programs keep the limit; harmless.

## Services and apps

Disabling unnecessary services and removing apps.

- **Retail demo service disabled** (`apps.retail-demo-off`). Level: baseline. "Office": enabled; "Strict": enabled.
  The RetailDemo service is needed only on store display PCs.
  Effect: One background service fewer.
- **Xbox services disabled, game recording (Game DVR) off** (`apps.xbox-services-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  Xbox Live services (authentication, game saves, networking, controllers) are disabled; a policy prohibits game recording and Game Bar.
  Effect: No Xbox background services and no background screen recording that slows down low-end PCs. Store games that use Xbox Live do not work.
- **Offline maps download service disabled** (`apps.maps-broker-off`). Level: optional. "Office": enabled; "Strict": enabled.
  MapsBroker serves the Maps app; without the app the service is not needed. In the v0.2 file it was disabled under the Xbox condition; here it is tied to removing Maps.
  Effect: One automatic service fewer.
- **Remove Quick Assist** (`apps.remove-quick-assist`). Level: recommended. "Office": enabled; "Strict": enabled.
  The built-in remote control tool that "tech support" scammers ask people to launch over the phone is removed (the Windows 10 feature and the Windows 11 Store version).
  Effect: The organization chooses its own tool for support by its administrator. The user can reinstall Quick Assist from the Store.

### Apps to remove

Each app is a separate rule: clear the check box to keep the app.

- **Bing Search (for the Start menu)** (`apps.remove.bing-search`). Level: optional. "Office": enabled; "Strict": enabled.
  Sends Start menu queries to Bing and shows ads.
  Effect: Present in the 24H2 image and later.
- **News (MSN)** (`apps.remove.bing-news`). Level: optional. "Office": enabled; "Strict": enabled.
  MSN news with ads.
  Effect: Present in Windows 10 and 11 up to 23H2.
- **Weather (MSN)** (`apps.remove.bing-weather`). Level: optional. "Office": enabled; "Strict": enabled.
  MSN Weather: ads and location requests.
  Effect: Present in all versions.
- **Get Help (technical support)** (`apps.remove.get-help`). Level: optional. "Office": enabled; "Strict": enabled.
  Chat with Microsoft support; not needed and serves as a channel for "support" scams.
  Effect: Present in all versions.
- **Tips (Get Started)** (`apps.remove.get-started`). Level: optional. "Office": enabled; "Strict": enabled.
  Advertising for Windows features.
  Effect: Present in Windows 10 and 11 up to 22H2.
- **Feedback Hub** (`apps.remove.feedback-hub`). Level: optional. "Office": enabled; "Strict": enabled.
  Sends feedback and diagnostics to Microsoft.
  Effect: Present in all versions.
- **3D Viewer** (`apps.remove.3d-viewer`). Level: optional. "Office": enabled; "Strict": enabled.
  Viewer for 3D models; not needed in an office.
  Effect: Present in Windows 10 and 11 up to 22H2.
- **Mixed Reality Portal** (`apps.remove.mixed-reality`). Level: optional. "Office": enabled; "Strict": enabled.
  Outdated portal for VR headsets.
  Effect: Present in Windows 10 and 11 up to 23H2.
- **Microsoft Solitaire Collection** (`apps.remove.solitaire`). Level: optional. "Office": enabled; "Strict": enabled.
  Card games with ads.
  Effect: Present in all versions.
- **Xbox app** (`apps.remove.xbox-gaming-app`). Level: optional. "Office": enabled; "Strict": enabled.
  Game store and Xbox Live.
  Effect: Present in all versions.
- **Xbox (old Windows 10 app)** (`apps.remove.xbox-app`). Level: optional. "Office": enabled; "Strict": enabled.
  The old Xbox app.
  Effect: Present in Windows 10.
- **Game Bar (overlay)** (`apps.remove.xbox-game-overlay`). Level: optional. "Office": enabled; "Strict": enabled.
  Game Bar overlay: background screen recording.
  Effect: Present in all versions.
- **Game Bar (Xbox Gaming Overlay)** (`apps.remove.xbox-gaming-overlay`). Level: optional. "Office": enabled; "Strict": enabled.
  The second part of Game Bar.
  Effect: Present in all versions.
- **Xbox Identity Provider** (`apps.remove.xbox-identity`). Level: optional. "Office": enabled; "Strict": enabled.
  Sign-in to Xbox Live.
  Effect: Present in all versions.
- **Game Bar captions (Speech to Text)** (`apps.remove.xbox-speech-to-text`). Level: optional. "Office": enabled; "Strict": enabled.
  Captions for game chat.
  Effect: Present in all versions.
- **Xbox Live interface (TCUI)** (`apps.remove.xbox-tcui`). Level: optional. "Office": enabled; "Strict": enabled.
  Internal Xbox Live interface component.
  Effect: Present in all versions.
- **Game Assist (Edge in-game overlay)** (`apps.remove.edge-game-assist`). Level: optional. "Office": enabled; "Strict": enabled.
  The browser's in-game overlay.
  Effect: Present in 24H2 and later (2025).
- **Maps** (`apps.remove.maps`). Level: optional. "Office": enabled; "Strict": enabled.
  Offline maps and the MapsBroker service.
  Effect: Present in all versions.
- **People (contacts)** (`apps.remove.people`). Level: optional. "Office": enabled; "Strict": enabled.
  Outdated contacts app with cloud sync.
  Effect: Present in Windows 10 and 11 up to 23H2.
- **Phone Link** (`apps.remove.phone-link`). Level: optional. "Office": enabled; "Strict": enabled.
  Access to the phone's SMS messages and files through the Microsoft cloud.
  Effect: Present in all versions.
- **Power Automate** (`apps.remove.power-automate`). Level: optional. "Office": enabled; "Strict": enabled.
  Desktop automation tool; potential for abuse.
  Effect: Present in Windows 10 21H2+ and 11.
- **Microsoft To Do** (`apps.remove.todo`). Level: optional. "Office": enabled; "Strict": enabled.
  Requires a Microsoft account.
  Effect: Present in all versions.
- **Family Safety** (`apps.remove.family`). Level: optional. "Office": enabled; "Strict": enabled.
  Requires a Microsoft account.
  Effect: Present in Windows 11 22H2+.
- **Dev Home** (`apps.remove.dev-home`). Level: optional. "Office": enabled; "Strict": enabled.
  Developer tool, retired in 2025.
  Effect: Present in Windows 11 23H2-24H2.
- **Clipchamp (video editor)** (`apps.remove.clipchamp`). Level: optional. "Office": enabled; "Strict": enabled.
  Cloud service with subscription ads.
  Effect: Present in Windows 11 22H2+.
- **Teams (personal)** (`apps.remove.teams`). Level: optional. "Office": enabled; "Strict": enabled.
  Not the work version; Teams for work is installed separately.
  Effect: Present in Windows 11 23H2+.
- **Skype** (`apps.remove.skype`). Level: optional. "Office": enabled; "Strict": enabled.
  The service was shut down in 2025.
  Effect: Present in Windows 10 and 11 up to 23H2.
- **Office (Microsoft 365 launcher)** (`apps.remove.office-hub`). Level: optional. "Office": enabled; "Strict": enabled.
  Advertising for a Microsoft 365 subscription.
  Effect: Present in all versions.
- **New Outlook** (`apps.remove.outlook-new`). Level: optional. "Office": enabled; "Strict": enabled.
  Mail through the Microsoft cloud; syncs IMAP passwords to the cloud.
  Effect: Present in Windows 11 23H2+. Clear the check box if employees use the new Outlook.
- **Mail and Calendar** (`apps.remove.mail-calendar`). Level: optional. "Office": enabled; "Strict": enabled.
  Replaced by the new Outlook and no longer updated.
  Effect: Present in Windows 10 and 11 up to 24H2.
- **Copilot (app)** (`apps.remove.copilot`). Level: optional. "Office": enabled; "Strict": enabled.
  AI assistant that sends data.
  Effect: Present in Windows 11 24H2+.
- **Copilot provider** (`apps.remove.copilot-provider`). Level: optional. "Office": enabled; "Strict": enabled.
  Internal Copilot component.
  Effect: Present in Windows 11 23H2.
- **Cortana** (`apps.remove.cortana`). Level: optional. "Office": enabled; "Strict": enabled.
  Removed by Microsoft in 2023; present on old images.
  Effect: Present in Windows 10 and 11 up to 22H2.

## Default user profile

Values that every new user gets at first sign-in (can be changed in Settings).

- **Show file name extensions** (`default-user.show-file-extensions`). Level: baseline. "Office": enabled; "Strict": enabled.
  File name extensions are visible: "invoice.pdf.exe" cannot pass itself off as a PDF.
  Effect: The most important security setting in this section; by default Windows hides extensions.
- **No OneDrive and Microsoft 365 ads in File Explorer** (`default-user.no-sync-provider-ads`). Level: baseline. "Office": enabled; "Strict": enabled.
  Sync provider notifications in File Explorer are turned off.
  Effect: File Explorer does not show OneDrive and subscription banners.
- **No preinstalled apps, ads, tips or "Let's finish setting up" screen** (`default-user.no-consumer-content`). Level: recommended. "Office": enabled; "Strict": enabled.
  17 ContentDeliveryManager values (the Store does not install apps silently, no tips or "fun facts"), no "Let's finish setting up your device" screen, no recommendations or Microsoft account reminders in Start, advertising ID and tailored experiences turned off.
  Effect: These values do on Pro what the DisableWindowsConsumerFeatures policy does on Enterprise.
- **Widgets button hidden** (`default-user.widgets-button-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The widgets button on the taskbar is hidden for every new user (duplicates the Dsh policy).
  Effect: A taskbar without the weather and news button.
- **Copilot turned off in the user profile** (`default-user.copilot-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The Copilot button is hidden; the TurnOffWindowsCopilot user policy is written to the profile (the only level where it applies).
  Effect: Copilot Preview (23H2) does not appear; in 24H2 the app is removed by a separate rule.
- **No AutoPlay dialog for media** (`default-user.autoplay-off`). Level: recommended. "Office": enabled; "Strict": enabled.
  The "What do you want to do with this media?" dialog is turned off for every new user.
  Effect: Complements the machine-level AutoRun policy.
- **User region** (`default-user.region`). Level: baseline. "Office": enabled; "Strict": enabled.
  Country (GeoID) for new users: affects the Store, weather and content offers; does not change the display language or the time zone.
  Effect: Default is Ukraine (241, UA).
- **Do not share the user's language list with websites** (`default-user.http-accept-language-optout`). Level: optional. "Office": enabled; "Strict": enabled.
  Browsers do not send the list of preferred languages to websites (reduces the fingerprint).
  Effect: Websites determine the language by other means.

## First sign-in of each user

Active Setup script: display language and input language list.

- **Pin the display language to the image language** (`user-logon.pin-ui-language`). Level: baseline. "Office": enabled; "Strict": enabled.
  Set-WinUILanguageOverride locks the display language to the installed one so that reordering input languages (English first) does not switch the interface.
  Effect: The customer's requirement "do not change the display language" relies on this line.
- **User input language list from the profile (including "Russian (Ukraine)")** (`user-logon.input-languages`). Level: recommended. "Office": enabled; "Strict": enabled.
  Replaces the user's input language list with the list from the "Languages and region" node (by default en-US, uk-UA, ru-UA). Languages without a numeric code, such as "Russian (Ukraine)", cannot be set in XML, so they are applied here; if Windows has not assigned them a keyboard layout, a fallback list is applied in which they are replaced with the base language.
  Effect: The user's language switcher shows the same order as the profile; the sign-in screen keeps the list from XML (with the base language instead of "Russian (Ukraine)").

## After OOBE

Scheduled task after OOBE completes: passwords, built-in accounts, cleanup.

- **"Password never expires" flag on the initial accounts** (`post-oobe.password-never-expires`). Level: recommended. "Office": enabled; "Strict": enabled.
  PasswordNeverExpires is set for every account in the profile. Duplicates the machine-wide net accounts setting in case it is changed.
  Effect: The initial accounts without a password will not be required to change the password.
- **Built-in Administrator and Guest stay disabled** (`post-oobe.disable-builtin-accounts`). Level: baseline. "Office": enabled; "Strict": enabled.
  The accounts with RID 500 and 501 are found by SID (the names are localized on the Ukrainian image) and disabled if they are enabled.
  Effect: The well-known names cannot be used to sign in.
- **Move specialize pass errors to the log** (`post-oobe.collect-specialize-errors`). Level: baseline. "Office": enabled; "Strict": enabled.
  If the specialize command wrappers recorded an error (the script was not extracted or failed), its text goes to Post-OOBE.log marked SPECIALIZE ERROR.
  Effect: The only way to find out that the machine script did not run.
- **Delete answer file copies from the system** (`post-oobe.delete-answer-file-copies`). Level: baseline. "Office": enabled; "Strict": enabled.
  Windows 11 24H2 leaves copies of the answer file (with account names and passwords, if there were any) in C:\Windows\Panther; they are deleted.
  Effect: No description of the accounts remains on the disk.
