# T01. Каркас проекта, портабельные пути, лог, тесты

Статус: done (25.09.2026: пакет, пути, лог, точка входа, `tools/run-tests.ps1`, тесты путей и исходников;
внешний `Validate-Unattend.ps1` на собранном файле вызывается из `tests/test_build.py`. Проверка в чистом
окружении Python переносится в приёмку T12 в ВМ). Этап 0. Зависимости: нет.

## Цель

Создать структуру `WinKickOff/` по `02-architecture.md`, раздел 2, реализовать `core/paths.py`,
`core/log.py`, точку входа и тестовую инфраструктуру на `unittest`.

## Шаги

1. `WinKickOff/pyproject.toml`: имя `winkickoff`, `requires-python = ">=3.14"`, без зависимостей
   времени выполнения; необязательные группы `build` (pyinstaller) и `dev` (ruff, mypy).
2. Пакет `winkickoff` с подпакетами `core`, `ui`; `__init__.py` с `APP_VERSION`; `__main__.py`.
3. `core/paths.py`: `AppPaths`, `app_paths()`; создание `profiles/`, `output/`, `logs/`.
4. `core/log.py`: `setup_logging(paths)` в `logs/winkickoff.log`, ротация 1 МБ, три файла.
5. `app.py`: DPI-awareness, загрузка каталога, окно; при ошибке каталога окно с сообщением.
6. `tests/`: `test_paths.py` (dev и «замороженный» режим через подмену `sys.frozen`), запуск
   `python -m unittest discover -s tests`.
7. `tools/run-tests.ps1`: запуск тестов и `Validate-Unattend.ps1` на собранном файле (когда появится).
8. `README.md` в `WinKickOff/`: запуск из исходников, тесты, сборка, правила.

## Критерии приёмки

- `python -m winkickoff` открывает окно (в тестах создаётся скрытым).
- Тесты путей зелёные; в пакете нет `os.getcwd()`, `APPDATA`, `winreg` (тест по исходникам).

## Заметки исполнителя

25.09.2026: созданы `pyproject.toml`, пакет, `paths.py`, `log.py`, `app.py`, `__main__.py`, тесты
путей и проверка исходников, `README.md`. Осталось: `tools/run-tests.ps1`, проверка на Python 3.14
в чистом окружении (сделано только на машине заказчика через `py_compile` и `unittest`).
