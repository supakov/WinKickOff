# ============================================================================
# DEFAULT USER PROFILE (inherited by every account whose profile is created after this pass)
# ============================================================================
$hive = 'C:\Users\Default\NTUSER.DAT'
$mount = 'HKU\UnattendDefault'
$du = 'HKU:\UnattendDefault'
$loaded = $false
try {
    $r = & reg.exe load $mount $hive 2>&1
    if ($LASTEXITCODE -eq 0) { $loaded = $true; Write-Log 'Default user hive loaded' 'OK' } else { Write-Log "reg load failed: $r" 'ERROR' }
} catch { Write-Log "reg load: $($_.Exception.Message)" 'ERROR' }

if ($loaded) {
{{blocks}}

    [gc]::Collect(); [gc]::WaitForPendingFinalizers(); Start-Sleep -Seconds 2
    $r = & reg.exe unload $mount 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Log 'Default user hive unloaded' 'OK' } else { Write-Log "reg unload: $r" 'WARN'; Start-Sleep 3; $null = & reg.exe unload $mount 2>&1 }
}
