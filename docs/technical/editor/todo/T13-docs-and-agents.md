# T13. User documentation, AGENTS.md, acceptance

Status: blocked (25.09.2026: the documentation part is done; the acceptance installation needs a VM,
which only the customer can run). Stage 5. Dependencies: T12. Milestone M5.

Related: the user documentation is issued in Ukrainian, English and Russian under task T16;
the technical documentation is in English.

## Goal

User instructions in the build, an up-to-date project map, an acceptance installation.

## Steps

1. `README-user.md`: running from a USB stick, a profile from a preset, finding and turning off a rule, building,
   the installation media, what to verify after installation (link to the checklist in the root README), where the logs are,
   limitations (plain-text passwords, SmartScreen on the exe).
2. Update `docs/technical/editor/README.md` and the root `AGENTS.md` (structure, commands, status).
3. Acceptance installation in a VM with a file from the build; report `docs/04-acceptance-<date>.md`.

## Acceptance criteria

- A person with no knowledge of the project builds an XML following `README-user.md` within 10 minutes.
- Every path in AGENTS.md exists.

## Implementer notes

25.09.2026: step 1 is covered by the user documentation of T16 (`docs/user/{ru,uk,en}`: quick start,
profiles, installation and checks with the checklist and log locations, safety with plain-text passwords);
the SmartScreen note for the unsigned exe is added when the T12 build exists. Step 2 is done; the criterion
"every path in AGENTS.md exists" is checked by `tests/test_docs.py`. Step 3 waits for a VM: install from a
"Office" build, go through `docs/user/ru/install-and-check.md`, write the report in Russian.
