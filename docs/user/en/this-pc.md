# Checking and applying on a running computer

The "This PC" menu and a right click on a rule or group in the tree let you check an already installed
Windows and, if needed, adjust it without reinstalling. First select a rule or a group in the tree.

## Check the selection on this PC

The check only reads: the registry, service start types, components, apps. It changes nothing and works
without administrator rights; without them some checks (components, apps of other users) are marked
"not checked". The result for each rule appears in the list at the bottom of the window: "in effect",
"not in effect" (with the current and the expected value), "partly in effect", "not checked".
Values of the default user profile are checked for the current user.

## Read the settings of this PC into a new profile

The "This PC" menu item "Read the settings of this PC into a new profile..." turns the state of the computer into a
profile. Set up a reference computer and install others from its profile, or study a damaged or infected system:
which protections do not take effect on it and what is there instead.

The read only reads, like the check above, and changes nothing on the computer. It reads every rule a running Windows
can show, built-in and imported: a rule in effect is switched on with the parameters found on the computer (the
screen lock time, for example); a rule partly in effect is switched off and named in the list at the bottom of the
window, so that you decide; a rule not in effect is switched off. Rules that act only during installation or at the
first sign-in, and checks that need administrator rights, keep the state of the open profile. The data forms get the
edition, the time zone, the languages and the local accounts (without passwords). The computer name is not taken, so
that the computers installed from the profile do not share one name.

As administrator ("Read the settings of this PC as administrator into a new profile...") Windows asks to confirm
the rights once, and the read itself runs hidden and still changes nothing; it then reads the optional features,
capabilities and the apps of every user too.

The result opens as a new profile with unsaved changes: check it ("Check", F7) and save it under a name of your own.
The values come from this computer; on a damaged or infected system they may be anything, so look through them before
a build.

## Save an apply script

"Save an apply script for the selection..." creates a folder with three files:

| File | Purpose |
|---|---|
| `Apply.ps1` | Makes the computer match the profile for the selection: rules with a check mark are applied, rules without one return to the Windows defaults. Run it as administrator. Before every change of the registry, a service or a component it saves the previous value to `backup-*.json` and writes the log `apply-*.log` next to itself |
| `Undo-Apply.ps1` | Restores the previous values from the latest backup |
| `README.txt` | How to run it, the list of rules, what is not applied and what is not rolled back |

The script can be taken to another computer. Test it on a test computer or a virtual machine first.

## Apply now

"Apply the selection now..." asks, the first time, for permission to change this computer (with a
warning); the answer is kept in the "Allow applying on this PC" item of the "This PC" menu, where it can
also be withdrawn. Before starting, the program shows the computer name, the number of rules, what is not
rolled back automatically and whether a restart is needed; then Windows asks for administrator rights. The
log and the backup are saved in the program's `logs` folder.

## Return to Windows defaults

"Return the selection to Windows defaults now..." undoes the selected rules on this computer: the values go
back to those of a clean Windows, whether the rules came with the installation or were applied later.
Policies are simply deleted; other values and service start types come from the catalog. Rules that depend
on the selected ones are returned together with them. Permission, confirmation and administrator rights are
asked for as when applying; the previous values are saved to a backup, and `Undo-Apply.ps1` in the
`logs\revert-*` folder undoes the return.

Not returned automatically: removed apps and components, PowerShell steps and values whose Windows default
depends on the build (SMB signing, for example). They are listed at the bottom of the window.

## What is not applied

- Rules that take effect only during Windows installation (bypassing checks, OOBE screens).
- Rules of a user's first sign-in, including the input language list: changing keyboard layouts on a
  running system can break layout switching. For the same reason the keys that switch the input language are
  not changed here, because that rule also changes the sign-in screen.
- Rules without a check mark whose Windows defaults are unknown (app removal, PowerShell steps): they are listed at
  the bottom of the window. The other rules without a check mark return to the Windows defaults together with the
  rules that depend on them; rules the selected ones depend on are added automatically.
- When there is nothing to apply in the selection, the program says so in a separate window with the reasons.

App and component removal and PowerShell steps are not rolled back automatically: the description of every
rule has a "Rollback" section. Restart the computer after applying.
