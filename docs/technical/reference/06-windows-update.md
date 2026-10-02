# 06. Windows Update and Delivery Optimization

Section 2 of `Setup-System.ps1`. Customer requirement: updates must work. All settings
only speed up and organize updates; they do not disable anything.

## Unconditional actions of the section

Before applying the parameters, the script deletes values that could disable updates
(they are absent on a clean image, but they appear after third-party "optimizers" or when the script
is run again on an already configured system):

| Key | Value | Why it is deleted |
|---|---|---|
| `Pol\WindowsUpdate\AU` | `NoAutoUpdate` | 1 disables automatic updates completely |
| `Pol\WindowsUpdate` | `DoNotConnectToWindowsUpdateInternetLocations` | 1 blocks access to Microsoft servers |
| `Pol\WindowsUpdate` | `DisableWindowsUpdateAccess` | 1 hides the updates page |
| `Pol\WindowsUpdate` | `ExcludeWUDriversInQualityUpdate` | 1 excludes drivers; vulnerable drivers must be updated |
| `HKLM\SOFTWARE\Policies\Microsoft\WindowsStore` | `AutoDownload` | 2 disables automatic updates of Store apps |

Then, for the services `wuauserv`, `UsoSvc`, `BITS`, `DoSvc`, `WaaSMedicSvc`: if the startup type is 4 (disabled),
it is changed to 3 (manual; normally they are started by triggers).

## WindowsUpdateAutomatic

- Value: `$true`.
- Where applied: specialize, policies `Pol\WindowsUpdate` and `Pol\WindowsUpdate\AU`.
- What it does:
  - `AU\NoAutoUpdate = 0`, `AU\AUOptions = 4`: download and install automatically;
  - `SetActiveHours = 1`, `ActiveHoursStart = 8`, `ActiveHoursEnd = 20`: active hours
    08:00-20:00, automatic restart is not allowed during this time.
- Expected effect: updates install by themselves; the restart happens at night or before 8 a.m. The user sees
  a notification about the scheduled restart and can postpone it within the limits of Windows policy.
- Cross-links:
  - The maximum span of active hours is 18 hours; 12 hours leave the night for the restart.
  - `NoAutoRebootWithLoggedOnUsers=1` is not set: with it, a PC that is never switched off would not
    restart and would accumulate uninstalled updates.
  - The policy makes the «Период активности» (Active hours) page in Settings unavailable for changes.
  - Defender updates (signatures) come through the same channel and do not depend on active hours.
- Version differences: `AUOptions=4` works on Windows 10 and 11; on Windows 11 24H2 "smart active
  hours" (automatic detection based on usage) is turned off by fixed hours.
- Verification: `Get-ItemProperty HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU`;
  Settings → Windows Update → Advanced options → Active hours.
- Rollback: delete `SetActiveHours`, `ActiveHoursStart`, `ActiveHoursEnd`; `AUOptions` can be kept.

## UpdateOtherMicrosoftProducts

- Value: `$true`.
- What it does: `Pol\WindowsUpdate\AU\AllowMUUpdateService = 1`: connection to Microsoft Update
  (updates for Office, .NET, SQL Server Express, Surface drivers and other Microsoft products).
- Expected effect: the «Получать обновления для других продуктов Майкрософт» (Receive updates for other Microsoft products)
  toggle is on and locked. Office 2016/2019 (MSI) and .NET 3.5 receive security fixes together with Windows.
- Cross-links: Office 365/2021 (Click-to-Run) is updated by its own mechanism; the policy does not affect it.
  The value 0 would deprive Office of updates.
- Version differences: none.
- Verification: `(New-Object -ComObject Microsoft.Update.ServiceManager).Services | ? IsDefaultAUService`.
- Rollback: delete the value.
- WinKickOff: rule `update.other-microsoft-products`, off by default since 26.09.2026 (the "Office" preset
  as chosen in the repository, commit d33fc41); the "Strict" preset keeps it on. Without the policy the
  toggle stays as Windows leaves it (off) and users may switch it themselves. v0.2 set 1.

## DeferFeatureUpdatesDays

- Value: `90`. The value `0` disables the deferral.
- What it does: `Pol\WindowsUpdate\DeferFeatureUpdates = 1`, `DeferFeatureUpdatesPeriodInDays = 90`.
- Expected effect: annual feature updates (for example 24H2 → 25H2) arrive 90 days after
  general availability. During this time Microsoft fixes the bugs of the first weeks, and accounting software has time
  to get compatible versions released. Monthly security updates are never deferred.
- Cross-links:
  - Requires a working compatibility assessment: `MinimalTelemetry` (section 12) deliberately leaves
    the DiagTrack service in manual mode and does not disable the Application Experience tasks.
  - The allowed range is 0-365 days. The deferral does not prevent manual installation of a feature update
    via the Media Creation Tool.
  - A Windows version stops receiving security updates 24 months after release (Pro);
    a 90-day deferral fits safely within this period.
- Version differences: the policy works on Windows 10 1703+ and Windows 11 Pro/Enterprise. On Home
  there is no deferral. For Windows 11 Microsoft also recommends `TargetReleaseVersion`; it is not set
  so as not to tie the fleet to a single version.
- Verification: Settings → Windows Update shows "Some settings are managed by your organization";
  `Get-ItemProperty HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate`.
- Rollback: delete both values.

## DeliveryOptimizationLANOnly

- Value: `$true`.
- What it does: `Pol\DeliveryOptimization\DODownloadMode = 1`: update fragments are exchanged only
  with PCs on the same local network (one subnet / one NAT).
- Expected effect: in an office with 10 PCs an update is downloaded from the internet once, and the others
  take it from their neighbors. No traffic is uploaded to the outside.
- Cross-links:
  - Value 1 matches the Windows default for local accounts; the policy enforces it.
  - Value 99 (simple mode without peers, HTTP only) works, but every PC downloads everything by itself.
  - The exchange needs open port 7680 TCP between the PCs; Windows creates the firewall rule itself.
    The `DefaultInboundAction=block` policy (section 09) does not interfere: the rule is an allow rule.
- Version differences: modes 0 (HTTP), 1 (LAN), 2 (group), 3 (internet), 99 (simple), 100 (bypass)
  have been the same since Windows 10 1607. Unchanged on 24H2.
- Verification: `Get-DeliveryOptimizationStatus`, `Get-DOConfig`.
- Rollback: delete the value (the default 1 or 3 comes back).
