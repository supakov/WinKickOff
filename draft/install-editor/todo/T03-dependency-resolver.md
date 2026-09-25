# T03. Резолвер зависимостей и порядок применения

Статус: in-progress (25.09.2026: базовый резолвер с каскадом и тестами создан). Этап 2. Зависимости: T02.

## Цель

Реализовать `core/deps.py`: каскадное выключение и включение, конфликты, групповые операции,
порядок применения правил.

## Шаги

1. `Resolver(catalog)`: индексы `requires`, `required_by`, `conflicts`.
2. `disable(profile, rule_id) -> list[Change]`: обход по `required_by`, только включённые.
3. `enable(profile, rule_id) -> list[Change]`: обход по `requires`, затем выключение `conflicts`
   с их каскадом.
4. `set_group(profile, group_id, enabled) -> list[Change]`: по правилам группы и подгрупп.
5. `apply_order(profile) -> list[rule_id]`: включённые правила по фазе, позиции в каталоге и
   устойчивому топосорту по `requires`.
6. `Change(rule_id, enabled, reason)`, где reason: `"user"`, `"requires <id>"`, `"required by <id>"`,
   `"conflicts <id>"`.
7. `tests/test_deps.py` по `04-testing.md`, раздел core/deps.

## Критерии приёмки

- Все тесты резолвера зелёные; повторная операция даёт пустой список изменений.
- `apply_order` на пресете «Офис» воспроизводит порядок разделов v0.2.

## Заметки исполнителя

25.09.2026: реализованы `disable`, `enable`, `set_group`, `apply_order` и тесты на цепочки, конфликты,
идемпотентность. Не проверено: порядок на пресете «Офис» против v0.2 (зависит от T06).
