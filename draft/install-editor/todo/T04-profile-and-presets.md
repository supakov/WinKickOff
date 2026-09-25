# T04. Профиль JSON и пресеты

Статус: todo. Этап 1. Зависимости: T02, T03.

## Цель

Реализовать `core/profile.py`: объект профиля, загрузку и сохранение JSON по формату
`03-data-model.md`, раздел 3, миграцию, сравнение, и `core/presets.py` с пресетами «Офис» и «Строгий».

## Шаги

1. Класс `Profile` с разделами `install`, `languages`, `accounts`, `config`, `apps_to_remove`,
   `asr_rules`, `unknown` и метаданными (`format_version`, `template_version`, `name`, `author`,
   `created`, `modified`, `comment`).
2. `Profile.defaults(schema)`: из умолчаний схемы и справочников.
3. `Profile.load(path, schema)`: JSON → объект; недостающие ключи из умолчаний с предупреждениями;
   неизвестные в `unknown`; `template_version` старше текущей → `migrate()`.
4. `Profile.save(path)`: порядок ключей по схеме, отступ 2, UTF-8, `ensure_ascii=False`.
5. `Profile.diff(other) -> list[Change]` с путём параметра, старым и новым значением.
6. Вычисляемые `AdminAccount`/`UserAccount` из `accounts`.
7. `core/presets.py`: «Офис» (= умолчания), «Строгий» (`ControlledFolderAccess=1`,
   `SmartScreenLevel='Block'`, ASR prevalence → 1, `DisableNetBIOS=true`, `RemoveVBScript=true`).
8. Тесты из `04-testing.md`, раздел core/profile; фикстуры профилей в `tests/profiles/`.

## Результат

Цикл load/save воспроизводит объект; пресеты доступны; diff работает.

## Критерии приёмки

- Профиль «Офис», сохранённый и загруженный, равен `Profile.defaults()`.
- Профиль с неизвестным ключом сохраняет его.
- Файл профиля читается человеком (ключи в порядке схемы, кириллица не экранирована).

## Заметки исполнителя
