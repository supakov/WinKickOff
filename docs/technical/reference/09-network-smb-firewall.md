# 09. SMB, name resolution, firewall

Section 5 of `Setup-System.ps1`. Notation: `Srv` = `HKLM\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters`,
`Wks` = `HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters`.

General context: a workgroup without a domain relies on SMB (shared folders, printers), NetBIOS and mDNS
(computer names), and the typical attack inside the network is spoofing responses to broadcast name
queries (LLMNR/NBT-NS poisoning) followed by interception of NTLM hashes. This section closes these vectors
while keeping sharing functional.

## DisableSMB1

- Value: `$true`.
- What it does:
  1. `Srv\SMB1 = 0`: the server does not respond over SMB1;
  2. the `mrxsmb10` driver service (the SMB1 client part) gets startup type 4, if present;
  3. `Disable-WindowsOptionalFeature -FeatureName SMB1Protocol`, if the feature is installed.
- Expected effect: the 1996 protocol through which WannaCry and NotPetya spread
  is completely absent.
- Cross-links: devices that support only SMB1 (printers and MFPs with scan to a network folder
  released before 2015, old NAS devices, Windows XP) will not be able to connect to the shared folders of these PCs, and
  vice versa. Solution: update the MFP firmware to SMB2/3, or scan to FTP/e-mail, or use
  a separate old PC as a "gateway". SMB1 must not be turned back on.
- Version differences: Windows 11 24H2 does not contain SMB1 at all (the feature was removed from the image, so the
  WARN "service mrxsmb10 not present" in the log is expected). Windows 10 1709+ and Windows 11 21H2-23H2:
  SMB1 is not installed by default, but the feature is available for enabling; the file disables it.
  Windows 10 before 1709: SMB1 is installed, and the file removes it.
- Verification: `Get-SmbServerConfiguration | Select EnableSMB1Protocol` → False;
  `Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol` → Disabled or absent.
- Rollback: not recommended; `Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol` on builds
  where it exists.

## RequireSMBSigning

- Value: `$true`.
- What it does: `Srv\RequireSecuritySignature = 1`, `Srv\EnableSecuritySignature = 1`,
  `Wks\RequireSecuritySignature = 1`, `Wks\EnableSecuritySignature = 1`.
- Expected effect: every SMB packet is signed; "man-in-the-middle" attacks and NTLM relay
  against shared folders are impossible. Performance on a gigabit network drops by a few
  percent, which is unnoticeable for office work.
- Cross-links:
  - A client with mandatory signing will not connect to a server without signing, and vice versa. Windows PCs
    of the workgroup configured by this file are compatible with each other. Old NAS devices and MFPs without support for
    SMB2 signing drop out (the same group of devices as for SMB1 and NTLMv1).
  - `NTLMv2Only` (section 08) and `DisableLLMNR` complement the protection: signing prevents relaying,
    NTLMv2 prevents cracking what was intercepted, and disabling LLMNR prevents interception.
- Version differences: Windows 11 24H2 and Server 2025 themselves require SMB signing for all connections
  on Pro and Enterprise (the new default since 2024); the file does this explicitly for Windows 10 and for Windows 11 up to 23H2,
  where the default is "signing not required". On Home 24H2 signing is not required.
- Verification: `Get-SmbServerConfiguration | Select RequireSecuritySignature`;
  `Get-SmbClientConfiguration | Select RequireSecuritySignature` → True, True.
- Rollback: `Set-SmbServerConfiguration -RequireSecuritySignature $false`;
  `Set-SmbClientConfiguration -RequireSecuritySignature $false`.

## DisableLLMNR

- Value: `$true` → `HKLM\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient\EnableMulticast = 0`.
- What it does: disables Link-Local Multicast Name Resolution: the broadcast query "who is PC-BUH?",
  which any host on the network can answer, including an attacker.
- Expected effect: Responder-class tools stop receiving hashes from these PCs through LLMNR.
- Cross-links: name resolution for workgroup computers keeps working through NetBIOS
  (left enabled, see below) and mDNS (Windows 10 1703+, answers `имя.local`). If NetBIOS is
  turned off as well, only mDNS and the router's DNS remain.
- Version differences: the policy exists since Windows Vista. In Windows 11 24H2 Microsoft declared LLMNR deprecated
  in favor of mDNS; disabling it follows that direction.
- Verification: `Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -Name EnableMulticast` → 0.
- Rollback: delete the value.

## DisableNetBIOS

- Value: `$false` (NetBIOS is left enabled).
- What it does when `$true`: `HKLM\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\NodeType = 2`
  (P-node: WINS only, no broadcast) and, for each interface in
  `NetBT\Parameters\Interfaces\Tcpip_{GUID}`, the value `NetbiosOptions = 2` (NetBIOS over TCP/IP is off).
- Expected effect when `$true`: the second name spoofing channel (NBT-NS poisoning) and ports 137-139 are closed.
- Why it is off by default: without a domain and WINS, names like `\\PC-BUH` are resolved through NetBIOS
  or mDNS. mDNS in Windows answers only queries of the form `pc-buh.local`; the usual `\\PC-BUH` entry
  in File Explorer may not be found without NetBIOS, and users and shortcuts to shared folders are used to that form.
  In addition, interfaces added after installation (a new Wi-Fi adapter, VPN) will get the default.
- Cross-links: a workaround is the `hosts` file or DNS records on the router. The parameter is intended
  for the "Strict" preset after verification in the specific network.
- Version differences: the values have been the same since Windows 2000. In 24H2 NetBIOS is still enabled by default.
- Verification: `Get-CimInstance Win32_NetworkAdapterConfiguration | Select Description, TcpipNetbiosOptions`.
- Rollback: `NetbiosOptions = 0` (via DHCP) for the interfaces, delete `NodeType`.

## FirewallOnWithLogging

- Value: `$true`.
- What it does: for each profile `DomainProfile`, `PrivateProfile`, `PublicProfile` in
  `HKLM\SOFTWARE\Policies\Microsoft\WindowsFirewall\<профиль>`:
  - `EnableFirewall = 1`;
  - `DefaultInboundAction = 1` (block inbound connections not allowed by rules);
  - `DefaultOutboundAction = 0` (outbound connections are allowed);
  - `Logging\LogDroppedPackets = 1`, `Logging\LogFileSize = 16384` (KB), `Logging\LogFilePath =
    %systemroot%\system32\LogFiles\Firewall\pfirewall.log`.
- Expected effect: the firewall cannot be turned off from Control Panel (policy); dropped
  inbound packets are written to a 16 MB log file (rotated to `.old` when full). During an investigation
  you can see who knocked on which ports.
- Cross-links:
  - Allow rules (file and printer sharing, Delivery Optimization, mDNS) keep
    working: the policy sets only the default action. Local rules created by
    program installers are applied (local policy merge is enabled by default).
  - The file does not set the network profile (private/public): on the first connection Windows 11 asks
    "Allow discovery?" for a wired network or assigns the public profile. Folder sharing
    requires the private profile: a parameter of the future constructor.
  - Successful connections are not logged (`LogSuccessfulConnections` is not set): there are too many of them.
- Version differences: the policy has been the same since Windows Vista. Unchanged on 24H2.
- Verification: `Get-NetFirewallProfile | Select Name, Enabled, DefaultInboundAction, LogBlocked`;
  the file `C:\Windows\System32\LogFiles\Firewall\pfirewall.log`.
- Rollback: delete the profile keys under `Policies\Microsoft\WindowsFirewall`.
