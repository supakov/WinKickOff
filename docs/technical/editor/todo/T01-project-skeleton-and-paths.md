# T01. Project skeleton, portable paths, log, tests

Status: done (25.09.2026: package, paths, log, entry point, `tools/run-tests.ps1`, path and source tests;
the external `Validate-Unattend.ps1` on the built file is called from `tests/test_build.py`. Verification in a clean
Python environment moves to the T12 acceptance in a VM). Stage 0. Dependencies: none.

## Goal

Create the `WinKickOff/` structure according to `02-architecture.md`, section 2, implement `core/paths.py`,
`core/log.py`, the entry point and the test infrastructure on `unittest`.

## Steps

1. `WinKickOff/pyproject.toml`: name `winkickoff`, `requires-python = ">=3.14"`, no runtime
   dependencies; optional groups `build` (pyinstaller) and `dev` (ruff, mypy).
2. The `winkickoff` package with subpackages `core`, `ui`; `__init__.py` with `APP_VERSION`; `__main__.py`.
3. `core/paths.py`: `AppPaths`, `app_paths()`; creation of `profiles/`, `output/`, `logs/`.
4. `core/log.py`: `setup_logging(paths)` into `logs/winkickoff.log`, rotation at 1 MB, three files.
5. `app.py`: DPI-awareness, catalog loading, window; on a catalog error, a window with a message.
6. `tests/`: `test_paths.py` (dev and "frozen" mode by overriding `sys.frozen`), run with
   `python -m unittest discover -s tests`.
7. `tools/run-tests.ps1`: running the tests and `Validate-Unattend.ps1` on the built file (once it exists).
8. `README.md` in `WinKickOff/`: running from source, tests, build, rules.

## Acceptance criteria

- `python -m winkickoff` opens the window (in tests it is created hidden).
- Path tests are green; the package contains no `os.getcwd()`, `APPDATA`, `winreg` (a test over the sources).

## Implementer notes

25.09.2026: created `pyproject.toml`, the package, `paths.py`, `log.py`, `app.py`, `__main__.py`, path
tests and the source verification, `README.md`. Remaining: `tools/run-tests.ps1`, verification on Python 3.14
in a clean environment (done only on the customer's machine via `py_compile` and `unittest`).
