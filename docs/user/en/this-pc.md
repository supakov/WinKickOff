# Checking and applying on a running computer

The "This PC" menu and a right click on a rule or group in the tree let you check an already installed
Windows and, if needed, adjust it without reinstalling. First select a rule or a group in the tree.

## Check the selection on this PC

The check only reads: the registry, service start types, components, apps. It changes nothing and works
without administrator rights; without them some checks (components, apps of other users) are marked
"not checked". The result for each rule appears in the list at the bottom of the window: "in effect",
"not in effect" (with the current and the expected value), "partly in effect", "not checked".
Values of the default user profile are checked for the current user.

## Save an apply script

"Save an apply script for the selection..." creates a folder with three files:

| File | Purpose |
|---|---|
| `Apply.ps1` | Applies the selected rules. Run it as administrator. Before every change of the registry, a service or a component it saves the previous value to `backup-*.json` and writes the log `apply-*.log` next to itself |
| `Undo-Apply.ps1` | Restores the previous values from the latest backup |
| `README.txt` | How to run it, the list of rules, what is not applied and what is not rolled back |

The script can be taken to another computer. Test it on a test computer or a virtual machine first.

## Apply now

"Apply the selection now..." is unavailable by default. The "Allow applying on this PC" item of the
"This PC" menu turns it on (with a warning). Before starting, the program shows the computer name, the
number of rules, what is not rolled back automatically and whether a restart is needed; then Windows asks
for administrator rights. The log and the backup are saved in the program's `logs` folder.

## What is not applied

- Rules that take effect only during Windows installation (bypassing checks, OOBE screens).
- Rules of a user's first sign-in, including the input language list: changing keyboard layouts on a
  running system can break layout switching.
- Rules disabled in the profile. Rules the selected ones depend on are added automatically.

App and component removal and PowerShell steps are not rolled back automatically: the description of every
rule has a "Rollback" section. Restart the computer after applying.
