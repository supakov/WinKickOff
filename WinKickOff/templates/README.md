# Runtime templates

The fixed parts of the output file. The generator (`winkickoff/core/render.py`) fills the `{{name}}` slots with
the blocks of the enabled rules and with profile data; everything else is copied as is.

| File | Content | Slots |
|---|---|---|
| `autounattend.template.xml` | Skeleton of the answer file and the extraction script (ExtractScript) | `header`, `settings`, `files`, `profile_json` |
| `Setup-System.runtime.ps1` | Functions Write-Log, Set-Reg, Remove-Reg, Open-RegKey, Set-RegList (a key with a list of values: `-Names` and `-Values` pair up by position, without `-Additive` the other values of the key are deleted first), Set-ServiceStart, Invoke-Exe, Set-Feature, Remove-Capability, Remove-Apps; trap; log header | `build_label`, `blocks`, `default_user_section`, `active_setup_section`, `post_oobe_section` |
| `section-default-user.ps1` | Mounting of the default user hive (`$du`) around the blocks of the default-user phase | `blocks` |
| `section-active-setup.ps1` | Active Setup registration of `Setup-User.ps1` (added when the user-first-logon phase has rules) | none |
| `section-post-oobe-task.ps1` | Scheduled task for `Post-OOBE.ps1` (added when the post-oobe phase has rules) | none |
| `Setup-User.runtime.ps1` | Per-user log, Set-Reg and Remove-Reg (HKCU of the user), input language lists from the profile | `input_languages`, `input_fallback`, `transient_languages`, `blocks` |
| `Post-OOBE.runtime.ps1` | Waiting for OOBE to finish, Set-Reg and Remove-Reg, list of accounts, removal of the task | `accounts`, `blocks` |
| `Audit.runtime.ps1` | Read-only audit of selected rules on a running Windows (T15): Test-Reg, Test-RegList, Test-ServiceStart, Test-Feature, Test-AppAbsent and others; JSON report | `build_label`, `blocks` |
| `Apply.runtime.ps1` | Applying selected rules to a running Windows (T15): administrator check, the same helpers as Setup-System with the previous state saved to `backup-*.json` (Set-RegList saves every value of the key it touches), default user hive mounting | `build_label`, `accounts`, `blocks` |
| `Undo.runtime.ps1` | Restoring from `backup-*.json` (T15); a list of values comes back value by value | `build_label` |

`VERSION` holds the version of the catalog and the runtime; profiles store it as `catalog_version`. 0.5
(1.1.0-rc.2): Set-RegList and Test-RegList for lists of values, and `Set-Reg` accepts an empty MultiString. 0.6:
Set-Reg and Remove-Reg in Setup-User and Post-OOBE (rules of the phases user-first-logon and post-oobe may write the
registry; their other action types stay limited to `ps`), values of the sign-in screen (`HKU:\.DEFAULT\`), rules of
File Explorer namespaces, desktop icons and the keys that switch the input language.
Any change of a template or of the catalog that changes the output file needs a new version and a run of
`python -m unittest discover -s tests` (the tests compare the built file with the verified v0.2).

Everything the generator itself writes (header, block markers, embedded profile) is ASCII, so the answer
file does not depend on how Windows Setup treats national characters.
