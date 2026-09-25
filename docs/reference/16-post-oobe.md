# 16. Задача планировщика и Post-OOBE.ps1: очистка после первичной настройки

Раздел 12 `Setup-System.ps1` создаёт задачу; скрипт встроен в XML как
`C:\ProgramData\Unattend\Scripts\Post-OOBE.ps1`.

## Зачем отдельный этап

Часть действий невозможна в specialize: учётные записи Admin и User ещё не существуют (их создаёт
oobeSystem), а файлы `C:\Windows\Panther\unattend*.xml` ещё нужны установщику. Поэтому они
выполняются после завершения OOBE задачей планировщика от SYSTEM.

## Задача Unattend-PostOOBE

- Создание: `schtasks.exe /Create /F /TN Unattend-PostOOBE /XML C:\ProgramData\Unattend\Scripts\Post-OOBE.task.xml`.
  XML-описание записывается скриптом в UTF-16 (формат, который требует schtasks).
- Почему не `Register-ScheduledTask`: командлет работает через CIM/WMI, который в specialize
  ненадёжен (задокументированный источник ошибок 0x8004100a).
- Почему XML, а не `/SC ONSTART`: у задачи, созданной ключами `/SC`, остаются умолчания
  «не запускать от батареи» и «останавливать при переходе на батарею». На ноутбуке, который после
  установки отключили от сети, задача никогда бы не сработала. В XML заданы:

| Параметр | Значение | Смысл |
|---|---|---|
| Trigger | BootTrigger | При каждой загрузке |
| Principal | S-1-5-18 (SYSTEM), HighestAvailable | Права на удаление файлов в Panther и управление учётными записями |
| DisallowStartIfOnBatteries | false | Работает от батареи |
| StopIfGoingOnBatteries | false | Не прерывается при отключении сети |
| StartWhenAvailable | true | Если момент загрузки пропущен, запускается при первой возможности |
| MultipleInstancesPolicy | IgnoreNew | Одна копия |
| ExecutionTimeLimit | PT6H | Максимум 6 часов (скрипт ждёт OOBE до 5 часов) |
| Hidden | false | Видна в планировщике, чтобы администратор понимал, что это |

- Различия версий: формат Task Scheduler 1.2 одинаков с Windows Vista. На 24H2 без изменений.
- Проверка: `schtasks /Query /TN Unattend-PostOOBE /V /FO LIST` (до первого успешного выполнения);
  после него задача отсутствует, а в логе строка `task removed (exit 0)`.

## Что делает Post-OOBE.ps1

Лог: `C:\ProgramData\Unattend\Logs\Post-OOBE.log`.

1. Ожидание завершения OOBE: каждые 30 секунд читается
   `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Setup\State\ImageState`; нужен `IMAGE_STATE_COMPLETE`.
   Предел 5 часов; если не дождался, `exit 0` и повтор при следующей загрузке (задача остаётся).
   Обычно первая загрузка после specialize это и есть OOBE, состояние становится COMPLETE через
   минуту после появления экрана входа.
2. Пауза 2 минуты после COMPLETE: чтобы первый вход пользователя (если он уже происходит) не
   конкурировал за диск и реестр.
3. Чтение `C:\ProgramData\Unattend\config.json`: имена учётных записей и флаг `PasswordNeverExpires`.
   Если файл нечитаем, используются имена `Admin` и `User`.
4. Для каждой учётной записи: `Set-LocalUser -PasswordNeverExpires $true` (если флаг включён).
   Отсутствующая учётная запись пишется в лог и пропускается.
5. Встроенные учётные записи по SID: все локальные пользователи с RID 500 (Administrator) и 501 (Guest)
   отключаются, если включены. Поиск по SID, а не по имени, потому что на украинском образе они
   называются «Адміністратор» и «Гість».
6. Перенос ошибок specialize: если существует `C:\Windows\Temp\ua.err` (его пишут обёртки команд
   Order 1 и 3, раздел 02), каждая строка попадает в лог с пометкой `SPECIALIZE ERROR`, файл удаляется.
   Это единственный способ узнать, что скрипт машины не извлёкся или упал на старте.
7. Удаление копий файла ответов: `C:\Windows\Panther\unattend.xml`, `C:\Windows\Panther\unattend-original.xml`,
   `C:\Windows\Panther\Unattend\unattend.xml`, `C:\Windows\System32\Sysprep\unattend.xml`,
   `C:\unattend.xml`, `C:\autounattend.xml`. Существующие удаляются, остальные пропускаются.
8. Удаление задачи: `schtasks.exe /Delete /TN Unattend-PostOOBE /F`.
9. `exit 0`.

- Ожидаемый эффект: через несколько минут после первого появления экрана входа (даже если никто
  не вошёл) на диске нет файлов с описанием учётных записей, срок действия пустых паролей снят,
  встроенные учётные записи отключены, задача исчезла из планировщика.
- Кросс-связи:
  - Windows 11 24H2 хранит в `unattend-original.xml` полную копию файла, включая пароли открытым
    текстом, если они были заданы. Сейчас пароли пустые, но конструктор в будущем может их задавать:
    удаление обязательно.
  - Скрипты в `C:\ProgramData\Unattend` не удаляются: они не содержат секретов и служат
    документацией того, что было применено.
  - Если планируется захват образа через Sysprep после установки, отсутствие `unattend.xml` в Panther
    не мешает: Sysprep использует свой файл.
  - `PasswordNeverExpires` продублирован в specialize через `net accounts /maxpwage:unlimited`
    (раздел 04), поэтому даже при сбое этой задачи срок действия не сработает.
- Различия версий: `ImageState` и его значения одинаковы с Windows Vista. `Set-LocalUser`,
  `Get-LocalUser -SID`, `Disable-LocalUser -SID` с Windows 10 1607. На 24H2 без изменений.
- Проверка: `Test-Path C:\Windows\Panther\unattend.xml` → False; `Get-LocalUser | Where { $_.SID -match '-50[01]$' } | Select Name, Enabled`
  → оба False; лог заканчивается строкой `Post-OOBE.ps1 finished`.
- Откат: не требуется. Повторный запуск от администратора безопасен.
