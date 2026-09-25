# 12. Телеметрия, реклама и предустановки, Copilot и Recall, виджеты, веб-поиск

Раздел 8 `Setup-System.ps1` плюс связанные значения в профиле по умолчанию (раздел 14).
Это не косметика: каждый пункт либо уменьшает отправку данных наружу, либо убирает канал, через
который на ПК появляются нежелательные приложения и ссылки.

## MinimalTelemetry

- Значение: `$true`.
- Что делает:

| Ключ | Значение | Эффект |
|---|---|---|
| `Pol\DataCollection\AllowTelemetry` | 1 | Уровень диагностических данных «Обязательные» (минимум для Pro; 0 «Выкл» действует только на Enterprise/Education) |
| `Pol\DataCollection\DoNotShowFeedbackNotifications` | 1 | Windows не просит оценить систему |
| `Pol\DataCollection\AllowDeviceNameInDiagnosticData` | 0 | Имя ПК не отправляется |
| `Pol\AdvertisingInfo\DisabledByGroupPolicy` | 1 | Рекламный идентификатор выключен для всех пользователей |
| `Pol\Windows Error Reporting\Disabled` | 1 | Отчёты о сбоях не отправляются в Microsoft; локальные события 1000/1001 в журнале Application остаются |
| `Pol\System\PublishUserActivities` | 0 | История действий (Timeline) не собирается |
| `Pol\System\UploadUserActivities` | 0 | И не отправляется |
| служба `DiagTrack` | Start = 3 (вручную) | Не отключена (4): служба нужна оценке совместимости для обновлений функций и отчётам Defender о заблокированных угрозах |
| задачи планировщика | отключены | `Customer Experience Improvement Program\Consolidator`, `...\UsbCeip`, `Feedback\Siuf\DmClient`, `...\DmClientOnScenarioDownload` |

- Ожидаемый эффект: минимальный уровень отправки данных, доступный на Pro, без ущерба для
  обновлений и Defender. Переключатель «Необязательные диагностические данные» в Параметрах серый.
- Кросс-связи:
  - Оригинальный файл отключал DiagTrack (4) и задачи Application Experience (Compatibility Appraiser),
    что мешало предложениям обновлений функций; здесь они оставлены ради `DeferFeatureUpdatesDays`
    (раздел 06). Критик подтвердил, что задачи Appraiser на сборке 26200 отсутствуют под старыми именами.
  - Windows Error Reporting отключён: дампы для разработчиков (`LocalDumps`) не затронуты; окно
    «Программа перестала работать» появляется, отчёт не уходит.
- Различия версий: значение `AllowTelemetry=0` на Windows 10/11 Pro трактуется как 1. В Windows 11
  названия уровней: 1 «Обязательные», 3 «Необязательные». Задачи CEIP в 24H2 присутствуют, но
  `Consolidator` может отсутствовать на части сборок (WARN в логе ожидаем).
- Проверка: Параметры → Конфиденциальность → Диагностика: «управляется организацией»;
  `Get-Service DiagTrack | Select StartType` → Manual; `schtasks /Query /TN "\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip"` → Disabled.
- Откат: удалить значения; `Set-Service DiagTrack -StartupType Automatic`; `schtasks /Change /Enable`.

## DisableConsumerContent

- Значение: `$true`.
- Что делает: в `Pol\CloudContent`: `DisableWindowsConsumerFeatures = 1`, `DisableSoftLanding = 1`,
  `DisableCloudOptimizedContent = 1`, `DisableConsumerAccountStateContent = 1`,
  `DisableThirdPartySuggestions = 1`; `Pol\Windows Chat\ChatIcon = 3` (скрыт);
  `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Communications\ConfigureChatAutoInstall = 0`.
  Плюс 17 значений `ContentDeliveryManager` и ещё пять в профиле по умолчанию (раздел 14).
- Ожидаемый эффект: Store не ставит тихо TikTok, Candy Crush и подобное; в меню Пуск и на экране
  блокировки нет рекламы и «советов»; нет автоустановки Teams (личного); нет «Завершим настройку
  устройства» после входа.
- Кросс-связи: главный рабочий механизм на Pro это значения `ContentDeliveryManager` в профиле
  пользователя (раздел 14), а не политики. Политики `DisableWindowsConsumerFeatures`,
  `DisableSoftLanding`, `DisableThirdPartySuggestions` действуют только на Enterprise/Education и на Pro
  игнорируются; они оставлены как безвредные на случай других редакций.
  `DisableCloudOptimizedContent` (Windows 10 20H2+/Windows 11) и `DisableConsumerAccountStateContent`
  (Windows 11 22H2+) на Pro работают.
- Различия версий: `Windows Chat` и `ConfigureChatAutoInstall` относятся к Windows 11 21H2-22H2
  (значок чата Teams); в 23H2+ его нет, значения безвредны. На 24H2 без изменений.
- Проверка: после установки в меню Пуск нет закреплённых сторонних приложений; Параметры →
  Персонализация → Экран блокировки без «интересных фактов».
- Откат: удалить значения; предустановки вернутся при следующем обращении Store к каналу подписок.

## DisableCopilotAndRecall

- Значение: `$true`.
- Что делает:
  - `Pol\WindowsCopilot\TurnOffWindowsCopilot = 1` (машинная копия; действует только на 23H2 с Copilot
    Preview) и та же политика в профиле по умолчанию (раздел 14), где она действительно применяется;
  - `Pol\WindowsAI\DisableAIDataAnalysis = 1`: Recall (снимки экрана для «памяти» ПК) выключен;
  - `Pol\WindowsAI\AllowRecallEnablement = 0`: пользователь не может включить Recall сам;
  - `Pol\WindowsAI\DisableClickToDo = 1`: Click to Do (действия по содержимому экрана) выключен;
  - `Disable-WindowsOptionalFeature -FeatureName Recall`, если компонент включён;
  - приложение Copilot (`Microsoft.Copilot`, `Microsoft.Windows.Ai.Copilot.Provider`) удаляется
    через `$AppsToRemove` (раздел 13); кнопка на панели задач скрыта в профиле по умолчанию.
- Ожидаемый эффект: ни один ИИ-компонент не делает снимки экрана и не отправляет содержимое
  документов в облако; кнопки Copilot нет.
- Кросс-связи: Recall и Click to Do существуют только на Copilot+ PC (NPU) с 24H2; на обычных ПК
  политики безвредны и заранее защищают от появления функций после обновления. Удаление приложения
  Copilot через Store обратимо пользователем (Store сохранён).
- Различия версий: `TurnOffWindowsCopilot` появился в 23H2, в 24H2 объявлен устаревшим (Copilot стал
  обычным приложением). `DisableAIDataAnalysis` с 24H2, `AllowRecallEnablement` и `DisableClickToDo`
  с обновлений 2025 года. Компонент `Recall` есть только в 24H2+.
- Проверка: `Get-WindowsOptionalFeature -Online -FeatureName Recall` → Disabled или отсутствует;
  `Get-AppxPackage -AllUsers Microsoft.Copilot` пусто.
- Откат: удалить значения; установить Copilot из Store.

## DisableWidgetsAndNews

- Значение: `$true`.
- Что делает: `HKLM\SOFTWARE\Policies\Microsoft\Dsh\AllowNewsAndInterests = 0` (виджеты Windows 11);
  `Pol\Windows Feeds\EnableFeeds = 0` (лента «Новости и интересы» Windows 10); в профиле по умолчанию
  `Explorer\Advanced\TaskbarDa = 0` (кнопка виджетов скрыта).
- Ожидаемый эффект: нет кнопки виджетов и панели с новостями, погодой и рекламой MSN; фоновый
  процесс `Widgets.exe` не запускается.
- Кросс-связи: панель виджетов это WebView2 с контентом MSN, то есть постоянно открытая веб-страница
  с рекламой на каждом ПК. Её отключение убирает и канал доставки вредоносной рекламы (malvertising).
  Пакет `MicrosoftWindows.Client.WebExperience` не удаляется (системный).
- Различия версий: `Dsh` политика с Windows 11 21H2, работает на Pro. `Windows Feeds` для
  Windows 10 20H1+. На 24H2 без изменений.
- Проверка: Параметры → Персонализация → Панель задач: «Виджеты» серый и выключен.
- Откат: удалить значения.

## DisableWebSearchInStart

- Значение: `$true`.
- Что делает: `Pol\Explorer\DisableSearchBoxSuggestions = 1` (нет результатов Bing в поиске меню Пуск);
  `Pol\Windows Search\AllowCortana = 0`; `Pol\Windows Search\DisableWebSearch = 1`.
- Ожидаемый эффект: поиск в меню Пуск ищет только приложения, файлы и параметры; ничего не
  отправляется в Bing при каждом нажатии клавиши; нет «рекомендуемых» веб-результатов.
- Кросс-связи: Cortana в Windows 11 удалена (2023), политика безвредна. Поиск в проводнике и
  индексирование (`WSearch`) не затронуты: оригинальный файл переводил службу индексирования в
  ручной режим, что ломало поиск в Outlook; здесь она не трогается.
- Различия версий: `DisableSearchBoxSuggestions` с Windows 10 2004, действует на Pro. `DisableWebSearch`
  из старого набора Windows 8.1/10, на 11 частично дублирует первую. На 24H2 без изменений.
- Проверка: поиск в Пуске по слову «погода» не показывает веб-результатов.
- Откат: удалить значения.

## LongPathsEnabled (безусловно)

- Что делает: `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled = 1`.
- Эффект: программы с манифестом `longPathAware` (PowerShell 7, Git, современные архиваторы) работают
  с путями длиннее 260 символов. Проводник и старые программы ограничение сохраняют.
- Различия версий: Windows 10 1607+. Безвредно.
- Откат: значение 0.
