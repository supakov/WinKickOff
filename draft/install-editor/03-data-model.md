# 03. Модель данных

## 1. Схема параметров: `schema/parameters.json`

Один документ, описывающий все параметры, группы и порядок. Пример двух записей:

```json
{
  "schema_version": 1,
  "template_version": "0.2",
  "groups": [
    { "id": "install",  "title": { "ru": "Установка", "uk": "Встановлення" }, "doc": "docs/reference/01-windows-pe.md" },
    { "id": "accounts", "title": { "ru": "Учётные записи", "uk": "Облікові записи" }, "doc": "docs/reference/03-oobe-accounts-languages.md" },
    { "id": "defender", "title": { "ru": "Microsoft Defender", "uk": "Microsoft Defender" }, "doc": "docs/reference/07-defender.md" }
  ],
  "parameters": [
    {
      "id": "DefenderPUAProtection",
      "group": "defender",
      "target": "config",
      "type": "bool",
      "default": true,
      "label": { "ru": "Блокировать нежелательные программы (PUA)", "uk": "Блокувати небажані програми (PUA)" },
      "hint":  { "ru": "Adware, установщики-бандлы, майнеры блокируются Defender.", "uk": "..." },
      "comment": "block potentially unwanted apps (adware, bundlers)",
      "doc": "docs/reference/07-defender.md#defenderpuaprotection",
      "flags": []
    },
    {
      "id": "ControlledFolderAccess",
      "group": "defender",
      "target": "config",
      "type": "enum",
      "values": [ { "value": 0, "label": { "ru": "Выключено" } }, { "value": 1, "label": { "ru": "Блокировать" } }, { "value": 2, "label": { "ru": "Аудит" } } ],
      "default": 0,
      "label": { "ru": "Контролируемый доступ к папкам" },
      "hint":  { "ru": "Защита от шифровальщиков. Ломает старые программы, пишущие в Документы." },
      "comment": "0 off, 1 block, 2 audit. Anti-ransomware, but breaks legacy apps writing to Documents.",
      "doc": "docs/reference/07-defender.md#controlledfolderaccess",
      "flags": ["risk_when:1"]
    }
  ]
}
```

Поля параметра:

| Поле | Обязательное | Смысл |
|---|---|---|
| id | да | Имя ключа `$Config` или имя XML-параметра; латиница, как в шаблоне |
| group | да | Ссылка на группу |
| target | да | `config` (блок `$Config`), `xml` (элемент файла ответов), `list` (списки приложений/ASR), `derived` (вычисляется) |
| type | да | `bool`, `int`, `enum`, `string`, `string_list`, `accounts`, `languages`, `apps`, `asr` |
| default | да | Значение по умолчанию; для пресета «Офис» совпадает с v0.2 |
| values | для enum | Допустимые значения с подписями |
| min, max | для int | Диапазон |
| label, hint | да | Подписи и пояснения по языкам |
| comment | для config | Комментарий, который попадёт в `$Config` (английский, как в шаблоне, чтобы golden-тест совпал) |
| doc | да | Относительная ссылка на карточку справочника |
| flags | нет | `risk_when:<value>` (предупреждение), `enterprise_only`, `deprecated`, `advanced` |
| depends | нет | Условия видимости или доступности: `{"param": "RemoveBloatApps", "equals": true}` |

Порядок параметров в файле задаёт порядок в `$Config` и в форме. Комментарии групп в `$Config`
(`# --- Printing ---`) берутся из группы: поле `config_header`.

## 2. Отдельные справочники

- `schema/apps.json`: массив `{ "name": "Microsoft.BingWeather", "title": {...}, "reason": {...},
  "versions": "all", "default_remove": true }` для удаляемых и `{ "name": ..., "keep_reason": {...} }`
  для сохраняемых. Порядок в списке `$AppsToRemove` совпадает с порядком файла.
- `schema/asr_rules.json`: `{ "guid": "...", "title": {...}, "blocks": {...}, "false_positive_risk": "low|medium|high",
  "min_build": "1709", "needs_cloud": false, "supports_warn": true, "default_mode": 1 }`.
  Режимы: 0 выключено, 1 блокировать, 2 аудит, 6 предупреждать. Правило LSASS присутствует
  с `default_mode: 0` и пометкой «избыточно при LSAProtection».
- `resources/keyboards.json`: `{ "tag": "uk-UA", "lcid": "0422", "klid": "00020422", "title": {...}, "transient": false }`;
  для `ru-UA` `"lcid": null, "transient": true`, что означает «только через Setup-User.ps1».
- `resources/timezones.json`: `{ "id": "FLE Standard Time", "title": { "ru": "(UTC+02:00) Киев" } }`.

## 3. Профиль: `profiles/<имя>.json`

```json
{
  "format_version": 1,
  "template_version": "0.2",
  "name": "Офис",
  "author": "",
  "created": "2026-09-25T10:00:00",
  "modified": "2026-09-25T10:00:00",
  "comment": "",
  "install": {
    "edition": "Pro",
    "product_key_mode": "generic",
    "product_key": "",
    "bypass_checks": ["TPM", "SecureBoot", "CPU", "RAM", "Storage"],
    "time_zone": "FLE Standard Time"
  },
  "languages": {
    "ui_language": "uk-UA",
    "system_locale": "uk-UA",
    "user_locale": "uk-UA",
    "geo_id": 241,
    "input": ["en-US", "uk-UA", "ru-UA"]
  },
  "accounts": [
    { "name": "Admin", "display_name": "Admin", "group": "Administrators", "description": "Local administrator (starter account)", "password": "" },
    { "name": "User",  "display_name": "User",  "group": "Users",          "description": "Standard user (starter account)",      "password": "" }
  ],
  "config": {
    "PasswordNeverExpires": true,
    "EnableNetFx3": true,
    "EnsurePrintSpooler": true,
    "ControlledFolderAccess": 0,
    "SmartScreenLevel": "Warn"
  },
  "apps_to_remove": ["Microsoft.BingSearch", "Microsoft.BingNews"],
  "asr_rules": { "56a863a9-875e-4185-98a7-b882c64b5ce5": 1, "01443614-cd74-433a-b99e-2ecdc07bfc25": 2 },
  "unknown": {}
}
```

Правила:

- `config` содержит только ключи, известные схеме; `AdminAccount` и `UserAccount` вычисляются из
  `accounts` (первая запись Administrators и первая Users) и в профиле не хранятся.
- `input` хранит теги языков; в XML `InputLocale` попадают только те, у кого есть LCID; языки с
  `transient: true` заменяются ближайшим (для `ru-UA` это `ru`, то есть `0419:00000419`) в XML и
  передаются в `Setup-User.ps1` как список `New-WinUserLanguageList` (в v0.2 список в скрипте
  зашит; в шаблоне он станет маркером `{{user_language_list}}`).
- `unknown`: параметры из более новых профилей, которые эта версия не знает; сохраняются как есть.
- Пароль хранится открытым текстом, если пользователь его ввёл; в списке недавних файлов
  профили с паролями помечаются, при сохранении показывается предупреждение.

## 4. Отображение профиля на XML и скрипты

| Профиль | Куда | Правило |
|---|---|---|
| install.edition + product_key_mode | `<Key>`, `<WillShowUI>` | generic → универсальный ключ редакции, OnError; custom → введённый ключ, OnError; ask → `00000-00000-00000-00000-00000`, Always |
| install.bypass_checks | RunSynchronous в windowsPE | По одному `reg.exe add ... Bypass<X>Check` на элемент, Order с 1; пустой список: элемент RunSynchronous не выводится |
| install.time_zone | `<TimeZone>` | Как есть |
| languages.* | International-Core | `InputLocale` = join(';') LCID:KLID; остальные как есть |
| languages.geo_id | Setup-System.ps1, раздел 10 | Маркер `{{geo_id}}` и `{{geo_name}}` (в v0.2 зашито 241/UA; в шаблоне станет маркером) |
| accounts | `<LocalAccounts>` | Порядок элементов: Password, Description, DisplayName, Group, Name; пароль пустой → `<Value></Value>` |
| config.* | `$Config` | По схеме, в её порядке |
| apps_to_remove | `$AppsToRemove` | В порядке `apps.json` |
| asr_rules | `$AsrRules` | Только правила с режимом больше 0; режим 0 не выводится |

## 5. Версионирование

- `schema_version`: формат самой схемы; меняется редко.
- `template_version`: версия шаблона XML и скриптов (0.2 сейчас). Профиль хранит версию, с которой
  сохранён; при открытии профилем старой версии применяется миграция (`profile.migrate()`), которая
  добавляет новые параметры со значениями по умолчанию и пишет предупреждение.
- Версия приложения независима (семантическая), показывается в «О программе» и в шапке XML.
