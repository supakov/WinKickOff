# T06. Генератор и golden-тест

Статус: todo. Этап 2. Зависимости: T04, T05. Веха M1.

## Цель

Реализовать `core/render.py`: из профиля и шаблонов собрать текст `autounattend.xml`; закрепить
golden-тестом, что профиль «Офис» даёт эталон v0.2 побайтно.

## Шаги

1. Сериализация PowerShell: `ps_value(value) -> str` для bool, int, str, list[str].
2. `render_config_block(profile, schema)`: строки `Name = value   # comment` с выравниванием как в
   v0.2 (имя дополнено до 28 символов, затем `= `; проверить по эталону), заголовки групп
   `# --- Title ---`, пустые строки между группами.
3. `render_apps(profile)`, `render_asr(profile, rules)`: с отступом 4 пробела и комментариями.
4. `render_accounts(profile)`: элементы `LocalAccount` в порядке Password, Description, DisplayName,
   Group, Name; отступы как в эталоне; одинаковый блок для amd64 и arm64.
5. `render_labconfig(profile)`: по элементу на флажок; пустой набор убирает `RunSynchronous`.
6. `render_international(profile, keyboards)`: `InputLocale` из языков с LCID; языки transient
   заменяются базовым языком; список для `Setup-User.ps1`.
7. `render_header(profile, versions)`: комментарий шапки; для golden содержимое шапки v0.2 должно
   воспроизводиться при значениях по умолчанию (дата и версия из констант эталона).
8. `build(profile, schema, templates) -> str`: полная сборка; CRLF; без BOM.
9. Тесты из `04-testing.md`, раздел core/render, включая golden.

## Результат

`build(Profile.defaults())` равен `tests/golden/autounattend-v0.2.xml`.

## Критерии приёмки

- Golden проходит.
- Для пресета «Строгий» результат проходит `tools/Validate-Unattend.ps1` (внешний тест, пропуск без PowerShell).
- Все `Path` не длиннее 259 для обоих пресетов (модульный тест).

## Заметки исполнителя
