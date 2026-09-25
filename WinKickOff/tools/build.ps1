<#
.SYNOPSIS
    Build the portable WinKickOff folder (PyInstaller, onedir) and a zip with the version.
.DESCRIPTION
    RUN ONLY IN A VIRTUAL MACHINE OR ON A BUILD PC. The script creates a virtual environment inside
    WinKickOff\build\ and installs PyInstaller from the internet into it; pip may also use its cache in
    the user profile. That is a change of the computer, which the project rules forbid on the customer's
    work PC (AGENTS.md, rule 1).

    Steps: unit tests, venv with PyInstaller, onedir build without a console window, data files
    (rules, templates, resources, presets, technical reference, user documentation), a copy of the
    user documentation next to the exe, a zip dist\WinKickOff-<version>.zip.

    Layout of the result (app_paths() in frozen mode):
      dist\WinKickOff\WinKickOff.exe
      dist\WinKickOff\_internal\{rules,templates,resources,profiles,docs\technical\reference,docs\user}
      dist\WinKickOff\docs\user\...           (the same user documentation, easy to find)
      profiles\, output\, logs\, settings.json are created next to the exe on first use.
.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\build.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File tools\build.ps1 -Python 'C:\Python313\python.exe'
#>
[CmdletBinding()]
param(
    [string]$Python = '',
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$repo = Split-Path -Parent $root
if (-not $Python) { $Python = (Get-Command python -ErrorAction Stop).Source }

Push-Location $root
try {
    $version = & $Python -c "import winkickoff; print(winkickoff.APP_VERSION)"
    Write-Host "WinKickOff $version, Python: $(& $Python --version)"

    if (-not $SkipTests) {
        & $Python -m unittest discover -s tests
        if ($LASTEXITCODE -ne 0) { throw "tests failed" }
    }

    $venv = Join-Path $root 'build\venv'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) { & $Python -m venv $venv }
    $vpy = Join-Path $venv 'Scripts\python.exe'
    & $vpy -m pip install --upgrade pip pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

    # Absolute sources: with --specpath PyInstaller resolves relative paths from the spec folder.
    $data = @(
        "$root\rules;rules", "$root\templates;templates", "$root\resources;resources",
        "$root\profiles\preset-office.json;profiles", "$root\profiles\preset-strict.json;profiles",
        "$repo\docs\technical\reference;docs\technical\reference",
        "$repo\docs\user;docs\user"
    )
    $pyiArgs = @('--noconfirm', '--clean', '--noconsole', '--onedir', '--name', 'WinKickOff',
              '--distpath', 'dist', '--workpath', 'build\pyinstaller', '--specpath', 'build',
              '--paths', $root)
    foreach ($item in $data) { $pyiArgs += @('--add-data', $item) }
    $pyiArgs += (Join-Path $root 'winkickoff\__main__.py')
    & $vpy -m PyInstaller @pyiArgs
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

    $dist = Join-Path $root 'dist\WinKickOff'
    Copy-Item -Path (Join-Path $repo 'docs\user') -Destination (Join-Path $dist 'docs\user') -Recurse -Force
    $zip = Join-Path $root "dist\WinKickOff-$version.zip"
    Compress-Archive -Path $dist -DestinationPath $zip -Force
    $size = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
    Write-Host "Built $dist ($size MB) and $zip"
} finally {
    Pop-Location
}
