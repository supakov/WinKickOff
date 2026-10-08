# ============================================================================
# COMPUTER NAME FROM THE TEMPLATE OF THE PROFILE
# ============================================================================
# The answer file gives the computer a temporary name in this pass. This block computes the name of the template and
# starts a hidden PowerShell process that writes it every 50 ms until the restart that ends the pass, so whatever name
# Windows Setup writes in the meantime does not stay. A part that cannot be read (no serial number, no network adapter)
# becomes random characters of the same length.
try {
    $nameChars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    $computerName = ''
    foreach ($part in @({{name_parts}})) {
        $kind, $arg = $part -split ':', 2
        if ($kind -eq 'text') { $computerName += $arg; continue }
        $length = [int]$arg
        $value = ''
        if ($kind -eq 'serial') {
            $serial = [string](Get-CimInstance -ClassName Win32_BIOS -ErrorAction SilentlyContinue).SerialNumber
            $value = ($serial -replace '[^A-Za-z0-9]', '').ToUpperInvariant()
            if ($value -match '^0*$|OEM|DEFAULT|SERIAL|NONE|NOTAPPLICABLE|NOTSPECIFIED|INVALID|^NA$') { $value = '' }
        } elseif ($kind -eq 'mac') {
            $adapter = Get-CimInstance -ClassName Win32_NetworkAdapter -Filter 'PhysicalAdapter = TRUE' -ErrorAction SilentlyContinue | Where-Object { $_.MACAddress } | Sort-Object -Property DeviceID | Select-Object -First 1
            if ($adapter) { $value = ([string]$adapter.MACAddress -replace '[^A-Fa-f0-9]', '').ToUpperInvariant() }
        }
        if ($value.Length -gt $length) { $value = $value.Substring($value.Length - $length) }
        if (-not $value) { $value = -join (1..$length | ForEach-Object { $nameChars[(Get-Random -Maximum $nameChars.Length)] }) }
        $computerName += $value
    }
    if ($computerName.Length -gt 15) { $computerName = $computerName.Substring(0, 15) }
    $loop = '$n = ''' + $computerName + '''; while ($true) { ' +
        'Set-ItemProperty -LiteralPath ''HKLM:\SYSTEM\CurrentControlSet\Control\ComputerName\ComputerName'' -Name ''ComputerName'' -Value $n; ' +
        'Set-ItemProperty -LiteralPath ''HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'' -Name ''Hostname'' -Value $n; ' +
        'Set-ItemProperty -LiteralPath ''HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'' -Name ''NV Hostname'' -Value $n; ' +
        'Start-Sleep -Milliseconds 50 }'
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($loop))
    $arguments = '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded
    $null = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 10
    Write-Log ("computer name from the template: {0}" -f $computerName) 'OK'
} catch {
    Write-Log ("FAILED computer name from the template: {0}" -f $_.Exception.Message) 'ERROR'
}
