# Встановлення і перевірка

## Підготовка флешки

1. Завантажте останню версію образу Windows 11 із сайту Microsoft.
2. Створіть завантажувальну флешку (Rufus або Media Creation Tool).
3. Скопіюйте зібраний `autounattend.xml` у кореневу папку флешки.

Для Ventoy файл розміщують поруч з образом і підключають через плагін Auto Install.

## Що запитає інсталятор

1. Мову інсталятора й розкладку клавіатури на першому екрані (залежить від образу).
2. Диск і розділ для встановлення. Автоматичну розмітку навмисно не задано: вона стирає диск без
   запитань, а для робочих комп'ютерів це небезпечно.

Усе інше відбувається без участі людини: ліцензія, ключ, випуск, екрани початкового налаштування,
створення облікових записів. Після встановлення відкривається робочий стіл.

## Перевірка файлу перед встановленням

У вікні програми: «Перевірити» (F7). З папки проєкту також можна запустити утиліту
перевірки, вона лише читає файл:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\Validate-Unattend.ps1 -Path WinKickOff\output\autounattend.xml
```

## Перевірка після встановлення (на віртуальній машині)

Увійдіть як Admin і виконайте в PowerShell:

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

Очікуваний результат для пресету «Офіс»: у журналах немає ERROR; служба друку працює і
запускається автоматично; строк дії пароля для Admin і User не обмежено; мови введення en-US, uk-UA,
ru-UA; захист від небажаних програм і мережевий захист увімкнено; кількість правил ASR: 17; файлу
`unattend.xml` у Panther немає.

Для кожного правила в програмі є розділ «Перевірка після інсталяції»
з точною командою.

## Журнали

| Журнал | Що в ньому |
|---|---|
| `C:\ProgramData\Unattend\Logs\Setup-System.log` | Налаштування комп'ютера під час першого завантаження: кожне правило і його результат |
| `C:\ProgramData\Unattend\Logs\Setup-User.<ім'я>.log` | Налаштування під час першого входу кожного користувача (мови введення) |
| `C:\ProgramData\Unattend\Logs\Post-OOBE.log` | Дії після початкового налаштування, помилки першого завантаження з позначкою SPECIALIZE ERROR |
| `C:\Windows\Panther\setuperr.log` | Помилки самого інсталятора Windows |

## Якщо щось пішло не так

- Інсталятор повідомив, що файл відповідей недійсний: перевірте файл кнопкою «Перевірити» та утилітою
  перевірки; надішліть `C:\Windows\Panther\setuperr.log` і `setupact.log` зі встановленої системи.
- Після першого входу немає «Російської (Україна)»: іноді вона з'являється лише після другого входу,
  а до того стоїть звичайна «Російська». Що застосовано, видно в `Setup-User.<ім'я>.log`.
- Програма перестала працювати після встановлення з пресетом «Суворий»: відкрийте
  в WinKickOff правила захисту папок, SmartScreen і ASR; розділ «Відкат» у кожному з них
  описує, як повернути попередню поведінку.
