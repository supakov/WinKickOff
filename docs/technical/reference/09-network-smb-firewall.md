# 09. SMB, разрешение имён, брандмауэр

Раздел 5 `Setup-System.ps1`. Обозначения: `Srv` = `HKLM\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters`,
`Wks` = `HKLM\SYSTEM\CurrentControlSet\Services\LanmanWorkstation\Parameters`.

Общий контекст: рабочая группа без домена живёт на SMB (общие папки, принтеры), NetBIOS и mDNS
(имена компьютеров), а типовая атака внутри сети это подмена ответов на широковещательные запросы
имён (LLMNR/NBT-NS poisoning) с последующим перехватом хэшей NTLM. Раздел закрывает эти векторы,
оставляя общий доступ работоспособным.

## DisableSMB1

- Значение: `$true`.
- Что делает:
  1. `Srv\SMB1 = 0`: сервер не отвечает по SMB1;
  2. служба-драйвер `mrxsmb10` тип запуска 4 (клиентская часть SMB1), если присутствует;
  3. `Disable-WindowsOptionalFeature -FeatureName SMB1Protocol`, если компонент установлен.
- Ожидаемый эффект: протокол 1996 года, через который распространялись WannaCry и NotPetya,
  отсутствует полностью.
- Кросс-связи: устройства, умеющие только SMB1 (принтеры и МФУ со сканированием в сетевую папку
  выпуска до 2015 года, старые NAS, Windows XP), не смогут подключаться к общим папкам этих ПК и
  наоборот. Решение: обновление прошивки МФУ до SMB2/3, либо сканирование на FTP/e-mail, либо
  отдельный старый ПК как «шлюз». Включать SMB1 обратно нельзя.
- Различия версий: Windows 11 24H2 не содержит SMB1 вообще (компонент удалён из образа, поэтому в
  логе WARN «service mrxsmb10 not present» ожидаем). Windows 10 1709+ и Windows 11 21H2-23H2:
  SMB1 не установлен по умолчанию, но компонент доступен для включения; файл его отключает.
  Windows 10 до 1709: SMB1 установлен, файл его удалит.
- Проверка: `Get-SmbServerConfiguration | Select EnableSMB1Protocol` → False;
  `Get-WindowsOptionalFeature -Online -FeatureName SMB1Protocol` → Disabled или отсутствует.
- Откат: не рекомендуется; `Enable-WindowsOptionalFeature -Online -FeatureName SMB1Protocol` на сборках,
  где он есть.

## RequireSMBSigning

- Значение: `$true`.
- Что делает: `Srv\RequireSecuritySignature = 1`, `Srv\EnableSecuritySignature = 1`,
  `Wks\RequireSecuritySignature = 1`, `Wks\EnableSecuritySignature = 1`.
- Ожидаемый эффект: каждый пакет SMB подписан; атаки «человек посередине» и ретрансляция NTLM
  (NTLM relay) на общие папки невозможны. Производительность на гигабитной сети снижается на несколько
  процентов, незаметно для офисной работы.
- Кросс-связи:
  - Клиент с обязательной подписью не подключится к серверу без подписи и наоборот. Windows-ПК
    рабочей группы, настроенные этим файлом, совместимы между собой. Старые NAS и МФУ без поддержки
    подписи SMB2 отпадают (та же группа устройств, что и для SMB1 и NTLMv1).
  - `NTLMv2Only` (раздел 08) и `DisableLLMNR` дополняют защиту: подпись мешает ретрансляции,
    NTLMv2 мешает взлому перехваченного, отключение LLMNR мешает перехвату.
- Различия версий: Windows 11 24H2 и Server 2025 сами требуют подпись SMB для всех подключений
  на Pro и Enterprise (новое умолчание 2024 года); файл делает это явно и для Windows 10 и 11 до 23H2,
  где умолчание «подпись не обязательна». На Home 24H2 подпись не обязательна.
- Проверка: `Get-SmbServerConfiguration | Select RequireSecuritySignature`;
  `Get-SmbClientConfiguration | Select RequireSecuritySignature` → True, True.
- Откат: `Set-SmbServerConfiguration -RequireSecuritySignature $false`;
  `Set-SmbClientConfiguration -RequireSecuritySignature $false`.

## DisableLLMNR

- Значение: `$true` → `HKLM\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient\EnableMulticast = 0`.
- Что делает: отключает Link-Local Multicast Name Resolution: широковещательный опрос «кто такой PC-BUH?»,
  на который может ответить любой узел сети, включая злоумышленника.
- Ожидаемый эффект: инструменты класса Responder перестают получать хэши от этих ПК через LLMNR.
- Кросс-связи: разрешение имён компьютеров рабочей группы продолжает работать через NetBIOS
  (оставлен включённым, см. ниже) и mDNS (Windows 10 1703+, отвечает на `имя.local`). Если выключить
  ещё и NetBIOS, останется только mDNS и DNS маршрутизатора.
- Различия версий: политика с Windows Vista. В Windows 11 24H2 Microsoft объявила LLMNR устаревшим
  в пользу mDNS; отключение соответствует курсу.
- Проверка: `Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient' -Name EnableMulticast` → 0.
- Откат: удалить значение.

## DisableNetBIOS

- Значение: `$false` (NetBIOS оставлен включённым).
- Что делает при `$true`: `HKLM\SYSTEM\CurrentControlSet\Services\NetBT\Parameters\NodeType = 2`
  (P-node: только WINS, без широковещания) и для каждого интерфейса в
  `NetBT\Parameters\Interfaces\Tcpip_{GUID}` значение `NetbiosOptions = 2` (NetBIOS over TCP/IP выключен).
- Ожидаемый эффект при `$true`: закрыт второй канал подмены имён (NBT-NS poisoning) и порты 137-139.
- Почему выключено по умолчанию: без домена и WINS имена `\\PC-BUH` разрешаются через NetBIOS
  или mDNS. mDNS в Windows отвечает только на запросы вида `pc-buh.local`; обычная запись `\\PC-BUH`
  в проводнике без NetBIOS может не найтись, а пользователи и ярлыки на общие папки к ней привыкли.
  Кроме того, интерфейсы, добавленные после установки (новый Wi-Fi адаптер, VPN), получат умолчание.
- Кросс-связи: обход через файл `hosts` или DNS-записи на маршрутизаторе. Параметр предназначен
  для «строгого» профиля конструктора после проверки в конкретной сети.
- Различия версий: значения одинаковы с Windows 2000. В 24H2 NetBIOS по-прежнему включён по умолчанию.
- Проверка: `Get-CimInstance Win32_NetworkAdapterConfiguration | Select Description, TcpipNetbiosOptions`.
- Откат: `NetbiosOptions = 0` (по DHCP) для интерфейсов, `NodeType` удалить.

## FirewallOnWithLogging

- Значение: `$true`.
- Что делает: для каждого профиля `DomainProfile`, `PrivateProfile`, `PublicProfile` в
  `HKLM\SOFTWARE\Policies\Microsoft\WindowsFirewall\<профиль>`:
  - `EnableFirewall = 1`;
  - `DefaultInboundAction = 1` (блокировать входящие, не разрешённые правилами);
  - `DefaultOutboundAction = 0` (исходящие разрешены);
  - `Logging\LogDroppedPackets = 1`, `Logging\LogFileSize = 16384` (КБ), `Logging\LogFilePath =
    %systemroot%\system32\LogFiles\Firewall\pfirewall.log`.
- Ожидаемый эффект: брандмауэр нельзя выключить из Панели управления (политика), отброшенные
  входящие пакеты пишутся в файл журнала 16 МБ (при переполнении ротация в `.old`). При расследовании
  видно, кто и на какие порты стучался.
- Кросс-связи:
  - Разрешающие правила (общий доступ к файлам и принтерам, Delivery Optimization, mDNS) продолжают
    работать: политика задаёт только действие по умолчанию. Локальные правила, создаваемые
    установщиками программ, применяются (слияние локальной политики включено по умолчанию).
  - Профиль сети (частная/общедоступная) файл не задаёт: при первом подключении Windows 11 спросит
    «Разрешить обнаружение?» для проводной сети или назначит общедоступный профиль. Общий доступ
    к папкам требует частного профиля: параметр будущего конструктора.
  - Успешные подключения не журналируются (`LogSuccessfulConnections` не задан): их слишком много.
- Различия версий: политика одинакова с Windows Vista. На 24H2 без изменений.
- Проверка: `Get-NetFirewallProfile | Select Name, Enabled, DefaultInboundAction, LogBlocked`;
  файл `C:\Windows\System32\LogFiles\Firewall\pfirewall.log`.
- Откат: удалить ключи профилей под `Policies\Microsoft\WindowsFirewall`.
