# Установка и проверка

## Подготовка флешки

1. Скачайте актуальный образ Windows 11 с сайта Microsoft.
2. Запишите флешку (Rufus или Media Creation Tool).
3. Скопируйте собранный `autounattend.xml` в корень флешки.

Для Ventoy файл кладётся рядом с образом и подключается через плагин Auto Install.

## Что спросит установщик

1. Язык установщика и раскладку на первом экране (зависит от образа).
2. Диск и раздел для установки. Автоматическая разметка не задаётся намеренно: она стирает диск без
   вопросов, для рабочих компьютеров это опасно.

Всё остальное проходит без участия человека: лицензия, ключ, редакция, экраны первичной настройки,
создание учётных записей. После установки открывается рабочий стол.

## Проверка файла до установки

В окне программы: «Проверить» (F7); «Собрать autounattend.xml» (F9) вдобавок проверяет синтаксис PowerShell
встроенных скриптов. Из папки проекта можно также запустить утилиту проверки, она только читает файл:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

## Проверка после установки (на виртуальной машине)

Войдите как Admin и выполните в PowerShell:

```powershell
Get-Content C:\ProgramData\Unattend\Logs\Setup-System.log | Select-String 'ERROR|WARN'
Get-ChildItem C:\ProgramData\Unattend\Logs\Setup-User.*.log | Get-Content
Get-Content C:\ProgramData\Unattend\Logs\Post-OOBE.log
Get-Service Spooler | Select-Object Status, StartType
Get-LocalUser Admin, User | Select-Object Name, Enabled, PasswordExpires
Get-WinUserLanguageList | Select-Object LanguageTag, InputMethodTips
Get-MpPreference | Select-Object PUAProtection, MAPSReporting, EnableNetworkProtection, AttackSurfaceReductionRules_Ids
Test-Path C:\Windows\Panther\unattend.xml
```

Ожидаемый результат для пресета «Офис»: в журналах нет ERROR; служба печати запущена и запускается
автоматически; у Admin и User не ограничен срок пароля; языки ввода en-US, uk-UA, ru-UA; защита от
нежелательных программ и сетевая защита включены; правил ASR 16 (в пресете «Строгий» 17); файла `unattend.xml` в Panther нет.

Для каждого правила в программе есть раздел «Проверка после установки» с точной командой.

## Журналы

| Журнал | Что в нём |
|---|---|
| `C:\ProgramData\Unattend\Logs\Setup-System.log` | Настройка компьютера при первой загрузке: каждое правило и результат |
| `C:\ProgramData\Unattend\Logs\Setup-User.<имя>.log` | Настройка при первом входе каждого пользователя (языки ввода) |
| `C:\ProgramData\Unattend\Logs\Post-OOBE.log` | Действия после первичной настройки, ошибки первой загрузки с пометкой SPECIALIZE ERROR |
| `C:\Windows\Panther\setuperr.log` | Ошибки самого установщика Windows |

## Если что-то пошло не так

- Установщик сообщил, что файл ответов недействителен: проверьте файл кнопкой «Проверить» и утилитой
  проверки; пришлите `C:\Windows\Panther\setuperr.log` и `setupact.log` с установленной системы.
- После первого входа нет «Русского (Украина)»: он иногда появляется только после второго входа, до
  этого стоит обычный «Русский». Что применилось, видно в `Setup-User.<имя>.log`.
- Программа перестала работать после установки со «Строгим» пресетом: откройте в WinKickOff правила
  защиты папок, SmartScreen и ASR, раздел «Откат» у каждого из них описывает, как вернуть поведение.
