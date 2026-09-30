# T10. Rule parameters, data forms (installation, accounts, languages)

Status: done (25.09.2026: rule parameters by type with a "changed" mark, rules with changed
parameters highlighted in the tree; the "Installation", "Accounts" and "Languages and region"
forms; tests). Stage 4. Dependencies: T09.

## Goal

Editing rule parameters in the description panel, and forms for the data nodes.

## Steps

1. Parameters: a widget per type (`int` → Spinbox with a range, `enum` → read-only Combobox,
   `string` → Entry, `bool` → Checkbutton); a change goes straight into the profile; highlighting of values
   that differ from the default.
2. `ui/data_forms.py`: the "Installation" node (edition, key mode, key, time zone from the reference,
   ISO language); the "Accounts" node (table, add/edit/delete/up/down, on-the-fly name
   check, warning when a password is set); the "Languages and region" node (display language, formats, region, input
   list with ordering, transient mark).
3. All forms write to the profile immediately and set the modified flag.
4. Tests: changing a parameter changes the profile; adding an account with a reserved name
   is rejected with a reason.

## Acceptance criteria

- The "Office" preset opens and is displayed without loss; the order of languages is preserved in the XML.

## Implementer notes
