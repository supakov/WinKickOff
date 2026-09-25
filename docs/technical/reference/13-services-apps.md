# 13. Службы и удаление приложений

Раздел 9 `Setup-System.ps1`. Принцип: удаляется только то, что не нужно в рабочей группе и либо
расширяет поверхность атаки, либо тянет данные в облако, либо показывает рекламу. Всё, что нужно
для обслуживания системы или офисной работы, остаётся.

## Безусловно: RetailDemo

Служба `RetailDemo` (демонстрационный режим магазина) тип запуска 4. Нужна только витринным ПК.

## RemoveXboxServices

- Значение: `$true`.
- Что делает: службы `XblAuthManager`, `XblGameSave`, `XboxNetApiSvc`, `XboxGipSvc` тип запуска 4;
  `Pol\GameDVR\AllowGameDVR = 0` (запись игр и Game Bar выключены); внутри блока удаления приложений
  дополнительно `MapsBroker` тип запуска 4 (см. известное несоответствие ниже).
- Ожидаемый эффект: нет фоновых служб Xbox Live, нет наложения Game Bar по Win+G, нет записи экрана
  в фоне (которая на слабых ПК заметно грузит систему).
- Кросс-связи: приложения Xbox удаляются в `$AppsToRemove`; без них службы всё равно стартовали бы
  по триггерам. Игры из Store с Xbox Live не работают: на рабочих ПК приемлемо.
- Различия версий: `XboxGipSvc` с Windows 10 1709. На 24H2 без изменений.
- Проверка: `Get-Service Xbl*, XboxNetApiSvc, XboxGipSvc | Select Name, StartType` → Disabled.
- Откат: `Set-Service <имя> -StartupType Manual`; удалить `AllowGameDVR`.

Известное несоответствие версии 0.2: `MapsBroker` (загрузка офлайн-карт для приложения «Карты»)
отключается внутри условия `RemoveBloatApps` при `RemoveXboxServices = $true`, хотя логически
относится к удалению приложения `Microsoft.WindowsMaps`. Работает правильно при значениях по
умолчанию; при `RemoveXboxServices = $false` служба останется включённой без приложения (безвредно).
Исправление запланировано в конструкторе: привязать `MapsBroker` к удалению Maps.

## RemoveBloatApps

- Значение: `$true`. Список в `$AppsToRemove`.
- Где применяется: specialize, SYSTEM, до создания пользовательских профилей.
- Что делает: один раз запрашивает `Get-AppxProvisionedPackage -Online` (приложения, которые
  Windows ставит каждому новому пользователю) и `Get-AppxPackage -AllUsers` (уже установленные
  копии). Для каждого имени из списка: `Remove-AppxProvisionedPackage` (новые пользователи не получат)
  и `Remove-AppxPackage -AllUsers` (существующие копии удаляются). Отсутствующие имена
  пропускаются молча; ошибки пишутся как WARN.
- Ожидаемый эффект: у Admin, User и всех будущих пользователей перечисленных приложений нет.
  Меню Пуск содержит только системные и оставленные приложения.
- Кросс-связи:
  - Удалённые приложения можно вернуть из Store (сохранён). Обновление функций (24H2 → 25H2)
    иногда возвращает часть предустановок; после него список стоит применить повторно.
  - Оригинальный файл запускал удаление задачей при каждом входе, чтобы «бороться» с возвратом;
    здесь удаление однократное и прозрачное.
  - `DisableConsumerContent` (раздел 12) не даёт Store тихо ставить новые рекламные приложения.
- Различия версий: имена пакетов меняются между версиями; приложения, которых нет в образе,
  просто не найдутся. Ниже отмечено, в каких версиях приложение существует.

### Таблица удаляемых приложений

| Имя пакета | Что это | Почему удаляется | Есть в образе |
|---|---|---|---|
| Microsoft.BingSearch | «Поиск в Интернете от Bing» для меню Пуск | Отправляет запросы в Bing, реклама | 24H2+ |
| Microsoft.BingNews | Новости MSN | Реклама, трафик | Win10, 11 до 23H2 |
| Microsoft.BingWeather | Погода MSN | Реклама, местоположение | все |
| Microsoft.GetHelp | «Техническая поддержка» (чат с Microsoft) | Не нужна, канал для мошенничества «поддержка» | все |
| Microsoft.Getstarted | «Советы» | Реклама функций | Win10, 11 до 22H2 |
| Microsoft.WindowsFeedbackHub | Центр отзывов | Телеметрия, не нужен | все |
| Microsoft.Microsoft3DViewer | Просмотр 3D | Не нужно | Win10, 11 до 22H2 |
| Microsoft.MixedReality.Portal | Портал смешанной реальности | Не нужно, устарел | Win10, 11 до 23H2 |
| Microsoft.MicrosoftSolitaireCollection | Пасьянсы с рекламой | Реклама, отвлекает | все |
| Microsoft.GamingApp | Приложение Xbox | Игры, службы Xbox | все |
| Microsoft.XboxApp | Старое приложение Xbox | То же | Win10 |
| Microsoft.XboxGameOverlay, Microsoft.XboxGamingOverlay | Game Bar | Запись экрана в фоне | все |
| Microsoft.XboxIdentityProvider | Вход Xbox Live | Не нужен | все |
| Microsoft.XboxSpeechToTextOverlay | Субтитры Game Bar | Не нужен | все |
| Microsoft.Xbox.TCUI | Интерфейс Xbox Live | Не нужен | все |
| Microsoft.Edge.GameAssist | Game Assist (оверлей Edge в играх) | Не нужен | 24H2+ (2025) |
| Microsoft.WindowsMaps | Карты | Офлайн-карты, служба MapsBroker | все |
| Microsoft.People | Люди (контакты) | Устарело, синхронизация с облаком | Win10, 11 до 23H2 |
| Microsoft.YourPhone | Связь с телефоном | Доступ к SMS и файлам телефона через облако Microsoft | все |
| Microsoft.PowerAutomateDesktop | Power Automate | Средство автоматизации, потенциально для злоупотреблений | Win10 21H2+, 11 |
| Microsoft.Todos | Microsoft To Do | Требует учётную запись Microsoft | все |
| MicrosoftCorporationII.MicrosoftFamily | Семейная безопасность | Требует учётную запись Microsoft | 11 22H2+ |
| Microsoft.Windows.DevHome | Dev Home | Инструмент разработчика, снят с поддержки в 2025 | 11 23H2-24H2 |
| Clipchamp.Clipchamp | Видеоредактор | Облачный сервис, реклама подписки | 11 22H2+ |
| MSTeams | Teams (личный, новый) | Не рабочая версия; рабочий Teams ставится отдельно | 11 23H2+ |
| Microsoft.SkypeApp | Skype | Сервис закрыт в 2025 | Win10, 11 до 23H2 |
| Microsoft.MicrosoftOfficeHub | «Office» (лаунчер M365) | Реклама подписки | все |
| Microsoft.OutlookForWindows | Новый Outlook | Почта через облако Microsoft, синхронизирует пароли IMAP в облако | 11 23H2+ |
| microsoft.windowscommunicationsapps | Почта и Календарь | Заменены новым Outlook, не обновляются | Win10, 11 до 24H2 |
| Microsoft.Copilot | Copilot (приложение) | ИИ-помощник, отправка данных | 11 24H2+ |
| Microsoft.Windows.Ai.Copilot.Provider | Поставщик Copilot | То же | 11 23H2 |
| Microsoft.549981C3F5F10 | Cortana | Удалена Microsoft в 2023 | Win10, 11 до 22H2 |

### Что намеренно сохранено

| Пакет | Почему |
|---|---|
| Microsoft.WindowsStore, Microsoft.StorePurchaseApp | Обновление приложений и компонентов (WebView2, Photos, кодеки), установка программ |
| Microsoft.DesktopAppInstaller | winget: установка программ из командной строки, будущий канал для проекта пользователей |
| Microsoft.Windows.Photos, Microsoft.Paint, Microsoft.ScreenSketch | Просмотр и правка изображений, скриншоты: офисная работа |
| Microsoft.WindowsCalculator, Microsoft.WindowsNotepad, Microsoft.WindowsTerminal | Базовые инструменты |
| Microsoft.WindowsCamera, Microsoft.WindowsSoundRecorder | Видеозвонки, диктофон |
| Microsoft.MicrosoftStickyNotes, Microsoft.WindowsAlarms | Безвредны, используются |
| Microsoft.WindowsScan | Сканирование с МФУ |
| Microsoft.ZuneMusic, Microsoft.ZuneVideo | Медиаплеер и «Кино и ТВ»: кодеки и просмотр видео |
| Microsoft.SecHealthUI | Интерфейс «Безопасность Windows»: без него Defender не настроить |
| Microsoft Edge, EdgeWebView2 | Аварийный браузер и компонент для приложений (Outlook, Teams, установщики) |
| OneDrive | Без учётной записи Microsoft неактивен; удаление скриптами избыточно |
| Microsoft.HEIFImageExtension, Microsoft.WebpImageExtension и другие кодеки | Открытие фото с телефонов |
| Microsoft.LanguageExperiencePack* | Языковые пакеты образа |

- Проверка: `Get-AppxProvisionedPackage -Online | Select DisplayName` не содержит имён из списка;
  `Get-AppxPackage -AllUsers -Name Microsoft.BingWeather` пусто.
- Откат: установить из Store; либо на носителе `Add-AppxProvisionedPackage` из `install.wim`
  (сложно, не рекомендуется).

## RemoveQuickAssist

- Значение: `$true`.
- Что делает: `Remove-WindowsCapability -Online -Name App.Support.QuickAssist*` (компонент Windows 10)
  и `Remove-AppxProvisionedPackage` для `MicrosoftCorporationII.QuickAssist` (Store-версия Windows 11).
- Ожидаемый эффект: приложение «Быстрая помощь» отсутствует.
- Почему: Quick Assist это штатное средство удалённого управления, которое мошенники «техподдержки
  Microsoft» и группы вроде Storm-1811 просят запустить по телефону; для непрофессиональных
  пользователей риск выше пользы. Удалённая поддержка своим администратором должна идти через
  инструмент, который выбирает организация (параметр конструктора).
- Кросс-связи: `DisableRemoteAssistance` (раздел 08) закрывает второй встроенный канал.
  Пользователь может установить Quick Assist обратно из Store: политика запрета установки не задана
  (потребовала бы блокировать Store целиком).
- Различия версий: компонент `App.Support.QuickAssist~~~~0.0.1.0` в Windows 10 1809+ и Windows 11
  21H2; с 22H2 приложение Store. Файл обрабатывает оба варианта.
- Проверка: `Get-WindowsCapability -Online -Name 'App.Support.QuickAssist*'` → NotPresent;
  `Get-AppxPackage -AllUsers MicrosoftCorporationII.QuickAssist` пусто.
- Откат: Store → «Быстрая помощь», или `Add-WindowsCapability -Online -Name App.Support.QuickAssist~~~~0.0.1.0`.
