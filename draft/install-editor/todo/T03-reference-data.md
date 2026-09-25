# T03. Справочники: приложения, правила ASR, раскладки, часовые пояса

Статус: todo. Этап 1. Зависимости: T02.

## Цель

Вынести списки, которые в v0.2 зашиты в скрипт, в файлы данных с пояснениями для интерфейса.

## Шаги

1. `schema/apps.json`: 33 удаляемых приложения из `$AppsToRemove` в том же порядке, с полями из
   `03-data-model.md`, раздел 2; тексты `title.ru` и `reason.ru` из таблицы `docs/reference/13-services-apps.md`.
   Отдельный массив `keep` для сохраняемых пакетов с `keep_reason.ru`.
2. `schema/asr_rules.json`: 17 правил из `$AsrRules` плюс правило LSASS с `default_mode: 0`;
   поля из модели данных; тексты из таблицы `docs/reference/07-defender.md`.
3. `resources/keyboards.json`: минимум `en-US`, `uk-UA` (расширенная и обычная раскладки),
   `ru-UA` (transient), `ru-RU`, `en-GB`, `pl-PL`, `de-DE`; данные из документации Microsoft
   (Default input profiles); поле `transient: true` только у языков без LCID.
4. `resources/timezones.json`: полный список из `tzutil /l` текущей Windows (снять один раз,
   только чтение), с подписями на русском; `FLE Standard Time` первым в рекомендуемых.
5. `core/schema.py`: загрузка справочников, доступ по имени/GUID/тегу.
6. Тесты: порядок apps совпадает с `$AppsToRemove` v0.2; GUID ASR совпадают с `$AsrRules`;
   у `ru-UA` нет LCID; все `min_build` в ASR это строки вида `1709`.

## Результат

Четыре файла данных и их загрузчик; тесты соответствия v0.2.

## Критерии приёмки

- Сумма `default_remove: true` в apps равна 33; порядок равен v0.2.
- Сумма правил с `default_mode > 0` равна 17 и режимы равны v0.2.

## Заметки исполнителя
