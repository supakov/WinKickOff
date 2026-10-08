# T24. Computer name; account texts outside ASCII

Status: done in code (08.10.2026), version 1.3.0-rc.2; acceptance in a VM pending.
Stage 9. Dependencies: T05 (forms), T15 (runtime).

## Goal

Two requests of the customer of 08.10.2026:

1. The Cyrillic description of a user becomes question marks after installation; find the other places where Cyrillic
   could break.
2. An optional computer name, and if possible a name made from a template.

## Result

- Cyrillic: Windows Setup 24H2 and later turns the characters of a `LocalAccount` outside ASCII into question marks
  (reference card 03). Everything else that carries Cyrillic was checked and keeps it: the answer file is UTF-8 and
  read by `XmlDocument.Load`, the scripts are extracted as UTF-8 with a byte order mark, the logs of the scripts are
  UTF-8, the Apply, Undo and Audit scripts are written with a byte order mark and the audit report is read as
  `utf-8-sig`, the PowerShell syntax check writes `utf-8-sig`, MCP sends UTF-8 bytes, launching uses Unicode APIs.
  So the build writes a display name or a description outside ASCII as the account name and no description, and
  `Post-OOBE.ps1` sets them after OOBE through ADSI (`Set-AccountText`, the text as UTF-8 in Base64,
  `render.ps_text`), also when there is no post-oobe rule. The check refuses an account name or a password outside
  ASCII, and both XML checks (`validate.validate_xml`, `tools/Validate-Unattend.ps1`, now 37 checks on v0.2) refuse
  such texts in any file.
- Computer name (`core/computername.py`, profile format 4, catalog and runtime 0.7, reference card 02): the form
  "Installation" offers "Windows chooses a name" (as before), "This name" (`ComputerName` of specialize) and "A name
  from a template" with `{serial}`, `{mac}` and `{random}` and optional lengths. A template is computed by
  `templates/section-computer-name.ps1` at the start of `Setup-System.ps1`; the answer file holds `WINKICKOFF-TMP`,
  and a hidden process writes the computed name until the restart after specialize, the technique of the answer file
  generator of Christoph Schneegans.

## Acceptance criteria

- `python -m unittest discover -s tests` is green; the scripts with a template and account texts parse in Windows
  PowerShell 5.1; the validator accepts a build with a fixed name and a Cyrillic description.
- In a VM: a fixed name and a template give the expected name at the first sign-in; a Cyrillic display name and
  description of an account are correct after OOBE (`Get-LocalUser ... FullName, Description`, `Post-OOBE.log`).

## Open points

- The VM checks above, and `{mac}` on a PC whose network driver is missing in specialize.
