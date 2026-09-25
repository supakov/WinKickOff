# Рантайм-шаблоны

Неизменяемые части выходного файла. Генератор (`winkickoff/core/render.py`) подставляет в слоты
`{{имя}}` блоки включённых правил и данные профиля; всё остальное переносится как есть.

| Файл | Содержание | Слоты |
|---|---|---|
| `autounattend.template.xml` | Скелет файла ответов и скрипт извлечения (ExtractScript) | `header`, `settings`, `files`, `profile_json` |
| `Setup-System.runtime.ps1` | Функции Write-Log, Set-Reg, Remove-Reg, Set-ServiceStart, Invoke-Exe, Set-Feature, Remove-Capability, Remove-Apps; trap; шапка лога | `build_label`, `blocks`, `default_user_section`, `active_setup_section`, `post_oobe_section` |
| `section-default-user.ps1` | Монтирование куста профиля по умолчанию (`$du`) вокруг блоков фазы default-user | `blocks` |
| `section-active-setup.ps1` | Регистрация Active Setup для `Setup-User.ps1` (добавляется, если есть правила фазы user-first-logon) | нет |
| `section-post-oobe-task.ps1` | Задача планировщика для `Post-OOBE.ps1` (добавляется, если есть правила фазы post-oobe) | нет |
| `Setup-User.runtime.ps1` | Лог на пользователя, списки языков ввода из профиля | `input_languages`, `input_fallback`, `transient_languages`, `blocks` |
| `Post-OOBE.runtime.ps1` | Ожидание завершения OOBE, список учётных записей, удаление задачи | `accounts`, `blocks` |

`VERSION` содержит версию каталога и рантайма; профили хранят её как `catalog_version`.
Любая правка шаблона или каталога, меняющая выходной файл, требует новой версии и прогона
`python -m unittest discover -s tests` (тесты сравнивают собранный файл с проверенным v0.2).

Содержимое, которое пишет сам генератор (шапка, маркеры блоков, встроенный профиль), только ASCII:
так файл ответов не зависит от того, как установщик Windows обработает национальные символы.
