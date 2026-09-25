# 03. Модель данных

Редакция 0.2 от 25.09.2026. Форматы: TOML для каталога (читается `tomllib`, редактируется людьми),
JSON для профилей и справочников (пишется программой).

## 1. Группы дерева: `rules/groups.toml`

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

Идентификатор с точками задаёт путь; `parent` обязателен для вложенных. Порядок узлов по `order`.

## 2. Правило: `rules/NN-<направление>.toml`

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
doc = "docs/reference/07-defender.md#defenderpuaprotection"
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

Поля правила:

| Поле | Обязательное | Смысл |
|---|---|---|
| id | да | `группа.имя`, латиница, точки; уникален в каталоге |
| group | да | Идентификатор группы дерева |
| phase | да | `windowspe`, `specialize-xml`, `specialize`, `default-user`, `user-first-logon`, `post-oobe`, `oobe-xml` |
| title | да | Название в дереве |
| level | да | `baseline` (выключение даёт предупреждение), `recommended`, `optional`, `risky` (включение даёт предупреждение) |
| default | да | Состояние в пресете «Офис» |
| requires | нет | Идентификаторы правил, без которых это правило выключается |
| conflicts | нет | Идентификаторы правил, которые выключаются при включении этого |
| tags | нет | Слова для поиска |
| doc | да | Ссылка на карточку справочника |
| summary | да | Одно-два предложения |
| effect, risk, versions | effect да | Текст для панели описания |
| verify, rollback | нет | Команда проверки и способ отката |
| params | нет | Таблица параметров (ниже) |
| actions | да | Список действий; правило без действий недопустимо (кроме `level = "baseline"` с `phase = "oobe-xml"` для служебных) |

### Параметры

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

В действиях параметр подставляется строкой `"{seconds}"`; генератор приводит к типу действия.

### Действия

| type | Поля | Генерируется |
|---|---|---|
| reg | path, name, kind (DWord, QWord, String, ExpandString, MultiString, Binary), value, why? | `Set-Reg ...` |
| reg-remove | path, name | `Remove-Reg ...` |
| service | name, start (2, 3, 4) | `Set-ServiceStart ...` |
| exe | file, args (список строк) | `Invoke-Exe ...` |
| feature | name, state (`Enabled`, `Disabled`) | обёртка рантайма над DISM |
| capability | pattern | обёртка рантайма |
| appx | names (список) | обёртка рантайма (deprovision + remove) |
| ps | script (многострочный литерал) | текст как есть |
| xml-pe-command | command, description | `RunSynchronousCommand` в windowsPE |
| xml-specialize-command | command, description | `RunSynchronousCommand` в specialize |
| xml-oobe | element, value | элемент внутри `<OOBE>` |

Пути реестра: префикс `HKLM:\`, `HKCU:\` (только фаза user-first-logon), `DU:\` (профиль по умолчанию;
генератор заменяет на `$du\`). Литеральные строки TOML в одинарных кавычках не требуют экранирования
обратных слешей.

Идентификаторы правил каталога 0.2 (перенос v0.2): по одному правилу на логически отдельную
настройку; безусловные действия v0.2 сгруппированы в правила уровня `baseline`
(например `uac.baseline`, `lsa.baseline`, `edge.baseline`, `default-user.baseline`).

## 3. Переводы: `rules/lang/uk.toml`

```toml
["defender.pua"]
title = "Блокувати потенційно небажані програми (PUA)"
summary = "..."
```

Ключ таблицы это идентификатор правила; переводятся `title`, `summary`, `effect`, `risk`, `versions`,
`rollback`, названия параметров. Отсутствующий перевод показывает русский текст.

## 4. Профиль: `profiles/<имя>.json`

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

- В `rules` перечислены все правила каталога (полнота нужна для сравнения профилей и для того,
  чтобы новое правило каталога было заметно при загрузке).
- `params` присутствует только у правил с параметрами; отсутствующий параметр = значение по умолчанию.
- Правила из старого профиля, которых нет в каталоге, переносятся в `unknown` и не теряются.
- Пароли открытым текстом; профили с паролем помечаются в списке недавних.

## 5. Справочники

- `resources/keyboards.json`: `{ "tag": "uk-UA", "lcid": "0422", "klid": "00020422", "title": "Українська (розширена)", "transient": false }`;
  для `ru-UA`: `"lcid": null, "transient": true, "fallback": "ru"`.
- `resources/timezones.json`: `{ "id": "FLE Standard Time", "title": "(UTC+02:00) Киев", "recommended": true }`.
- Языки с `transient: true` не попадают в `InputLocale` (вместо них `fallback`), но попадают в
  список для скрипта первого входа (правило `languages.user-input-list`).

## 6. Встроенный профиль в XML

Генератор добавляет в `Extensions` элемент `<Profile format="json"><![CDATA[ ... ]]></Profile>` с
тем же JSON, что сохраняется в файл. Импорт из XML читает его; если элемента нет (файл v0.2 или
чужой), импорт разбирает действия из скриптов и сопоставляет с каталогом по типу, пути и имени
(тот же код, что семантический golden), а несопоставленное показывает списком.

## 7. Версионирование

- `format_version` профиля: 2 (в 0.1 был 1; миграция: `config.*` → состояния правил по таблице соответствия).
- `catalog_version` = содержимое `templates/VERSION`; при расхождении профиль загружается с
  предупреждением и дополняется.
- Версия приложения независима.
- Каталог 0.3 (25.09.2026): страна перенесена из `languages.geo_id` в параметры `geo_id` и `geo_name`
  правила `default-user.region`; поле `install.iso_language` удалено (язык интерфейса всегда равен языку
  ISO); маркер блока в скриптах `# [<rule.id>]` без названия. При загрузке старого профиля `geo_id`
  переносится в параметр правила с предупреждением, `iso_language` отбрасывается с предупреждением.
