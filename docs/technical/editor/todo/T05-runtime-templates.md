# T05. Рантайм-шаблоны XML и PowerShell

Статус: done (25.09.2026). Этап 2. Зависимости: T02. Отличие от шагов: вместо отдельных слотов XML
один слот `settings`, который генератор заполняет целиком; фазы Setup-System собираются из секций
`section-*.ps1`; `VERSION` = 0.3. Список слотов: `WinKickOff/templates/README.md`.

## Цель

Вынести из файла v0.2 всё, что не является правилом, в `templates/`: скелет XML со слотами,
рантайм трёх скриптов (функции, обработка ошибок, шапки, монтирование куста, ожидание OOBE).

## Шаги

1. `templates/autounattend.template.xml`: структура v0.2 со слотами `{{header}}`, `{{pe_commands}}`,
   `{{product_key}}`, `{{will_show_ui}}`, `{{specialize_commands}}`, `{{time_zone}}`,
   `{{international}}`, `{{oobe}}`, `{{local_accounts}}`, `{{files}}`, `{{profile}}`; обе архитектуры.
2. `templates/Setup-System.runtime.ps1`: `Write-Log`, `Set-Reg`, `Remove-Reg`, `Set-ServiceStart`,
   `Invoke-Exe`, новые обёртки `Set-Feature`, `Remove-Capability`, `Remove-Apps`, `trap`, HKU-диск,
   шапка лога; слоты `{{blocks_specialize}}`, `{{default_user_block}}` (с монтированием куста вокруг
   `{{blocks_default_user}}`), `{{active_setup}}`, `{{post_oobe_task}}`, `{{config_json}}`.
3. `templates/Setup-User.runtime.ps1`: лог на пользователя, слот `{{blocks_user}}`, `exit 0`.
4. `templates/Post-OOBE.runtime.ps1`: ожидание `IMAGE_STATE_COMPLETE`, пауза, чтение профиля,
   слот `{{blocks_post_oobe}}`, перенос `ua.err`, удаление задачи, `exit 0`.
5. `templates/VERSION` = `0.2`; `templates/README.md` со списком слотов.
6. Тест: подстановка пустых слотов даёт валидный XML и разбираемые скрипты.

## Критерии приёмки

- Ни один фрагмент рантайма не содержит логики правил.
- Скрипты рантайма разбираются PowerShell 5.1 (тест через `pscheck`, пропуск без PowerShell).

## Заметки исполнителя
