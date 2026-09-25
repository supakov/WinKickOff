# 02. Архитектура WinKickOff

Редакция 0.2 от 25.09.2026.

## 1. Принципы

1. Каталог правил (`rules/*.toml`) это единственный источник истины о том, что умеет делать
   установка. Интерфейс, генератор, валидатор, описания и тесты читают его; код правил не содержит.
2. Рантайм отделён от правил: неизменяемые фрагменты PowerShell и XML лежат в `templates/`.
3. Логика без интерфейса: `core/` не импортирует tkinter и тестируется `unittest`.
4. Одна функция путей `app_paths()`; никто не собирает пути сам.
5. Никаких зависимостей за пределами стандартной библиотеки в самом приложении.
6. Любая ошибка данных (правило, профиль, шаблон) превращается в сообщение с указанием файла и
   идентификатора; приложение не падает.

## 2. Структура каталога `WinKickOff/`

```
WinKickOff/
  README.md                  как запустить из исходников, тесты, сборка
  pyproject.toml             метаданные, requires-python >= 3.14, настройки ruff/mypy
  winkickoff/
    __init__.py              APP_VERSION
    __main__.py              python -m winkickoff
    app.py                   старт: пути, лог, каталог, окно
    core/
      paths.py               AppPaths, app_paths()
      log.py                 логирование в logs/
      catalog.py             модели Rule, Action, Group, Param; загрузка TOML; проверка целостности
      deps.py                Resolver: enable/disable с каскадом, порядок применения
      profile.py             Profile: состояние правил и параметров, данные установки; JSON
      render.py              сборка скриптов и XML из рантайма и включённых правил
      validate.py            проверки профиля и XML; Issue
      importer.py            профиль из XML (встроенный) или из файла v0.2 (разбор действий)
      pscheck.py             проверка синтаксиса через powershell.exe, если доступен
      i18n.py                строки интерфейса и переводы правил
    ui/
      main_window.py         окно, меню, три области, горячие клавиши
      rule_tree.py           дерево с флажками, поиск, фильтр
      detail_panel.py        описание правила, таблица действий, редактор параметров
      data_forms.py          формы узлов данных: установка, учётные записи, языки
      dialogs.py             о программе, сравнение профилей, список каскада
  rules/
    groups.toml              дерево групп
    NN-<направление>.toml    правила по направлениям, порядок файлов = порядок применения
    lang/uk.toml             переводы строк правил
  templates/
    autounattend.template.xml      скелет с маркерами слотов
    Setup-System.runtime.ps1       функции, trap, шапка, монтирование куста
    Setup-User.runtime.ps1         шапка и лог скрипта первого входа
    Post-OOBE.runtime.ps1          ожидание OOBE, чтение профиля, завершение
    VERSION                        версия каталога и рантайма (0.2)
  resources/
    strings.ru.json, strings.uk.json   строки интерфейса
    keyboards.json, timezones.json     справочники
  profiles/
    preset-office.json, preset-strict.json
  tests/
    test_catalog.py, test_deps.py, test_profile.py, test_render.py, test_validate.py,
    test_coverage_v02.py (семантический golden), test_ui_smoke.py
  tools/
    build.ps1, run-tests.ps1
```

## 3. Модель данных в памяти

```
Catalog
  groups: dict[id, Group(id, parent, title, order, summary)]
  rules:  dict[id, Rule]
  order:  list[id]              порядок по файлам и позиции
Rule
  id, group, phase, title, level, default, requires[], conflicts[], tags[]
  summary, effect, risk, versions, verify, rollback, doc
  params: dict[name, Param(type, default, min, max, values, title)]
  actions: list[Action(type, fields...)]
Profile
  meta: format_version, catalog_version, name, author, created, modified, comment
  install: edition, product_key_mode, product_key, time_zone
  languages: ui_language, system_locale, user_locale, geo_id, input[]
  accounts: [Account(name, display_name, group, description, password)]
  rules: dict[id, RuleState(enabled, params: dict)]
  unknown: dict
Resolver(catalog)
  disable(profile, id) -> list[Change]
  enable(profile, id)  -> list[Change]
  set_group(profile, group_id, enabled) -> list[Change]
  apply_order(enabled_ids) -> list[id]    фаза, файл, топосорт по requires
Renderer(catalog, templates)
  build(profile) -> BuildResult(xml_text, scripts: dict[name, text], rule_ids: list)
Validator
  catalog(catalog) -> list[Issue]
  profile(profile, catalog) -> list[Issue]
  xml(text) -> list[Issue]
```

## 4. Портабельные пути

```python
# core/paths.py
import sys
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class AppPaths:
    root: Path      # папка exe (сборка) или WinKickOff/ (исходники)
    data: Path      # rules/, templates/, resources/ (в сборке: root/_internal)
    profiles: Path
    output: Path
    logs: Path

def app_paths() -> AppPaths:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        data = Path(getattr(sys, "_MEIPASS", root / "_internal"))
    else:
        root = Path(__file__).resolve().parents[2]
        data = root
    paths = AppPaths(root, data, root / "profiles", root / "output", root / "logs")
    for p in (paths.profiles, paths.output, paths.logs):
        p.mkdir(parents=True, exist_ok=True)
    return paths
```

Правила те же, что в 0.1: никаких `os.getcwd()`, `%APPDATA%`, `%TEMP%`; временные файлы в
`logs/tmp/`; `settings.json` рядом с exe.

## 5. Поток данных

```
rules/*.toml ──> Catalog ──┬──> Validator.catalog
                           ├──> Resolver
profiles/*.json ──> Profile┴──> Renderer ──> XML + скрипты ──> Validator.xml ──> файл
templates/* ───────────────────────┘                 └──> pscheck (необязательно)
```

1. Старт: загрузка каталога и проверка целостности; при ошибке окно с сообщением и выход.
2. Профиль: из пресета или файла; неизвестные правила в `unknown`, новые с `default`.
3. Дерево строится по группам; состояния из профиля; поиск фильтрует по индексу строк, построенному
   при загрузке каталога (идентификатор, название, теги, резюме, строки действий).
4. Изменение флажка: `Resolver.disable/enable` → список изменений → обновление узлов дерева и
   строки состояния; профиль помечается изменённым.
5. Сборка: `Validator.profile` → стоп при ошибках; `Renderer.build` → `Validator.xml` →
   `pscheck` (фон) → запись файла.

## 6. Генератор

Порядок правил: `Resolver.apply_order` возвращает включённые правила, отсортированные по фазе,
затем по позиции в каталоге, с устойчивой топологической поправкой: правило не раньше своих `requires`.

Сборка по фазам:

| Фаза | Куда попадает | Инфраструктура (включается по наличию правил) |
|---|---|---|
| windowspe | `RunSynchronous` в компоненте Setup (обе архитектуры) | нет |
| specialize-xml | `RunSynchronous` в Deployment, после команды извлечения, до запуска скрипта | извлечение скриптов и запуск `Setup-System.ps1` (всегда, если есть правила specialize или default-user) |
| specialize | блоки в `Setup-System.ps1` | рантайм: функции, trap, лог |
| default-user | блоки внутри `reg load`/`reg unload` куста в `Setup-System.ps1` | монтирование куста |
| user-first-logon | блоки в `Setup-User.ps1` | регистрация Active Setup в `Setup-System.ps1` |
| post-oobe | блоки в `Post-OOBE.ps1` | задача планировщика из `Setup-System.ps1`; ожидание OOBE в рантайме |
| oobe-xml | элементы `OOBE` и International-Core, учётные записи | нет |

Преобразование действий в PowerShell (фаза specialize, default-user, user-first-logon, post-oobe):

| Тип | Строка |
|---|---|
| reg | `Set-Reg -Path '<path>' -Name '<name>' -Type <kind> -Value <value> -Why '<why>'` (для `DU:` путь через `$du`) |
| reg-remove | `Remove-Reg -Path '<path>' -Name '<name>'` |
| service | `Set-ServiceStart -Name '<name>' -Start <n>` |
| exe | `Invoke-Exe '<file>' @('<arg>', ...)` |
| feature | `Set-Feature -Name '<name>' -State <Enabled|Disabled>` (обёртка над DISM в рантайме) |
| capability | `Remove-Capability -Pattern '<pattern>'` |
| appx | `Remove-Apps @('<name>', ...)` |
| ps | текст как есть, с отступом |

Каждый блок начинается строкой `# [<rule.id>] <title>`; значения параметров подставляются по имени
`{param}` с приведением типа. Строки экранируются для PowerShell (удвоение одинарных кавычек).

XML-действия: `xml-pe-command` и `xml-specialize-command` добавляют `RunSynchronousCommand` с
`Order` по порядку; `xml-oobe` добавляет элемент с именем и значением в блок `OOBE`. Данные
профиля (ключ, часовой пояс, языки, учётные записи) подставляются в фиксированные слоты.

Профиль встраивается в `Extensions/Profile` как JSON внутри CDATA. Валидатор считает длины `Path`
по распакованному тексту.

## 7. Резолвер зависимостей

- `required_by` строится один раз при загрузке (обратный индекс `requires`).
- `disable(id)`: обход в ширину по `required_by`, выключение каждого включённого; результат:
  `[Change(id, enabled=False, reason="requires <id>")]`.
- `enable(id)`: обход по `requires`, включение; затем для каждого включённого правила выключение
  его `conflicts` с обходом `required_by`.
- Группа: последовательное применение к правилам группы; изменения объединяются.
- Все операции чистые относительно каталога и меняют только профиль.

## 8. Интерфейс

- `ttk.PanedWindow` горизонтальная: слева `Frame` с полем поиска и `ttk.Treeview` (одна колонка
  `#0` с текстом «☐ Название» или «☑ Название», «◪» для частично включённой группы); справа
  `Frame` с прокручиваемым `Text` (описание) и панелью параметров; снизу `ttk.Treeview` сообщений.
- Щелчок по узлу в зоне первых символов или пробел: переключение через резолвер; изменённые узлы
  перерисовываются; строка состояния показывает число каскадных изменений, щелчок раскрывает список.
- Поиск: при вводе (с задержкой 150 мс) дерево перестраивается из отфильтрованного списка;
  пустой запрос возвращает полное дерево с сохранением состояния раскрытия.
- Описание формируется из данных правила и таблицы действий; ссылка «Подробнее» открывает
  карточку справочника (`os.startfile`), если файл есть в сборке.
- Параметры: виджеты по типу (Spinbox, Combobox, Entry) под описанием; изменение сразу в профиль.
- Узлы данных: «Установка», «Учётные записи», «Языки и регион» открывают формы в правой панели.
- DPI: `SetProcessDpiAwareness(1)` до создания Tk; тема `vista`.

## 9. Сборка

PyInstaller onedir, `--noconsole`, данные `rules`, `templates`, `resources`, `profiles`, и
`docs/reference` из корня репозитория для ссылок «Подробнее». Результат `dist/WinKickOff/`.
