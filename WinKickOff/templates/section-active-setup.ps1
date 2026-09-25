# ============================================================================
# PER-USER SCRIPT (Active Setup runs Setup-User.ps1 once at each user's first sign-in)
# ============================================================================
$as = 'HKLM:\SOFTWARE\Microsoft\Active Setup\Installed Components\{7A6C3F5E-2B1D-4C8E-9F0A-5D3E6B7C8D91}'
Set-Reg -Path $as -Name '(Default)' -Type String -Value 'Workgroup per-user setup'
Set-Reg -Path $as -Name 'StubPath' -Type String -Value 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\ProgramData\Unattend\Scripts\Setup-User.ps1"'
Set-Reg -Path $as -Name 'Version' -Type String -Value '1,0,0,0'
Set-Reg -Path $as -Name 'IsInstalled' -Type DWord -Value 1
