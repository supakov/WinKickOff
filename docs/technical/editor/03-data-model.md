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
type = "int"            # int | enum | string | bool
title = "Seconds of inactivity before locking"
default = 900
min = 60
max = 599940

[rule.params.mode]
type = "enum"
title = "Mode"
default = 1
values = [ { value = 1, title = "Block" }, { value = 2, title = "Audit" }, { value = 6, title = "Warn" } ]
```

In actions, a parameter is substituted as the string `"{seconds}"`; the generator converts it to the action's type.

### Actions

| type | Fields | Generated |
|---|---|---|
| reg | path, name, kind (DWord, QWord, String, ExpandString, MultiString, Binary), value, why?, default? | `Set-Reg ...` |
| reg-remove | path, name, default? | `Remove-Reg ...` |
| service | name, start (2, 3, 4), default? | `Set-ServiceStart ...` |
| exe | file, args (list of strings) | `Invoke-Exe ...` |
| feature | name, state (`Enabled`, `Disabled`), default? | runtime wrapper around DISM |
| capability | pattern | runtime wrapper |
| appx | names (list) | runtime wrapper (deprovision + remove) |
| ps | script (multiline literal) | text as is |
| xml-pe-command | command, description | `RunSynchronousCommand` in windowsPE |
| xml-specialize-command | command, description | `RunSynchronousCommand` in specialize |
| xml-oobe | element, value | element inside `<OOBE>` |

`default` (catalog 0.4) is the state of a clean Windows, used by "Return the selection to Windows defaults"
(`core/apply.py` `plan_revert`): `"absent"` (no such value), a value of
the action's kind, a start type 2-4, `Enabled`/`Disabled`, or `"unknown"` (not returned automatically). Without
the field a value under `SOFTWARE\Policies` returns to "absent" (a missing policy is the Windows default), a
`reg-remove` needs nothing (the removed values do not exist in a clean Windows) and anything else is unknown.
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

## 4. Profile: `profiles/<имя>.json`

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
  that a new catalog rule is noticeable on load).
- `params` is present only for rules with parameters; a missing parameter = the default value.
- Rules from an old profile that are not in the catalog are moved to `unknown` and are not lost.
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
