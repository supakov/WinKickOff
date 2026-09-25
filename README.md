# WindowsInstaller: Windows deployment tools for workgroups

**User documentation:** [Русский](docs/user/ru/README.md) · [Українська](docs/user/uk/README.md) · [English](docs/user/en/README.md)

A toolkit for small workgroups without a Windows domain, where the computers are used by non-professionals
and the organisation is under constant cyber attack. The goal: install Windows 11 Pro already hardened and
updatable, without configuring every PC by hand and without third-party programs.

## Tools

| Tool | What it does | Where | State |
|---|---|---|---|
| **WinKickOff** | Desktop editor: every installation rule in a searchable tree with descriptions, dependent rules are disabled automatically, profiles are saved, the output is `autounattend.xml` built from the selection only | [`WinKickOff/`](WinKickOff/README.md) | 0.2.0: the full cycle works in the window; installation from a built file not yet tested in a VM |
| **Validate-Unattend** | Static check of any answer file against the limits of Windows Setup (36 checks), read-only | [`tools/Validate-Unattend.ps1`](tools/Validate-Unattend.ps1) | Done |

The next tool, applying selected rules to an already installed Windows with an audit and a rollback, is
described in [task T15](docs/technical/editor/todo/T15-apply-to-running-system.md). Passwords and groups are
assigned by a separate project of the customer after installation.

## Quick start

Python 3.14 for Windows is needed (standard library only).

```powershell
cd WinKickOff
python -m winkickoff
```

In the window: choose a profile (the «Офис» (Office) preset), disable or adjust rules if needed, press
«Собрать autounattend.xml» (Build autounattend.xml, F9) and put the file into the root of a USB drive with the
Windows 11 installation image. Step by step: [quick start](docs/user/en/quick-start.md).

Check a built file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

## Safety

- Every new answer file is first tested by an installation in a virtual machine, then used on production PCs.
- The starter accounts Admin and User are created without passwords: passwords and groups are assigned by a
  separate project after installation. A password entered in the editor is stored in the file in plain text.
- The tools change nothing on the computer they run on: the editor writes only into its own folder, the
  checker only reads the file.

## Documentation

- [docs/](docs/README.md): user documentation in three languages, technical documentation, appendices.
- [Appendices](docs/appendices/README.md) (Russian): the original UnattendedWinstall file, our hand-written
  answer file v0.2 (the reference the WinKickOff catalog grew from), the reviews.
- [AGENTS.md](AGENTS.md): project map for developers and agents.

## Repository

https://github.com/supakov/WindowsInstaller (private). The local folder and the repository match; the
program's working folders (`output/`, `logs/`, `settings.json`) and user profiles are not versioned.

```bash
git clone https://github.com/supakov/WindowsInstaller.git
```
