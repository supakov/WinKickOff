# Рантайм-шаблоны (задача T05)

Здесь будут лежать неизменяемые части выходного файла:

| Файл | Содержание | Слоты |
|---|---|---|
| `autounattend.template.xml` | Скелет файла ответов v0.2 (обе архитектуры) | `{{header}}`, `{{pe_commands}}`, `{{product_key}}`, `{{will_show_ui}}`, `{{specialize_commands}}`, `{{time_zone}}`, `{{international}}`, `{{oobe}}`, `{{local_accounts}}`, `{{files}}`, `{{profile}}` |
| `Setup-System.runtime.ps1` | Функции Write-Log, Set-Reg, Remove-Reg, Set-ServiceStart, Invoke-Exe, Set-Feature, Remove-Capability, Remove-Apps, trap, шапка лога | `{{blocks_specialize}}`, `{{default_user_block}}`, `{{active_setup}}`, `{{post_oobe_task}}`, `{{config_json}}` |
| `Setup-User.runtime.ps1` | Лог на пользователя | `{{blocks_user}}` |
| `Post-OOBE.runtime.ps1` | Ожидание завершения OOBE, чтение профиля в `$cfg` и `$accounts`, удаление задачи | `{{blocks_post_oobe}}` |

`VERSION` содержит версию каталога и рантайма; профили хранят её как `catalog_version`.
Любая правка шаблона или каталога, меняющая выходной файл, требует новой версии.
