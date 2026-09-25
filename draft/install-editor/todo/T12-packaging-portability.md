# T12. Сборка PyInstaller и проверка портабельности

Статус: todo. Этап 5. Зависимости: T11.

## Цель

Получить портабельную сборку `dist/InstallEditor/` и подтвердить чек-лист портабельности
из `04-testing.md`, раздел 4, в виртуальной машине.

## Шаги

1. `tools/build.ps1`: создание venv на Python 3.14, установка зависимостей, `pyinstaller --noconsole
   --onedir --name InstallEditor --add-data schema;schema --add-data templates;templates
   --add-data resources;resources --add-data docs/reference;docs/reference install_editor/__main__.py`;
   копирование `README-user.md` в `dist/InstallEditor/`; упаковка в zip с версией в имени.
2. Проверить, что `app_paths()` в сборке находит данные в `_internal` и создаёт папки рядом с exe.
3. Значок приложения (`resources/app.ico`), сведения о версии в exe (`version.txt` для PyInstaller).
4. Если PyInstaller не поддерживает 3.14: зафиксировать в заметках и собрать на 3.13, код не менять.
5. Прогнать чек-лист портабельности в ВМ Windows 11 (чистая, без Python): пункты 1-6.
   Снимки реестра `HKCU\Software` и папок `%APPDATA%`, `%LOCALAPPDATA%` до и после запуска.
6. Проверить поведение SmartScreen на неподписанном exe; описать в README-user.md, как запустить.
7. Размер сборки и время старта записать в заметки.

## Результат

zip `InstallEditor-<версия>.zip`, чек-лист портабельности заполнен, замечания устранены.

## Критерии приёмки

- Все шесть пунктов чек-листа выполнены в ВМ.
- Старт до 2 секунд, размер до 40 МБ.
- `output/autounattend.xml`, собранный в ВМ из пресета «Офис», равен golden.

## Заметки исполнителя
