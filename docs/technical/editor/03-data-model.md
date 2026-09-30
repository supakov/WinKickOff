# 03. Data model

Revision 0.2 of 25.09.2026, updated 30.09.2026 (T18: English catalog, translation files, themes). Formats:
TOML for the catalog (read by `tomllib`, edited by people), JSON for profiles, reference data, interface
translations and colour themes.

## 1. Tree groups: `rules/groups.toml`

```toml
[[group]]
id = "security"
title = "Security"
order = 60
summary = "UAC, accounts, credential protection, remote access, encryption."

[[group]]
id = "security.lsa"
parent = "security"
title = "Credential protection (LSA, NTLM)"
order = 3
```

A dotted identifier defines the path; `parent` is required for nested groups. Nodes are ordered by `order`.

## 2. Rule: `rules/NN-<area>.toml`

```toml
[[rule]]
id = "defender.pua"
group = "defender"
phase = "specialize"
title = "Block potentially unwanted apps (PUA)"
level = "recommended"          # baseline | recommended | optional | risky
default = true
requires = ["defender.realtime"]
conflicts = []
tags = ["defender", "pua", "adware", "bundleware", "miners"]
doc = "docs/technical/reference/07-defender.md#defenderpuaprotection"
summary = "Defender blocks adware, bundling installers and miners on download and launch."
effect = """
Closes the most common infection channel for non-professional users:
"a free program from a website with a Download button".
"""
risk = "Legitimate utilities flagged as PUA (some remote access tools) require an exclusion."
versions = "Policy since Windows 10 1607; toggle in Settings since 2004."
verify = "Get-MpPreference | Select-Object PUAProtection"
rollback = "Delete the PUAProtection value."

[[rule.actions]]
type = "reg"
path = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender'
name = "PUAProtection"
kind = "DWord"
value = 1
why = "block potentially unwanted apps"
```

Rule fields:

| Field | Required | Meaning |
|---|---|---|
| id | yes | `group.name`, Latin letters, dots; unique in the catalog |
| group | yes | Identifier of the tree group |
| phase | yes | `windowspe`, `specialize-xml`, `specialize`, `default-user`, `user-first-logon`, `post-oobe`, `oobe-xml` |
| title | yes | Title in the tree (English; translations in `rules/lang/<code>.toml`) |
| level | yes | `baseline` (disabling gives a warning), `recommended`, `optional`, `risky` (enabling gives a warning) |
| default | yes | State in the Office preset |
| requires | no | Identifiers of rules without which this rule is disabled |
| conflicts | no | Identifiers of rules that are disabled when this one is enabled |
| tags | no | English words for search (a translation file may add words in its language) |
| doc | yes | Link to the reference card |
| summary | yes | One or two sentences |
| effect, risk, versions | effect yes | Text for the description panel |
| verify, rollback | no | Verification command and rollback method |
| params | no | Parameter table (below) |
| actions | yes | List of actions; a rule without actions is not allowed (except `level = "baseline"` with `phase = "oobe-xml"` for internal rules) |

### Parameters

```toml
[rule.params.seconds]
type = "int"            # int | enum | string | bool | list
title = "Seconds of inactivity before locking"
default = 900
min = 60
max = 599940

[rule.params.mode]
type = "enum"
title = "Mode"
default = 1
values = [ { value = 1, title = "Block" }, { value = 2, title = "Audit" }, { value = 6, title = "Warn" } ]

[rule.params.sites]
type = "list"           # a list of strings, edited as one item per line
title = "Sites"
default = []
pairs = true            # optional: every item is "name=value" (the names of a reg-list with explicit = true)
required = false        # optional: true when the list may not be empty
```

In actions, a parameter is substituted as the string `"{seconds}"`; the generator converts it to the action's type.
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
| ps | script (multiline literal) | text as is |
| xml-pe-command | command, description | `RunSynchronousCommand` in windowsPE |
| xml-specialize-command | command, description | `RunSynchronousCommand` in specialize |
| xml-oobe | element, value | element inside `<OOBE>` |

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

Registry paths: prefix `HKLM:\`, `HKCU:\` (user-first-logon phase only), `DU:\` (default user profile;
the generator replaces it with `$du\`). TOML literal strings in single quotes do not require escaping
backslashes.

Rule identifiers of catalog 0.2 (port of v0.2): one rule per logically separate
setting; the unconditional actions of v0.2 are grouped into rules of the `baseline` level
(for example `uac.baseline`, `lsa.baseline`, `edge.baseline`, `default-user.baseline`).

## 3. Translations: `rules/lang/<lang>.toml` and interface strings

Since 30.09.2026 the source language is English: the code, the rule catalog (`rules/*.toml`) and every
interface string are written in English, and the English text is the key of each translation. Russian and
Ukrainian are translation files like any other language. A language is available when one of its files
exists (`core/i18n.py` `available_languages`), so a user adds a language by adding files, without code:

Rule texts, `rules/lang/<code>.toml` (now `ru.toml`, `uk.toml`):

```toml
_language = "Українська"          # native name, used when there is no strings file

["defender.pua"]
title = "Блокувати потенційно небажані програми (PUA)"
summary = "..."
tags = ["небажані програми"]     # extra search words in this language (optional)
params.mode = "..."               # parameter title
values.mode."1" = "..."           # option title

[_groups."defender"]
title = "..."
```

The table key is the rule identifier; `title`, `summary`, `effect`, `risk`, `versions`, `verify`,
`rollback`, parameter titles and option titles are translated; `_groups` holds group titles and summaries.
Search looks at the English source and at the translated title, summary and tags of the current language.

Interface strings, `resources/strings.<code>.json`: `{"_language": "<native name>", "<English text>":
"<translation>"}` (gettext style). Code marks texts with `tr("...")`; templates use positional fields,
`tr("Profile \"{0}\" opened", name)`. Texts stored before the language is known (module-level constants)
are marked with `N_("...")` and translated with `tr()` where shown.

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
  "format_version": 2,
  "catalog_version": "0.4",
  "name": "Office",
  "author": "",
  "created": "2026-09-25T10:00:00",
  "modified": "2026-09-25T10:00:00",
  "comment": "",
  "install": { "edition": "Pro", "product_key_mode": "generic", "product_key": "", "time_zone": "FLE Standard Time" },
  "languages": { "ui_language": "uk-UA", "system_locale": "uk-UA", "user_locale": "uk-UA", "input": ["en-US", "uk-UA", "ru-UA"] },
  "accounts": [
    { "name": "Admin", "display_name": "Admin", "group": "Administrators", "description": "Local administrator (starter account)", "password": "" },
    { "name": "User",  "display_name": "User",  "group": "Users", "description": "Standard user (starter account)", "password": "" }
  ],
  "rules": {
    "defender.pua": { "enabled": true },
    "accounts.inactivity-lock": { "enabled": true, "params": { "seconds": 900 } },
    "network.netbios-off": { "enabled": false }
  },
  "unknown": {}
}
```

- `rules` lists all rules of the catalog (completeness is needed for comparing profiles and so
  that a new catalog rule is noticeable on load), except imported policies (`admx.*`, section 8): only those that
  are on or have parameters are written, an absent one is "not configured" and is not reported as new.
- `params` is present only for rules with parameters; a missing parameter = the default value.
- Rules from an old profile that are not in the catalog are moved to `unknown` and are not lost; when such a
  rule is in the catalog again (templates loaded again), its state comes back from `unknown`.
- Passwords are in plain text; profiles with a password are marked in the recent list.

## 5. Reference data

- `resources/keyboards.json`: `{ "tag": "uk-UA", "lcid": "0422", "klid": "00020422", "title": "Українська (розширена)", "transient": false }`;
  for `ru-UA`: `"lcid": null, "transient": true, "fallback": "ru"`.
- `resources/timezones.json`: `{ "id": "FLE Standard Time", "title": "(UTC+02:00) Киев", "recommended": true }`.
- Languages with `transient: true` do not go into `InputLocale` (their `fallback` is used instead), but they do go into
  the list for the first sign-in script (rule `languages.user-input-list`).

## 6. Embedded profile in XML

The generator adds to `Extensions` the element `<Profile format="json"><![CDATA[ ... ]]></Profile>` with
the same JSON that is saved to the file. Import from XML reads it; if the element is absent (a v0.2 file or a
third-party one), the import parses the actions from the scripts and matches them against the catalog by type, path and name
(the same code as the semantic golden), and shows whatever is unmatched as a list.

## 7. Versioning

- Profile `format_version`: 2 (in 0.1 it was 1; migration: `config.*` → rule states via a mapping table).
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

## 8. Imported policy templates (ADMX, ADML): `admx/<id>/`

`core/admx.py` reads every `*.admx` of a folder (the ADMX menu: `%SystemRoot%\PolicyDefinitions` or a chosen
folder) and the ADML files of the cultures that match the languages of the program (`en-US` always first). The
result is kept next to the settings, in the writable program folder:

- `admx/<id>/import.json`: `{format, id, name, folder, created, windows, cultures, policies, skipped, files}`;
  the id is `system-YYYYMMDD-HHMMSS` or `folder-...`, the name is generated ("PolicyDefinitions 10.0.26200,
  2026-09-30 13:05"; the folder name for a chosen folder). Format 2 (1.1.0-rc.2) adds list and multiText
  elements; imports of format 1 still load, and the description of their branch counts the policies with lists
  that 1.1.0-rc.1 skipped (import the templates again to get them); a newer format is not loaded.
- `admx/<id>/policies.json`: the policies as records: file, namespace, name, class, category, the texts of every
  kept culture (title, explain, supported), the writes of the Enabled and Disabled states (`{key, name, kind,
  value}`, kind `delete` for a removal) and the elements (`{param, type, key, name, kind, default, min, max,
  values, label, required}`; a list element has `element: "list"`, no name and `explicit`, `additive` and, for
  valuePrefix, `prefix`; a multiText element has `element: "multiText"`, type `list` and kind `MultiString`);
  categories with their parents; skipped policies with a reason code.
- `settings.json` `admx`: the imports shown in the tree; they are merged into the catalog at start
  (`with_imports`, `catalog.merge`) in the interface language, so every text of the subtree comes from ADML.

Conversion of a policy (`policy_rules`):

| Policy | Rules |
|---|---|
| one value, Enabled and Disabled of the same kind | one rule, enum parameter `state` (Enabled or Disabled value) |
| elements or value lists | rule of the Enabled state, elements as parameters (`decimal` int with min and max, `longDecimal` QWord, `text` string or ExpandString, `boolean` bool or a two-value enum, `enum` enum, `multiText` a `list` parameter written as one MultiString value, `required` means not empty) |
| `list` element | a `list` parameter (empty by default, `pairs` for explicitValue) and a `reg-list` action on the key of the element or of the policy: String or ExpandString (`expandable`), names from `valuePrefix` (an empty prefix gives 1, 2, ...), from the items for `explicitValue`, otherwise the data; `additive` keeps the other values of the key. The list actions come first in the rule, so a list that is not additive cannot delete a value the same policy writes into its key |
| the Disabled state writes values | plus the rule `<id>.off`, the two rules conflict; its list actions are empty and not additive, so the keys of the lists keep no values |
| value lists inside an option or a check box, values over the signed DWORD range, unsafe characters (also in the key or the prefix of a list) | skipped with a reason |

Ids: rule `admx.<namespace>.<policy>` in lower case (other characters become `-`), so a profile keeps its choice
across imports of the same templates; groups `admx.<import id>`, `.machine` or `.user`, `.c<n>` per category,
`.none` without a category. Machine and Both policies write `HKLM:\` in phase `specialize`, User policies `DU:\` in
phase `default-user`. Level `optional`, default off, no `doc`; `Catalog.origins` holds the source (import, file,
policy), `Catalog.same_values()` the rules of the other kind that write the same (scope, key, value name); a list
meets every value of its key, so a list policy that clears a key links to the built-in rules writing into it.

Several imports (T20): a policy is one rule, owned by the first import loaded (`settings.admx` order); the
imports loaded later show it too, as an alias (`Catalog.aliases`: rule id to more groups, `placements()`), so it
has one check mark and one set of parameters everywhere. The tree gives an alias its own item id
`r:<rule id>@<group id>` (`main_window.rule_of()` reads the rule id); group counts and group actions include the
aliases. An import of a folder that is already imported asks whether to update that import in place (same id,
`save_import(replace=...)`, files written through a temporary file) or to add a tree. `import.json` may hold
`renamed: true`: the name was given by the user (`rename_import`, at most 120 characters, no control characters)
and survives an update; a generated name follows the date of the update.

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

Untrusted input: documents with a DTD or entities are refused (the parser does not resolve entities anyway), a
file is at most 16 MB and a folder at most 3000 templates, files are decoded by their BOM; keys and value names
with control characters, `"`, backquote, `$` or typographic quotes and strings with control characters,
typographic quotes or `]]>` skip the policy, because the DU path is a double-quoted PowerShell string and the
scripts are CDATA sections. `ps_quote` doubles the typographic single quotes as well.

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
