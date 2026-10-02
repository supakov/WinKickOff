# T16. Splitting the documentation: technical in English, user in three languages

Status: done (25.09.2026). Stage 5. Dependencies: T17.
Changes part of T13: the user documentation is issued in three languages at once.

## Goal

Split the documentation into two branches with different readers:

- technical (developers, agents, administrators who edit the catalog): English only;
- user (those who build the answer file and install Windows): Ukrainian, English, Russian.

## What goes where

| Now | Reader | Becomes |
|---|---|---|
| `docs/technical/reference/` (18 parameter cards) | technical | `docs/technical/reference/`, English |
| `docs/technical/editor/01-06` (specification, architecture, data model, tests, plan, review of 0.1) | technical | `docs/technical/editor/`, English |
| `docs/technical/editor/todo/` (tasks) | technical | English; open tasks are translated, closed ones as they are touched |
| `AGENTS.md`, `WinKickOff/templates/README.md`, `WinKickOff/profiles/README.md` | technical | English |
| `WinKickOff/README.md` | both | a short technical README in English plus links to the user documentation |
| The "Workflow" node in the window, `README.md` (how to apply, VM verification checklist) | user | `docs/user/{uk,en,ru}/` |
| `docs/appendices/C-critical-review/` (critic report), reports at the customer's request | customer | stay in Russian in the appendices (moved in T17) |

Code comments and log messages are already in English. Rule texts in the catalog (`summary`,
`effect`, `risk`) are interface, not documentation: Russian plus `rules/lang/uk.toml`; English
is added with the file `rules/lang/en.toml` (related to T14).

## Contents of the user documentation (each language)

1. `README.md`: what WinKickOff is, who it is for, what the output is.
2. `quick-start.md`: from launching the program to a USB stick with `autounattend.xml` in 7 steps (the text of the
   "Workflow" node).
3. `profiles.md`: the "Office" and "Strict" presets, custom profiles, where they are stored, how to move them to another PC,
   how to restore a profile from a built file.
4. `install-and-check.md`: installing from a USB stick, what the installer will ask, verification after installation
   (the checklist from `README.md`), where the logs are, what to do on an error.
5. `rules.md`: a rule reference, generated from the catalog in the document's language
   (`tools/make_rule_docs.py`), so that it does not diverge from the program.
6. `safety.md`: a VM first, then work PCs; passwords are in the file in plain text; what to do if keyboard
   layouts break (example of 12.09.2026).

## Steps

1. The structure of `docs/technical/` and `docs/user/{uk,en,ru}/` with indexes; `docs/README.md` as the entry point
   in three languages (one paragraph per language).
2. Translation of the technical documents into English, preserving the structure; the `doc` fields of the 130 catalog
   rules are rewritten to the new paths and English anchors (the anchors are currently Russian, for example
   `#безусловные-значения`, and will change after translation).
3. The `doc` link check is extended: the catalog loader checks not only the file but also the anchor
   (a heading in the file). Test in `test_catalog.py`.
4. User documentation in Russian as the source, then Ukrainian and English translations;
   the header of each file: language, program version, date.
5. `tools/make_rule_docs.py`: `rules.md` in three languages from the catalog and the `rules/lang/*.toml` files.
6. Synchronization test: the three languages have the same set of files and the same number of second-level
   headings; `rules.md` matches what the tool generates.
7. Window: "Help, User documentation" opens the user documentation in the display language;
   "More details" on a rule leads to the technical reference.
8. `AGENTS.md`, rule 4, changes: communication with the customer in Russian; technical documentation in
   English; user documentation in Ukrainian, English and Russian; reports at the customer's request in
   Russian in Markdown.

## Acceptance criteria

- `docs/technical/` contains no Cyrillic except quotations of Windows values (layout names, interface
  examples) and agreed terms; checked by a test with an exception list.
- The user documentation exists in three languages with the same structure; the synchronization test is green.
- All catalog `doc` links point to an existing file and anchor.
- No em dashes or en dashes in any language.

## Risks

- Volume: 18 reference cards and 6 specification documents. Estimate 6 days; the translation is done
  section by section with a link check after each one.
- The three languages drift apart over time. Protection: generating the rule reference from the catalog and a
  structure synchronization test.

## Implementer notes

25.09.2026:
- Moved with `git mv`: `docs/reference` to `docs/technical/reference`, `draft/install-editor` to
  `docs/technical/editor`; the first requirements draft (Russian, customer-facing) to Appendix D.
- Translated into English: 18 reference cards, the specification (01-06), all task files, `AGENTS.md`,
  `WinKickOff/README.md`, `templates/README.md`, `profiles/README.md`, the root `README.md`. Heading
  structure was kept one to one, so 62 rule `doc` anchors were remapped by position automatically.
- User documentation in `docs/user/{ru,uk,en}`: README, quick-start, profiles, install-and-check, safety,
  and `rules.md` generated by `tools/make_rule_docs.py` from the catalog and `rules/lang/{uk,en}.toml`
  (complete translations of all 130 rules, 24 groups, parameters and options; this also covers step 2 of T14).
- `tests/test_docs.py`: no dashes, technical docs in English (Cyrillic only in «UI names» and code), the
  same structure in the three languages, generated rule lists up to date, complete translations, every
  relative link and anchor resolves. The loader-level anchor check is a warning of `validate_catalog`.
- The editor: "Help, User documentation" opens `docs/user/ru/README.md`;
  the rule description links to the technical reference card.
- The appendices stay Russian (customer materials). Commit messages stay Russian.
