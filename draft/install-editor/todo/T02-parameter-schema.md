# T02. Схема параметров

Статус: todo. Этап 1. Зависимости: T01.

## Цель

Описать все параметры `$Config` v0.2 и параметры XML в `schema/parameters.json` по формату из
`03-data-model.md`, раздел 1, и реализовать `core/schema.py` с загрузкой и проверкой целостности.

## Шаги

1. Перенести из `autounattend.xml` каждый ключ `$Config` (45 ключей, включая `AdminAccount` и
   `UserAccount` с `target: derived`) с его комментарием, умолчанием и типом. Группы и порядок
   как в блоке `$Config`: users, media, printing, update, defender, accounts, network, removable,
   logging, privacy, apps, encryption.
2. Добавить XML-параметры (`target: xml`): `edition`, `product_key_mode`, `product_key`,
   `bypass_checks`, `time_zone`, `ui_language`, `system_locale`, `user_locale`, `geo_id`,
   `input_languages`, `protect_your_pc`.
3. Для каждого параметра: `label.ru`, `hint.ru` (одно-два предложения из карточки справочника),
   `doc` со ссылкой на файл и якорь в `docs/reference/`, `flags` (`risk_when`, `enterprise_only`,
   `deprecated`, `advanced`) по разделу 17 справочника.
4. `core/schema.py`: классы `Group`, `Parameter`, `Schema`; `Schema.load(path)`; проверки
   целостности (уникальные id, существующие группы, `default` в `values`, `min <= default <= max`,
   файлы `doc` существуют относительно корня репозитория).
5. Тест синхронизации со шаблоном: множество `target: config` равно множеству ключей `$Config`
   в `autounattend.xml` (до T05 читать из корневого файла по регулярному выражению).
6. Тесты из `04-testing.md`, раздел core/schema.

## Результат

Схема со всеми параметрами v0.2; `Schema.load()` проходит проверки; тест синхронизации зелёный.

## Критерии приёмки

- Ни одного параметра без `hint.ru` и `doc`.
- Комментарии `comment` совпадают с комментариями в `$Config` v0.2 символ в символ (нужно для golden).
- Порядок параметров в схеме равен порядку в `$Config` v0.2.

## Заметки исполнителя
