# WinKickOff: deliberate decisions and window labels

Part of [concepts.md](concepts.md). Read it when a request touches a decision of the customer, or when you guide the person through a Russian or Ukrainian window.

## Deliberate decisions (do not fix)

These are decisions of the customer or of the design. Explain them when asked; do not propose to change them unless
the person insists after hearing the reason.

1. **Admin and User have no passwords.** A separate project assigns passwords and groups after installation. Effects:
   User cannot confirm UAC with Admin's credentials; network sign-in with a blank password is refused, so shared
   folders between PCs and RDP do not work. A password typed in the form is stored in plain text. MCP cannot set
   passwords anyway.
2. **The display language equals the ISO language** (`uk-UA` for the target Ukrainian ISO). `user-logon.pin-ui-language`
   (baseline) pins it; `user-logon.input-languages` only sets keyboards.
3. **BitLocker is off in every preset.** `encryption.prevent-auto-bitlocker` is on: without a domain or Microsoft
   account the recovery key would be saved nowhere and data could be lost if the TPM or motherboard fails. BitLocker is
   turned on later together with key escrow.
4. **No automatic disk partitioning.** Setup asks for the disk on purpose so that no disk is erased without asking.
5. **`uac.admin-always-notify` is off in Office** so that Task Manager opened by Admin does not ask for UAC. It is on in
   Strict.
6. **Office differs from the old hand-written file on purpose**: browser policies, `apps.remove.onedrive`, AI,
   telemetry and ads rules and `edge.signin-off` on; `update.other-microsoft-products`, `asr.usb-untrusted` and
   `uac.admin-always-notify` off.
7. **`edge.signin-off` is on** because most Edge AI policies do not apply to a profile signed in with a personal
   Microsoft account.
8. **Russian (Ukraine) keyboard `ru-UA`** has no LCID. The file writes plain Russian and `Setup-User.ps1` replaces it at
   first sign-in; sometimes it appears only after the second sign-in. Expected.
9. **Passwords never expire** (`accounts.password-never-expires`, `post-oobe.password-never-expires`) so blank passwords
   are not forced to change.
10. **`privacy.telemetry-minimal` keeps the DiagTrack service on Manual**: feature update compatibility checks and
    Defender reporting need it. Pro cannot go below "Required".
11. **Policies grey out Settings items** ("managed by your organization") on purpose: in a workgroup it is the only
    tamper-proof way.
12. **App removal does not touch the Store or winget**, so apps keep updating. Quick Assist is removed
    (`apps.remove-quick-assist`) because scammers use it; it can be reinstalled from the Store.
13. **`lsa.protection` uses mode 2** (reversible). Mode 1 cannot be undone without firmware access.
14. **`defender.controlled-folder-access` is on with mode 0 (Off)** in Office: it only stops users from turning it on by
    accident. Block (1) breaks accounting and banking programs; the safe path is a month in
    Audit (2), then Block.
15. **`thispc.*` folders are off by default**, as in Windows 11. Showing both variants of a folder may duplicate it.
16. **`privacy.office` and all `default-user` rules reach new profiles only.** Accounts created during installation get
    them; existing profiles on a running PC do not.
17. **The Home preset leaves out the WinKickOff protection set**: UAC, LSA, Defender (only its notifications rule is
    on), ASR, logging and others stay at the Windows defaults; the region, input language and printing rules are off
    too. Recommend Office for work PCs.
18. **No third-party programs.** `update.unblock` (baseline) removes leftovers of "optimizer" tools that block updates.
19. **Hardware check bypasses** (`install.bypass-tpm`, `install.bypass-secureboot`, `install.bypass-cpu`,
    `install.bypass-ram`, `install.bypass-storage`) are on so older PCs can be installed. They change nothing on
    supported PCs. On unsupported PCs Microsoft does not guarantee updates; change them only on request.

## Window labels in Russian and Ukrainian

The window may run in Russian or Ukrainian. Use its labels when you guide the person. The "MCP" and "ADMX" menu names
are never translated.

| English | Russian | Ukrainian |
|---|---|---|
| "Read only" | "Только чтение" | "Лише читання" |
| "Read and change the open profile" | "Чтение и изменение открытого профиля" | "Читання і зміна відкритого профілю" |
| "Change and create files" | "Изменение и создание файлов" | "Зміна і створення файлів" |
| "Save profile" | "Сохранить профиль" | "Зберегти профіль" |
| "Save profile as..." | "Сохранить профиль как..." | "Зберегти профіль як..." |
| "Check" (F7) | "Проверить" | "Перевірити" |
| "Build autounattend.xml..." (F9) | "Собрать autounattend.xml..." | "Зібрати autounattend.xml..." |
| "Open profile from autounattend.xml..." | "Открыть профиль из autounattend.xml..." | "Відкрити профіль з autounattend.xml..." |
| "Installation" | "Установка" | "Інсталяція" |
| "Accounts" | "Учётные записи" | "Облікові записи" |
| "Languages and region" | "Языки и регион" | "Мови та регіон" |
| "This PC" | "Этот ПК" | "Цей ПК" |
