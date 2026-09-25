# T01. Каркас проекта и портабельные пути

Статус: todo. Этап 0. Зависимости: нет.

## Цель

Создать структуру пакета `install_editor`, настроить инструменты качества и тесты, реализовать
единственный источник путей `core/paths.py`, чтобы все последующие задачи опирались на готовый каркас.

## Шаги

1. Создать `draft/install-editor/app/` (корень кода) со структурой из `02-architecture.md`, раздел 2:
   пакет `install_editor` с подпакетами `core`, `ui`, каталоги `schema`, `templates`, `resources`, `tests`, `tools`.
2. `pyproject.toml`: имя `install-editor`, `requires-python = ">=3.14"`, зависимости для разработки
   `pytest`, `pytest-cov`, `ruff`, `mypy`, `pyinstaller`; настройки `ruff` (line-length 100) и `mypy` (strict для `core`).
3. `core/paths.py`: `AppPaths` и `app_paths()` по образцу из архитектуры; создание `profiles/`, `output/`, `logs/`.
4. `core/log.py`: логирование в `logs/editor.log` с ротацией (1 МБ, 3 файла), формат с временем и уровнем.
5. `app.py` и `__main__.py`: создание `tk.Tk()`, заголовок с версией, пустое окно 900×600; DPI-awareness
   через `ctypes.windll.shcore.SetProcessDpiAwareness(1)` до создания Tk, в try/except.
6. `install_editor/version.py`: `APP_VERSION = "0.1.0"`.
7. `tests/conftest.py`: фикстура `app_root(tmp_path)` с подменой `sys.frozen`/`sys.executable`.
8. `tests/test_paths.py`: тесты из `04-testing.md`, раздел core/paths.

## Результат

`python -m install_editor` открывает пустое окно; `pytest -q` зелёный; `ruff check` и `mypy` без ошибок.

## Критерии приёмки

- В «замороженном» режиме `root` равен папке exe; в dev-режиме корню кода.
- Повторный вызов `app_paths()` не падает, папки существуют.
- Нет обращений к `os.getcwd()`, `%APPDATA%`, реестру во всём пакете (тест grep по исходникам).

## Заметки исполнителя

(заполняется при выполнении: дата, отклонения, проблемы)
