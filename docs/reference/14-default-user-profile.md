# 14. Профиль пользователя по умолчанию

Раздел 10 `Setup-System.ps1`. Механизм: куст `C:\Users\Default\NTUSER.DAT` монтируется командой
`reg.exe load HKU\UnattendDefault`, в него записываются значения, затем куст выгружается
(`reg.exe unload`, с повтором через 3 секунды при занятости). Windows копирует этот куст в `HKCU`
каждого нового профиля при первом входе. Admin и User создаются в oobeSystem, а их профили при
первом входе, то есть после specialize: они наследуют всё перечисленное.

Особенности метода:

- Это личные настройки пользователя, не политики: пользователь может их изменить в Параметрах,
  и никаких серых пунктов нет. Для непрофессионалов это правильные умолчания, а не запрет.
- Уже существующие профили (при повторном запуске скрипта на настроенной системе) не затрагиваются.
- Если `reg load` не удался (куст занят), раздел пропускается целиком с ERROR в логе; остальные
  разделы не зависят от него.
- Строка `[gc]::Collect()` перед выгрузкой освобождает дескрипторы реестра PowerShell, иначе
  `reg unload` вернёт «доступ запрещён».

Обозначение `DU` = `HKU\UnattendDefault` (после входа: `HKCU`).

## Безусловные значения

| Ключ (относительно DU) | Значение | Эффект | Различия версий |
|---|---|---|---|
| `Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\HideFileExt` | 0 | Расширения файлов видны: `счёт.pdf.exe` не притворится PDF. Главная настройка безопасности этого раздела | Все версии; умолчание 1 |
| `...\Explorer\Advanced\ShowSyncProviderNotifications` | 0 | Нет рекламы OneDrive и Microsoft 365 в проводнике | Win10 1607+ |
| `Control Panel\International\Geo\Nation` | 241 | Регион «Украина» (GeoID) | Все |
| `Control Panel\International\Geo\Name` | UA | То же, двухбуквенный код (Windows 10 1803+ читает его в первую очередь) | 1803+ |
| `Control Panel\International\User Profile\HttpAcceptLanguageOptOut` | 1 | Браузеры не сообщают сайтам список языков пользователя (уменьшает отпечаток) | Win10+ |

Регион влияет на Store (какие приложения и цены показывать), на формат «Погода» и на предложения
контента. Он не меняет язык интерфейса и не связан с часовым поясом.

## Значения по условию DisableConsumerContent

| Ключ | Значение | Эффект |
|---|---|---|
| `...\ContentDeliveryManager\ContentDeliveryAllowed` | 0 | Канал доставки контента выключен |
| `...\FeatureManagementEnabled` | 0 | Нет «экспериментов» с функциями |
| `...\OemPreInstalledAppsEnabled` | 0 | Нет предустановок производителя |
| `...\PreInstalledAppsEnabled` | 0 | Нет предустановок Microsoft |
| `...\PreInstalledAppsEverEnabled` | 0 | Флаг «уже ставили» сброшен |
| `...\SilentInstalledAppsEnabled` | 0 | Store не ставит приложения тихо (главное значение) |
| `...\SoftLandingEnabled` | 0 | Нет «советов» после обновлений |
| `...\SystemPaneSuggestionsEnabled` | 0 | Нет рекомендаций в меню Пуск |
| `...\RotatingLockScreenOverlayEnabled` | 0 | Нет «интересных фактов» на экране блокировки |
| `...\SubscribedContent-310093Enabled` | 0 | Нет «Что нового» после обновлений |
| `...\SubscribedContent-338387Enabled` | 0 | Нет фактов на экране блокировки |
| `...\SubscribedContent-338388Enabled` | 0 | Нет предложений приложений в Пуске |
| `...\SubscribedContent-338389Enabled` | 0 | Нет советов и подсказок |
| `...\SubscribedContent-338393Enabled`, `-353694Enabled`, `-353696Enabled` | 0 | Нет предложений в Параметрах |
| `...\SubscribedContent-353698Enabled` | 0 | Нет предложений на Timeline |
| `...\UserProfileEngagement\ScoobeSystemSettingEnabled` | 0 | Нет экрана «Завершим настройку устройства» после входа |
| `...\Explorer\Advanced\Start_IrisRecommendations` | 0 | Нет рекомендаций в Пуске (Windows 11 22H2+) |
| `...\Explorer\Advanced\Start_AccountNotifications` | 0 | Нет напоминаний про учётную запись Microsoft в Пуске (23H2+) |
| `...\AdvertisingInfo\Enabled` | 0 | Рекламный идентификатор выключен для пользователя |
| `...\Privacy\TailoredExperiencesWithDiagnosticDataEnabled` | 0 | Нет «персонализированных предложений» по диагностике |

Кросс-связи: именно эти значения делают на Pro то, что политика `DisableWindowsConsumerFeatures`
делает на Enterprise. Раздел «Рекомендации» в меню Пуск Windows 11 остаётся (файлы и последние
документы), но без рекламы приложений.

## Значения по другим условиям

| Условие | Ключ | Значение | Эффект |
|---|---|---|---|
| DisableWidgetsAndNews | `...\Explorer\Advanced\TaskbarDa` | 0 | Кнопка виджетов скрыта (дублирует политику Dsh) |
| DisableCopilotAndRecall | `...\Explorer\Advanced\ShowCopilotButton` | 0 | Кнопка Copilot скрыта (23H2) |
| DisableCopilotAndRecall | `Software\Policies\Microsoft\Windows\WindowsCopilot\TurnOffWindowsCopilot` | 1 | Пользовательская политика отключения Copilot: единственный уровень, где она действует |
| DisableAutoRun | `...\Explorer\AutoplayHandlers\DisableAutoplay` | 1 | Нет диалога автозапуска для носителей |

## Что намеренно не задано

Тема (тёмная/светлая), обои, выравнивание панели задач, классическое контекстное меню, показ
скрытых файлов, отключение анимаций: всё это дело вкуса пользователя, а не базового образа.
При необходимости добавляется как отдельный профиль конструктора «косметика».

## Проверка и откат

- Проверка до входа: `reg load HKU\Test C:\Users\Default\NTUSER.DAT`, посмотреть значения, `reg unload HKU\Test`.
- Проверка после входа: `Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced -Name HideFileExt`.
- Откат для пользователя: Параметры или `Set-ItemProperty` в HKCU; для будущих пользователей: те же
  ключи в кусте Default.
