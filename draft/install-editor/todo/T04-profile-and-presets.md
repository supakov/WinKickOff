# T04. Профиль JSON, пресеты, миграция, сравнение

Статус: in-progress (25.09.2026: модель, загрузка и сохранение созданы). Этап 2. Зависимости: T02.

## Цель

Реализовать `core/profile.py` по `03-data-model.md`, раздел 4, и пресеты как файлы.

## Шаги

1. `Profile` с разделами `meta`, `install`, `languages`, `accounts`, `rules`, `unknown`.
2. `Profile.from_catalog(catalog)`: все правила с `default`, параметры с умолчаниями.
3. `Profile.load(path, catalog) -> (Profile, warnings)`: дополнение новыми правилами, `unknown`,
   миграция формата 1 → 2 по таблице `config → rules`.
4. `Profile.save(path)`: порядок ключей, отступ 2, `ensure_ascii=False`.
5. `Profile.diff(other) -> list[Difference]`.
6. `profiles/preset-office.json` (= каталог по умолчанию) и `preset-strict.json` (контролируемый
   доступ к папкам, SmartScreen Block, ASR prevalence в блокировку, NetBIOS выключен, VBScript удалён).
7. `tests/test_profile.py`.

## Критерии приёмки

- Цикл сохранения и загрузки даёт равный объект; пресет «Офис» равен `from_catalog`.
- Неизвестное правило переживает цикл; новое правило каталога добавляется с предупреждением.

## Заметки исполнителя

25.09.2026: `Profile`, `from_catalog`, `load`, `save`, `diff` и тесты созданы; пресеты пока не
записаны в файлы (генерируются из каталога при первом запуске, задача сохранить их в `profiles/`).
