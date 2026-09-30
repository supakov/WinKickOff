# 08. UAC, credential protection, lockout, remote access, BitLocker

Section 4 of `Setup-System.ps1`. Notation: `Sys` = `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System`,
`Lsa` = `HKLM\SYSTEM\CurrentControlSet\Control\Lsa`.

## Unconditional actions in this section

| Key | Value | Meaning | Windows default |
|---|---|---|---|
| `Sys\EnableLUA` | 1 | UAC enabled | 1 |
| `Sys\PromptOnSecureDesktop` | 1 | UAC prompt on the secure desktop (other programs cannot click through it) | 1 |
| `Sys\ConsentPromptBehaviorUser` | 3 | Standard user: prompt for administrator credentials on the secure desktop | 3 |
| `Sys\EnableInstallerDetection` | 1 | Installers request elevation automatically | 1 |
| `Sys\FilterAdministratorToken` | 1 | The built-in Administrator also runs in Admin Approval Mode | 0 |
| `Sys\LocalAccountTokenFilterPolicy` | 0 | Local administrators get a filtered token on network logon (protection against remote use of a stolen password over SMB/WMI) | 0 |
| `Sys\DisableLockWorkstation` and the same in `Winlogon` | removed | Win+L and locking work | absent |
| `Lsa\NoLMHash` | 1 | LM password hashes are not stored | 1 |
| `Lsa\LimitBlankPasswordUse` | 1 | Accounts with a blank password: console logon only | 1 |
| `Lsa\RestrictAnonymous` | 1 | Anonymous enumeration of shares is denied | 0 on client editions |
| `Lsa\RestrictAnonymousSAM` | 1 | Anonymous enumeration of accounts is denied | 1 |
| `Lsa\EveryoneIncludesAnonymous` | 0 | The «Все» (Everyone) group does not include anonymous users | 0 |
| `HKLM\SYSTEM\CurrentControlSet\Control\SecurityProviders\WDigest\UseLogonCredential` | 0 | Passwords are not kept in memory in clear text (Mimikatz) | 0 since Windows 8.1 |
| `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\kernel\DisableExceptionChainValidation` | 0 | SEHOP enabled (protection against overflow exploits) | 0 on 64-bit |
| `Terminal Server\WinStations\RDP-Tcp\UserAuthentication` | 1 | NLA required if RDP is ever enabled | 1 |
| `Pol\WorkplaceJoin\BlockAADWorkplaceJoin` | 1 | No «Разрешить организации управлять устройством» (Allow my organization to manage my device) prompt when signing in to Office with a work account | 0 |

Cross-links of the unconditional settings: `LimitBlankPasswordUse=1` combined with the blank passwords of the
starter accounts means that, until passwords are assigned, the UAC prompt for User (`ConsentPromptBehaviorUser=3`)
cannot be satisfied with the Admin credentials (error 1327). `RestrictAnonymous=1` may get in the way of very old
devices (printers, NAS) that look for shares anonymously; in that case use the value 0.

## UACAlwaysNotify

- Value: `$true` → `Sys\ConsentPromptBehaviorAdmin = 2`; `$false` → 5 (Windows default).
- Expected effect at 2: the administrator sees a UAC prompt for every elevation, including changes to
  Windows settings. At 5 the prompt appears only for third-party programs, while system components
  elevate silently (which is what UAC bypasses via fodhelper, eventvwr and others exploited).
- Cross-links: the original file set 0 (no prompts at all), which gave any program administrator
  rights without a click. Level 2 closes the known UAC bypasses. For Admin with a blank password
  the UAC prompt is simply a «Да» (Yes) button: protection against automatic elevation, not against the person at the keyboard.
- Version differences: the values have been the same since Windows Vista. No changes in 24H2.
- Side effect at 2: Windows tools whose manifest asks for the highest available rights and that normally
  elevate silently (Task Manager via Ctrl+Shift+Esc, Registry Editor, Computer Management) show a prompt when
  an administrator opens them. A standard user (User) gets no prompt: for such an account these tools open
  without elevation.
- WinKickOff: rule `uac.admin-always-notify`, off by default since 26.09.2026 at the customer's request (no
  prompt for Task Manager), so the "Office" and "Laptop" presets leave Windows at 5; the
  "Strict" preset turns it on with level 2. v0.2 set 2.
- Verification: Control Panel → User Accounts → Change User Account Control settings: slider at the top.
- Rollback: value 5.

## InactivityLockSeconds

- Value: `900` (15 minutes). `0` disables it.
- What it does: `Sys\InactivityTimeoutSecs = 900` (the «Интерактивный вход: предел неактивности компьютера» (Interactive logon: Machine inactivity limit) policy).
- Expected effect: after 15 minutes without input the screen locks regardless of the screen saver and power settings.
- Cross-links: with a blank password, unlocking means pressing Enter; the setting becomes meaningful once
  passwords are assigned. The parameter also applies on the sign-in screen. The screen saver and the display-off timer are not touched.
- Version differences: the policy exists since Windows 8 / Server 2012. Maximum 599940 seconds.
- Verification: `Get-ItemProperty $Sys -Name InactivityTimeoutSecs`.
- Rollback: delete the value.

## LSAProtection

- Value: `$true` → `Lsa\RunAsPPL = 2`.
- What it does: the LSASS process starts as a protected process (Protected Process Light). Other processes,
  even with administrator rights, cannot read its memory and extract hashes and passwords.
- Expected effect: Mimikatz and similar tools do not work; dumping LSASS through Task Manager is impossible.
- Value 2 rather than 1: 1 enables protection with a UEFI lock (a variable that cannot be cleared
  without physical access to the firmware); 2 enables it without the lock, so rollback through the registry is possible.
  For a fleet with old PCs and possible compatibility problems, 2 was chosen.
- Cross-links:
  - Plug-ins loaded into LSA (drivers for smart cards and digital signature tokens, third-party
    authentication providers) must be signed by Microsoft; unsigned ones will not load and will log event
    3033/3063 in the `Microsoft-Windows-CodeIntegrity/Operational` log. Before mass rollout,
    check the digital signature keys used by the organization (Almaz-1K, Crystal-1, SecureToken).
  - The ASR rule for LSASS is not enabled because it is redundant.
  - Credential Guard is not enabled: it requires VBS/Secure Boot and is unavailable on part of the fleet.
- Version differences: the value 2 is understood by Windows 11 22H2 and later; Windows 10 treats any
  non-zero value as 1 (with UEFI lock). Windows 11 22H2+ on a clean install with UEFI and TPM enables LSA protection
  by itself (audit mode, then enforcement); the file does this explicitly, including on PCs without TPM.
- Verification: System log, event 12 from WinInit («LSASS.exe was started as a protected process»);
  `Get-ItemProperty $Lsa -Name RunAsPPL`.
- Rollback: delete the value or set 0, reboot.

## NTLMv2Only

- Value: `$true` → `Lsa\LmCompatibilityLevel = 5`.
- What it does: the client and the server use only NTLMv2 and refuse LM and NTLMv1.
- Expected effect: authentication hashes intercepted on the network cannot be used in old attacks
  on NTLMv1; modern PCs and NAS devices do not notice the change.
- Cross-links: very old NAS devices, printers with scan-to-folder and embedded devices that use NTLMv1
  will stop connecting. Together with `RequireSMBSigning` and `DisableSMB1` (section 09) this forms a single
  "retirement of legacy protocols" group; they should be relaxed together and deliberately.
- Version differences: the default value (when the key is absent) on Windows 10/11 is 3
  (the client sends only NTLMv2, but the server accepts everything). In Windows 11 24H2 Microsoft began
  a phased retirement of NTLM altogether; 5 is consistent with this direction.
- Verification: `Get-ItemProperty $Lsa -Name LmCompatibilityLevel`.
- Rollback: value 3 or delete.

## AccountLockout

- Value: `$true` → `net.exe accounts /lockoutthreshold:10 /lockoutduration:15 /lockoutwindow:15`.
- What it does: after 10 wrong passwords in a row the account is locked for 15 minutes; the counter
  resets after 15 minutes.
- Expected effect: password guessing over the network (SMB, RDP if it is ever enabled) becomes useless.
- Cross-links: applies to all local accounts, including Admin. Irrelevant while passwords are blank;
  once passwords are assigned, this is the first line of defense. The built-in Administrator (RID 500)
  is not locked out by default; it is disabled.
- Version differences: Windows 11 22H2 and later already sets 10/10/10 on a clean install; on Windows 10
  and on upgraded systems the threshold is "never". The file sets the values explicitly.
- Verification: `net accounts`.
- Rollback: `net accounts /lockoutthreshold:0`.

## DisableRemoteAssistance

- Value: `$true`.
- What it does: `HKLM\SYSTEM\CurrentControlSet\Control\Remote Assistance\fAllowToGetHelp = 0`,
  `fAllowFullControl = 0`.
- Expected effect: Remote Assistance invitations (msra.exe) are impossible; the firewall rule
  «Удалённый помощник» (Remote Assistance) is not activated.
- Cross-links: Quick Assist is removed separately (section 13). Remote support by your own administrator
  requires a separate tool (the "remote administration" constructor parameter).
- Version differences: none.
- Verification: System Properties → Remote: the check box is cleared and unavailable.
- Rollback: `fAllowToGetHelp = 1`.

## DisableRemoteDesktopInbound

- Value: `$true` → `HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server\fDenyTSConnections = 1`.
- Expected effect: inbound RDP is off (Windows default); outbound connections to other
  PCs work.
- Cross-links: `UserAuthentication=1` (NLA) applies if RDP is enabled; `AccountLockout` protects
  against password guessing; `LimitBlankPasswordUse` will not let accounts without a password in over RDP. The TermService service
  stays in manual mode.
- Version differences: none.
- Verification: Settings → System → Remote Desktop: off.
- Rollback: value 0 plus the firewall rule «Удалённый рабочий стол» (Remote Desktop) (`Enable-NetFirewallRule -DisplayGroup "Remote Desktop"`).

## DisableRemoteRegistry

- Value: `$true` → service `RemoteRegistry` startup type 4 (disabled).
- Expected effect: remote reading and writing of the registry is impossible (attacks use it for
  reconnaissance and persistence).
- Cross-links: on client Windows 10/11 the service is disabled anyway; it is set explicitly. Some
  inventory tools (old monitoring agents) require it to be enabled.
- Version differences: on Windows 7/8 the service was in manual mode.
- Verification: `Get-Service RemoteRegistry | Select StartType` → Disabled.
- Rollback: `Set-Service RemoteRegistry -StartupType Manual`.

## PreventAutoDeviceEncryption

- Value: `$true` → `HKLM\SYSTEM\CurrentControlSet\Control\BitLocker\PreventDeviceEncryption = 1`.
- What it does: prevents automatic «шифрование устройства» (device encryption), a simplified form of BitLocker.
- Why: without a domain and without a Microsoft account there is nowhere to save the recovery key.
  Windows 11 24H2 on a clean install encrypts the system drive on any PC with TPM (the
  Modern Standby and HSTI requirements have been dropped). With a local account the drive stays encrypted with a "clear
  key", waiting for a sign-in to a Microsoft account. Consequences: cloning and restoring the drive
  become harder, and after a TPM failure or a motherboard replacement data may be lost without the key.
- Expected effect: the drive is not encrypted. Protection against laptop theft is enabled deliberately (the
  "BitLocker for laptops" constructor parameter, with mandatory saving of the recovery key to USB
  or printing it before the reboot).
- WinKickOff: rule `encryption.prevent-auto-bitlocker` is on in every preset, "Laptop" included, since
  28.09.2026 (customer decision: BitLocker is off everywhere; disk encryption comes as a separate task together
  with the escrow of recovery keys and user passwords). The editor warns when the rule is turned off.
- Cross-links: on PCs without TPM (check bypassed in section 01) device encryption is unavailable even
  without this key. The key does not prevent full BitLocker enabled manually (`manage-bde`, Control Panel).
- Version differences: the key works since Windows 8.1. Automatic encryption on Pro 24H2 on a clean install
  became new behavior in 2024; on 23H2 and older it was enabled only on devices with Modern Standby.
- Verification: `Get-BitLockerVolume C: | Select ProtectionStatus, VolumeStatus` → Off, FullyDecrypted;
  `manage-bde -status`.
- Rollback: delete the value, then Settings → Privacy & security → Device encryption.
