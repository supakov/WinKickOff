@echo off
rem Starts the WinKickOff editor from the sources, without a build.
rem Needs Python 3.14 or newer for Windows (the standard installer includes tkinter and the "py" launcher).
rem The program writes only inside the WinKickOff folder (settings.json, logs, output), like the portable build.
setlocal
set "APP=%~dp0WinKickOff"
if not exist "%APP%\winkickoff\__main__.py" (
    echo WinKickOff sources were not found in "%APP%".
    pause
    exit /b 1
)
cd /d "%APP%"

set "CHECK=import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 14) else 1)"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "%CHECK%" >nul 2>nul
    if not errorlevel 1 (
        start "WinKickOff" pyw -3 -m winkickoff %*
        exit /b 0
    )
)
where pythonw >nul 2>nul
if not errorlevel 1 (
    pythonw -c "%CHECK%" >nul 2>nul
    if not errorlevel 1 (
        start "WinKickOff" pythonw -m winkickoff %*
        exit /b 0
    )
)
echo Python 3.14 or newer with tkinter was not found.
echo Install it from https://www.python.org/downloads/windows/ (keep "tcl/tk" and "py launcher" selected),
echo or use the portable build from the GitHub releases, which needs no Python.
pause
exit /b 1
