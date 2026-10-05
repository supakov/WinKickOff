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

A ready import can also come without ADMX files: from a catalog file exported on another computer, or from a
catalog of the program (sections below).

The import is kept in the `admx` folder next to the program (in the portable build next to `WinKickOff.exe`) and
is available at later starts in the same "ADMX" menu: the check mark at the name of an import shows or hides its
branch, and "Delete imported templates" removes an import from the program folder.

The name of a branch can be changed: the "Rename..." button at the bottom when the root of the branch is selected,
or "Rename imported templates" in the "ADMX" menu. A name of your own is kept when the import is updated.

When the folder is already imported, the program asks what to do: "Yes" updates the earlier import (its branch
and the choices in profiles stay, handy after a Windows update), "No" adds one more branch. How a policy found in
several branches behaves is described in the section "One policy in several branches".

## Catalog files

A catalog file holds imported templates in full: the policies, their parameters and translations. With it the
templates move to another computer with WinKickOff 1.3 or later that has neither the folder with the ADMX and ADML
files nor the same version of Windows.

To move the templates:

1. The "ADMX" menu, "Export imported templates": pick the import in the submenu and choose where to save the file.
   The result is a text file `.json`. The path of the folder the templates were once imported from is not written
   into the file: it is a path on your computer and is not needed on another one. In the messages about template
   files that could not be read, only the file name is left of a path too.
2. Take the file to the other computer (on a USB drive or through a shared folder).
3. There, choose "Import a catalog file..." in the "ADMX" menu and open the file. Both a plain `.json` and a file
   compressed with gzip or xz (`.json.gz`, `.json.xz`) are accepted: the program unpacks it by itself.
4. After a few seconds a new branch appears in the tree with the same name as on the first computer (the name is
   written in the file, also a name you gave the branch yourself). From then on it works as after an import of
   templates: the check mark in the "ADMX" menu shows or hides it, and it can be renamed, deleted and exported
   again. The file itself may be deleted after the import: the program keeps its own copy in the `admx` folder.

A profile in which policies of these templates are chosen can be moved along with the catalog file (it is a
separate file): the rule names are the same, so once the catalog is imported, the profile finds its choices
(section "Profiles"). A choice made in the templates of this Windows or in templates from a folder does not pass to
the catalog file on the other computer by itself: it stays in the profile but is not used until a source of the
same kind or a more trusted one has the policy. A choice in a profile saved before version 1.3 behaves the same
way. To use such a policy from the catalog file, choose it again in the branch of the file.

When the same file (from the same place on disk) is already imported, the program asks what to do: "Yes" updates
the earlier import (its branch and the choices in profiles stay), "No" adds one more branch, "Cancel" imports
nothing.

A catalog file, like templates from a folder, is treated as untrusted and is checked in full before the import
(section "Safety" lists what is checked). When something in the file is unsafe or broken, the catalog is not
imported: the program shows the message "The catalog was not imported" with the reason (written in English), and
nothing changes in the program folder. The program does not repair a catalog file: in templates from a folder an
unsuitable policy is simply skipped (section "What is not imported"), while in a catalog file one wrong record
refuses the whole file.

## Catalogs of the program

The "Import a catalog of the program" entry of the "ADMX" menu opens a submenu with the catalogs that ship with the
program, named by their file names. Such a catalog holds templates that are already imported (for example the
policies of Windows 11), so they can be added to the tree without ADMX files on the computer. Importing the same
catalog again updates the same branch without asking, and a name you gave the branch is kept.

This version of the program ships no catalog yet, so the entry is greyed out.

## One policy in several branches

The same policy may turn up in several branches, for example in the templates of this Windows and in a catalog
file. It is one policy: its check mark and parameters are shared, and a check mark in one branch shows in all of
them.

What such a policy writes into the registry is taken from the most trusted source:

1. a catalog of the program;
2. the templates of this Windows;
3. templates from a folder;
4. a catalog file.

When two imports of the same kind hold the policy, the one whose branch is higher in the tree wins; a branch that
was just imported, updated or shown again goes to the end. Hidden branches take no part in this. So a file received
from outside cannot replace with its own values a policy that the shown templates of Windows already have. The
other branches show the policy with the same check mark; the order of the branches in the tree does not depend on
the trust of their source. Before version 1.3 the import loaded first won.

A profile remembers in templates of which kind a policy was chosen. When only a less trusted import has the policy
now, the choice is kept but not used (section "Profiles").

## Language

Policy names and descriptions come only from the ADML files in the language of the program interface; when there
is no translation, the English text (en-US) is shown. Translations are read only from language folders named by
a language code (`ru-RU`, `en-US`): a folder such as `en-US - Copy` is skipped. An import keeps the translations
for the languages the program has. Windows itself has almost no Ukrainian ADML files, so in the Ukrainian
interface this branch is mostly in English. A catalog file and a catalog of the program hold the translations the
original import had: when they have no translation into the language of the program, the policies are shown in
English.

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
built-in rule: it is reviewed and documented.

When a built-in rule is on and writes everything the policy writes (with some value of the policy), the check mark
of the policy follows that rule: the policy is shown checked (in the link colour), its description says "Set by
the built-in rule", and it is not written into the answer file separately. Its parameters come from the built-in
rule meanwhile.

- When the policy writes exactly what the built-in rule writes, it is one setting: the check mark of the policy
  switches the built-in rule itself on and off.
- When the policy sets only part of the values of the built-in rule, unchecking the policy asks whether to switch
  the whole built-in rule off.
- When the policy was switched on by itself and then the built-in rule that writes the same is switched on, the
  policy's own check mark goes off by itself, so that the value is not written twice; the messages at the bottom
  show it.

## What is not imported

A policy that cannot be written into the answer file safely is skipped, and the import goes on: one such policy
does not keep the other policies of the folder from being imported. Skipped are policies:

- with options or check boxes that write several values at once;
- with numbers larger than Windows PowerShell writes;
- with characters that are not safe in a script (also in the key or the prefix of a list);
- with a registry key that has an empty part, `.` or `..` between its backslashes (`..\.DEFAULT\Control Panel`,
  for example) or consists of backslashes only: PowerShell takes `..` as a step one level up, and such a policy
  would write its value outside its own registry branch, outside the default user profile for example. The
  message list counts them with the characters that are not safe;
- with an error in the template: for example, the policy has no name, or a check box has the same value for the
  checked and the unchecked state.

After the import their number by reason is shown in the message list at the bottom of the window (the lines
"Not imported: ..."), and the total in the description of the branch. In the templates of Windows 11 build 26300,
for example, these are 20 policies of 3552.

The rest the program repairs by itself, and the policies are imported: control characters in names and
descriptions become spaces, and when categories are nested deeper than 32 levels or refer to each other in a
circle, the chain is cut: one of its categories moves right under "Computer policies" or "User policies".

An import saved by an earlier version of the program (1.2, for example) still loads in this version: the policies
this version does not accept are skipped in the same way and counted among the skipped in the description of the
branch. When such a policy was chosen in a profile, the choice is not lost and shows in the branch "Unknown rules
and policies".

Policies with lists of values and multi-line text are imported since version 1.1.0-rc.2. An import made by
1.1.0-rc.1 does not contain them, and the description of its branch says how many were skipped: delete such an
import and import the templates again.

## Profiles

A profile keeps only imported policies that have a check mark or changed parameters. When such a profile is
opened without the templates loaded (or on another computer), the choice is not lost: the program keeps it and
brings it back when the templates are shown again. Rule names depend on the template and the policy, not on a
particular import, so a new import of the same templates fits older profiles.

While the templates are not loaded, such policies are listed in the last branch of the tree, "Unknown rules and
policies". It appears only when the profile keeps choices for rules the loaded catalog does not have, or a held
choice (see below). Each policy shows its name (the rule id), the kept state and parameters. They cannot be changed
there, and they are not written to the answer file, checked or applied on this PC. When a saved but hidden import
has the policy, the description names that import, and the button "Show" with its name brings the branch of the
import back and opens the policy with the kept choice. When no import in the program folder has the policy, the
buttons below offer to import the templates or a catalog file.

A profile also remembers in templates of which kind a policy was chosen: a catalog of the program, the templates
of this Windows, templates from a folder or a catalog file (the order of trust is in the section "One policy in
several branches"). When the choice was used later from more trusted templates, the profile remembers those: a
policy chosen in a catalog file and used from the templates of this Windows does not go back to the catalog file
by itself. When only a less trusted import has the policy now, for example the choice was made in the templates of
this Windows and now only a catalog file is shown, the choice is kept but not used, that is, it is held:

- in the branch of that import the policy has no check mark and does not go into the answer file;
- the choice shows in the branch "Unknown rules and policies" marked "held: a less trusted source holds the policy
  now", and the description names the source the choice was made with and the source that has the policy now;
- a warning with the list of such policies appears at the bottom of the window: when you open the profile and
  every time the window opens again after a change of the templates (a branch hidden or shown, templates or a
  catalog file imported), the language or the theme.

So a file received from outside cannot quietly set its own values for a policy chosen in more trusted templates.
The choice comes back by itself when templates of the same kind or a more trusted one are shown again. That is why
the description of a held choice names, and offers with the button "Show", only such saved but hidden imports: for
a choice made in the templates of this Windows, a hidden catalog file is not offered. When there is no such
import, the buttons below offer to import templates. To use the policy from the less trusted import, choose it
again in its branch.

Profiles saved before version 1.3 do not record the kind of templates. Catalog files did not exist then, so a
choice in such a profile counts as made in templates from a folder: with a catalog of the program, the templates
of this Windows or templates from a folder it is used as before, and when only a catalog file has the policy now,
the choice is held with the same warning.

## Safety

WinKickOff has not reviewed imported policies: try every new policy in a virtual machine first. Templates from a
folder and catalog files are treated as untrusted, and nothing in them is run:

- template files with a DTD and files that are too big are refused;
- a catalog file larger than 64 MB (also once unpacked) or with more than a million values is not read;
- every record of a catalog file is checked as strictly as what the program itself takes from templates: unknown
  fields, special characters in registry keys and value names, parts `.` and `..` in keys, texts that are too
  long, wrong value types, numbers out of range and categories nested deeper than 32 levels or referring to each
  other in a circle refuse the whole file;
- policies of template files with values that are not safe in a script are not imported (section "What is not
  imported").

The imports in the `admx` folder are checked as well every time the program loads them (at the start and when a
branch is shown), because that folder can be changed by hand. Their policies are checked like the policies of
templates from a folder: an unsuitable policy is skipped and counted among the skipped in the description of the
branch, the others load. An import whose file of records is damaged as a whole (for example, it cannot be read as
JSON or is too big) is not loaded, and the message "Imported templates ... were not loaded" with the reason in
English appears at the bottom of the window; in place of the dots stands the name of the import folder inside
`admx`, for example `package-20261004-120000`. An import whose description file `import.json` is damaged is not
shown in the "ADMX" menu either; the reason is written to the log `logs\winkickoff.log`.

The check sees to it that the values of a file reach the answer file only as data, but it does not judge whether a
policy is useful: a policy may write outside the policy branches of the registry, as the templates of Windows itself
do. So import catalog files only from sources you trust.
