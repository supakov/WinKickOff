# Quick start

The same steps are shown by the "Workflow" node at the top of the program's tree.

## 1. Profile

The "Profile" field on the top bar. "Preset: Office" is based on the tested v0.2
answer file: security, updates, printing, the initial Admin and User accounts, and English, Ukrainian and
"Russian (Ukraine)" input languages. "Preset: Strict" adds restrictions that may get in
the way of older programs. Presets are never overwritten: a modified profile is saved under its own name.

## 2. Rules

The tree on the left contains all installation settings, grouped by area. The box in front of a name
turns a rule or a whole group on or off; «+» only expands the branch. The counter next to a group shows
how many rules are enabled.

Rules are linked. If you turn off a rule that other rules depend on, they are turned off along with it; if
you turn on a rule, whatever it needs is turned on too. What changed automatically is shown in the status
bar and in the list at the bottom of the window. Rules that differ from the default settings are highlighted
in color.

Search (Ctrl+F) looks through names, tags and technical details, for example the name of a registry key or
a service. Esc clears the search. Space turns the selected rule on or off.

## 3. Description and parameters

On the right, the program shows for the selected rule: what it does technically (registry keys, services,
commands), its effect, risks, Windows versions, dependencies, how to check it after installation and how to
roll it back. Dependencies are clickable and take you to the related rules. "Reference entry" opens a detailed technical description.

Some rules have parameters (screen lock time, protection modes). You change them below the description;
a changed value is marked with the word "changed". The "Restore defaults" button undoes the changes.

## 4. Installation data

Nodes at the top of the tree:

- "Installation": Windows edition and product key (generic key, your own key, or choose the edition during
  installation), time zone, computer name (chosen by Windows, set in the form or made from a template such as
  `OFFICE-{serial:6}`, where `{serial}` is the end of the serial number). Apart from Pro and Education, the generic keys of the list are KMS client keys: without a
  KMS server of the organisation, Windows stays unactivated until the key of the license is entered after
  installation. The installation media must contain the chosen edition.
- "Accounts": the initial accounts, their groups and descriptions, or "Ask for the account during installation": then
  Windows Setup itself asks for the name of one administrator account. Write account names and passwords in Latin
  letters: Windows Setup 24H2 and later turns other characters into question marks. The display name and the
  description may be Cyrillic: WinKickOff sets them after the out-of-box experience.
- "Languages and region": display language (the same as the image language), formats,
  code page and the list of input languages in order.

## 5. Saving the profile

"Save" (Ctrl+S) writes the profile to the `profiles` folder next to the program. You need the
profile to repeat the same installation on other computers and to make changes later. The "File, Recent"
(File, Recent) menu opens recent profiles and files. The next time you start the program, it opens the
profile that was open when it was closed.

## 6. Checking and building

"Check" (F7) checks the profile and the file it will produce, and shows errors and warnings
in the list at the bottom; double-clicking a message takes you to the rule or field.

"Build autounattend.xml" (F9) builds the file from the enabled rules only, checks
the limits of Windows Setup and the syntax of PowerShell scripts, and asks where to save the file (the
`output` folder by default). The file must be named `autounattend.xml`: Windows Setup looks only for this name.

## 7. Installation

Copy `autounattend.xml` to the root of the USB drive with the Windows 11 installation image and boot the
computer from it. Details and how to check the result: [Installation and checks](install-and-check.md).
