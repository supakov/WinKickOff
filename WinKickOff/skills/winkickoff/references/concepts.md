# WinKickOff concepts

Catalog 0.7: 278 rules in 40 groups; 214 rules are on by default, 190 are optional.

## Contents

- [What WinKickOff is](#what-winkickoff-is)
- [Rules](#rules)
- [Levels](#levels)
- [Phases](#phases)
- [Parameters](#parameters)
- [Dependencies](#dependencies)
- [Groups](#groups)
- [Presets](#presets)
- [Profiles](#profiles)
- [Data forms](#data-forms)
- [Imported ADMX policies](#imported-admx-policies)
- [Check messages](#check-messages)
- [The build](#the-build)
- [Testing in a virtual machine](#testing-in-a-virtual-machine)
- [This PC menu](#this-pc-menu)

## What WinKickOff is

- A portable Windows program that builds `autounattend.xml` for an unattended installation of **Windows 11 Pro** in
  small workgroups without a domain, where users are not professionals and the organisation is under constant attack.
- Priorities: security and updatability. No cosmetic tweaks, no third-party programs, no "optimizers".
- Usual path: pick a profile (Office is the recommended start), switch rules in the tree, fill the three data forms,
  check, build, put the file on a USB stick, install. Setup then asks only for the disk, unless the "Installation" form
  asks for the key and the edition (key mode `ask`) or the "Accounts" form for the account (`account_mode` `ask`).
- Building an answer file changes nothing on the PC it runs on, and the program writes only inside its own folder
  (`profiles`, `output`, `logs`, `admx`, `settings.json`) or to a file the person picks in a dialog. The exception is
  the window's "This PC" menu: "Apply the selection now..." and "Return the selection to Windows defaults now..."
  change this computer after the person allows it and accepts a UAC prompt; never through MCP.

## Rules

A rule is one switch in the tree. The answer file contains **only the rules that are on**.

| Field | Meaning |
|---|---|
| `id` | Stable English id, for example `defender.pua`. Never translated. Ids starting with `admx.` are imported policies |
| `group` | Tree group (see [Groups](#groups)). The id prefix is not always the group: `uac.*` is in `security.uac`, `asr.*` in `defender.asr` |
| `level` | See [Levels](#levels) |
| `phase` | When it runs, see [Phases](#phases) |
| `default` | State in the catalog. The catalog defaults are exactly the Office preset |
| `params` | Typed settings of the rule, see [Parameters](#parameters) |
| `requires`, `dependents` | See [Dependencies](#dependencies) |
| `effect`, `risk`, `versions` | What changes for users, what may break, which Windows versions |
| `actions` | What the rule really does: registry values, services, Windows features, app removal, PowerShell steps, XML elements |
| `verify`, `rollback` | Command to check it after installation; how to undo it on an installed PC |
| `doc` | Reference card, readable as `winkickoff://docs/reference/<file>` |

**On and off.** A rule that is off is not configured: Windows keeps its own default. Many ids end in `-off`; switching
such a rule **on** turns the Windows feature **off**. Switching it off does not turn the feature on. Example:
`remote.rdp-inbound-off` off does not enable remote desktop.

## Levels

| Level | Count | Meaning |
|---|---|---|
| `baseline` | 21 | The core of protection. Switching one off gives a Check warning |
| `recommended` | 63 | On in Office; switch off only for a reason |
| `optional` | 190 | Privacy, apps, browsers, convenience |
| `risky` | 4 | May disturb programs. Switching one on gives a Check warning: `network.netbios-off`, `scripts.remove-vbscript`, `edge.password-manager-off`, `chrome.password-manager-off` |

## Phases

| Phase | Where it goes | When it runs |
|---|---|---|
| `windowspe` | windowsPE pass | In Setup before copying files (hardware check bypasses) |
| `specialize-xml` | specialize pass | First boot, before OOBE |
| `specialize` | `Setup-System.ps1` | First boot, as SYSTEM, no network, no users yet |
| `default-user` | default user profile, inside `Setup-System.ps1` | Every profile created afterwards (Admin and User at OOBE, later accounts too). Existing profiles do not get it. `default-user.input-switch-keys` also writes the sign-in screen (`HKU:\.DEFAULT`) at installation; it is never applied to a running PC |
| `user-first-logon` | `Setup-User.ps1` | First sign-in of each user (display language pin, keyboard list) |
| `post-oobe` | `Post-OOBE.ps1` | After OOBE (password flags, built-in accounts, cleanup) |
| `oobe-xml` | oobeSystem pass | OOBE screens |

## Parameters

Types: `int` (with `min` and `max`), `enum` (fixed `values`), `string`, `bool` and `list`. Built-in rules use only
`int`, `enum` and `string`; `bool` and `list` exist only in imported policies.

| Rule | Parameter | Default | Values |
|---|---|---|---|
| `update.automatic` | `start`, `end` | 8, 20 | Hours 0-23 (active hours) |
| `update.defer-feature` | `days` | 90 | 1-365 |
| `update.delivery-optimization-lan` | `mode` | 1 | 1 local network only, 0 HTTP only, 99 simple mode without the cloud |
| `defender.cloud` | `block_level`, `timeout` | 2, 50 | Level 2 High, 0 Default, 4 High plus, 6 Zero tolerance; timeout 0-50 s |
| `defender.network-protection` | `mode` | 1 | 1 Block, 2 Audit |
| `asr.*` (18 rules) | `mode` | 1 | 1 Block, 2 Audit, 6 Warn. Exceptions: `asr.copied-system-tools` 6, `asr.prevalence` 2, `asr.psexec-wmi` 2 |
| `defender.controlled-folder-access` | `mode` | 0 | 0 Off, 2 Audit, 1 Block (breaks older programs) |
| `defender.smartscreen-shell` | `level` | `"Warn"` | `"Warn"`, `"Block"` (strings) |
| `uac.admin-always-notify` | `level` | 2 | 2 Always notify, 5 Windows default |
| `accounts.inactivity-lock` | `seconds` | 900 | 60-599940 |
| `accounts.lockout` | `threshold`, `duration`, `window` | 10, 15, 15 | 1-999 attempts; minutes 1-99999 |
| `lsa.protection` | `mode` | 2 | 2 without UEFI lock (reversible), 1 with UEFI lock (irreversible without firmware access) |
| `privacy.telemetry-minimal` | `level` | 1 | 1 Required, 0 Security (acts as 1 on Pro) |
| `oobe.protect-your-pc` | `mode` | 3 | 3 all express settings off, 1 on |
| `default-user.region` | `geo_id`, `geo_name` | `"241"`, `"UA"` | Strings (country of the user profile) |
| `default-user.input-switch-keys` | `language`, `layout` | `"1"`, `"2"` | Strings: `"1"` left Alt+Shift, `"2"` Ctrl+Shift, `"3"` not assigned (Win+Space always works). The two must differ unless one is `"3"` |
| `chrome.variations` | `mode` | 1 | 1 critical fixes only, 2 disable all |
| `chrome.sync` | `value` | 1 | 1 Blocked, 0 user decides |

In the window, "Restore defaults" in the parameter panel resets the parameters of a rule. Through MCP, set the
`default` value with `set_param`.

## Dependencies

- Switching a rule on also switches on every rule it `requires`.
- Switching a rule off also switches off every rule that requires it, transitively (`dependents` in `get_rule`).
- Main chains:
  - `defender.realtime` is needed by `defender.cloud`, `defender.pua`, `defender.network-protection`, `defender.asr`
    and `defender.controlled-folder-access`; `defender.asr` by all 18 `asr.*`; `defender.cloud` by
    `asr.obfuscated-scripts`, `asr.ransomware`, `asr.prevalence`. Switching `defender.realtime` off switches off up
    to 23 rules (21 in Office).
  - `update.unblock` is needed by `update.automatic`, `update.other-microsoft-products`, `update.defer-feature`.
  - Single links: `uac.baseline` to `uac.admin-always-notify`; `logging.eventlog-sizes` to `logging.audit-policy` and
    `logging.powershell`; `removable.autorun-off` to `default-user.autoplay-off`; `privacy.copilot-recall-off` to
    `default-user.copilot-off`; `privacy.consumer-content` to `default-user.no-consumer-content`;
    `privacy.widgets-off` to `default-user.widgets-button-off`; `apps.remove.maps` to `apps.maps-broker-off`;
    `accounts.password-never-expires` to `post-oobe.password-never-expires`; `user-logon.pin-ui-language` to
    `user-logon.input-languages`; `nav.launch-to-this-pc` to `nav.home-hidden`.
- Conflicts: `desktop.gallery` with `nav.gallery-hidden` and `desktop.home` with `nav.home-hidden` (each pair shows and
  hides the same item); an imported policy and its "(Disabled)" variant. Two conflicting rules cannot both be on.

## Groups

`list_rules` with `group` includes subgroups.

| Id | Title |
|---|---|
| `install` | Installation (windowsPE and specialize) |
| `oobe` | Out-of-box experience (OOBE) |
| `printing` | Printing |
| `update` | Windows Update |
| `defender` | Microsoft Defender and SmartScreen |
| `defender.asr` | Attack surface reduction (ASR) rules |
| `security` | Security |
| `security.uac` | User Account Control (UAC) |
| `security.accounts` | Accounts and sign-in |
| `security.lsa` | Credential protection (LSA, NTLM) |
| `security.remote` | Remote access |
| `security.encryption` | Drive encryption |
| `network` | Network and sharing |
| `removable` | Removable media and scripts |
| `removable.scripts` | Script files |
| `browsers` | Browsers |
| `browsers.edge` | Microsoft Edge |
| `browsers.chrome` | Google Chrome |
| `browsers.brave` | Brave |
| `logging` | Logging for investigations |
| `privacy` | Telemetry, ads, AI |
| `privacy.ai` | Artificial intelligence |
| `privacy.telemetry` | Telemetry and feedback |
| `privacy.ads` | Ads and recommendations |
| `privacy.search` | Search and the Start menu |
| `privacy.speech` | Speech and input |
| `privacy.office` | Microsoft Office |
| `system` | System |
| `system.drivers` | Drivers and devices |
| `system.explorer` | File Explorer and the desktop |
| `system.explorer.thispc` | Folders in "This PC" |
| `system.explorer.nav` | Navigation pane |
| `system.explorer.desktop` | Desktop icons (subgroup `system.explorer.desktop.folders`) |
| `apps` | Services and apps |
| `apps.remove` | Apps to remove (summary: one rule per app; clear it to keep the app) |
| `apps.onedrive` | OneDrive |
| `default-user` | Default user profile |
| `user-logon` | First sign-in of each user |
| `post-oobe` | After OOBE |

Prefix hints: `lsa.*` in `security.lsa`; `edge.*` in `browsers.edge`; `ai.*` and `default-user.copilot-off` in
`privacy.ai`; `office.*` in `privacy.office`; `thispc.*` in `system.explorer.thispc`, `nav.*` in
`system.explorer.nav`, `desktop.*` in `system.explorer.desktop`; `default-user.no-sync-provider-ads`,
`default-user.no-consumer-content` and `default-user.http-accept-language-optout` in `privacy.ads`.

## Presets

Four presets ship with the program. They are read-only: a changed preset is saved under a new name.

| Id | For | Difference from the catalog defaults |
|---|---|---|
| `office` | Ordinary work PCs. Recommended start | None (214 of 278 rules on) |
| `strict` | Higher-risk PCs; may break older programs; test on one PC first | On: `update.other-microsoft-products`, `asr.usb-untrusted`, `uac.admin-always-notify`, `network.netbios-off`, `scripts.remove-vbscript`. Parameters: `defender.controlled-folder-access` `mode` 1 (Block), `defender.smartscreen-shell` `level` `"Block"`, `asr.prevalence` `mode` 1 (Block). 219 on |
| `laptop` | Laptops | `accounts.inactivity-lock` `seconds` 600 instead of 900. 214 on |
| `home` | Home PCs: installation screens, app removal and privacy only | 70 on; key mode `ask`; `privacy.telemetry-minimal` `level` 0; of the protection rules only `defender.notifications` and `update.delivery-optimization-lan` (`mode` 99) stay on, Windows keeps its defaults; also off: `install.netfx3`, `printing.spooler-automatic`, `default-user.region`, `user-logon.input-languages`, `user-logon.pin-ui-language`, `removable.autorun-off`, the AI rules of Notepad, Paint, Office and Edge; Check warns per baseline rule. Not for work PCs |

All presets share the data forms: edition Pro, generic key (home: ask), time zone `FLE Standard Time`
(Kyiv), computer name chosen by Windows, display language `uk-UA`, keyboards `en-US`, `uk-UA`, `ru-UA`, accounts Admin (Administrators) and User (Users)
without passwords (account mode `file`).

## Profiles

- A profile is a JSON file in `profiles/` next to the program: rule states, parameters, data forms, name, author,
  comment. Passwords in a profile are stored in plain text.
- `get_profile` `changed_from_defaults` lists differences from the catalog defaults, that is from Office.
- "File, Open profile from autounattend.xml..." in the window restores a WinKickOff build completely; other
  answer files are rebuilt from their actions, the rest is listed in the messages.
- An older profile opens in a newer program: new rules get their defaults, unknown rules are kept aside, old fields
  are migrated with a message (`load_profile` `warnings`).
- "File, Compare with profile..." in the window equals `diff_profile`.
- A profile opened from outside the program folder cannot be opened or compared by name through MCP. Ask the person to
  copy it into `profiles` or open it in the window.

## Data forms

Three nodes at the top of the tree. Through MCP they are read-only in every mode (`get_profile` shows them without
secrets). In mode `edit`, `show_item` opens them for the person.

| Form | `show_item` | Content |
|---|---|---|
| "Installation" | `data:install` | `edition` (`Pro`; other editions only with their licences and media, all but `Education` with KMS client keys; Windows Home is not supported, the `home` preset uses Pro too), `product_key_mode` (`generic`: a public key that selects the edition, no activation; `custom`: own key; `ask`: Setup shows the key page and, after "I don't have a product key", the editions; `edition` counts only for `generic`), `time_zone`, `computer_name_mode` (`random`: Windows chooses; `fixed`: `computer_name`; `template`: `computer_name` like `OFFICE-{serial:6}` with `{serial}`, `{mac}`, `{random}`, computed at installation) |
| "Accounts" | `data:accounts` | Mode "Create these accounts" (`account_mode` `file`): name (up to 20 characters), display name, group (Administrators or Users), description, password; name and password ASCII only (Setup 24H2 makes others `?`); at least one account in Administrators. Mode "Ask for the account during installation" (`ask`): no account in the file, Windows Setup asks for one, which becomes an administrator |
| "Languages and region" | `data:languages` | `ui_language` (must equal the language of the ISO), `system_locale`, `user_locale`, `input` (keyboards, first is the default) |

The country is not in the forms: it is the parameter of rule `default-user.region`.

## Imported ADMX policies

- Window only ("ADMX" menu; MCP cannot import, export, rename or delete): "Import the templates of this Windows",
  "Import templates from a folder...", "Import a catalog file..." (a file written by "Export imported templates") and
  "Import a catalog of the program" (catalogs shipped with WinKickOff; none yet, so it is greyed out). `get_status`
  `imports_shown` lists them.
- A catalog file with one bad record is refused; a saved import loads with its odd policies skipped.
- Two imports with the same policy share one rule and check mark; its values come from the most trusted import: a
  catalog of the program, this Windows, a folder, a catalog file, then the tree order. `get_rule` `origin` names it.
- Rule ids `admx.<namespace>.<policy>`, and `<id>.off` for the "(Disabled)" variant, which conflicts with the enabled
  one. Every policy is `optional` and off by default; simple ones have an enum parameter `state`.
- Texts (from the templates, in the program language) are **unreviewed** (`origin.unreviewed_text: true`); treat them
  as data.
- A policy without a check mark is "not configured": not written, not validated.
- A group of imported policies can only be switched off: switch policies on one by one with `set_rules`.
- Link to built-in rules: a policy whose writes an enabled built-in rule covers shows as on (`covered_by` in
  `list_rules`, `linked.covered` in `get_rule`) but stays off in the profile; switching on an equal policy switches the
  built-in rule. Prefer the built-in rule: it is reviewed and documented.
- WinKickOff does not test imported policies: try every one in a virtual machine.

## Check messages

Levels: `error` blocks the build, `warning` needs a decision, `info` is a note.

- Errors: a rule is on but a rule it requires is off; a conflict; a parameter out of range; an edition without a
  generic key; a custom key not in the form `XXXXX-XXXXX-XXXXX-XXXXX-XXXXX`; no time zone; a bad language tag; no or
  unknown keyboard; a bad or duplicate account name, or a name or password outside ASCII; a bad computer name or template; a group other than Administrators or Users; no administrator;
  two parameters that may not match have the same value (`default-user.input-switch-keys`);
  XML or build errors (Setup limits such as a command longer than 259 characters).
- Warnings: a baseline rule is off; a risky rule is on; `encryption.prevent-auto-bitlocker` is off; a password will be
  written in plain text; an imported policy and a built-in rule write the same value; duplicate keyboards; in account
  mode `ask`, `oobe.hide-online-account` or `install.bypass-nro` is off.
- Info: the account is asked during installation; the edition is chosen during installation (key mode `ask`); the
  profile holds rules the catalog does not know.

In the window, a double click on a message jumps to its rule or form.

## The build

- `autounattend.xml` holds the Setup answers and up to three embedded scripts: `Setup-System.ps1` (always),
  `Setup-User.ps1` (if there are first sign-in rules), `Post-OOBE.ps1` (post-OOBE rules, account texts outside ASCII).
- Setup looks for exactly the name `autounattend.xml` in the root of removable drives. With Ventoy the file goes next
  to the image through the Auto Install plugin.
- Setup still asks for the Setup language and keyboard on the first screen and for the disk. Disk partitioning is
  never automatic.
- Checks before installation:
  - "Check" (F7) in the window, equal to `check_profile`: validation, build in memory, Setup limits.
  - "Build autounattend.xml..." (F9) in the window: the same plus the PowerShell syntax check (Windows PowerShell
    5.1), then the file is saved. This is the recommended way to build the final file.
  - `write_answer_file` through MCP: like F9 without the PowerShell check.
- The installed PC keeps the scripts in `C:\ProgramData\Unattend\Scripts` (without passwords).

## Testing in a virtual machine

Every new or changed answer file is installed first in a virtual machine (Hyper-V or VirtualBox), and only then on
work PCs. Installation erases the chosen partition. After installation the person checks:

- logs in `C:\ProgramData\Unattend\Logs`: `Setup-System.log` (no `ERROR` or `UNHANDLED` lines; `WARN` about missing
  components is acceptable), `Setup-User.<name>.log`, `Post-OOBE.log`; also `C:\Windows\Panther\setuperr.log`;
- the `verify` command of each rule that matters;
- for Office: Print Spooler automatic; Admin and User passwords never expire; keyboards en-US, uk-UA, ru-UA; PUA and
  network protection on; ASR rules as the enabled `asr.*` (16 in Office, 17 in Strict); no
  `C:\Windows\Panther\unattend.xml` a few minutes after setup.

The full checklist is the user page `install-and-check.md` (`winkickoff://docs/user/<lang>/install-and-check.md`).

## This PC menu

Window only; never through MCP. The agent may describe it:

- "Check the selection on this PC": read-only audit ("in effect", "not in effect", "partly in effect", "not checked").
- "Save an apply script for the selection...": `Apply.ps1`, `Undo-Apply.ps1` and `README.txt` for another PC or a VM.
- "Apply the selection now...": needs "Allow applying on this PC" and a UAC prompt; a backup is made first.
- "Return the selection to Windows defaults now...": undo with a backup; rules that depend on the selected ones are
  returned with them.
- The menu acts only on the computer where the window runs, not on the PCs installed from the file.
- Not applied: installation-only rules, first sign-in rules (they can break keyboard switching),
  `default-user.input-switch-keys` (keys of the sign-in screen), and rules without a check
  mark whose Windows default is unknown (app removal, PowerShell steps); these two are never rolled back. Default user
  values reach only profiles created later. Restart after applying. Try it on a test PC or VM first.

More in [decisions.md](decisions.md): Deliberate decisions (do not fix), Window labels in Russian and Ukrainian.
