# T12. PyInstaller build and portability verification

Status: in-progress (25.09.2026: `tools/build.ps1` written and syntax-checked; the build itself installs
PyInstaller and therefore runs only in a VM, see AGENTS.md rule 1). Stage 5. Dependencies: T11.

## Goal

A portable build `dist/WinKickOff/` and a portability checklist in a VM.

## Steps

1. `tools/build.ps1`: venv on Python 3.14, PyInstaller installation, `pyinstaller --noconsole --onedir
   --name WinKickOff --add-data rules;rules --add-data templates;templates --add-data resources;resources
   --add-data profiles;profiles --add-data ../docs/technical/reference;docs/technical/reference --add-data ../docs/user;docs/user winkickoff/__main__.py`
   (implemented in `tools/build.ps1` with absolute paths);
   copying `README-user.md`; a zip with the version.
2. `app_paths()` in the build finds the data in `_internal` and creates folders next to the exe.
3. Icon and exe version information.
4. If PyInstaller does not support 3.14: build on 3.13, do not change the code, note it.
5. Portability checklist in a clean VM (snapshots of the registry and `%APPDATA%` before and after, moving the folder,
   removal without traces).
6. SmartScreen behavior with an unsigned exe: describe it in `README-user.md`.

## Acceptance criteria

- The six checklist items are done; startup within 2 seconds; size up to 40 MB.
- An XML built in the VM from the «Офис» (Office) preset passes `Validate-Unattend.ps1`.

## Implementer notes

25.09.2026: `tools/build.ps1` runs the tests, creates `build/venv`, installs PyInstaller there, builds
`dist/WinKickOff` (onedir, no console) with rules, templates, resources, presets, the technical reference
and the user documentation in `_internal`, copies the user documentation next to the exe and zips the
folder. Not executed on the customer's PC. Remaining: run in a VM, icon and version resource, the
portability checklist, SmartScreen note for the unsigned exe in the user documentation.
