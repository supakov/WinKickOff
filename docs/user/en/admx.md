# Policy templates (ADMX)

Besides the built-in rule catalog, the program can show the administrative templates of Windows (ADMX files with
their ADML translations) and build the chosen policies into the answer file just like ordinary rules. This is a
feature for experienced administrators: the built-in rules are reviewed and documented, imported policies are not.

## How to import

1. The "ADMX" menu, "Import the templates of this Windows": the program reads the `C:\Windows\PolicyDefinitions`
   folder of this computer. The files are only read; nothing in the system changes.
2. Or "Import templates from a folder...": a folder with downloaded templates (Microsoft Edge, Google Chrome,
   Office and others) holding the `.admx` files and the language folders (`en-US`, `ru-RU` and so on) with the
   `.adml` files.
3. Reading takes a few seconds. Then a new branch appears in the tree with a name like
   "PolicyDefinitions 10.0.26200, 2026-09-30 13:05"; inside are "Computer policies" and "User policies" with the
   categories of the templates.

The import is kept in the `admx` folder next to the program (in the portable build next to `WinKickOff.exe`) and
is available at later starts in the same "ADMX" menu: the check mark at the name of an import shows or hides its
branch, and "Delete imported templates" removes an import from the program folder.

## Language

Policy names and descriptions come only from the ADML files in the language of the program interface; when there
is no translation, the English text (en-US) is shown. An import keeps the translations for the languages the
program has. Windows itself has almost no Ukrainian ADML files, so in the Ukrainian interface this branch is
mostly in English.

## How a policy becomes a rule

- A check mark at a policy means "set it", no check mark means "not configured": such a policy does not go into
  the answer file, and "Apply the selection now" leaves it alone (built-in rules without a check mark, on the
  contrary, return to the Windows values).
- A simple policy that sets one value gets the parameter "Policy state": "Enabled" or "Disabled".
- A complex policy gets its parameters from its fields: numbers, lists of options, text, check boxes. When the
  "Disabled" state writes values of its own, a second rule marked "(Disabled)" appears; only one of the two can be
  on.
- A list of values (for example allowed addresses) and multi-line text are edited in a multi-line box: one item
  per line, empty lines and spaces around items are dropped. When every item has a name of its own, the line is
  written as `name=value`; the hint next to the box says so. Unless the template allows adding to the list, it
  replaces everything that was in its registry key, as Group Policy does; such a list left empty clears the key.
  The "(Disabled)" rule of a policy with a list also leaves the key of the list empty.
- Computer policies are written to HKLM during installation, user policies to the default user profile, so every
  account created during installation gets them.
- Imported policies are switched on one by one; the check box of a group in this branch only switches them off.
  An imported policy returns to the Windows default value when the policy itself is selected, not its group.

## Matches with built-in rules

When a policy writes the same registry value as a built-in rule, its description has a section "Built into the
catalog" with a link to that rule, and the built-in rule has a section "Also in imported templates". Prefer the
built-in rule: it is reviewed and documented. When both are on, the check warns about it.

## What is not imported

Policies with options or check boxes that write several values at once, with numbers larger than Windows
PowerShell writes, and with characters that are not safe in a script (also in the key or the prefix of a list)
are skipped. After the import their number by reason is shown in the message list at the bottom of the window,
and the total in the description of the branch. In the templates of Windows 11 build 26300, for example, these are
20 policies of 3552.

Policies with lists of values and multi-line text are imported since version 1.1.0-rc.2. An import made by
1.1.0-rc.1 does not contain them, and the description of its branch says how many were skipped: delete such an
import and import the templates again.

## Profiles

A profile keeps only imported policies that have a check mark or changed parameters. When such a profile is
opened without the templates loaded (or on another computer), the choice is not lost: the program keeps it and
brings it back when the templates are shown again. Rule names depend on the template and the policy, not on a
particular import, so a new import of the same templates fits older profiles.

## Safety

WinKickOff has not reviewed imported policies: try every new policy in a virtual machine first. Templates from a
folder are treated as untrusted: files with a DTD, files that are too big and values with special characters are
refused.
