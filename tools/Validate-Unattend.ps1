<#
.SYNOPSIS
    Static validation of autounattend.xml. Read-only: parses the file, never touches the system.
.DESCRIPTION
    Checks everything that is known to abort Windows Setup (0x80220005) or to break the embedded
    scripts, and prints a table. Exit code 0 when all checks pass, 1 otherwise.
    Runs on Windows PowerShell 5.1 (the engine the scripts target) without extra modules.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path build\autounattend.xml -Verbose
#>
[CmdletBinding()]
param(
    [string]$Path = '',
    [int]$MaxPathLength = 259,
    [int]$MaxDescriptionLength = 259
)

$ErrorActionPreference = 'Stop'
if (-not $Path) {
    # $PSScriptRoot is empty inside param() on Windows PowerShell 5.1, so resolve the default here.
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Path = Join-Path (Split-Path -Parent $scriptDir) 'autounattend.xml'
}
$results = New-Object System.Collections.Generic.List[object]
function Add-Result { param([string]$Check, [bool]$Pass, [string]$Detail = '')
    $results.Add([pscustomobject]@{ Check = $Check; Result = $(if ($Pass) { 'PASS' } else { 'FAIL' }); Detail = $Detail })
}

if (-not (Test-Path -LiteralPath $Path)) { Write-Error "File not found: $Path" }
$raw = [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)

# 1. Well-formed XML
$xml = $null
try { $xml = [xml]::new(); $xml.Load($Path); Add-Result 'XML well-formed' $true }
catch { Add-Result 'XML well-formed' $false $_.Exception.Message; $results | Format-Table -AutoSize; exit 1 }

$ns = New-Object System.Xml.XmlNamespaceManager($xml.NameTable)
$ns.AddNamespace('u', 'urn:schemas-microsoft-com:unattend')

# 2. Root element and namespaces
Add-Result 'Root <unattend> in Microsoft namespace' ($xml.DocumentElement.NamespaceURI -eq 'urn:schemas-microsoft-com:unattend') $xml.DocumentElement.NamespaceURI
Add-Result 'wcm namespace declared' ($raw -match 'xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State"')

# 3. No comments inside <component>
$comments = @($xml.SelectNodes('//u:component//comment()', $ns))
Add-Result 'No XML comments inside <component>' ($comments.Count -eq 0) "found $($comments.Count)"

# 4. Command lengths
$cmds = @($xml.SelectNodes('//u:RunSynchronousCommand', $ns))
$tooLong = @($cmds | Where-Object { $_.Path.Length -gt $MaxPathLength })
$maxLen = ($cmds | ForEach-Object { $_.Path.Length } | Measure-Object -Maximum).Maximum
Add-Result "RunSynchronousCommand/Path <= $MaxPathLength chars" ($tooLong.Count -eq 0) "max $maxLen, over limit: $($tooLong.Count)"
$descLong = @($cmds | Where-Object { $_.Description -and $_.Description.Length -gt $MaxDescriptionLength })
Add-Result "RunSynchronousCommand/Description <= $MaxDescriptionLength chars" ($descLong.Count -eq 0)
$emptyPath = @($cmds | Where-Object { [string]::IsNullOrWhiteSpace($_.Path) })
Add-Result 'No empty Path' ($emptyPath.Count -eq 0)

# 5. Order values unique per component
$dupOrders = 0
foreach ($rs in @($xml.SelectNodes('//u:RunSynchronous', $ns))) {
    $orders = @($rs.RunSynchronousCommand | ForEach-Object { $_.Order })
    if (($orders | Select-Object -Unique).Count -ne $orders.Count) { $dupOrders++ }
}
Add-Result 'Order values unique within each RunSynchronous' ($dupOrders -eq 0)

# 6. Every PowerShell one-liner in specialize ends with exit 0 and parses
$psCmds = @($cmds | Where-Object { $_.Path -like 'powershell*' })
$badExit = @($psCmds | Where-Object { $_.Path -notmatch 'exit 0"$' })
Add-Result 'PowerShell commands end with exit 0' ($badExit.Count -eq 0) "checked $($psCmds.Count)"
$inlineErrors = 0
foreach ($c in $psCmds) {
    $m = [regex]::Match($c.Path, '-Command "(.*)"$')
    if ($m.Success) { $e = $null; $null = [System.Management.Automation.PSParser]::Tokenize($m.Groups[1].Value, [ref]$e); $inlineErrors += $e.Count }
}
Add-Result 'Inline PowerShell commands parse' ($inlineErrors -eq 0) "errors: $inlineErrors"

# 7. International-Core completeness (all four values, else OOBE shows the language page)
foreach ($comp in @($xml.SelectNodes('//u:settings[@pass="oobeSystem"]/u:component[@name="Microsoft-Windows-International-Core"]', $ns))) {
    $arch = $comp.GetAttribute('processorArchitecture')
    $missing = @('InputLocale','SystemLocale','UILanguage','UserLocale') | Where-Object { [string]::IsNullOrWhiteSpace($comp.$_) }
    Add-Result "International-Core complete ($arch)" ($missing.Count -eq 0) ("missing: " + ($missing -join ','))
    $badLocale = @(($comp.InputLocale -split ';') | Where-Object { $_ -notmatch '^[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}$' -and $_ -notmatch '^[a-z]{2,3}(-[A-Za-z]{2,4})?(-[A-Z]{2})?$' })
    Add-Result "InputLocale entries well-formed ($arch)" ($badLocale.Count -eq 0) ($badLocale -join ',')
}

# 8. Local accounts: names, groups, duplicates, reserved names
$accounts = @($xml.SelectNodes('//u:LocalAccount', $ns))
$reserved = 'Administrator','Guest','DefaultAccount','WDAGUtilityAccount','SYSTEM','LOCAL SERVICE','NETWORK SERVICE'
foreach ($comp in @($xml.SelectNodes('//u:settings[@pass="oobeSystem"]/u:component[@name="Microsoft-Windows-Shell-Setup"]', $ns))) {
    $arch = $comp.GetAttribute('processorArchitecture')
    $names = @($comp.SelectNodes('.//u:LocalAccount/u:Name', $ns) | ForEach-Object { $_.InnerText })
    Add-Result "LocalAccount names unique ($arch)" ((@($names | Select-Object -Unique)).Count -eq $names.Count) ($names -join ',')
    $bad = @($names | Where-Object { $reserved -contains $_ -or $_ -match '[\\/\[\]:;|=,+*?<>"@]' -or $_.Length -gt 20 -or $_ -eq '' })
    Add-Result "LocalAccount names valid ($arch)" ($bad.Count -eq 0) ($bad -join ',')
    $groups = @($comp.SelectNodes('.//u:LocalAccount/u:Group', $ns) | ForEach-Object { $_.InnerText })
    Add-Result "At least one Administrators account ($arch)" ($groups -contains 'Administrators')
}

# 9. Extensions: scripts extract and parse under PowerShell 5.1
$ext = $xml.unattend.Extensions
Add-Result 'Extensions/ExtractScript present' ($null -ne $ext -and -not [string]::IsNullOrWhiteSpace($ext.ExtractScript))
if ($ext) {
    $e = $null; $null = [System.Management.Automation.PSParser]::Tokenize($ext.ExtractScript, [ref]$e)
    Add-Result 'ExtractScript parses' ($e.Count -eq 0) "errors: $($e.Count)"
    $files = @($ext.File)
    Add-Result 'Embedded files present' ($files.Count -ge 3) "count: $($files.Count)"
    $tmp = Join-Path $env:TEMP ("unattend-validate-" + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $tmp -Force
    try {
        foreach ($f in $files) {
            $name = Split-Path $f.GetAttribute('path') -Leaf
            $out = Join-Path $tmp $name
            [System.IO.File]::WriteAllText($out, $f.InnerText.Trim(), [System.Text.UTF8Encoding]::new($true))
            $t = $null; $perr = $null
            $null = [System.Management.Automation.Language.Parser]::ParseFile($out, [ref]$t, [ref]$perr)
            $detail = if ($perr.Count) { ($perr | ForEach-Object { "line $($_.Extent.StartLineNumber): $($_.Message)" }) -join '; ' } else { "$((Get-Content $out).Count) lines" }
            Add-Result "Script parses: $name" ($perr.Count -eq 0) $detail
            $body = Get-Content $out -Raw
            Add-Result "Script ends with exit 0: $name" ($body -match '(?m)^\s*exit 0\s*$')
            $cdataClose = ([regex]::Matches($f.InnerText, '\]\]>')).Count
            Add-Result "No ']]>' inside CDATA: $name" ($cdataClose -eq 0)
        }
        # Embedded Task Scheduler XML inside Setup-System.ps1
        $sysScript = Join-Path $tmp 'Setup-System.ps1'
        if (Test-Path $sysScript) {
            $body = Get-Content $sysScript -Raw
            $m = [regex]::Match($body, "taskXml = @'\r?\n(.*?)\r?\n'@", 'Singleline')
            if ($m.Success) {
                try { $tx = [xml]::new(); $tx.LoadXml($m.Groups[1].Value); Add-Result 'Embedded task XML well-formed' $true $tx.Task.Triggers.FirstChild.Name }
                catch { Add-Result 'Embedded task XML well-formed' $false $_.Exception.Message }
            }
            $cfgMatch = [regex]::Match($body, '\$Config = @\{(.*?)\n\}', 'Singleline')
            Add-Result '$Config block found in Setup-System.ps1' $cfgMatch.Success
        }
    } finally { Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue }
}

# 10. Style: no em/en dashes (project rule), file size
$em = ([regex]::Matches($raw, [string][char]0x2014)).Count
$en = ([regex]::Matches($raw, [string][char]0x2013)).Count
Add-Result 'No em/en dashes' (($em + $en) -eq 0) "em: $em, en: $en"
Add-Result 'File size < 1 MB' ($raw.Length -lt 1MB) "$([math]::Round($raw.Length / 1KB)) KB"

$results | Format-Table -AutoSize -Wrap
$failed = @($results | Where-Object Result -eq 'FAIL').Count
Write-Host ("`n{0} checks, {1} failed" -f $results.Count, $failed) -ForegroundColor $(if ($failed) { 'Red' } else { 'Green' })
exit $(if ($failed) { 1 } else { 0 })
