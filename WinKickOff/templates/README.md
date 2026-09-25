# Runtime templates

The fixed parts of the output file. The generator (`winkickoff/core/render.py`) fills the `{{name}}` slots with
the blocks of the enabled rules and with profile data; everything else is copied as is.

| File | Content | Slots |
|---|---|---|
| `autounattend.template.xml` | Skeleton of the answer file and the extraction script (ExtractScript) | `header`, `settings`, `files`, `profile_json` |
| `Setup-System.runtime.ps1` | Functions Write-Log, Set-Reg, Remove-Reg, Set-ServiceStart, Invoke-Exe, Set-Feature, Remove-Capability, Remove-Apps; trap; log header | `build_label`, `blocks`, `default_user_section`, `active_setup_section`, `post_oobe_section` |
| `section-default-user.ps1` | Mounting of the default user hive (`$du`) around the blocks of the default-user phase | `blocks` |
| `section-active-setup.ps1` | Active Setup registration of `Setup-User.ps1` (added when the user-first-logon phase has rules) | none |
| `section-post-oobe-task.ps1` | Scheduled task for `Post-OOBE.ps1` (added when the post-oobe phase has rules) | none |
| `Setup-User.runtime.ps1` | Per-user log, input language lists from the profile | `input_languages`, `input_fallback`, `transient_languages`, `blocks` |
| `Post-OOBE.runtime.ps1` | Waiting for OOBE to finish, list of accounts, removal of the task | `accounts`, `blocks` |

`VERSION` holds the version of the catalog and the runtime; profiles store it as `catalog_version`.
Any change of a template or of the catalog that changes the output file needs a new version and a run of
`python -m unittest discover -s tests` (the tests compare the built file with the verified v0.2).

Everything the generator itself writes (header, block markers, embedded profile) is ASCII, so the answer
file does not depend on how Windows Setup treats national characters.
