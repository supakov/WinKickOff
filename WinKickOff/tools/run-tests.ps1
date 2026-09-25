<#
.SYNOPSIS
    Run the WinKickOff test suite (unittest, standard library only). Read-only: nothing on the
    machine changes; tests write only into temporary folders.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\run-tests.ps1
#>
[CmdletBinding()]
param([switch]$Quiet)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $root
try {
    $py = Get-Command python -ErrorAction Stop
    $version = & $py.Source -c "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "Python $version at $($py.Source)"
    $testArgs = @('-m', 'unittest', 'discover', '-s', 'tests')
    if (-not $Quiet) { $testArgs += '-v' }
    & $py.Source @testArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
