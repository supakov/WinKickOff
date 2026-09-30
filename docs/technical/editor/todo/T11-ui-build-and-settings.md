# T11. Build from the window, verification, export, recent files, settings

Status: done (25.09.2026: F7, F9 with the PowerShell check in a background thread (buttons and keys
are blocked), save dialog, output folder; File menu: presets, open, save, save as,
import from XML, recent (up to 8); `settings.json` next to the program: window size, last profile,
recent files, a corrupted file is ignored; "About"; full-session test `test_portable.py`:
the program writes only to its own folder. The display language setting will appear with the T14 localization).
Stage 4. Dependencies: T07, T08, T10. Milestone M4.

## Goal

Close the loop in the window: verify, build, save the XML, import, recent profiles, `settings.json`.

## Steps

1. Build menu: Check (F7): the result in the bottom panel, a double-click leads to the rule or field;
   Build (F9): verification → build → XML verification → PowerShell check in the background → save dialog
   (default `output/autounattend.xml`); Open folder.
2. File menu: New from preset, Open, Save, Save as, Import from XML, recent (up to 8).
3. `settings.json` next to the exe: language, geometry, recent files; a corrupted file is ignored.
4. "About": application and catalog versions, links to the documentation.
5. Background operations via `threading.Thread` and `after()`; buttons are disabled for the duration.
6. Tests: a build from the window equals `Renderer.build`; a validator error blocks the build; the application
   does not write outside its folder (`app_paths` substituted with a temporary folder).

## Acceptance criteria

- Full cycle without a console; nothing outside the application folder.

## Implementer notes
