# 04. Учётные записи в $Config и .NET Framework 3.5

Раздел `$Config` в `Setup-System.ps1`, группы «Users» и «Installation media».

## AdminAccount, UserAccount

- Значение: `'Admin'`, `'User'`.
- Где применяется: сохраняются в `C:\ProgramData\Unattend\config.json` в конце `Setup-System.ps1`;
  читаются `Post-OOBE.ps1`.
- Что делает: сообщают Post-OOBE.ps1 имена учётных записей, которым нужно снять срок действия пароля.
  Сами учётные записи создаёт XML (раздел 03), а не эти параметры.
- Ожидаемый эффект: `Set-LocalUser -PasswordNeverExpires $true` для обоих имён после завершения OOBE.
- Кросс-связи: имена обязаны совпадать с `<Name>` в `<LocalAccounts>`; при расхождении Post-OOBE.ps1
  запишет в лог «user not found» и не снимет срок действия, но глобальная команда `net accounts`
  (см. ниже) всё равно сработает. Конструктор должен вести оба места из одного поля.
- Различия версий: нет.
- Проверка: `Get-Content C:\ProgramData\Unattend\config.json`.
- Откат: не применимо.

## PasswordNeverExpires

- Значение: `$true`.
- Где применяется: два места. `Setup-System.ps1` раздел 4 (specialize, всегда выполняется) и
  `Post-OOBE.ps1` (после OOBE, для каждой учётной записи).
- Что делает:
  1. `net.exe accounts /maxpwage:unlimited`: максимальный срок действия пароля для всех локальных
     учётных записей снимается (по умолчанию 42 дня).
  2. `Set-LocalUser -Name <имя> -PasswordNeverExpires $true`: флаг «Срок действия пароля не ограничен»
     на самих учётных записях Admin и User.
- Ожидаемый эффект: Windows никогда не покажет «Ваш пароль истёк и должен быть изменён». Для пустых
  паролей это критично: непрофессиональный пользователь не поймёт, что от него хотят.
- Кросс-связи:
  - Стартовые учётные записи без паролей (раздел 03). Отдельный проект управления пользователями
    назначает пароли и вправе вернуть срок действия (`net accounts /maxpwage:90`).
  - `AccountLockout` (раздел 08) задаётся той же утилитой `net accounts`; порядок вызовов не важен.
  - Если Post-OOBE.ps1 не выполнится (ПК выключили до завершения), глобальная настройка из
    specialize всё равно действует.
- Различия версий: `net accounts` работает во всех версиях. `Set-LocalUser` доступен в Windows 10 1607+
  (модуль Microsoft.PowerShell.LocalAccounts). На Windows 11 22H2+ значение по умолчанию 42 дня сохранено.
- Проверка: `net accounts` → «Maximum password age: Unlimited»; `Get-LocalUser Admin | Select PasswordExpires`
  (пусто).
- Откат: `net accounts /maxpwage:42`; `Set-LocalUser -Name Admin -PasswordNeverExpires $false`.

## EnableNetFx3

- Значение: `$true`.
- Где применяется: `Setup-System.ps1` раздел 0, specialize, SYSTEM.
- Что делает: перебирает все готовые диски, ищет папку `sources\sxs` с `.cab` внутри (носитель
  установки: USB, DVD, смонтированный ISO Ventoy). Если найдена:
  `dism.exe /Online /Enable-Feature /FeatureName:NetFx3 /All /LimitAccess /Source:<путь> /NoRestart /Quiet`.
  Если не найдена: в лог пишется WARN, компонент не включается.
- Ожидаемый эффект: .NET Framework 3.5 (включая 2.0 и 3.0) доступен сразу после установки без
  интернета. Нужен старым программам учёта, клиент-банкам, драйверам ключей ЭЦП старых версий.
- Кросс-связи:
  - Носитель должен оставаться подключённым во время specialize (первая перезагрузка). Если флешку
    вынули сразу после копирования файлов, компонент не установится; тогда его можно добавить позже
    через Параметры → Дополнительные компоненты (нужен интернет) или командой DISM с носителя.
  - `/LimitAccess` запрещает обращаться к Windows Update во время установки компонента: в specialize
    сети всё равно нет, а без ключа DISM ждал бы тайм-аут.
  - Обновления безопасности для .NET 3.5 приходят через Windows Update (раздел 06).
- Различия версий: папка `sources\sxs` есть во всех официальных ISO Windows 10/11. На образах,
  урезанных сторонними инструментами, может отсутствовать. В Windows 11 24H2 компонент по-прежнему
  необязательный и по умолчанию выключен.
- Проверка: `Get-WindowsOptionalFeature -Online -FeatureName NetFx3` → State Enabled;
  в логе строка `dism.exe ... -> exit 0`.
- Откат: `Disable-WindowsOptionalFeature -Online -FeatureName NetFx3`.
