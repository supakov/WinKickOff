# T08. Импорт $Config и проверка PowerShell

Статус: todo. Этап 3. Зависимости: T06. Веха M2 вместе с T07.

## Цель

Дать возможность открыть существующий `autounattend.xml` (v0.2 и собранные редактором) и получить
из него профиль; при наличии `powershell.exe` проверять синтаксис встроенных скриптов.

## Шаги

1. `core/importer.py`: `parse_config_block(text) -> dict` (регулярное выражение по блоку `$Config = @{ ... }`,
   значения `$true/$false`, числа, строки в одинарных кавычках), `parse_apps(text)`, `parse_asr(text)`,
   `parse_accounts(xml)`, `parse_international(xml)`, `parse_labconfig(xml)`, `parse_timezone(xml)`.
2. `import_profile(text, schema) -> tuple[Profile, list[Issue]]`: несопоставленные ключи как предупреждения.
3. `core/pscheck.py`: если `shutil.which("powershell.exe")`, извлечь три скрипта во временную папку
   `logs/tmp/`, запустить `powershell -NoProfile -Command` с `[System.Management.Automation.Language.Parser]::ParseFile`
   и вернуть список ошибок; иначе статус «пропущено». Тайм-аут 30 секунд, никаких изменений системы.
4. Тесты из `04-testing.md`, разделы core/importer и core/pscheck.

## Результат

Импорт эталона даёт профиль «Офис»; PowerShell-проверка находит подсаженную синтаксическую ошибку.

## Критерии приёмки

- `import_profile(golden)` равен `Profile.defaults()` по всем разделам.
- Изменённое значение в XML переносится в профиль.
- Без `powershell.exe` функция возвращает «пропущено», не исключение.

## Заметки исполнителя
