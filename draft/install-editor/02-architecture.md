# 02. Архитектура редактора

## 1. Принципы

1. Схема параметров это единственный источник истины. UI, генератор, валидатор, документация и тесты
   читают `schema/parameters.json`; ни один параметр не описан в коде дважды.
2. Шаблоны отделены от кода. XML-скелет и три PowerShell-скрипта лежат в `templates/` как текстовые
   файлы с явными точками подстановки; редактор не знает PowerShell.
3. Логика без UI. Всё, что можно протестировать без окна (модель, профиль, генератор, валидатор,
   пути), лежит в пакете `core` и не импортирует tkinter.
4. Портабельность через одну функцию `app_paths()`, которая вычисляет корень приложения и все
   рабочие папки; никто больше не собирает пути сам.
5. Отказоустойчивость: любая ошибка чтения профиля, шаблона или записи файла превращается в
   понятное сообщение; приложение не падает.

## 2. Модули

```
install_editor/
  __main__.py            точка входа: python -m install_editor
  app.py                 создание Tk, загрузка схемы, запуск главного окна
  core/
    paths.py             app_paths(): корень, profiles/, output/, logs/, templates/, schema/
    schema.py            загрузка и проверка schema/parameters.json, доступ к параметрам и группам
    profile.py           Profile: значения, загрузка/сохранение JSON, миграция версий, сравнение
    presets.py           встроенные пресеты (Офис, Строгий, Ноутбук) как профили
    render.py            генерация $Config, списков, XML-фрагментов из профиля и шаблонов
    validate.py          проверки профиля и собранного XML; результат: список Issue(level, field, text)
    importer.py          обратный разбор блока $Config из существующего XML (по регулярным выражениям)
    pscheck.py           необязательная проверка синтаксиса скриптов через powershell.exe, если доступен
    i18n.py              строки интерфейса (ru, uk) из resources/strings.*.json
    log.py               настройка логирования в logs/editor.log
  ui/
    main_window.py       окно, меню, дерево групп, панель сообщений
    widgets.py           фабрика виджетов по типу параметра (bool, int, enum, string, list, table)
    pages.py             страницы групп, привязка виджетов к Profile
    accounts_table.py    таблица учётных записей
    languages_table.py   упорядоченный список языков ввода
    apps_list.py         списки приложений с флажками
    asr_table.py         таблица правил ASR с режимами
    dialogs.py           о программе, сравнение профилей, подсказка по параметру
  resources/
    strings.ru.json, strings.uk.json
    keyboards.json       справочник языков и раскладок (код, LCID, KLID, подпись)
    timezones.json       список идентификаторов часовых поясов Windows с подписями
schema/
  parameters.json        схема параметров (см. 03-data-model.md)
  apps.json              описание удаляемых и сохраняемых приложений
  asr_rules.json         описание правил ASR
templates/
  autounattend.template.xml
  Setup-System.template.ps1
  Setup-User.template.ps1
  Post-OOBE.template.ps1
  VERSION                версия шаблона (например 0.2)
tests/
  golden/autounattend-v0.2.xml
  profiles/bad-*.json    профили для проверок валидатора
  test_*.py
tools/
  build.ps1              сборка PyInstaller
```

Все каталоги `schema/`, `templates/`, `resources/` упаковываются в сборку как данные и читаются
через `app_paths().templates` и т. д.

## 3. Портабельные пути

```python
# core/paths.py
import sys
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class AppPaths:
    root: Path        # папка с exe (frozen) или корень репозитория (dev)
    data: Path        # упакованные данные: schema/, templates/, resources/ (в сборке: root/_internal)
    profiles: Path    # root/profiles
    output: Path      # root/output
    logs: Path        # root/logs

def app_paths() -> AppPaths:
    if getattr(sys, "frozen", False):            # сборка PyInstaller
        root = Path(sys.executable).resolve().parent
        data = Path(getattr(sys, "_MEIPASS", root / "_internal"))
    else:                                        # запуск из исходников
        root = Path(__file__).resolve().parents[2]
        data = root
    paths = AppPaths(root, data, root / "profiles", root / "output", root / "logs")
    for p in (paths.profiles, paths.output, paths.logs):
        p.mkdir(parents=True, exist_ok=True)
    return paths
```

Правила:

- Никаких `os.getcwd()`: рабочий каталог при запуске с ярлыка непредсказуем.
- Никаких `%APPDATA%`, `%TEMP%` для данных пользователя; временные файлы для проверки PowerShell
  создаются в `logs/tmp/` и удаляются.
- Пути в профиле и настройках хранятся относительно `root`, если лежат внутри него, иначе абсолютно.
- Файл `settings.json` рядом с exe: язык интерфейса, последние профили, размер окна. Отсутствие
  файла или его повреждение равнозначно умолчаниям.

## 4. Поток данных

```
schema/parameters.json ──> Schema ──┐
                                    ├──> Profile (значения) ──> render ──> XML text ──> validate(XML) ──> файл
profiles/*.json ──> Profile ────────┘        │                     ▲
presets ───────────> Profile                 └──> validate(profile) │
templates/*.xml|ps1 ───────────────────────────────────────────────┘
```

1. При старте загружается схема и проверяется её целостность (каждый параметр имеет тип и умолчание,
   каждая группа существует, ссылки на документацию указывают на существующие файлы).
2. Профиль создаётся из умолчаний схемы, затем поверх накладывается JSON.
3. UI привязывает виджеты к полям профиля через `tk.Variable` с обратным вызовом; профиль
   всегда актуален, «грязный» флаг управляет заголовком окна и вопросом при закрытии.
4. Сборка: `validate.profile()` → при ошибках стоп; `render.build()` → `validate.xml()` →
   при ошибках стоп; запись файла в `output/` или по выбранному пути.
5. Импорт: `importer.parse_config_block(xml_text)` возвращает словарь; несопоставленные ключи
   попадают в предупреждения.

## 5. Генерация: точки подстановки в шаблонах

Шаблоны содержат маркеры вида `{{name}}` только в тех местах, которые меняет профиль. Всё остальное
переносится байт в байт. Список маркеров:

| Маркер | Где | Источник |
|---|---|---|
| `{{header_comment}}` | шапка XML | версия шаблона, дата, имя профиля, комментарий |
| `{{product_key}}`, `{{will_show_ui}}` | windowsPE, обе архитектуры | параметры edition, product_key_mode |
| `{{labconfig_commands}}` | windowsPE RunSynchronous | набор флажков обхода; при пустом наборе элемент `RunSynchronous` опускается |
| `{{time_zone}}` | specialize Shell-Setup | параметр |
| `{{input_locale}}`, `{{system_locale}}`, `{{ui_language}}`, `{{user_locale}}` | oobeSystem International-Core | параметры языков |
| `{{oobe_block}}` | oobeSystem OOBE | фиксированный набор, кроме ProtectYourPC (параметр) |
| `{{local_accounts}}` | oobeSystem UserAccounts | таблица учётных записей; порядок элементов как в документации |
| `{{config_block}}` | Setup-System.ps1 | `$Config = @{ ... }` из схемы: имя, значение в синтаксисе PowerShell, комментарий |
| `{{apps_to_remove}}` | Setup-System.ps1 | список `'Name'` с отступом |
| `{{asr_rules}}` | Setup-System.ps1 | строки `'guid' = N   # подпись` |

Правила сериализации значений PowerShell: bool → `$true`/`$false`, int → число, str → `'строка'`
с удвоением одинарных кавычек, список строк → блок с отступом. Порядок ключей `$Config` строго по схеме,
комментарии из схемы, чтобы файл оставался читаемым и воспроизводимым.

## 6. Валидатор

`validate.profile(profile, schema) -> list[Issue]` и `validate.xml(text) -> list[Issue]`.
`Issue` = уровень (error, warning, info), идентификатор параметра или элемента, текст, ссылка на справочник.
Проверки перечислены в 01-problem-statement.md, раздел 3.4. XML-проверки реализуются на `xml.etree`
с пространством имён; длины `Path` считаются по распакованному тексту (после замены `&amp;` на `&`),
как их считает Setup.

## 7. Интерфейс: устройство окна

- `ttk.PanedWindow`: слева `ttk.Treeview` групп, справа `ttk.Notebook` с одной вкладкой на группу
  (строятся при первом обращении), внизу `ttk.Treeview` сообщений валидатора с двойным щелчком
  «перейти к полю».
- Форма группы: сетка `ttk.Frame` с подписью, виджетом, кнопкой «i». Прокрутка через `Canvas`.
- Таблицы (учётные записи, языки, ASR) на `ttk.Treeview` с кнопками Добавить/Удалить/Вверх/Вниз и
  редактированием через диалог, а не in-place (надёжнее в tkinter).
- Длинные операции (проверка PowerShell) в `threading.Thread` с обновлением UI через `after()`.
- Тема `vista`/`winnative`, масштабирование по `tk scaling` для HiDPI (вызов `SetProcessDpiAwareness`
  через `ctypes` до создания Tk).

## 8. Сборка и распространение

- PyInstaller, режим onedir, `--noconsole`, `--name InstallEditor`, данные через `--add-data`
  для `schema`, `templates`, `resources`.
- Результат: `dist/InstallEditor/InstallEditor.exe` плюс `_internal/`. Рядом создаются `profiles/`,
  `output/`, `logs/`, `settings.json` при первом запуске.
- Версия приложения и версия шаблона показываются в «О программе» и пишутся в шапку XML.
- Сборка воспроизводима скриптом `tools/build.ps1`; чек-лист портабельности в 04-testing.md.
- Без установщика: архив zip с папкой.
