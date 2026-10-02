# WinKickOff

**User documentation:** [Русский](docs/user/ru/README.md) · [Українська](docs/user/uk/README.md) · [English](docs/user/en/README.md)

A toolkit for installing and configuring Windows 11 Pro in small workgroups without a Windows domain,
where the computers are used by non-professionals and the organisation is under constant cyber attack.
The goal: Windows hardened and updatable from the first boot, without configuring every PC by hand and
without third-party programs.

State on 02.10.2026: version 1.2.0-rc.4 (release candidate; MCP server for AI clients, read-only by default, with a
skill that teaches assistants to use it; import of ADMX policy templates, including policies with lists of values; Back and Forward; imported policies follow the built-in rules). Installation from a built answer file has been
confirmed by the customer on real hardware. Downloads: the GitHub releases of the repository (portable zip,
no installation, no administrator rights).

## Tools

| Tool | What it does |
|---|---|
| Editor (`WinKickOff/`) | Every installation rule in a searchable tree with descriptions; dependent rules are disabled automatically; profiles and presets; the output is `autounattend.xml` built from the selection only; interface in English with Russian and Ukrainian translations (more languages are added as files), light, dark, Latte and Matrix colour themes; optional import of ADMX policy templates (Windows, Edge, Chrome, Office) as a subtree of selectable policies; an MCP server (stdio and HTTP on 127.0.0.1, read-only by default) for AI clients such as Claude Code and Claude Desktop |
| This PC (menu of the editor) | Read-only check of an installed Windows; apply the selected rules or return them to Windows defaults, with a backup and rollback |
| Validate-Unattend (`tools/Validate-Unattend.ps1`) | Static check of any answer file against the limits of Windows Setup (36 checks), read-only |

Passwords and groups of the accounts are assigned by a separate project of the customer after installation.

## Quick start

Portable build: unzip `WinKickOff-<version>.zip` from a release and run `WinKickOff.exe`. From sources,
Python 3.14 for Windows is needed (standard library only): double-click `Start-WinKickOff.cmd` in the repository
root, or run

```powershell
cd WinKickOff
python -m winkickoff
```

In the window: choose a profile (the Office preset), disable or adjust rules if needed, press
"Build autounattend.xml" (F9) and put the file into the root of a USB drive with the
Windows 11 installation image. Step by step: [quick start](docs/user/en/quick-start.md).

Check a built file:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

## Safety

- Every new answer file is first tested by an installation in a virtual machine, then used on production PCs.
- The starter accounts Admin and User are created without passwords: passwords and groups are assigned by a
  separate project after installation. A password entered in the editor is stored in the file in plain text.
- The tools change nothing on the computer they run on unless the user explicitly applies or returns rules
  through the This PC menu: the editor writes only into its own folder, the checker only reads the file. The MCP
  server is off by default, accepts connections only from this computer, is read-only until the user switches the
  mode, never runs PowerShell or applies anything, and never returns passwords or product keys.

## Documentation

- [docs/](docs/README.md): user documentation in three languages, technical documentation, appendices,
  [release notes](docs/releases/).
- [Appendices](docs/appendices/README.md) (Russian): our hand-written answer file v0.2 (the reference the
  WinKickOff catalog grew from), the critic's report, the first requirements draft.
- [AGENTS.md](AGENTS.md): repository map for developers and agents.
- [pi-agent/](pi-agent/README.md): a Podman image of an assistant with a local model (the pi agent) that analyses and
  changes WinKickOff profiles only through the MCP server, without a cloud model (its acceptance test is pending).

## Repository and builds

https://github.com/supakov/WinKickOff (private). Every push to `main` runs the tests, the answer file checker
and the portable build in GitHub Actions ([`.github/workflows/build.yml`](.github/workflows/build.yml)), and on Linux
builds the image of `pi-agent/` and checks its connection to a WinKickOff MCP server and the tools it gives the
model; a tag
`v<version>` also publishes a release with the zip. The program's working folders (`output/`, `logs/`,
`settings.json`) and user profiles are not versioned.

```bash
git clone https://github.com/supakov/WinKickOff.git
```
