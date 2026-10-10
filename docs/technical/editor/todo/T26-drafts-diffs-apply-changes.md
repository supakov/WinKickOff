# T26. Drafts, diff profiles, the comparison as a tree, applying the changes only, the read as administrator

Status: done in code (10.10.2026), version 1.4.0-rc.2; acceptance in a VM pending for the apply and the elevated read.
Stage 10. Dependencies: T11 (window), T14 (comparison), T15 (apply), T25 (read of this PC).

## Goal

The customer's requests of 10.10.2026, after T25: the read of this PC as administrator; a draft of the unsaved changes
written on a timer, loaded at the next start, so that closing asks nothing; the changes since the last save, diff
profiles with only the differences and their merge, the comparison as a tree with the description of the rule;
applying the changes, and only them, to this PC from the comparison.

## Result

- `core/apply.run_audit_elevated`: `ShellExecuteExW` with `runas`, a hidden `powershell.exe`, waits for it, reads the
  report; a declined prompt (`ERROR_CANCELLED`) is "Administrator rights were not given". The window offers "Read the
  settings of this PC as administrator into a new profile..." (`read_this_pc(elevated=True)`). MCP never elevates.
- `core/draft.py`: `draft.json` in the program folder (envelope with the profile path), written through a temporary
  file every `DRAFT_INTERVAL_MS` when the changes differ from the last draft and on close (`on_close` asks only when
  the draft cannot be written); `app.create_app` opens it unsaved with a message; saving, opening another profile as
  saved (`set_profile(dirty=False)`) or "No" in `confirm_discard` deletes it. Not versioned (`.gitignore`).
- `core/diffprofile.py`: `make_diff` (only differing states, effective parameter values, fields, the account list),
  `save_diff`, `load_diff` (strict, `.wkdiff`), `merge_diff` (resolver cascade, `check_param`, warnings).
- Window: "File, Changes since the last save...", "File, Merge a diff profile..."; `open_comparison` is a tree
  (top groups, rules with their parameters, data forms) with the description of the selected rule and the buttons
  "Save the differences as a diff profile..." and "Apply these changes to this PC..." (`apply_now(rule_items)`).

## Acceptance criteria

- `python -m unittest discover -s tests` is green (`tests/test_drafts_diffs.py`); no test elevates, runs the audit or
  shows a window.
- In a VM: the elevated read reads features; applying the changes of a comparison changes only those rules.
