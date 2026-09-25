# 03. Data model

Revision 0.2 of 25.09.2026. Formats: TOML for the catalog (read by `tomllib`, edited by people),
JSON for profiles and reference data (written by the program).

## 1. Tree groups: `rules/groups.toml`

```toml
[[group]]
id = "security"
title = "Безопасность"
order = 30
summary = "Учётные данные, UAC, удалённый доступ, шифрование."

[[group]]
id = "security.lsa"
parent = "security"
title = "Защита учётных данных"
order = 2
```

A dotted identifier defines the path; `parent` is required for nested groups. Nodes are ordered by `order`.

## 2. Rule: `rules/NN-<направление>.toml`

```toml
[[rule]]
id = "defender.pua"
group = "defender"
phase = "specialize"
title = "Блокировать потенциально нежелательные программы (PUA)"
level = "recommended"          # baseline | recommended | optional | risky
default = true
requires = ["defender.realtime"]
conflicts = []
tags = ["defender", "adware", "bundlers"]
doc = "docs/technical/reference/07-defender.md#defenderpuaprotection"
summary = "Defender блокирует adware, установщики-бандлы и майнеры при скачивании и запуске."
effect = """
Пользователь видит уведомление Безопасности Windows и файл не запускается.
Закрывает самый частый канал заражения: «бесплатная программа с кнопкой Скачать».
"""
risk = "Легитимные утилиты, помеченные как PUA (некоторые средства удалённого доступа), требуют исключения."
versions = "Политика с Windows 10 1607; переключатель в Параметрах с 2004; на 24H2 без изменений."
verify = "Get-MpPreference | Select-Object PUAProtection"
rollback = "Удалить значение PUAProtection из ключа политик Defender."

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
| id | yes | `группа.имя`, Latin letters, dots; unique in the catalog |
| group | yes | Identifier of the tree group |
| phase | yes | `windowspe`, `specialize-xml`, `specialize`, `default-user`, `user-first-logon`, `post-oobe`, `oobe-xml` |
| title | yes | Title in the tree |
| level | yes | `baseline` (disabling gives a warning), `recommended`, `optional`, `risky` (enabling gives a warning) |
| default | yes | State in the «Офис» (Office) preset |
| requires | no | Identifiers of rules without which this rule is disabled |
| conflicts | no | Identifiers of rules that are disabled when this one is enabled |
| tags | no | Words for search |
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
title = "Секунд простоя до блокировки"
default = 900
min = 60
max = 599940

[rule.params.mode]
type = "enum"
title = "Режим"
default = 1
values = [ { value = 1, title = "Блокировать" }, { value = 2, title = "Аудит" }, { value = 6, title = "Предупреждать" } ]
```

In actions, a parameter is substituted as the string `"{seconds}"`; the generator converts it to the action's type.

### Actions

| type | Fields | Generated |
|---|---|---|
| reg | path, name, kind (DWord, QWord, String, ExpandString, MultiString, Binary), value, why? | `Set-Reg ...` |
| reg-remove | path, name | `Remove-Reg ...` |
| service | name, start (2, 3, 4) | `Set-ServiceStart ...` |
| exe | file, args (list of strings) | `Invoke-Exe ...` |
| feature | name, state (`Enabled`, `Disabled`) | runtime wrapper around DISM |
| capability | pattern | runtime wrapper |
| appx | names (list) | runtime wrapper (deprovision + remove) |
| ps | script (multiline literal) | text as is |
| xml-pe-command | command, description | `RunSynchronousCommand` in windowsPE |
| xml-specialize-command | command, description | `RunSynchronousCommand` in specialize |
| xml-oobe | element, value | element inside `<OOBE>` |

Registry paths: prefix `HKLM:\`, `HKCU:\` (user-first-logon phase only), `DU:\` (default user profile;
the generator replaces it with `$du\`). TOML literal strings in single quotes do not require escaping
backslashes.

Rule identifiers of catalog 0.2 (port of v0.2): one rule per logically separate
setting; the unconditional actions of v0.2 are grouped into rules of the `baseline` level
(for example `uac.baseline`, `lsa.baseline`, `edge.baseline`, `default-user.baseline`).

## 3. Translations: `rules/lang/uk.toml`

```toml
["defender.pua"]
title = "Блокувати потенційно небажані програми (PUA)"
summary = "..."
```

The table key is the rule identifier; `title`, `summary`, `effect`, `risk`, `versions`,
`rollback` and parameter titles are translated. A missing translation shows the Russian text.

## 4. Profile: `profiles/<имя>.json`

```json
{
  "format_version": 2,
  "catalog_version": "0.3",
  "name": "Офис",
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
