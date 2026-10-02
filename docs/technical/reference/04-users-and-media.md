# 04. Accounts in $Config and .NET Framework 3.5

The `$Config` section in `Setup-System.ps1`, groups "Users" and "Installation media".

## AdminAccount, UserAccount

- Value: `'Admin'`, `'User'`.
- Where applied: saved to `C:\ProgramData\Unattend\config.json` at the end of `Setup-System.ps1`;
  read by `Post-OOBE.ps1`.
- What it does: tells Post-OOBE.ps1 the names of the accounts whose password expiration must be removed.
  The accounts themselves are created by the XML (section 03), not by these parameters.
- Expected effect: `Set-LocalUser -PasswordNeverExpires $true` for both names after OOBE completes.
- Cross-links: the names must match `<Name>` in `<LocalAccounts>`; if they differ, Post-OOBE.ps1
  writes "user not found" to the log and does not remove the expiration, but the global `net accounts`
  command (see below) still takes effect. The constructor must drive both places from a single field.
- Version differences: none.
- Verification: `Get-Content C:\ProgramData\Unattend\config.json`.
- Rollback: not applicable.

## PasswordNeverExpires

- Value: `$true`.
- Where applied: two places. `Setup-System.ps1` section 4 (specialize, always runs) and
  `Post-OOBE.ps1` (after OOBE, for each account).
- What it does:
  1. `net.exe accounts /maxpwage:unlimited`: the maximum password age for all local
     accounts is removed (the default is 42 days).
  2. `Set-LocalUser -Name <name> -PasswordNeverExpires $true`: the «Срок действия пароля не ограничен»
     (Password never expires) flag on the Admin and User accounts themselves.
- Expected effect: Windows will never show "Your password has expired and must be changed". For empty
  passwords this is critical: a non-professional user will not understand what is being asked of them.
- Cross-links:
  - Starter accounts without passwords (section 03). A separate user management project
    assigns passwords and may restore password expiration (`net accounts /maxpwage:90`).
  - `AccountLockout` (section 08) is set by the same `net accounts` utility; the order of calls does not matter.
  - If Post-OOBE.ps1 does not run (the PC was switched off before it completed), the global setting from
    specialize still applies.
- Version differences: `net accounts` works in all versions. `Set-LocalUser` is available in Windows 10 1607+
  (the Microsoft.PowerShell.LocalAccounts module). On Windows 11 22H2+ the default of 42 days is retained.
- Verification: `net accounts` → "Maximum password age: Unlimited"; `Get-LocalUser Admin | Select PasswordExpires`
  (empty).
- Rollback: `net accounts /maxpwage:42`; `Set-LocalUser -Name Admin -PasswordNeverExpires $false`.

## EnableNetFx3

- Value: `$true`.
- Where applied: `Setup-System.ps1` section 0, specialize, SYSTEM.
- What it does: goes through all ready drives looking for a `sources\sxs` folder with `.cab` files inside (the installation
  media: USB, DVD, an ISO mounted by Ventoy). If found:
  `dism.exe /Online /Enable-Feature /FeatureName:NetFx3 /All /LimitAccess /Source:<path> /NoRestart /Quiet`.
  If not found: a WARN is written to the log and the feature is not enabled.
- Expected effect: .NET Framework 3.5 (including 2.0 and 3.0) is available right after installation without
  internet access. It is needed by old accounting and banking programs and old versions of digital signature key drivers.
- Cross-links:
  - The media must stay connected during specialize (the first reboot). If the USB drive
    was removed right after the files were copied, the feature will not be installed; it can then be added later
    via Settings → Optional features (requires internet) or with a DISM command from the media.
  - `/LimitAccess` prevents contacting Windows Update while the feature is being installed: there is no network
    in specialize anyway, and without this switch DISM would wait for a timeout.
  - Security updates for .NET 3.5 arrive through Windows Update (section 06).
- Version differences: the `sources\sxs` folder is present in all official Windows 10/11 ISOs. On images
  stripped down by third-party tools it may be missing. In Windows 11 24H2 the feature is still
  optional and disabled by default.
- Verification: `Get-WindowsOptionalFeature -Online -FeatureName NetFx3` → State Enabled;
  the log contains the line `dism.exe ... -> exit 0`.
- Rollback: `Disable-WindowsOptionalFeature -Online -FeatureName NetFx3`.
