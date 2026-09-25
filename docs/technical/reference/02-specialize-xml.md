# 02. Проход specialize в XML: извлечение, BypassNRO, запуск скрипта, часовой пояс

Проход specialize выполняется при первой загрузке установленной системы, от имени SYSTEM,
до появления любых экранов, без пользовательских профилей и, как правило, без сети (драйверы
сетевых адаптеров ещё могут устанавливаться). В это время работают реестр, DISM, службы,
планировщик через `schtasks.exe`. Ненадёжны: WMI/CIM (поэтому не используется `Register-ScheduledTask`),
сетевые командлеты, всё, что требует интерактивного сеанса.

Компонент `Microsoft-Windows-Deployment` (amd64 и arm64), три синхронные команды.

## Order 1. Извлечение встроенных скриптов

```
powershell.exe -NoProfile -WindowStyle Hidden -Command "try{$x=[xml]::new();$x.Load('C:\Windows\Panther\unattend.xml');$s=[scriptblock]::Create($x.unattend.Extensions.ExtractScript);icm $s -Args $x}catch{$_>C:\Windows\Temp\ua.err};exit 0"
```

- Длина 238 символов (предел 259).
- Что делает: загружает копию файла ответов из Panther, берёт текст элемента `Extensions/ExtractScript`,
  превращает его в блок кода и выполняет с самим XML в качестве аргумента. `ExtractScript` создаёт
  папки `C:\ProgramData\Unattend\Scripts` и `...\Logs` и записывает каждый `<File path="...">`
  в файл в кодировке UTF-8 с BOM (BOM нужен, чтобы PowerShell 5.1 верно прочитал кириллицу в скриптах).
- Обработка ошибок: любое исключение пишется в `C:\Windows\Temp\ua.err`, код возврата всегда 0.
- Кросс-связи: без этого шага команда Order 3 не найдёт скрипт и запишет «no script» в тот же файл;
  Post-OOBE.ps1 переносит содержимое `ua.err` в свой лог. Путь `C:\Windows\Panther\unattend.xml`
  фиксирован Setup для всех версий Windows 7 и новее.
- Различия версий: нет. Метод (скрипты внутри XML) взят из практики генератора Schneegans и
  UnattendedWinstall, работает на Windows 10 и 11.
- Проверка: после установки существуют три файла в `C:\ProgramData\Unattend\Scripts`.
- Откат: не требуется.

## Order 2. BypassNRO

```
reg.exe add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE" /v BypassNRO /t REG_DWORD /d 1 /f
```

- Что делает: разрешает OOBE завершиться без подключения к интернету и без учётной записи Microsoft
  (NRO = Network Required OOBE). Показывает пункт «У меня нет интернета», если экран сети всё же появится.
- Ожидаемый эффект: в нашем файле учётные записи создаются из XML, а экраны сети и учётной записи
  скрыты (`HideOnlineAccountScreens`, `HideWirelessSetupInOOBE`), поэтому ключ служит страховкой на
  случай, если Microsoft изменит поведение OOBE.
- Кросс-связи: связан с `HideOnlineAccountScreens` и `LocalAccounts` (раздел 03). При наличии
  локальных учётных записей в файле OOBE не требует ни сети, ни аккаунта Microsoft независимо от ключа.
- Различия версий: на Windows 10 не нужен (OOBE позволяет локальную учётную запись). На Windows 11
  21H2+ работает. В 2025 году Microsoft объявила об удалении обходов NRO в сборках Insider
  (сначала скрипта `oobe\bypassnro.cmd`, затем и ключа реестра). На выпущенных 24H2/25H2 ключ
  действует; если в будущих сборках перестанет, наш файл не пострадает благодаря `LocalAccounts`.
- Проверка: `Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE -Name BypassNRO`.
- Откат: удалить значение; на установленную систему не влияет.

## Order 3. Запуск Setup-System.ps1

```
powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "try{$p='C:\ProgramData\Unattend\Scripts\Setup-System.ps1';if(Test-Path $p){& $p}else{'no script'>C:\Windows\Temp\ua.err}}catch{$_>C:\Windows\Temp\ua.err};exit 0"
```

- Длина 241 символ.
- Что делает: запускает скрипт машинных настроек, если он извлечён. `-ExecutionPolicy Bypass` нужен,
  потому что политика выполнения по умолчанию на клиентских Windows запрещает запуск скриптов.
  `-WindowStyle Hidden` прячет окно консоли, которое иначе висело бы поверх экрана «Подготовка»
  несколько минут (удаление приложений занимает время).
- Обработка ошибок: три уровня. Обёртка ловит исключение при запуске; внутри скрипта `trap { ...; continue }`
  логирует любую необработанную ошибку и продолжает со следующей строки; каждый вызов обёрнут в try/catch
  или в `Set-Reg`/`Invoke-Exe`, которые сами пишут OK/WARN/ERROR. Скрипт завершается `exit 0`.
- Время выполнения: 2-6 минут в зависимости от диска (основное время: удаление 33 приложений и DISM).
- Кросс-связи: всё содержимое скрипта описано в разделах 04-14.
- Различия версий: `powershell.exe` это Windows PowerShell 5.1, встроенный во все версии Windows 10/11.
  PowerShell 7 не используется и не требуется.
- Проверка: `C:\ProgramData\Unattend\Logs\Setup-System.log` содержит строки «started» и «finished».
- Откат: не применимо.

## TimeZone

Компонент `Microsoft-Windows-Shell-Setup` в specialize.

- Значение: `FLE Standard Time` (Киев, UTC+2, летнее время по правилам ЕС).
- Что делает: задаёт часовой пояс системы до OOBE; иначе Windows определяет его по региону
  или через службу времени.
- Ожидаемый эффект: правильное время сразу после установки; в Параметрах пояс «(UTC+02:00) Киев».
- Кросс-связи: не зависит от `UserLocale`. Синхронизация времени (`W32Time`) остаётся включённой
  и корректирует часы через `time.windows.com` при появлении сети. Для журналов аудита правильное
  время критично: события с неверным временем трудно сопоставлять при расследовании.
- Различия версий: идентификатор один и тот же во всех версиях; список: `tzutil /l`.
- Проверка: `tzutil /g`.
- Откат: `tzutil /s "<другой пояс>"`.
