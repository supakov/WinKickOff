# 03. Data model

Revision 0.2 of 25.09.2026, updated 30.09.2026 (T18: English catalog, translation files, themes), 04.10.2026
(T23, editor 1.3.0: the catalog in JSON, catalog files) and 05.10.2026 (fixes of the reviews of T23: profiles read
strictly, the provenance of imported choices, the keys and characters of imported policies, the ids of policies that
share one). Every data file is JSON: the rule catalog (groups, rules
and their translations, edited by people and by the generators), profiles, reference data, interface translations,
colour themes and the catalog files of imported templates (section 10). Until editor 1.3.0 the catalog was TOML
(`06-critical-review-v0.1.md`, section 6 and its note on T23).

The catalog lives in `rules/`: `groups.json` (the tree), `NN-<area>.json` (the rules; the loader reads every other
`*.json` of the folder in the order of the file names) and `lang/<code>.json` (the translations). The same rules hold
for all of them:

- Strict reading (`core/jsonfile.py`): a key that appears twice, `null`, `NaN` or `Infinity`, a number too large for
  a float, a lone surrogate escape, nesting deeper than 32 levels, more than 1 000 000 values (counted before the
  text is parsed), a byte order mark or text that is not UTF-8 is an error naming the file (`[NN-<area>.json]` at the
  start of the `CatalogError`). The standard `json` module would keep the last of two equal keys without a word,
  which could hide a second `path` of an action.
- Known fields only (`core/catalog.py`: `GROUP_KEYS`, `RULE_KEYS`, `PARAM_KEYS` and, by parameter type,
  `PARAM_TYPE_KEYS`, `OPTION_KEYS`, the fields of each action type): an unknown key of a group or rule file, a group,
  a rule, a parameter, an enum option or an action is a `CatalogError` that names the field, so a misspelt field is
  an error, not a silently ignored line; so is a key of another parameter type (`min` of an enum). Text fields
  (`title`, `summary`, `risk`, `note`, the string fields of actions and so on) must be strings. A field of a type no
  check foresaw (an object where the action type should be, for example) still gives a `CatalogError` naming the file
  and the rule, never a crash of the loader. A translation file is checked by `i18n.language_file_problem` (known
  keys and fields, strings where texts belong); `tests/test_docs.py` also reports its entries for rules or groups the
  catalog does not have (section 3).
- Canonical layout: two spaces of indent, an object or an array on one line when it fits in 120 columns, CRLF line
  endings, UTF-8 without a byte order mark. `rules/*.json` are pure ASCII (the source is English); the translation
  files hold Cyrillic. `tools/format_catalog.py` rewrites the files that are not canonical (`--check` only lists
  them); `tests/test_catalog_format.py` fails when a file is not canonical, a rule file is not ASCII or a generated
  file is out of date. A change of one rule changes only its own lines, so the diffs of the catalog stay small.
- Generated files: `rules/14-browsers.json` is written by `tools/make_browser_rules.py`, `rules/17-shell.json` by
  `tools/make_shell_rules.py`; change the tables of the tools and run them, never the files.
- Comments: JSON has none. A catalog file may hold `comment`, a list of lines for the people who edit it (the
  leading comment of a former TOML file); a rule may hold `note`, a remark for catalog editors that is shown nowhere
  (the former comments between rules). A translation file has `_comment` for the same purpose.

## 1. Tree groups: `rules/groups.json`

```json
{
  "comment": [
    "Group tree of the interface. Ids with a dot are nested in their parent (parent is required).",
    "order sets the position among siblings. Rules refer to a group with the field group."
  ],
  "groups": [
    {
      "id": "security",
      "title": "Security",
      "order": 60,
      "summary": "UAC, accounts, credential protection, remote access, encryption."
    },
    {"id": "security.lsa", "parent": "security", "title": "Credential protection (LSA, NTLM)", "order": 3}
  ]
}
```

The file is an object with the list `groups` and the optional `comment`; any other key is an error. A group has
`id` and `title` (required), `parent`, `order` (an integer, 0 when absent) and `summary`. A dotted identifier
defines the path; `parent` is required for nested groups. Nodes are ordered by `order`.

## 2. Rule: `rules/NN-<area>.json`

A rule file is an object with the list `rules` and the optional `comment`; the order of the files and of the rules
in them is the application order within a phase. `04-defender.json`, shortened to the first line of its comment and
its third rule:

```json
{
  "comment": ["Microsoft Defender, ASR rules, SmartScreen. Section 3 of the v0.2 machine script."],
  "rules": [
    {
      "id": "defender.pua",
      "group": "defender",
      "phase": "specialize",
      "title": "Block potentially unwanted apps (PUA)",
      "level": "recommended",
      "default": true,
      "requires": ["defender.realtime"],
      "tags": ["defender", "pua", "adware", "bundleware", "miners"],
      "doc": "docs/technical/reference/07-defender.md#defenderpuaprotection",
      "summary": "Defender blocks adware, bundling installers, miners and \"optimizers\" on download and launch.",
      "effect": "Closes the most common infection channel for non-professional users: \"a free program from a website with a Download button\".",
      "risk": "Legitimate utilities flagged as PUA (some remote access tools) require an exclusion.",
      "versions": "Policy since Windows 10 1607; toggle in Settings since 2004.",
      "verify": "Get-MpPreference | Select-Object PUAProtection",
      "rollback": "Delete the PUAProtection value.",
      "actions": [
        {
          "type": "reg",
          "path": "HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows Defender",
          "name": "PUAProtection",
          "kind": "DWord",
          "value": 1,
          "why": "block potentially unwanted apps"
        }
      ]
    }
  ]
}
```

A string longer than the line stays on one line: JSON strings have no line breaks, and the layout never splits
one.

Rule fields:

| Field | Required | Meaning |
|---|---|---|
| id | yes | `group.name`: lowercase Latin letters and digits, words joined by dots or hyphens; unique in the catalog; the prefix `admx.` is reserved for imported policies |
| group | yes | Identifier of the tree group |
| phase | yes | `windowspe`, `specialize-xml`, `specialize`, `default-user`, `user-first-logon`, `post-oobe`, `oobe-xml` |
| title | yes | Title in the tree (English; translations in `rules/lang/<code>.json`) |
| level | yes | `baseline` (disabling gives a warning), `recommended`, `optional`, `risky` (enabling gives a warning) |
| default | yes | State in the Office preset (`true` or `false`) |
| requires | no | Identifiers of rules without which this rule is disabled |
| conflicts | no | Identifiers of rules that are disabled when this one is enabled |
| tags | no | English words for search (a translation file may add words in its language) |
| doc | yes | Link to the reference card |
| summary | yes | One or two sentences |
| effect, risk, versions | effect yes | Text for the description panel |
| verify, rollback | no | Verification command and rollback method |
| note | no | A remark for the people who edit the catalog (a former comment between rules); shown nowhere, not translated |
| params | no | Parameters, an object keyed by the parameter name (below) |
| actions | yes | List of actions, at least one; a rule without actions is a `CatalogError` |

### Parameters

The `params` object of a rule, shown alone:

```json
"params": {
  "seconds": {
    "type": "int",
    "title": "Seconds of inactivity before locking",
    "default": 900,
    "min": 60,
    "max": 599940
  },
  "mode": {
    "type": "enum",
    "title": "Mode",
    "default": 1,
    "values": [{"value": 1, "title": "Block"}, {"value": 2, "title": "Audit"}, {"value": 6, "title": "Warn"}]
  },
  "sites": {"type": "list", "title": "Sites", "default": [], "pairs": true, "required": false},
  "layout": {
    "type": "enum",
    "title": "Switch the keyboard layout of one language",
    "default": "2",
    "values": [
      {"value": "2", "title": "Ctrl+Shift"},
      {"value": "1", "title": "Left Alt+Shift"},
      {"value": "3", "title": "Not assigned"}
    ],
    "differs_from": "language",
    "same_allowed": ["3"]
  }
}
```

Parameter fields (`PARAM_KEYS`; any other key is an error). Beside `type`, `title` and `default`, a parameter takes
only the fields of its type (`PARAM_TYPE_KEYS`): `int` takes `min` and `max`, `enum` takes `values`, `differs_from`
and `same_allowed`, `string` takes `required`, `list` takes `required` and `pairs`, `bool` nothing more; a field of
another type is an error naming it.

| Field | Meaning |
|---|---|
| type | `int`, `enum`, `string`, `bool` or `list` (a list of strings, edited as one item per line) |
| title | Title of the parameter in the description panel (translated in `params` of the language file) |
| default | The default value; required, and for `enum` one of the `values` |
| min, max | Optional range of an `int`, integers |
| values | Options of an `enum`: objects with `value` (a string or an integer, not `true` or `false`) and `title` (when absent, the value is shown) and no other key (`OPTION_KEYS`) |
| pairs | Optional, `list`: every item is `name=value` (the names of a `reg-list` with `"explicit": true`) |
| required | Optional, `string` and `list`: a string may be empty only with `false` (default `true`); a list may be empty unless it is `true` (default `false`) |
| differs_from, same_allowed | Optional, `enum` (catalog 0.6): the parameter may not take the value of the other enum named by `differs_from`, except the values listed in `same_allowed`; the check of the profile reports a clash as an error |

In actions, a parameter is substituted as the string `"{seconds}"`; the generator converts it to the action's type.
Placeholders are filled in only in the fields `value`, `args`, `script` and `command` (`PLACEHOLDER_FIELDS`); a key,
a value name or a file is always literal, and the loader refuses a placeholder there (security fix of 04.10.2026: a
parameter of an imported template could reach a key that PowerShell expanded).
A `list` parameter goes into the `value` of a `reg-list` action or of a `reg` action of kind `MultiString`. The
validator requires every item to be a non-empty line of at most 4096 characters without control characters or
`]]>`; with `pairs` every item has a name before the first `=`, the name is a safe value name (no `"`, backquote,
`$` or typographic quotes) and no name repeats. The built-in catalog has no list parameters yet; imported policy
templates use them (section 8).

### Actions

| type | Fields | Generated |
|---|---|---|
| reg | path, name, kind (DWord, QWord, String, ExpandString, MultiString, Binary), value, why?, default? | `Set-Reg ...` |
| reg-remove | path, name, default? | `Remove-Reg ...` |
| reg-list | path, kind (String, ExpandString), value (list of strings or `"{param}"`), prefix?, explicit?, additive?, default? | `Set-RegList -Path ... -Type ... -Names @(...) -Values @(...) [-Additive]` |
| service | name, start (2, 3, 4), default? | `Set-ServiceStart ...` |
| exe | file, args (list of strings) | `Invoke-Exe ...` |
| feature | name, state (`Enabled`, `Disabled`), default? | runtime wrapper around DISM |
| capability | pattern | runtime wrapper |
| appx | names (list) | runtime wrapper (deprovision + remove) |
| ps | script (a string, or a list of lines for a script of several lines) | text as is |
| xml-pe-command | command, description | `RunSynchronousCommand` in windowsPE |
| xml-specialize-command | command, description | `RunSynchronousCommand` in specialize |
| xml-oobe | element, value | element inside `<OOBE>` |

An action holds the fields of its type and no other (an unknown field is an error naming it). A `ps` script of
several lines is written as a list of lines; the loader joins them with a line break, without a trailing one, and
refuses a line that holds a line break itself. A one-line script stays a string. From `06-network.json`:

```json
{
  "type": "ps",
  "script": [
    "Get-ChildItem 'HKLM:\\SYSTEM\\CurrentControlSet\\Services\\NetBT\\Parameters\\Interfaces' -ErrorAction SilentlyContinue | ForEach-Object {",
    "    Set-Reg -Path $_.PSPath -Name 'NetbiosOptions' -Type DWord -Value 2 -Why 'NetBIOS over TCP/IP off'",
    "}"
  ]
}
```

Registry paths start with `HKLM:\`, `HKCU:\` (phase user-first-logon), `DU:\` (the default profile, phase
default-user) or `HKU:\.DEFAULT\` (catalog 0.6: the profile of the system account, which the sign-in screen uses;
only in the phases specialize and default-user, whose script `Setup-System.ps1` creates the `HKU:` drive). A DU path is
rendered as `($du + '\...')`, a single-quoted literal. The scripts of the phases user-first-logon (`Setup-User.ps1`)
and post-oobe (`Post-OOBE.ps1`) define only `Set-Reg` and `Remove-Reg` (runtime 0.6), so rules of these phases may use
only `reg`, `reg-remove` and `ps` (`PHASE_ACTION_TYPES`); `tests/test_render.py` checks every runtime against that
table. `registry_values()` gives a `HKU:\.DEFAULT` value the scope `signin`, so it never matches a value of HKCU or
of the default profile.

`reg-list` (catalog 0.5) writes a key that holds a list of values, the `list` element of a policy template. The
generator pairs every item with a value name: with `explicit = true` the item is `name=value` (split at the first
`=`, spaces around both parts dropped); with `prefix` the names are the prefix and a number from 1 (`prefix = ""`
gives `1`, `2`, ...); otherwise the data is its own name. Without `additive = true` the runtime function
`Set-RegList` deletes every other value of the key first, as Group Policy does for a list that is not additive,
so an empty list leaves the key without values. `Set-RegList` works through the .NET registry API, which takes
value names literally (an item such as `https://*.example.com` is not a wildcard). The apply script saves every
value of the key it touches before the change, so `Undo-Apply.ps1` restores the list value by value; the audit
calls `Test-RegList`, which reports "differs" when a value is missing, holds other data or, for a list that is
not additive, when the key has other values.

`default` (catalog 0.4) is the state of a clean Windows, used by "Return the selection to Windows defaults"
(`core/apply.py` `plan_revert`): `"absent"` (no such value), a value of
the action's kind, a start type 2-4, `Enabled`/`Disabled`, or `"unknown"` (not returned automatically). Without
the field a value under `SOFTWARE\Policies` returns to "absent" (a missing policy is the Windows default), a
`reg-remove` needs nothing (the removed values do not exist in a clean Windows) and anything else is unknown.
A `reg-list` takes only `"absent"` or `"unknown"`; "absent" (and no field under `SOFTWARE\Policies`) returns the
key to having no values at all.
Write a default only when it is certain for Windows 10 and 11; if it changed between builds, write `"unknown"`.

Backslashes: a JSON string needs every backslash doubled, so the key
`HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender` is written
`"HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows Defender"` in the file (the TOML literal strings in single quotes of
the catalog before 1.3.0 did not need it). The same holds for backslashes in `ps` scripts, commands and arguments. A
single backslash is a JSON syntax error (`\S`) or, worse, another character (`\t` is a tab), so copy registry paths
into the catalog with the backslashes doubled.

Rule identifiers of catalog 0.2 (port of v0.2): one rule per logically separate
setting; the unconditional actions of v0.2 are grouped into rules of the `baseline` level
(for example `uac.baseline`, `lsa.baseline`, `edge.baseline`, `default-user.baseline`).

## 3. Translations: `rules/lang/<code>.json` and interface strings

Since 30.09.2026 the source language is English: the code, the rule catalog (`rules/*.json`) and every
interface string are written in English, and the English text is the key of each translation. Russian and
Ukrainian are translation files like any other language. A language is available when one of its files
exists (`core/i18n.py` `available_languages`), so a user adds a language by adding files, without code:

Rule texts, `rules/lang/<code>.json` (now `ru.json`, `uk.json`):

```json
{
  "_language": "Українська",
  "_comment": [
    "Ukrainian texts of the rule catalog (rules/NN-*.json). Key: the rule id; _groups: group titles and summaries."
  ],
  "oobe.protect-your-pc": {
    "title": "Екран параметрів конфіденційності: вимкнути експрес-параметри",
    "summary": "...",
    "tags": ["конфіденційність"],
    "params": {"mode": "Режим"},
    "values": {"mode": {"3": "Вимкнути всі експрес-параметри", "1": "Увімкнути експрес-параметри (надсилання даних)"}}
  },
  "_groups": {"defender": {"title": "Microsoft Defender і SmartScreen", "summary": "..."}}
}
```

The file is one object. `_language` is the native name of the language, used when there is no strings file;
`_comment` is an optional list of lines for translators; `_groups` maps a group id to its translated `title` and
`summary`. Every other key is a rule identifier with an object of translated fields: `title`, `summary`, `effect`,
`risk`, `versions`, `verify`, `rollback`, `tags` (extra search words in this language, optional), `params` (parameter
name to title) and `values` (parameter name to an object of option value, written as a string, to option title).
The file is read strictly like the rest of the catalog (`core/jsonfile.py`), and its shape is checked
(`i18n.language_file_problem`): the keys are `_language` (a string), `_comment` (a list of strings), `_groups` (group
entries with only the strings `title` and `summary`) and rule ids; any other key starting with `_` is an error, and a
rule entry is an object with only the fields above (texts as strings, `params` an object of strings, `values` an
object of objects of strings, `tags` a list of strings). A file that fails is not used: the window and the MCP server
log a warning and show the English source (`i18n.set_language`, `ToolRegistry.texts`), so a broken translation never
stops the program. Search looks at the English source and at the translated title, summary and tags of the current
language.

Interface strings, `resources/strings.<code>.json`: `{"_language": "<native name>", "<English text>":
"<translation>"}` (gettext style). A strings file that is not a JSON object is refused (`i18n.load_strings`), and the
interface stays English, as with a broken catalog translation. Code marks texts with `tr("...")`; templates use
positional fields, `tr("Profile \"{0}\" opened", name)`. Texts stored before the language is known (module-level
constants) are marked with `N_("...")` and translated with `tr()` where shown.

Anything missing (a file, a rule, a field, a string) falls back to English. `tests/test_i18n.py` requires a
Russian and a Ukrainian translation for every marked text, the same placeholders and line breaks, no stale
entries and no Cyrillic in the source strings; `tests/test_docs.py` requires complete catalog translations;
`tests/test_sources.py` requires English code, comments and catalog. The language is chosen in the menu
(`""` follows the Windows interface language) and stored in `settings.json`; the window is rebuilt with the
open profile, including unsaved changes.

### Colour themes: `resources/themes/<id>.json`

```json
{ "name": "Dark", "base": "clam", "dark": true, "font": "",
  "colors": { "background": "#202020", "foreground": "#e6e6e6", "field": "#2b2b2b", "select": "#264f78", ... } }
```

`base` is the ttk theme (`native` keeps the Windows look and only recolours texts, `clam` takes every colour),
`dark` gives the window a dark title bar, `font` optionally replaces the font family. Missing colours come
from the built-in light palette (`core/themes.py` `LIGHT_COLORS`), bad values are ignored with a log line, a
broken file is skipped. Bundled: `light` (the previous look), `dark`, `latte`, `matrix`. The setting `theme` in
`settings.json`: `""` follows Windows (read-only `AppsUseLightTheme`), otherwise a theme id. The window is
rebuilt on a change, like for the language.

Windows paints its own menu bar in system colours only, so a theme with `base = "clam"` gets a row of menu
buttons in the theme colours instead (access letters underlined while Alt is held, Alt + letter and F10 open
the menus); the drop-down menus are drawn by Tk in the theme colours, and `ui/winmenus.py` repaints the 2 px
margin Windows leaves around them (a WinEvent hook of this thread, `SetMenuInfo` `MIM_BACKGROUND`). Nothing
outside the program changes; `tests/test_sources.py` forbids system-wide calls such as `SetSysColors`.
On Windows 11 a coloured theme also paints the title bar, its text and the window border of this window
(DwmSetWindowAttribute 35, 36, 34): the optional colours `title_bar` and `title_text` default to
`background` and `foreground`, the border takes `border`. A dark theme additionally turns on the dark mode of
the frame (attribute 20), which older builds understand.

## 4. Profile: `profiles/<name>.json`

```json
{
  "format_version": 3,
  "catalog_version": "0.6",
  "name": "Office",
  "author": "",
  "created": "2026-09-25T10:00:00",
  "modified": "2026-09-25T10:00:00",
  "comment": "",
  "install": { "edition": "Pro", "product_key_mode": "generic", "product_key": "", "time_zone": "FLE Standard Time",
               "account_mode": "file" },
  "languages": { "ui_language": "uk-UA", "system_locale": "uk-UA", "user_locale": "uk-UA", "input": ["en-US", "uk-UA", "ru-UA"] },
  "accounts": [
    { "name": "Admin", "display_name": "Admin", "group": "Administrators", "description": "Local administrator (starter account)", "password": "" },
    { "name": "User",  "display_name": "User",  "group": "Users", "description": "Standard user (starter account)", "password": "" }
  ],
  "rules": {
    "defender.pua": { "enabled": true },
    "accounts.inactivity-lock": { "enabled": true, "params": { "seconds": 900 } },
    "network.netbios-off": { "enabled": false },
    "admx.microsoft.policies.terminalserver.ts-disable-connections": { "enabled": true, "source": "system" }
  },
  "unknown": {}
}
```

- `install.product_key_mode`: `generic` (the generic key of `edition`), `custom` (`product_key`) or `ask` (Setup shows
  the product key page and the list of editions; `edition` is ignored). `install.account_mode` (format 3): `file`
  writes `accounts` into `UserAccounts/LocalAccounts`; `ask` writes no account, so Windows Setup asks for the name of
  one administrator account, and `accounts` stays in the profile for the way back (`Profile.answer_file_accounts()`).
  Format 2 profiles have no `account_mode` and load without a warning as `file`; a profile of a newer format warns.
- `rules` lists all rules of the catalog (completeness is needed for comparing profiles and so
  that a new catalog rule is noticeable on load), except imported policies (`admx.*`, section 8): only those that
  are on or have parameters are written, an absent one is "not configured" and is not reported as new.
- `params` is present only for rules with parameters; a missing parameter = the default value.
- `source` (1.3.0) is written only in the entry of an imported policy: the most trusted kind of import the choice has
  been in effect in, `bundled`, `system`, `folder` or `package` (`catalog.IMPORT_KINDS`, most trusted first, as in the
  trust order of section 8; `RuleState.source`). A new choice takes the kind of the import that holds the policy
  (`RuleOrigin.kind`). `Profile.from_dict` and `Profile.to_dict(catalog)` keep the more trusted of the saved kind and
  the kind of the import that holds the policy now: a choice made in a catalog file and then used with the templates
  of this Windows (which took the policy over by the trust order) is saved as `system`, because it was in effect with
  the values of this Windows. When the policy now comes from a less trusted kind than `source` (only a catalog file
  with the same policy is shown now), `from_dict` holds the choice: the entry is kept unchanged in `unknown`, the
  policy is off, and one warning lists such policies. The entry comes back from `unknown` when an import of that kind
  or a more trusted one is shown again; choosing the policy again in its branch makes a new choice with the kind of the
  import that holds it, and the held entry gives way to it the next time the profile is read. So a catalog file
  received from elsewhere, whose policy of the same id may write other values, never takes over without a word a
  choice made for a more trusted source. An entry without `source`, or with a kind that is not one of the four, counts
  as `folder` (`profile.LEGACY_SOURCE`): an entry without it was saved before 1.3, when catalog files did not exist, so
  the choice was made in the templates of this Windows or of a folder. Such a choice is held, with the warning, when
  only a catalog file holds the policy, and used as before when a folder of templates, the templates of this Windows
  or a catalog of the program holds it. Older versions ignore the field, so the profile format stays 3.
- Rules from an old profile that are not in the catalog are moved to `unknown` and are not lost; when such a
  rule is in the catalog again (templates loaded again), its state comes back from `unknown`. Until then they are
  not built, validated or applied; the window lists them under the last root of the tree,
  "Unknown rules and policies" (`Profile.unknown_entries()`), which exists only while `unknown` is not empty. The
  choices held back by their `source` (above) wait there too.
- Wrong shapes (1.3.0): a profile may come from someone else. `Profile.load` reads the file strictly through
  `core/jsonfile.py`: at most 16 MB as stored and as text (`PROFILE_MAX_BYTES`); a key twice, `NaN`, `Infinity`, a lone
  surrogate escape, a byte order mark, nesting deeper than 32 levels and more than 1 000 000 values are errors, while
  `null` is allowed, because files of older versions may hold it. The embedded profile of an answer file is read the
  same way (section 6). Before 05.10.2026 both used the standard `json` module, which keeps the last of two equal keys
  and lets a deep nesting reach the code as a `RecursionError`. `Profile.from_dict` checks the depth of an object
  given to it directly (`jsonfile.check_depth`) and raises only `ValueError`: for a profile that is not a JSON object,
  for nesting deeper than 32 levels and for any `TypeError`, `AttributeError`, `KeyError` or `RecursionError` while it
  is read; the window and the MCP server report such a file instead of failing. A field of a wrong type falls back to
  its default: `format_version` that is not an integer (then the warning about the format), `install` or `languages`
  that is not an object, a value in them that is not a string (`languages.input` must be a list of strings; a
  warning names the field, and `"install": 5` no longer refuses the profile), a rule entry that is not an object,
  `enabled` that is not true or false (0 and 1 are taken as false and true, as 1.2 did; any other value gives the
  default of the rule with a warning), `params` that is not an object, and a parameter value of the wrong JSON type
  (`profile._fits`: a list of strings for `list`, true or false for `bool`, an integer for `int`, a string for
  `string`, a string or an integer for `enum`). A boolean saved for an enum (the MCP server of 1.2 accepted `true`
  and `false` there, since `True == 1` in Python) becomes the option it equals, 0 or 1 (`profile._as_option`),
  instead of being dropped; the MCP tool `set_param` of 1.3 refuses a boolean for an enum. Accounts that are not
  objects are skipped. A warning names a rule entry or a parameter value of the wrong type and the skipped accounts.
  Whether a value of the right type is allowed (a range, an option) is still told by the check of the profile.
- `name` and `author` stay on one line (`profile.one_line`): control characters, the C1 controls and the line and
  paragraph separators U+2028 and U+2029 become spaces, so a name cannot leave a comment line of a generated script.
  `comment` may have several lines.
- Passwords are in plain text; profiles with a password are marked in the recent list.

## 5. Reference data

- `resources/keyboards.json`: `{ "tag": "uk-UA", "lcid": "0422", "klid": "00020422", "title": "Українська (розширена)", "transient": false }`;
  for `ru-UA`: `"lcid": null, "transient": true, "fallback": "ru"`.
- `resources/timezones.json`: `{ "id": "FLE Standard Time", "title": "(UTC+02:00) Киев", "recommended": true }`.
- Languages with `transient: true` do not go into `InputLocale` (their `fallback` is used instead), but they do go into
  the list for the first sign-in script (rule `languages.user-input-list`).

## 6. Embedded profile in XML

The generator adds to `Extensions` the element `<Profile format="json"><![CDATA[ ... ]]></Profile>` with
the same JSON that is saved to the file. Import from XML reads it strictly with `jsonfile.loads` (`null` allowed, the
limits of depth and values of section 4), so an answer file from someone else cannot hide a second key or nest the
profile deep enough to crash the import; text that is not strict JSON, or a profile that `Profile.from_dict` refuses,
is reported as `ImportFailed` ("the embedded profile is corrupted: ..."), and a value that is not an object as
`ImportFailed` ("the embedded profile must be a JSON object"). If the element is absent (a v0.2 file or a
third-party one), the import parses the actions from the scripts and matches them against the catalog by type, path and name
(the same code as the semantic golden), and shows whatever is unmatched as a list.

## 7. Versioning

- Profile `format_version`: 3 (in 0.1 it was 1; migration: `config.*` → rule states via a mapping table; format 3 of
  catalog 0.6 adds `install.account_mode`, and a format 2 profile loads as `file` without a warning).
- `catalog_version` = the contents of `templates/VERSION`; if they differ, the profile is loaded with
  a warning and completed.
- The application version is independent.
- Catalog 0.3 (25.09.2026): the country moved from `languages.geo_id` to the parameters `geo_id` and `geo_name`
  of the rule `default-user.region`; the field `install.iso_language` was removed (the display language always equals the ISO
  language); the block marker in scripts `# [<rule.id>]` has no title. When an old profile is loaded, `geo_id`
  is moved into the rule parameter with a warning, and `iso_language` is dropped with a warning.
- Catalog 0.4 (26.09.2026): the optional action field `default`, the rule `apps.remove.onedrive`, new defaults
  (browser policies, `update.other-microsoft-products`, `asr.usb-untrusted`, `uac.admin-always-notify`). Profiles
  of 0.3 load with a warning; their saved rule states are kept, new rules get the defaults (one message).
- Editor 1.1.0 (30.09.2026, T19): imported policy templates (section 8); the catalog and profile formats did not
  change, the prefix `admx.` of rule and group ids is reserved for them.
- Catalog 0.5 (30.09.2026, editor 1.1.0-rc.2): the parameter type `list`, the action `reg-list` and the runtime
  functions `Open-RegKey`, `Set-RegList` (Setup-System, Apply) and `Test-RegList` (Audit); `Set-Reg` accepts an
  empty MultiString. The built-in rules did not change: profiles of 0.4 load with the usual warning about the
  catalog version and give the same rule blocks; only the runtime part of `Setup-System.ps1` gained the new
  functions.
- Catalog 0.6 (04.10.2026, customer requests of that day): the File Explorer namespaces and desktop icons
  (`17-shell.json`, generated by `tools/make_shell_rules.py`), the rule `default-user.input-switch-keys` with the
  parameter fields `differs_from` and `same_allowed`, the prefix `HKU:\.DEFAULT\` (the sign-in screen) in the phases
  specialize and default-user, and the runtime functions `Set-Reg` and `Remove-Reg` in `Setup-User.ps1` and
  `Post-OOBE.ps1`. Profiles of 0.5 load with the usual warning; the new rules get their defaults (all off).
- Editor 1.3.0 (04.10.2026, T23): the catalog files are JSON (`rules/groups.json`, `rules/NN-<area>.json`,
  `rules/lang/<code>.json`, sections 1-3) instead of TOML, read strictly with known fields only. The conversion
  changed nothing in the result: the four presets and a profile with every rule on build byte-identical answer files
  and scripts, and the catalog objects and translations are equal (nine scripts of several lines lost a trailing line
  break, which the build drops anyway). The catalog version stays 0.6 (`templates/VERSION` unchanged) and the profile
  format stays 3, so profiles load as before. New: catalog files of imported templates (section 10), the check of
  saved imports on load and the trust order of imports (section 8), the field `source` of the entries of imported
  policies (an entry without it counts as `folder`), the strict reading of profiles and the tolerance of wrong shapes
  (section 4); older versions ignore `source`.

## 8. Imported policy templates (ADMX, ADML): `admx/<id>/`

`core/admx.py` reads every `*.admx` of a folder (the ADMX menu: `%SystemRoot%\PolicyDefinitions` or a chosen
folder) and the ADML files of the cultures that match the languages of the program (`en-US` always first). The
result is kept next to the settings, in the writable program folder:

- `admx/<id>/import.json`: `{format, id, name, renamed, folder, created, windows, cultures, policies, skipped,
  files}`. The first word of the id names the source: `system-YYYYMMDD-HHMMSS` for the templates of this Windows,
  `folder-YYYYMMDD-HHMMSS` for a chosen folder, and since 1.3.0 `package-YYYYMMDD-HHMMSS` for a catalog file and
  `bundled-<file name in lowercase words>` for a catalog of the program (section 10); a dated id already taken
  gets `-2`, `-3`. The name is at most 120 characters (`admx.MAX_NAME`); it is generated for templates
  ("PolicyDefinitions 10.0.26200, 2026-09-30 13:05"; for a chosen folder the folder name and the date, a long folder
  name cut with "..." so that the date stays) and taken from the package for a catalog; `created` is the time of the
  import (or of its last update); `folder` is the folder of
  the templates, the path of the catalog file, or only the file name of a catalog of the program. Format 2
  (1.1.0-rc.2) adds list and multiText elements; imports of format 1 still load, and the description of their branch
  counts the policies with lists that 1.1.0-rc.1 skipped (import the templates again to get them); a newer format
  is not loaded.
- `admx/<id>/policies.json`: the policies as records: file, namespace, name, class, category, the texts of every
  kept culture (title, explain, supported), the writes of the Enabled and Disabled states (`{key, name, kind,
  value}`, kind `delete` for a removal) and the elements (`{param, type, key, name, kind, default, min, max,
  values, label, id, required}`, `id` being the id of the element in the template; a list element has
  `element: "list"`, no name and `explicit`, `additive` and, for valuePrefix, `prefix`; a multiText element has
  `element: "multiText"`, type `list` and kind `MultiString`);
  categories with their parents; skipped policies with a reason code. The same records travel in a catalog file
  (section 10).
- `settings.json` `admx`: the imports shown in the tree, in the order of the trees; they are merged into the catalog
  at start (`with_imports`, `catalog.merge`) in the interface language, so every text of the subtree comes from ADML.

Saved imports are checked on load (1.3.0): the program folder is writable, so the files may have been changed after
the import. Both are read with `core/jsonfile.py` like a catalog file: `import.json` strictly, at most 64 KB, and every
field must have its type (`admx._info`: an id of lowercase words, a known format, texts, counts that are integers,
`renamed` true or false), and its `id` must be the name of its folder: the kind of an import (and so its place in the
trust order) and the ids of its groups come from the folder, never from a file in it, so `load_import` refuses an
`import.json` that names another import and `list_imports` leaves such a folder out. `policies.json` is read with
`null` allowed, at most 64 MB, then brought into shape by `admx.conform` (below), which checks each policy once with
the check a catalog file gets (section 10) and moves a policy it refuses to the skipped policies; after it,
`admx.check_templates(data, policies=False)` checks only the sections (the records, the categories, the skipped
policies and the problems), without checking each policy a second time.
`store_import` checks the records before it writes, and encodes both files before it creates the folder, so a failed
import leaves no folder behind. A saved import that fails is not loaded: `list_imports` leaves out (and logs) an import
whose `import.json` cannot be read, and `with_imports` never raises: reading and converting each import
(`load_import` and `catalog_part`) share one `try`. It returns each failure as a message, which the window shows at
start ("Imported templates {0} were not loaded: {1}") and the headless MCP server logs; the program starts without
that import, and the profile keeps its policies in `unknown`.

Records of the parser and of older imports (`admx.conform`, 1.3.0): the function brings the records into the shape
`check_templates` accepts, in place. `read_templates` calls it on what the template parser made, and `load_import`
calls it before the check, because an import saved by an older version was made without some of the checks. A
catalog file is never conformed: one record that fails the check is enough to refuse the file (section 10).
`conform`:

- drops keys of the records it does not know and gives `format`, `cultures` and `files` of a wrong type their
  defaults; keeps only the cultures that match the culture pattern (2 or 3 letters and at most 4 subtags of 1-8
  letters or digits, at most 32 cultures); `adml_cultures` of the parser takes only folders whose names match it, so
  a copy `en-US - Copy` next to `en-US` is not read;
- replaces control characters in texts with spaces (DEL included, which XML allows), drops the keys of texts by
  culture that are not culture names, and cuts texts to their limits;
- cuts chains of categories: a category whose chain of parents is longer than `MAX_CATEGORY_DEPTH` (32) or closes a
  cycle loses its parent and becomes a category at the top of its side;
- reduces the quoted paths of this computer in the problems to file names (`without_paths`:
  `'C:\...\ru-RU\wktest.adml'` becomes `'wktest.adml'`), since the problems travel in an exported catalog file. A path
  is a text in single or double quotes that starts with a drive letter and a colon or with two slashes or backslashes
  (a UNC path), up to the closing quote of the same kind; the pattern has no nested repetition and runs in linear
  time, and each problem is cut to 4096 characters before it runs. An earlier pattern backtracked quadratically on a
  quote that never closes, so a saved import with long problems could hang the start;
- moves every policy the check would refuse to the skipped policies, with the reason `unsafe` when the check named an
  unsafe character and `broken` otherwise: a class in another case (`machine`), an empty name, a check box whose
  checked and cleared values are equal, a key that is only backslashes or has a `..` segment, `]]>` in a name, a C1
  control character in a value. Before, one such policy refused the whole import; now the other policies load, and
  the summary counts the skipped one.

It returns the number of policies it moved. The description of an imported tree counts its policies and skipped
policies from the records, so a policy that an older version kept and this one skips is counted as skipped.

Conversion of a policy (`policy_rules`):

| Policy | Rules |
|---|---|
| one value, Enabled and Disabled of the same kind | one rule, enum parameter `state` (Enabled or Disabled value) |
| elements or value lists | rule of the Enabled state, elements as parameters (`decimal` int with min and max, `longDecimal` QWord, `text` string or ExpandString, `boolean` bool or a two-value enum, `enum` enum, `multiText` a `list` parameter written as one MultiString value, `required` means not empty) |
| `list` element | a `list` parameter (empty by default, `pairs` for explicitValue) and a `reg-list` action on the key of the element or of the policy: String or ExpandString (`expandable`), names from `valuePrefix` (an empty prefix gives 1, 2, ...), from the items for `explicitValue`, otherwise the data; `additive` keeps the other values of the key. The list actions come first in the rule, so a list that is not additive cannot delete a value the same policy writes into its key |
| the Disabled state writes values | plus the rule `<id>.off`, the two rules conflict; its list actions are empty and not additive, so the keys of the lists keep no values |
| value lists inside an option or a check box, values over the signed DWORD range, unsafe characters (also in the key or the prefix of a list) | skipped with a reason |

A fixed string value of a template (a String value of the Enabled or the Disabled state, also of an item of
`enabledList` or `disabledList`) becomes a `reg` action marked `"literal": true` (`admx._action`).
`render.substitute_fields`, which every user of action fields calls (the build, This PC, the importer, the links of
`core/linked.py`), takes such an action as it is and drops the mark, so braces in the value are text:
`https://example.com/{id}` is written as it stands, never filled in from a parameter of the same policy and never
refused as an unknown placeholder. Only the rules made from imports carry the mark; in `rules/*.json` it would be an
unknown action field. "Check" (F7), "Build autounattend.xml" (F9) and the MCP tools that build (`check_profile`,
`preview_build` and `write_answer_file`, through `mcp/workspace.check_and_build` or, for `write_answer_file` with a
window, the checks of the window) report a `KeyError`, `ValueError` or `TypeError` of the build as a build issue,
never as an internal error.

Ids: rule `admx.<namespace>.<policy>` in lower case (other characters become `-`), so a profile keeps its choice
across imports of the same templates. Policies that give the same id (names that differ only in case, or in
characters that become `-`) are numbered `<id>`, `<id>-2`, `<id>-3` in the order of their English titles in lower
case (`pick(title, "en")`, the name when a policy has no title), then of their position in the records
(`admx._rule_ids`). That is the order 1.2 numbered them in for an English interface, so the ids an English user saved
stay the same; 1.2 took the titles of the interface language, so two policies with one id could swap their ids when
the language changed, and now the ids are the same in every language (the templates of Windows have no two policies
with one id, so their ids never changed). Every id reserves its `<id>.off`, so an id is never the `<id>.off` of
another policy's Disabled rule: of a policy `<policy>` and a policy named `off` in the namespace
`<namespace>.<policy>`, the one later in that order is numbered. A counter per base id keeps the numbering linear in
the number of policies. Groups: `admx.<import id>`, `.machine` or `.user`, `.c<n>` per
category, `.none` without a category; `catalog_part` walks the chain of parents of each category once (`group_for`
remembers the group of every side and category) and at most `MAX_CATEGORY_DEPTH` levels. Machine and Both policies
write `HKLM:\` in phase `specialize`, User policies `DU:\` in phase `default-user`. Level `optional`, default off, no
`doc`; `Catalog.origins` holds the source (import, file, policy; `RuleOrigin.kind` is the first word of the import id),
`Catalog.same_values()` the rules of the other kind that write the same (scope, key, value name); a list meets every
value of its key, so a list policy that clears a key links to the built-in rules writing into it.

Several imports (T20): a policy is one rule; the other imports that hold it show it too, as an alias
(`Catalog.aliases`: rule id to more groups, `placements()`), so it has one check mark and one set of parameters
everywhere. The tree gives an alias its own item id `r:<rule id>@<group id>` (`main_window.rule_of()` reads the rule
id); group counts and group actions include the aliases. A rule of one import never replaces a rule of another
(`catalog_part`): when the id of a policy is free but its Disabled rule `<id>.off` is already a rule, because an import
made into rules before it (a more trusted one, or one of the same kind shown higher) has a policy named `Off` in the
namespace `<namespace>.<policy>`, the policy is left out of this import's tree and the log names it. Before, the
Disabled rule of a catalog file could replace the policy of the templates of this Windows that had that id.

Trust order (1.3.0, `admx.trust_order`, `IMPORT_KINDS`): when two imports hold the same policy (the same rule id
`admx.<namespace>.<policy>`), the rule and its registry values come from the most trusted source: the catalogs of
the program (`bundled`), then the templates of this Windows (`system`), then a folder of templates (`folder`), then a
catalog file (`package`); within one kind, in the order of `settings.admx`. So a catalog file received from
elsewhere cannot change what a policy of the templates of this Windows writes. The trees keep their order
(`settings.admx`); only the owner of a shared policy follows the trust order. Before 1.3.0 the import loaded first
won.

An import of a folder that is already imported asks whether to update that import in place (same id,
`save_import(replace=...)`, files written through a temporary file) or to add a tree; a catalog file imported again
asks the same (`package.find_package_imports`), and a catalog of the program imported again always updates its
import `bundled-<name>`. `import.json` may hold `renamed: true`: the name was given by the user (`rename_import`,
`check_name`: at most 120 characters, no control characters) and survives an update; a generated name follows the
date of the update.

Built-in rules and imported policies (T21, `core/linked.py`): an imported policy is linked to a built-in rule
when everything it writes (`registry_writes`: registry values only), with its current parameters or with one value
of its first enum or bool parameter, is also written by the rule (`equal` when the sets are the same). While the
rule is on, the policy is covered: the window shows it checked with the tag `linked`, counts it in its groups and
shows a note instead of its parameters; the profile keeps it off, so the build and This PC write the value once.
Toggling a covered policy switches the rule off (a question first when not equal); toggling an equal policy that
is off switches the rule on. After every toggle, enabled policies whose writes an enabled rule already covers are
switched off (`redundant`, change reason `covered by <rule>`).

Behaviour that differs from built-in rules: an imported policy without a check mark is "not configured" (not
written to the profile, not validated, not reverted by "Apply the selection now"); "Return to Windows defaults"
takes it only when it is selected itself; the check box of an imported group only switches off; the validator
warns when an imported policy and a built-in rule with the same value are both on.

Policies of templates that are not loaded: a profile keeps them in `unknown` (section 4), and the window shows them
under the root "Unknown rules and policies" (tree items `unknown` and `u:<rule id>`; image on or off, tag `off`,
no toggling, found by search in their ids). The description of such an item names the saved imports, hidden now,
that have the policy: `admx.policy_ids()` gives the ids an import's policies get (the same code as `catalog_part`),
`has_policy()` also accepts `<id>.off`; the window reads each hidden import once and caches the ids, since every
change of the imports rebuilds it. A button "Show ..." shows that import (`show_templates` with the policy as the
item to open), and when no saved import has the policy the buttons "Import the templates of this Windows", "Import
templates from a folder..." and "Import a catalog file..." (1.3.0) of the ADMX menu import new ones.

The same root lists the choices held by their `source` (section 4): the policy is loaded, but only from a less trusted
kind of import. Such an item has the status "held: a less trusted source holds the policy now", and its description
(`UNKNOWN_HELD`) names the kind the choice was made with and the kind that holds the policy now
(`main_window.KIND_TITLES`: "a catalog of the program", "the templates of this Windows", "templates from a folder", "a
catalog file"; `_held_source` takes an entry without a known `source` as `folder`, as the profile does) and says how
to use it: show templates of that kind again, or choose the policy again in its branch to use it from the source that
holds it now. "Show ..." is offered only for hidden imports of the kind of the choice or a more trusted one, since
only they bring it back. After
a restart of the window (a tree shown or hidden, a catalog file imported, the language or the theme changed) the
profile is bound to the new catalog (`Profile.rebind`); its warnings are logged, and the warning about held choices
is also shown in the message list (`app.create_app`), so the person sees why a policy left the build.

Untrusted input: documents with a DTD or entities are refused (the parser does not resolve entities anyway), a
file is at most 16 MB and a folder at most 3000 templates, files are decoded by their BOM; keys and value names
with control characters, `"`, backquote, `$`, typographic quotes or `]]>` (`safe_name`; `]]>` since 1.3.0) and
strings with control characters, typographic quotes or `]]>` (`safe_value`) skip the policy, because keys, names and
values end up in single-quoted PowerShell strings and the scripts are CDATA sections (the DU path has been a
single-quoted literal since the security fix of 04.10.2026; before, it was a double-quoted string that PowerShell
expanded). The control characters are those of C0, DEL and, since 05.10.2026, the C1 controls 0x80-0x9F; the
non-characters U+FFFE and U+FFFF are unsafe too, because an XML document cannot hold them and the answer file would
not load. A key is also refused when a segment between its backslashes or slashes is empty, `.` or `..`
(`admx.safe_key`): PowerShell resolves `..` even with `-LiteralPath`, so a user policy with the key
`..\.DEFAULT\Control Panel` would write into the profile of the sign-in screen instead of the default user profile.
`ps_quote` doubles the typographic single quotes as well. Anything else the check of the records would refuse skips
the policy too (`conform`, above).

## 9. MCP server: settings and the shapes of the tool results

`settings.json` (editor 1.2, T22): `mcp_port` (integer, default 47831, 0 means any free port; validated by
`valid_port`), `mcp_token` (32 to 64 characters of `A-Za-z0-9_-`, generated by the window at the first start of the
server; an invalid value becomes empty and a new token is generated), `mcp_autostart` (boolean, default false; the
server then starts in the `read` mode). The mode of the server is never stored. The window's `Settings` object is the
only writer of the file: the service saves the token through `window.save_settings`, and a headless process
(`--mcp stdio`, `--mcp http`) never writes settings.

Tool results are JSON objects returned in `structuredContent` and as text; their shapes, the redaction rules
(passwords become `has_password`, the product key `has_product_key`, free texts get the suffix `_text`), the file
name rule of `check_name` and the resource URIs are described in `07-mcp-server.md`. The stored files of the MCP
server are only those it creates on request in `files` mode: `profiles/<name>.json` and `output/<name>.xml`, never
replacing an existing file. Headless processes log into `logs/mcp-<transport>-<pid>.log`.

## 10. Catalog files (packages)

`core/package.py` (T23, editor 1.3.0). A catalog file carries the records of imported policy templates in one JSON
file: "Export imported templates" writes one, "Import a catalog file..." reads one, and the catalogs that ship with
the program have the same form. The built-in catalog of `rules/` is not a package; it stays separate JSON files
(sections 1-3).

### Envelope

```json
{
  "format": "winkickoff-catalog",
  "version": 1,
  "kind": "admx",
  "name": "Windows 11 25H2 (26200)",
  "windows": "10.0.26200",
  "created": "2026-10-04T12:00:00",
  "comment": [
    "Policy templates of Windows 11 25H2 (26200): 224 ADMX files, cultures en-US, ru-RU, uk-UA.",
    "Made by tools/make_admx_catalogs.py; edit the templates, not this file."
  ],
  "templates": {
    "format": 2,
    "cultures": ["en-US", "ru-RU", "uk-UA"],
    "files": 224,
    "categories": {},
    "policies": [],
    "skipped": [],
    "problems": []
  }
}
```

The example has no policies; a real package holds the records of section 8 in `templates`. The comment is what
`tools/make_admx_catalogs.py` writes; an import does not keep it, and "Export imported templates" writes none.

| Field | Meaning |
|---|---|
| format | `"winkickoff-catalog"`; any other value means "not a WinKickOff catalog file" |
| version | `1`; another version is refused |
| kind | `"admx"`, the only kind so far |
| name | The name of the tree (`admx.check_name`: spaces collapsed, 1-120 characters, no control characters); an export cuts a longer name kept by an older version to 120 characters with "..." (`admx.fit_name`) |
| windows | The Windows version of the templates, a digit and then digits and dots, at most 32 characters (`package.WINDOWS_RE`); may be empty |
| created | Date and time of creation, ISO 8601 (at most 40 characters of digits, `T`, `:`, `.`, `+`, `-` and spaces) |
| comment | Optional: at most 100 lines of at most 1000 characters, for the people who read the file |
| templates | The records exactly as `admx/<id>/policies.json` (section 8): `format`, `cultures`, `files`, `categories`, `policies`, `skipped`, `problems` |

Any other key of the envelope is an error.

### File names, compression and limits

- A catalog file is called `*.json`, `*.json.gz` or `*.json.xz` (`jsonfile.SUFFIXES`). The compression is recognised
  by the first bytes, not by the name: gzip (`1f 8b`) and xz (`fd 37 7a 58 5a 00`); anything else is read as plain
  JSON. One stream only: a stream that is cut off, or any data after its end, is an error.
- Limits: 64 MB as stored and 64 MB unpacked (`MAX_PACKAGE_FILE`, `MAX_PACKAGE_JSON`; all the templates of
  Windows 11 take about 13 MB), at most 1 000 000 JSON values (`jsonfile.MAX_ITEMS`, counted from the commas and
  opening brackets before the text is parsed, an upper bound that also counts the commas inside strings; the same
  templates hold about 140 000 values and count about 190 000), and at most 128 MB of memory for the xz decoder
  (`jsonfile.MAX_XZ_MEMORY`; the presets up to 9 need 65 MB). Unpacking stops at the limit, so a small file never
  expands into gigabytes of text or of Python objects; a lack of memory is reported as an error of the file.
- The JSON is read strictly like the catalog files (a key twice, `NaN`, `Infinity`, a number too large for a float, a
  lone surrogate escape such as `\ud800`, nesting deeper than 32 levels, a byte order mark are errors) with one
  exception: `null` is allowed in a package, because the records use it for the value of a `delete` write and for the
  texts of the two states of a check box that has its own values. `admx.check_templates` decides where a `null` may
  stand. Messages quote at most 60 characters of the file.
- The writer (`jsonfile.dumps`, used by the export, the catalog tools and `jsonfile.write`) refuses what the reader
  would not give back: a key that is not a string at any level of nesting (inside lists too), a number that is not
  finite and nesting deeper than 32 levels.

### Checks of the records

`admx.check_templates` checks every record of a package and of every saved import (section 8) against what the
template parser writes. The first defect names the policy and the field and refuses the whole file; in a saved import
`conform` has moved a refused policy to the skipped policies first (below):

- known fields only: of the records, the policies, the elements (by element kind), the writes, the categories and
  the skipped entries;
- registry keys and value names are safe (`admx.safe_name`): not empty, no control characters (C0, DEL and the C1
  controls 0x80-0x9F), no U+FFFE or U+FFFF, `$`, backquote, double quotes, typographic quotes or `]]>`, at most 512
  characters; a key has no backslash at either end and (`admx.safe_key`) no segment between backslashes or slashes
  that is empty, `.` or `..`, so a key of backslashes only is refused (section 8, untrusted input);
- strings are safe (`admx.safe_value`): no control characters (C0, DEL, C1), no U+FFFE or U+FFFF, typographic quotes
  or `]]>`, at most 4096 characters;
- write kinds `DWord`, `QWord`, `String` and `delete` (with the value `null`); `DWord` values 0-0x7FFFFFFF, `QWord`
  values 0-0x7FFFFFFFFFFFFFFF;
- parameter names are unique within a policy, made of lowercase letters, digits and `_`, and never `state` (the
  parameter the two states of a policy become);
- an enum default is one of its values and every value is given once; an int default lies within `min` and `max`;
  `list` and `multiText` elements have their shapes (type `list`; kind `String` or `ExpandString` for a list,
  `MultiString` for multiText; flags as booleans; a safe `prefix` only without explicit names);
- the class is `Machine`, `User` or `Both`, written in this case; the namespace and the name are not empty and at
  most 512 characters; the file is `<name>.admx` without a path;
- texts by culture (titles, explanations, supported, labels, category titles, option texts) are keyed by culture names
  (2 or 3 letters and at most 4 subtags of 1-8 letters or digits), at most 32 per text, and hold no control
  characters except CR, LF and TAB, at most 64 K characters each;
- the chain of parents of every category is at most `admx.MAX_CATEGORY_DEPTH` (32) levels long and has no cycle (the
  templates of Windows nest a few levels);
- at most 20000 policies, 100 elements per policy, 1000 writes per state or options per element; every policy writes
  something; the records are of format 1 or 2, `cultures` holds at most 32 culture names and `files` counts at most
  3000 templates;
- a record of a shape none of these checks foresaw (a list where a text should be, for example) is refused as "a
  record of an unexpected shape", never passed on.

A catalog file is checked as it is: `admx.conform` (section 8) never runs on it, so a record that the template parser
would have skipped refuses the whole file, while a folder of templates and a saved import (also one of an older
version) lose only that policy. A message names the policy by its position and at most 80 characters of its name. A
saved import is not checked twice: `conform` checks each of its policies, then
`check_templates(data, policies=False)` checks the rest.

The registry branches are not limited to the policy branches (`Software\Policies` and the like): the templates of
Windows themselves write elsewhere, about 50 values of 50 policies under `System\CurrentControlSet` and
`Software\Microsoft` (outside `Windows\CurrentVersion\Policies`) in the templates of build 26300, so such a limit
would refuse records the parser makes from the templates of Windows. A package is therefore as strong as a folder of
templates and no stronger: the same safe characters and ranges, nothing of it runs, a policy writes nothing until a
person switches it on, and its description shows every key and value it writes. The trust order (section 8) keeps a
catalog file from changing a policy that a more trusted import holds, a policy of the file whose Disabled rule would
take the id of another import's rule is left out (section 8, several imports), and a choice made for a more trusted
source is held instead of moving to the file (section 4, `source`).

### Export and import (menu "ADMX")

Both live in the window only; the MCP server never imports or exports.

- "Export imported templates": a submenu of the saved imports, greyed out when there are none. `export_package`
  writes the import as a package in plain canonical JSON with CRLF (`jsonfile.dumps`, never compressed), through a
  temporary file; the suggested file name is the name of the import in lowercase words (`package_id`) with `.json`.
  `name`, `windows` and `created` come from `import.json`; the folder of the original import is not written, because
  it is a path of this computer, and the problems (files that could not be read) keep only the file names of the
  paths they quote (`admx.without_paths`).
- "Import a catalog file...": a file dialog titled "Import a catalog file" with the file type "WinKickOff catalog"
  (`*.json *.json.gz *.json.xz`). The file is read and checked in a background thread (`read_package`), kept as
  `admx/package-YYYYMMDD-HHMMSS/` (`import_package`; `store_import` checks the records again before it writes) and
  shown as a new tree, like imported templates; the policies the package lists as skipped are reported as
  information messages. The same file imported again (`find_package_imports` compares the path) asks: Yes updates
  that import in place (its tree and the choices in profiles stay), No adds one more tree, Cancel imports nothing.
- "Import a catalog of the program": below.
- While a catalog file or templates are read, the window is busy: the other import commands, "Rename imported
  templates", "Delete imported templates", showing or hiding an imported tree and a change of the language or the
  theme do nothing (each of them would rebuild the window and drop the work of the background thread). An error of
  the file or of saving it is shown as "The catalog was not imported: ..." or "The imported templates were not saved:
  ...", cut to 1500 characters (`ui.main_window.error_text`), since a file can make a message of any length; a
  failed export says "The imported templates were not exported: ...". Renaming and deleting imported templates show
  their errors the same way ("The name was not changed: ...", "The imported templates were not deleted: ...").

### Catalogs of the program

- Folder `WinKickOff/catalogs/` (`AppPaths.catalogs`; `_internal\catalogs` in the portable build): a `README.md` and
  packages `<name>.json` in the canonical layout (`tools/format_catalog.py` and `tests/test_catalog_format.py` cover
  them like the rule files, reading them as catalog files: with `null` and `check_templates`). The program takes
  `*.json`, `*.json.gz` and `*.json.xz` there, one file per import id (`bundled_catalogs`); two files that give the
  same id ("Windows 11.json" and "windows-11.json") stop the build (`bundled_collisions`), because the menu could offer
  only one of them (the first in the order of the file names).
- "Import a catalog of the program" (menu "ADMX") is a submenu that lists them by file name without the suffix and is
  greyed out when there are none. The import id is `bundled-<file name in lowercase words>`; importing the same
  catalog again updates the same tree (`import_bundled`), and a name the user gave the tree is kept.
- `tools/make_admx_catalogs.py <templates folder> <catalogs/name.json> --name "<tree name>" [--windows 10.0.26200]`
  makes a package: it refuses a `--windows` that is not a version (`package.WINDOWS_RE`: a digit, then digits and
  dots, at most 32 characters) before it reads anything, reads the templates as "Import templates from a folder"
  does, with the ADML of every language of the program, and checks the whole package as the program will read it
  (`parse_package` of its canonical text) before it writes; then it writes the canonical layout through a temporary
  file, so a failed run leaves neither a package nor half a file. Change the templates and run the tool again; do not
  edit a package by hand.
- The portable build (`tools/build.ps1`) runs `tools/pack_catalogs.py <target folder>`: it refuses two files with
  the same import id (`bundled_collisions`), checks every `catalogs/<name>.json` (`read_package`), writes it as
  `_internal/catalogs/<name>.json.xz` (xz, preset 9 extreme), reads it back and compares; then `build.ps1` fails when
  the number of packed files differs from the number of `catalogs/*.json`. Only these catalogs are compressed: the
  repository keeps them as plain JSON, so a change shows in the history line by line, and the built-in catalog of
  `rules/` is never compressed.
- Size: all templates of Windows 11 build 26300 (224 files, 3532 policies, 20 skipped; en-US, ru-RU and uk-UA) take
  about 13 MB as JSON and 0.83 MB in xz (measured 04.10.2026).
- The texts of the templates stay as Microsoft or the vendor wrote them, so `catalogs/*.json` are outside the dash
  checks of the tests.
- Status (04.10.2026): no package is committed yet. Shipping Microsoft templates waits for the license check the
  customer asked for; until then the folder holds only its README, and the menu entry is greyed out.
