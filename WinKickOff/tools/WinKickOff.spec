# -*- mode: python ; coding: utf-8 -*-
r"""PyInstaller spec of the portable WinKickOff folder: two executables that share one _internal folder.

Run only in GitHub Actions or in a virtual machine, through tools\build.ps1 (never on the customer's work PC):

    python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller tools\WinKickOff.spec

Result (app_paths() in frozen mode reads the data from sys._MEIPASS, which is dist\WinKickOff\_internal):

    dist\WinKickOff\WinKickOff.exe          the window, from winkickoff\__main__.py, no console
    dist\WinKickOff\WinKickOff-mcp.exe      the headless MCP server, from winkickoff\mcp_main.py, with a console
    dist\WinKickOff\_internal\              rules, templates, resources, profiles\preset-*.json,
                                            docs\technical\reference, docs\user

Both executables derive their folder from sys.executable, so they share settings.json, profiles\, output\, logs\
and admx\ next to them. The data sources below are the ones tools\build.ps1 used to pass with --add-data; they
are resolved from SPECPATH (the folder of this file, set by PyInstaller), because __file__ does not exist while
PyInstaller executes a spec. build.ps1 copies the documentation next to the exe afterwards and checks the result.
"""

import glob
import os

SPEC_DIR = os.path.abspath(SPECPATH)  # WinKickOff\tools: SPECPATH is a global that PyInstaller sets
ROOT = os.path.dirname(SPEC_DIR)  # WinKickOff: the package, rules, templates, resources, profiles
REPO = os.path.dirname(ROOT)  # the repository root: docs\ lives here

# (source, folder inside _internal): a folder is copied with its subfolders, a file into the named folder.
DATAS = [
    (os.path.join(ROOT, "rules"), "rules"),
    (os.path.join(ROOT, "templates"), "templates"),
    (os.path.join(ROOT, "resources"), "resources"),
    (os.path.join(REPO, "docs", "technical", "reference"), os.path.join("docs", "technical", "reference")),
    (os.path.join(REPO, "docs", "user"), os.path.join("docs", "user")),
]
# Every preset by pattern: a fixed list once left two of the presets out of the build.
PRESETS = sorted(glob.glob(os.path.join(ROOT, "profiles", "preset-*.json")))
if not PRESETS:
    raise SystemExit("no presets in " + os.path.join(ROOT, "profiles"))
DATAS.extend((preset, "profiles") for preset in PRESETS)
for source, _target in DATAS:
    if not os.path.exists(source):
        raise SystemExit("data source is missing: " + source)


# Analysis, PYZ, EXE and COLLECT are globals that PyInstaller defines while it executes this file.
def analysis(script):
    """An Analysis of one entry script with fresh option lists (PyInstaller extends hiddenimports in place)."""
    return Analysis(
        [os.path.join(ROOT, "winkickoff", script)],
        pathex=[ROOT],
        binaries=[],
        datas=list(DATAS),
        hiddenimports=[],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=[],
        noarchive=False,
    )


# The window: python -m winkickoff (the dispatcher also serves --mcp when a client passes pipes).
window = analysis("__main__.py")
# The console executable: a stdio MCP server unless another flag is given; never imports tkinter.
server = analysis("mcp_main.py")

window_pyz = PYZ(window.pure)
server_pyz = PYZ(server.pure)

# UPX is never installed on the build machines; saying so keeps the result independent of the machine.
window_exe = EXE(
    window_pyz,
    window.scripts,
    [],
    exclude_binaries=True,
    name="WinKickOff",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
server_exe = EXE(
    server_pyz,
    server.scripts,
    [],
    exclude_binaries=True,
    name="WinKickOff-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

# One COLLECT with both executables: PyInstaller writes dist\WinKickOff with the two exe files and one
# _internal folder (the data files appear twice in the list; COLLECT keeps one copy of every name).
collected = COLLECT(
    window_exe,
    window.binaries,
    window.datas,
    server_exe,
    server.binaries,
    server.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="WinKickOff",
)
