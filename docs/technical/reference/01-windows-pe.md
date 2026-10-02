# 01. windowsPE pass: key, edition, license, hardware check bypass

Component `Microsoft-Windows-Setup`, two copies: `processorArchitecture="amd64"` and `"arm64"`.
Setup applies the one that matches the architecture of the installation media; the other is ignored. The x86 copy was removed:
there is no 32-bit Windows 11.

## ProductKey / Key

- Value: `VK7JG-NPHTM-C97JM-9MPGT-3V66T`.
- Where applied: windowsPE, `UserData/ProductKey/Key`.
- What it does: this is the generic installation key for Windows 11 Pro (the same as for Windows 10 Pro).
  It does not activate the system. Setup matches the key against the editions in `install.wim` and selects Professional
  (log: `Product key using pkey edition = [Professional]`, `Product key is a default key`,
  `Matched Professional with Professional`).
- Expected effect: the product key entry window and the edition selection window are not shown. After installation the system
  is not activated until it connects to the internet; it then activates automatically with the digital license
  tied to the hardware (if Windows 10/11 Pro was previously activated on this PC).
- Cross-links: if the image has no Pro edition (for example an ISO with Home only), installation stops
  with a key error; `WillShowUI=OnError` then shows the window. If the PC has never been activated,
  a real key will have to be entered after installation (Settings → System → Activation).
- Version differences: the key is the same for Windows 10 and 11. Other editions need their own generic
  keys (Home: `YTMG3-N6DKC-DKB77-7M9GH-8HVX7`, Enterprise: `NPPR9-FWDCX-D2C8J-H872K-2YT43`);
  this is a parameter of the future constructor.
- Verification: after installation `slmgr /dli` shows Professional; `Get-ComputerInfo | Select WindowsProductName`.
- Rollback: not required; changing the edition requires a reinstallation.

## ProductKey / WillShowUI

- Value: `OnError`.
- What it does: the key entry window is shown only if the key is rejected. This is the default value,
  specified explicitly. `Always` with an empty key `00000-...` would show the key and edition selection
  window on every installation.
- Version differences: none.

## AcceptEula

- Value: `true`.
- What it does: accepts the license agreement on behalf of the user; the license screen in Setup
  is not shown. The license screen in OOBE is hidden separately (`HideEULAPage`, see section 03).
- Cross-links: legally, responsibility for accepting the terms lies with the organization that applies the file.

## Compatibility check bypass (LabConfig)

Five `reg.exe add "HKLM\SYSTEM\Setup\LabConfig" /v <name> /t REG_DWORD /d 1 /f` commands,
run in WinPE before copying starts.

| Order | Value | What it disables |
|---|---|---|
| 1 | BypassTPMCheck | The TPM 2.0 requirement |
| 2 | BypassSecureBootCheck | The requirement for Secure Boot to be enabled |
| 3 | BypassCPUCheck | The list of supported processors |
| 4 | BypassRAMCheck | The 4 GB memory requirement |
| 5 | BypassStorageCheck | The 64 GB disk requirement |

- Expected effect: Setup does not show «Этот компьютер не соответствует требованиям» (This PC does not meet the requirements).
  On PCs that meet the requirements the commands change nothing: TPM and Secure Boot stay
  enabled and in use.
- Cross-links:
  - Without TPM, automatic device encryption and BitLocker without a boot password are unavailable;
    the `PreventAutoDeviceEncryption` parameter is redundant on such PCs but harmless.
  - Without Secure Boot and VBS, Credential Guard does not work; `LSAProtection` does work (value 2 without
    the UEFI lock was chosen precisely for such PCs).
  - Microsoft does not guarantee updates for unsupported PCs; in practice cumulative updates
    arrive, while feature updates (24H2 → 25H2) may require the bypass again.
- Version differences: the LabConfig keys only work in the WinPE of Windows 11 Setup (21H2 and later).
  Windows 10 ignores them. In 24H2 Microsoft tightened the processor requirement (the
  POPCNT and SSE4.2 instructions): it cannot be bypassed, and installation on such processors is impossible.
- Verification: installation on a PC without TPM proceeds without a warning; `Get-Tpm` shows the actual state.
- Rollback: not required, the keys exist only in the Setup environment. To remove the bypass from the file, delete
  the five `RunSynchronousCommand` elements in both copies of the component.

## What the pass does not contain and why

| Element | Why it is absent | Consequence |
|---|---|---|
| `DiskConfiguration` | Automatic partitioning wipes the disk without asking | Setup shows disk and partition selection: the only screen that requires a person |
| `ImageInstall` | The edition is selected by the key; the image does not need to be specified | None |
| `Microsoft-Windows-International-Core-WinPE` | The Setup language depends on the ISO | The first Setup screen for choosing the language and keyboard layout remains (a constructor parameter) |
| `UseConfigurationSet` | There is no `$OEM$` folder | None |
