# T05. XML and PowerShell runtime templates

Status: done (25.09.2026). Stage 2. Dependencies: T02. Deviation from the steps: instead of separate XML slots,
a single `settings` slot that the generator fills entirely; the Setup-System phases are assembled from the
`section-*.ps1` sections; `VERSION` = 0.3. List of slots: `WinKickOff/templates/README.md`.

## Goal

Move everything in the v0.2 file that is not a rule into `templates/`: an XML skeleton with slots,
the runtime of the three scripts (functions, error handling, headers, hive mounting, waiting for OOBE).

## Steps

1. `templates/autounattend.template.xml`: the v0.2 structure with the slots `{{header}}`, `{{pe_commands}}`,
   `{{product_key}}`, `{{will_show_ui}}`, `{{specialize_commands}}`, `{{time_zone}}`,
   `{{international}}`, `{{oobe}}`, `{{local_accounts}}`, `{{files}}`, `{{profile}}`; both architectures.
2. `templates/Setup-System.runtime.ps1`: `Write-Log`, `Set-Reg`, `Remove-Reg`, `Set-ServiceStart`,
   `Invoke-Exe`, the new wrappers `Set-Feature`, `Remove-Capability`, `Remove-Apps`, `trap`, the HKU drive,
   the log header; the slots `{{blocks_specialize}}`, `{{default_user_block}}` (with hive mounting around
   `{{blocks_default_user}}`), `{{active_setup}}`, `{{post_oobe_task}}`, `{{config_json}}`.
3. `templates/Setup-User.runtime.ps1`: per-user log, the slot `{{blocks_user}}`, `exit 0`.
4. `templates/Post-OOBE.runtime.ps1`: waiting for `IMAGE_STATE_COMPLETE`, a pause, reading the profile,
   the slot `{{blocks_post_oobe}}`, moving `ua.err`, deleting the task, `exit 0`.
5. `templates/VERSION` = `0.2`; `templates/README.md` with the list of slots.
6. Test: substituting empty slots yields valid XML and parsable scripts.

## Acceptance criteria

- No runtime fragment contains rule logic.
- The runtime scripts are parsed by PowerShell 5.1 (test via `pscheck`, skipped without PowerShell).

## Implementer notes
