<#
.SYNOPSIS
    Build the portable WinKickOff folder (PyInstaller, onedir, two executables) and a zip with the version.
.DESCRIPTION
    RUN ONLY IN A VIRTUAL MACHINE, ON A BUILD PC OR IN GITHUB ACTIONS (.github/workflows/build.yml). The
    script creates a virtual environment inside WinKickOff\build\ and installs PyInstaller from the internet
    into it; pip may also use its cache in the user profile. That is a change of the computer, which the
    project rules forbid on the customer's work PC (AGENTS.md, rule 1).

    Steps: unit tests, venv with PyInstaller, the build from the spec file tools\WinKickOff.spec (the window
    WinKickOff.exe without a console and the MCP server WinKickOff-mcp.exe with a console, one shared _internal
    folder with the data files: rules, templates, resources, every profiles\preset-*.json, technical reference,
    user documentation), a copy of the documentation next to the exe, a zip dist\WinKickOff-<version>.zip.

    Layout of the result (app_paths() in frozen mode):
      dist\WinKickOff\WinKickOff.exe        the window
      dist\WinKickOff\WinKickOff-mcp.exe    the headless MCP server (a stdio server unless another flag is given)
      dist\WinKickOff\_internal\{rules,templates,resources,profiles,docs\technical\reference,docs\user}
      dist\WinKickOff\docs\{user,technical}\...  (the same documentation, easy to find; user links resolve)
      profiles\, output\, logs\, settings.json are created next to the exe on first use, so nothing starts an
      exe inside dist\WinKickOff before the zip is written (the smoke test of build.yml runs a copy).
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

    # Every preset: a fixed list once left the Laptop and memstechtips presets out of the build. The spec file
    # collects the presets with the same pattern; this count checks the result after the build.
    $presets = @(Get-ChildItem -Path (Join-Path $root 'profiles') -Filter 'preset-*.json' -File)
    if ($presets.Count -lt 1) { throw "no presets in $root\profiles" }

    # Sources, data files, names and console flags live in tools\WinKickOff.spec; with a spec file PyInstaller
    # accepts only the options below on the command line.
    $spec = Join-Path $root 'tools\WinKickOff.spec'
    $distPath = Join-Path $root 'dist'
    $workPath = Join-Path $root 'build\pyinstaller'
    & $vpy -m PyInstaller --noconfirm --clean --distpath $distPath --workpath $workPath $spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

    $dist = Join-Path $distPath 'WinKickOff'
    foreach ($exe in 'WinKickOff.exe', 'WinKickOff-mcp.exe') {
        if (-not (Test-Path (Join-Path $dist $exe) -PathType Leaf)) { throw "$exe is missing in $dist" }
    }
    if (-not (Test-Path (Join-Path $dist '_internal') -PathType Container)) { throw "_internal is missing in $dist" }
    foreach ($folder in 'rules', 'templates', 'resources', 'profiles', 'docs\technical\reference', 'docs\user') {
        if (-not (Test-Path (Join-Path $dist "_internal\$folder") -PathType Container)) { throw "_internal\$folder is missing in $dist" }
    }
    $built = @(Get-ChildItem -Path (Join-Path $dist '_internal\profiles') -Filter 'preset-*.json' -File)
    if ($built.Count -ne $presets.Count) { throw "presets in the build: $($built.Count) of $($presets.Count)" }
    Copy-Item -Path (Join-Path $repo 'docs\user') -Destination (Join-Path $dist 'docs\user') -Recurse -Force
    $tech = New-Item -ItemType Directory -Force -Path (Join-Path $dist 'docs\technical')
    Copy-Item -Path (Join-Path $repo 'docs\technical\reference') -Destination $tech.FullName -Recurse -Force
    Copy-Item -Path (Join-Path $repo 'docs\technical\memstechtips-profile.md') -Destination $tech.FullName -Force
    $zip = Join-Path $distPath "WinKickOff-$version.zip"
    Compress-Archive -Path $dist -DestinationPath $zip -Force
    $size = [math]::Round(((Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum) / 1MB, 1)
    Write-Host "Built $dist ($size MB) and $zip"
} finally {
    Pop-Location
}
