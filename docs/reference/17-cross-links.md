# 17. Сводная матрица кросс-связей и известные несоответствия

## 1. Матрица «параметр → на что влияет»

| Параметр | Зависит от | Влияет на | Конфликтует с |
|---|---|---|---|
| ProductKey | редакция в ISO | активация, WillShowUI | ISO без Pro |
| LabConfig bypass | нет | PreventAutoDeviceEncryption (без TPM избыточно), LSAProtection (значение 2 ради ПК без UEFI) | требование POPCNT/SSE4.2 в 24H2 (не обходится) |
| UILanguage | язык ISO | экран языка OOBE, Setup-User (override) | ISO другого языка |
| InputLocale | нет | экран входа, профиль по умолчанию | ru-UA (нет LCID, только через Setup-User) |
| LocalAccounts (пустые пароли) | нет | LimitBlankPasswordUse (сетевой вход закрыт), ConsentPromptBehaviorUser (UAC для User не проходит), PasswordNeverExpires, AccountLockout, InactivityLockSeconds, RestrictPrinterDriverInstallToAdmins (User не подключит принтер) | проект пользователей (назначит пароли, снимет ограничения) |
| AdminAccount / UserAccount | LocalAccounts (те же имена) | Post-OOBE | расхождение имён |
| PasswordNeverExpires | LocalAccounts | net accounts, Post-OOBE | политика паролей проекта пользователей |
| EnableNetFx3 | носитель подключён в specialize | старые программы, PowerShell 2.0 (не связано) | урезанные ISO |
| EnsurePrintSpooler | нет | печать | RestrictPrinterDriverInstallToAdmins (кто ставит драйверы) |
| RestrictPrinterDriverInstallToAdmins | нет | подключение сетевых принтеров пользователем | пустой пароль Admin (запрос UAC не проходит) |
| WindowsUpdateAutomatic | нет | перезагрузки вне 08:00-20:00 | ПК, работающие ночью (параметр периода) |
| UpdateOtherMicrosoftProducts | нет | Office MSI, .NET 3.5 | нет |
| DeferFeatureUpdatesDays | DiagTrack Manual, задачи Appraiser | версия Windows на парке | полное отключение телеметрии |
| DeliveryOptimizationLANOnly | порт 7680 между ПК | трафик | нет |
| DefenderCloudProtection | интернет | ASR (prevalence, ransomware, obfuscated), ложные срабатывания на редких программах | изолированная сеть (не работает, но не мешает) |
| DefenderPUAProtection | нет | установщики-бандлы, утилиты удалённого доступа | легитимные утилиты класса PUA |
| DefenderNetworkProtection | Defender основной антивирус | все браузеры, VPN-клиенты с фильтрами | сторонний антивирус (Defender пассивен) |
| DefenderASRRules | облачная защита для трёх правил, Office в стандартном пути | Office-макросы, скрипты, USB, PsExec (аудит) | внутренние программы без репутации (правило в аудите), удалённое администрирование через PsExec/WMI (аудит) |
| ControlledFolderAccess (0) | нет | при 1: программы учёта, пишущие в Документы | 1С, M.E.Doc, старый Office |
| SmartScreenLevel | Mark of the Web | запуск скачанных программ | Block ломает установку редких программ |
| UACAlwaysNotify | нет | запросы при системных изменениях | нет |
| InactivityLockSeconds | пароли | блокировка экрана | пустые пароли (Enter разблокирует) |
| LSAProtection | подписанные LSA-плагины | токены ЭЦП, сторонние провайдеры входа | неподписанные драйверы смарт-карт |
| NTLMv2Only | нет | старые NAS, МФУ | устройства с NTLMv1 |
| AccountLockout | пароли | перебор по сети | нет |
| DisableRemoteAssistance | нет | msra | удалённая поддержка (нужен свой инструмент) |
| DisableRemoteDesktopInbound | нет | RDP входящий | удалённое администрирование |
| DisableRemoteRegistry | нет | удалённый реестр | старые агенты инвентаризации |
| PreventAutoDeviceEncryption | TPM | 24H2 автошифрование, клонирование, восстановление | защита ноутбуков от кражи (включать отдельно с ключом) |
| DisableSMB1 | нет | старые МФУ и NAS | устройства только с SMB1 |
| RequireSMBSigning | нет | старые МФУ и NAS, ретрансляция NTLM | устройства без подписи SMB2 |
| DisableLLMNR | NetBIOS или mDNS для имён | responder-атаки | нет |
| DisableNetBIOS (выкл.) | mDNS, DNS | при включении: `\\ИМЯ` без DNS | старые ярлыки на общие папки |
| FirewallOnWithLogging | профиль сети | входящие по умолчанию, журнал | общий доступ требует частного профиля (не задаётся) |
| DisableAutoRun | нет | флешки, диски, телефоны | нет |
| ScriptFilesOpenInNotepad | HKCU не перекрывает | .js/.vbs/.hta по двойному клику | установщики, запускающие .vbs через оболочку |
| RemoveVBScript (выкл.) | 24H2+ (компонент) | при включении: старые установщики, макросы | старый софт |
| EdgeSmartScreenLocked | Edge | загрузки в Edge | нет |
| AuditLogging | правильное время | 256 МБ на диске, шум от съёмных носителей | нет |
| PowerShellLogging | размер журнала | секреты в командной строке попадают в журнал | нет |
| DisablePowerShellV2 | наличие компонента (нет в 24H2+) | downgrade-атаки | нет |
| MinimalTelemetry | нет | DeferFeatureUpdates (DiagTrack оставлен Manual), WER | нет |
| DisableConsumerContent | профиль по умолчанию (главный механизм на Pro) | предустановки, реклама | нет |
| DisableCopilotAndRecall | 24H2, Copilot+ PC | Copilot, Recall, Click to Do | нет |
| DisableWidgetsAndNews | нет | панель виджетов, malvertising | нет |
| DisableWebSearchInStart | нет | поиск в Пуске | нет |
| RemoveBloatApps | Store сохранён | 33 приложения, MapsBroker | обновление функций может вернуть часть |
| RemoveQuickAssist | нет | мошенничество «техподдержка» | удалённая поддержка (нужен свой инструмент) |
| RemoveXboxServices | нет | Game Bar, Xbox Live | игры из Store |
| TimeZone | нет | журналы аудита (время событий) | нет |

## 2. Цепочки, которые нужно помнить при изменении одного параметра

1. Стартовые учётные записи и пароли: `LocalAccounts` → `LimitBlankPasswordUse` → `ConsentPromptBehaviorUser`
   → `RestrictPrinterDriverInstallToAdmins` → `PasswordNeverExpires` → проект пользователей.
   Назначение паролей снимает все ограничения этой цепочки.
2. Устаревшие сетевые протоколы: `DisableSMB1` + `RequireSMBSigning` + `NTLMv2Only` + `DisableLLMNR`.
   Ослаблять только вместе с инвентаризацией старых устройств (МФУ, NAS).
3. Облачная защита: `DefenderCloudProtection` → три правила ASR → `SmartScreenLevel` → `DefenderNetworkProtection`.
   Без интернета работают только локальные сигнатуры и правила без облачной зависимости.
4. Обновления функций: `DeferFeatureUpdatesDays` → `MinimalTelemetry` (DiagTrack Manual, Appraiser не трогается)
   → `WindowsUpdateAutomatic`. Отключение DiagTrack «для приватности» сломает первый пункт.
5. Языки: `UILanguage` (= ISO) → `InputLocale` → профиль по умолчанию → `Setup-User.ps1` (override
   интерфейса, `ru-UA`). Смена ISO требует смены `UILanguage`, `SystemLocale` и `UserLocale` можно оставить.
6. Удалённое администрирование: `DisableRemoteAssistance` + `DisableRemoteDesktopInbound` +
   `DisableRemoteRegistry` + `RemoveQuickAssist` + правило ASR PsExec/WMI (аудит) + брандмауэр.
   Организация должна выбрать инструмент поддержки до внедрения.
7. Учётные данные: `LSAProtection` + `WDigest` + `NoLMHash` + `NTLMv2Only` + `LocalAccountTokenFilterPolicy`
   + `AccountLockout`. Вместе они делают украденный хэш или пароль малополезным.
8. Профиль по умолчанию: всё из раздела 14 применяется только к профилям, созданным после specialize.
   Повторный запуск скрипта на настроенной системе не изменит существующие профили.

## 3. Известные несоответствия и допущения версии 0.2

| Что | Где | Последствие | План |
|---|---|---|---|
| `MapsBroker` отключается под условием `RemoveXboxServices` внутри `RemoveBloatApps` | Setup-System.ps1 раздел 9 | При нестандартных значениях служба может остаться без приложения (безвредно) | Привязать к удалению Maps в конструкторе |
| Политики `DisableWindowsConsumerFeatures`, `DisableSoftLanding`, `DisableThirdPartySuggestions` на Pro не действуют | Раздел 8 | Безвредно; реальную работу делает профиль по умолчанию | Оставить, пометить в схеме конструктора как «Enterprise only» |
| `TurnOffWindowsCopilot` в HKLM не действует | Раздел 8 | Безвредно; действует копия в профиле по умолчанию и удаление приложения | Оставить |
| `AllowCortana`, `Windows Chat`, `ConfigureChatAutoInstall` относятся к прошлым версиям | Раздел 8 | Безвредно | Пометить как «устаревшее» в схеме |
| Профиль сети (частная/общедоступная) не задаётся | oobeSystem | Windows спросит при первом подключении или назначит общедоступный; общие папки потребуют переключения | Параметр конструктора |
| Язык установщика (WinPE) не задаётся | windowsPE | Первый экран установщика остаётся | Параметр конструктора, вычисляется из ISO |
| Пароли в файле ответов, если появятся, хранятся открытым текстом | oobeSystem | Post-OOBE.ps1 удаляет копии; носитель с файлом нужно хранить как секрет | Требование к конструктору: предупреждение при задании пароля |
| Правила ASR для Office не сработают, если Office установлен не в Program Files | Раздел 3 | Защита Office-макросов отсутствует | Документировать в инструкции установки Office |
| Отчёт критика указывал на `DisableLockWorkstation` в Winlogon | Раздел 4 | Исправлено в 0.2: значение удаляется из обоих мест | Закрыто |
| Задача очистки на ноутбуке от батареи | Раздел 12 | Исправлено в 0.2: XML задачи | Закрыто |
| auditpol с английскими именами на украинском образе | Раздел 7 | Исправлено в 0.2: GUID | Закрыто |
