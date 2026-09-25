# T12. Сборка PyInstaller и проверка портабельности

Статус: todo. Этап 5. Зависимости: T11.

## Цель

Портабельная сборка `dist/WinKickOff/` и чек-лист портабельности в ВМ.

## Шаги

1. `tools/build.ps1`: venv на Python 3.14, установка PyInstaller, `pyinstaller --noconsole --onedir
   --name WinKickOff --add-data rules;rules --add-data templates;templates --add-data resources;resources
   --add-data profiles;profiles --add-data ../docs/reference;docs/reference winkickoff/__main__.py`;
   копирование `README-user.md`; zip с версией.
2. `app_paths()` в сборке находит данные в `_internal`, создаёт папки рядом с exe.
3. Значок и сведения о версии exe.
4. Если PyInstaller не поддерживает 3.14: сборка на 3.13, код не менять, отметить.
5. Чек-лист портабельности в чистой ВМ (снимки реестра и `%APPDATA%` до и после, перенос папки,
   удаление без следов).
6. Поведение SmartScreen на неподписанном exe: описать в `README-user.md`.

## Критерии приёмки

- Шесть пунктов чек-листа выполнены; старт до 2 секунд; размер до 40 МБ.
- XML, собранный в ВМ из пресета «Офис», проходит `Validate-Unattend.ps1`.

## Заметки исполнителя
