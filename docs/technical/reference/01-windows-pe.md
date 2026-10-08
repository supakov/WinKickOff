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
- Verification: after installation `slmgr /dli` shows Professional; `reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v EditionID`
  shows `Professional` (`ProductName` still says "Windows 10 Pro" on Windows 11, so it is no check).
- Rollback: not required; changing the edition requires a reinstallation.

## ProductKey / WillShowUI

- Value: `OnError`.
- What it does: the key entry window is shown only if the key is rejected. This is the default value,
  specified explicitly. `Always` with the key `00000-00000-00000-00000-00000` shows the key and edition selection
  window on every installation: that is the WinKickOff key mode "ask".
- Version differences: none.

## Key modes of WinKickOff: who chooses the edition

The form "Installation" offers three key modes (profile field `install.product_key_mode`):

| Mode | `<Key>` | `<WillShowUI>` | What Setup shows |
|---|---|---|---|
| `generic` | the key of the chosen edition in `render.EDITION_KEYS` (Pro `VK7JG-NPHTM-C97JM-9MPGT-3V66T`; 14 editions, see below) | OnError | Nothing: Setup matches the key to an image ("Matched Professional with Professional") |
| `ask` | `00000-00000-00000-00000-00000` | Always | The product key page. A typed key installs the edition of that key; "I don't have a product key" opens the list of every edition in `install.wim` |
| `custom` | the key of the profile | OnError | The edition of that key; the page only if the key is rejected |

- The editions of `generic` (the list was extended by the customer on 05.10.2026): Pro and Education have generic
  installation keys, which select the edition and do not activate; Windows activates later with the digital licence of
  the PC or a key of the licence. The other twelve (Pro N, Pro for Workstations and its N, Pro Education and its N,
  Education N, Enterprise, Enterprise N, G and G N, Enterprise LTSC 2024 and Enterprise N LTSC 2024; the LTSC keys
  also install Windows 10 LTSC 2021 and 2019) are the KMS client keys (GVLK) of the Microsoft Learn table "Key
  Management Services (KMS) client activation and product keys" (every key compared on 08.10.2026). Windows installed
  with one is a KMS client: it activates only against a KMS host on the local network, and Microsoft warns that these
  keys "won't activate or serve as a retail license key". Without a KMS host, type the key of the licence after
  installation (Settings, System, Activation, or `slmgr /ipk`). The form says so under the edition list.
- Setup installs an edition only when `install.wim` (or `install.esd`) of the media holds it; list the editions of the
  target media with `dism /Get-WimInfo /WimFile:<media>\sources\install.wim` (read only). Enterprise G and LTSC come on
  their own media. What Setup shows when no image matches the key is to be confirmed in a virtual machine.
- The edition list of the form applies to `generic` only; the window disables it in the other modes, and the build
  writes a header line "Edition: chosen during Setup" in mode `ask`. The Home preset uses `ask`.
- Microsoft Learn ("Work with product keys and activation") names both ways: a key in `ProductKey\Key`, or typing the
  key during Setup, where "the product key selects a Windows edition to install". The exact pages of Windows 11 Setup
  ("I don't have a product key", then the list) are described by third parties; confirm in a virtual machine.
- `ei.cfg` and `pid.txt` on the media do not help: "If you use an answer file during installation, Windows Setup
  ignores the EI.cfg and PID.txt files" (Microsoft Learn). An empty `Key` is not allowed ("does not support empty
  elements"), and without the element Setup may silently take the edition of the key in the firmware.
- The protection of WinKickOff is made for Pro. On Home, the deferral of feature updates is ignored (Policy CSP Update
  lists Pro, Enterprise, Education), BitLocker cannot be turned on later, and the Copilot and Recall policies are not
  supported according to their ADMX; the check of the editor says so in mode `ask`.

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
