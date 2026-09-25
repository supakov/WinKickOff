# Справочник по настройкам autounattend.xml v0.2

Документация к файлу ответов `autounattend.xml` (версия 0.2 от 13.09.2026). Описано каждое направление
и каждый параметр: что именно записывается, каким методом, какой эффект ожидается, на что это влияет
в других подсистемах, чем отличается поведение на разных версиях Windows, как проверить и как откатить.

## Как читать карточку параметра

Каждый параметр описан по одной схеме:

| Поле | Что в нём |
|---|---|
| Значение по умолчанию | Что стоит в `$Config` (или в XML) в версии 0.2 |
| Где применяется | Проход установки, скрипт и раздел скрипта, от чьего имени выполняется |
| Что делает | Точные ключи реестра, значения, команды, включая безусловные действия того же раздела |
| Ожидаемый эффект | Что увидит пользователь или администратор |
| Кросс-связи | Другие параметры и подсистемы Windows, на которые это влияет или от которых зависит |
| Различия версий | Windows 10, Windows 11 21H2/22H2/23H2/24H2/25H2, редакции Home/Pro/Enterprise |
| Проверка | Команда, которой можно убедиться, что настройка применилась |
| Откат | Команда или ключ, возвращающий поведение Windows по умолчанию |

Пути реестра сокращены: `HKLM` = `HKEY_LOCAL_MACHINE`, `Pol` = `HKLM\SOFTWARE\Policies\Microsoft\Windows`,
`Sys` = `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System`,
`Def` = `HKLM\SOFTWARE\Policies\Microsoft\Windows Defender`, `DU` = куст профиля по умолчанию
(`C:\Users\Default\NTUSER.DAT`, во время применения смонтирован как `HKU\UnattendDefault`).

## Разделы

| Файл | Направление | Параметры |
|---|---|---|
| [00-architecture.md](00-architecture.md) | Устройство файла: проходы, порядок, механизмы применения, ограничения Setup, логи, общая карта кросс-связей | нет |
| [01-windows-pe.md](01-windows-pe.md) | Проход windowsPE: ключ, редакция, лицензия, обход проверок железа | ProductKey, WillShowUI, AcceptEula, LabConfig |
| [02-specialize-xml.md](02-specialize-xml.md) | Проход specialize в XML: извлечение скриптов, BypassNRO, запуск Setup-System.ps1, часовой пояс | Order 1..3, TimeZone |
| [03-oobe-accounts-languages.md](03-oobe-accounts-languages.md) | Проход oobeSystem: языки и регион, экраны OOBE, стартовые учётные записи | InputLocale, SystemLocale, UILanguage, UserLocale, OOBE, LocalAccounts |
| [04-users-and-media.md](04-users-and-media.md) | Учётные записи в `$Config`, .NET 3.5 с носителя | AdminAccount, UserAccount, PasswordNeverExpires, EnableNetFx3 |
| [05-printing.md](05-printing.md) | Печать | EnsurePrintSpooler, RestrictPrinterDriverInstallToAdmins |
| [06-windows-update.md](06-windows-update.md) | Обновления Windows и Delivery Optimization | WindowsUpdateAutomatic, UpdateOtherMicrosoftProducts, DeferFeatureUpdatesDays, DeliveryOptimizationLANOnly |
| [07-defender.md](07-defender.md) | Microsoft Defender, правила ASR, SmartScreen | DefenderCloudProtection, DefenderPUAProtection, DefenderNetworkProtection, DefenderASRRules, ControlledFolderAccess, SmartScreenLevel |
| [08-accounts-uac-lsa-remote.md](08-accounts-uac-lsa-remote.md) | UAC, защита учётных данных, блокировка, удалённый доступ, BitLocker | UACAlwaysNotify, LSAProtection, AccountLockout, InactivityLockSeconds, NTLMv2Only, DisableRemoteAssistance, DisableRemoteDesktopInbound, DisableRemoteRegistry, PreventAutoDeviceEncryption |
| [09-network-smb-firewall.md](09-network-smb-firewall.md) | SMB, разрешение имён, брандмауэр | DisableSMB1, RequireSMBSigning, DisableLLMNR, DisableNetBIOS, FirewallOnWithLogging |
| [10-removable-scripts-browser.md](10-removable-scripts-browser.md) | Съёмные носители, скриптовые файлы, Edge | DisableAutoRun, ScriptFilesOpenInNotepad, RemoveVBScript, EdgeSmartScreenLocked |
| [11-logging-audit.md](11-logging-audit.md) | Журналирование для расследований | AuditLogging, PowerShellLogging, DisablePowerShellV2 |
| [12-telemetry-consumer-ai.md](12-telemetry-consumer-ai.md) | Телеметрия, реклама, Copilot и Recall, виджеты, веб-поиск | MinimalTelemetry, DisableConsumerContent, DisableCopilotAndRecall, DisableWidgetsAndNews, DisableWebSearchInStart |
| [13-services-apps.md](13-services-apps.md) | Службы и удаление приложений | RemoveBloatApps ($AppsToRemove), RemoveQuickAssist, RemoveXboxServices |
| [14-default-user-profile.md](14-default-user-profile.md) | Профиль пользователя по умолчанию (наследуют все учётные записи) | значения куста DU |
| [15-per-user-script.md](15-per-user-script.md) | Active Setup и Setup-User.ps1: языки ввода каждого пользователя | нет параметров, механизм |
| [16-post-oobe.md](16-post-oobe.md) | Задача планировщика и Post-OOBE.ps1: очистка после первичной настройки | нет параметров, механизм |
| [17-cross-links.md](17-cross-links.md) | Сводная матрица кросс-связей и известные несоответствия версии 0.2 | нет |

## Соглашения о версиях Windows

Файл рассчитан на Windows 11 Pro 24H2 и новее (проверен на украинском ISO 25H2, сборка 26200).
В карточках упоминаются:

- Windows 10 (1809 и новее): файл формально совместим, но не тестировался; отличия отмечены.
- Windows 11 21H2, 22H2, 23H2: отличия отмечены там, где настройка появилась или изменилась.
- Windows 11 24H2 и 25H2: базовая версия; там, где 24H2 изменила поведение по умолчанию, это сказано явно.
- Редакции: Home не поддерживается (нет политик, нет части компонентов). Pro основная. Enterprise/Education:
  часть политик, которые на Pro игнорируются, там работает; отмечено в карточках.

## Источники

Документация Microsoft Learn (Unattended Windows Setup Reference, Group Policy reference, Defender ASR reference),
результаты установки 13.09.2026 (setupact.log, setuperr.log), проверки на сборке 26200, отчёт независимого
критика (`../03-critic-report-v0.2.docx`).
