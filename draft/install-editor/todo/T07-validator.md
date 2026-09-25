# T07. Валидатор профиля и XML

Статус: todo. Этап 3. Зависимости: T06.

## Цель

Реализовать `core/validate.py` с проверками из `01-problem-statement.md`, раздел 3.4, и покрыть
каждую проверку тестом на плохом профиле или плохом XML.

## Шаги

1. `Issue` (level: error/warning/info, field, message, doc).
2. `validate_profile(profile, schema) -> list[Issue]`: имена учётных записей (уникальность,
   зарезервированные, запрещённые символы `\/[]:;|=,+*?<>"@`, длина до 20), хотя бы один
   Administrators, пароль задан (warning), `risk_when` из схемы (warning), `enterprise_only` включён
   (info), `deprecated` включён (info), `ui_language` не равен выбранному языку ISO (warning),
   формат тегов языков, `DeferFeatureUpdatesDays` в 0..365, `InactivityLockSeconds` в 0..599940.
3. `validate_xml(text) -> list[Issue]`: well-formed, пространство имён, комментарии внутри
   `component`, длина `Path` (после декодирования сущностей) и `Description`, пустой `Path`,
   уникальные `Order`, четыре значения International-Core, формат `InputLocale`, `exit 0` в
   PowerShell-командах, `]]>` внутри CDATA, отсутствие длинных тире.
4. Сообщения на русском с указанием поля и ссылкой на справочник.
5. Плохие профили в `tests/profiles/bad-*.json` (по одному на проверку) и плохие XML-строки в тесте.
6. Тесты из `04-testing.md`, раздел core/validate.

## Результат

Валидатор ловит все перечисленные случаи; хороший профиль даёт ноль ошибок.

## Критерии приёмки

- Каждая проверка имеет тест «ловит» и участвует в тесте «не ловит на хорошем».
- Результаты `validate_xml` на эталоне v0.2: ноль ошибок, ноль предупреждений.

## Заметки исполнителя
