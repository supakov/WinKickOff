# T02. Rule catalog: format, loader, integrity, v0.2 transfer, semantic golden

Status: done (25.09.2026: format, groups, full transfer of v0.2 actions, loader, integrity
verification and the semantic golden `test_coverage_v02.py` are ready and green). Stage 1. Dependencies: T01. Milestone M1.

## Goal

Transfer every action of the v0.2 file into rules in `rules/*.toml` following the format in `03-data-model.md`,
implement the loader and the integrity verification, and prove the completeness of the transfer with a test.

## Steps

1. `rules/groups.toml`: a tree of groups following the areas of the reference (installation, OOBE, accounts,
   printing, updates, Defender, security, network, media and scripts, logging, privacy,
   applications, default profile, first sign-in, after OOBE).
2. `rules/NN-*.toml` files by phase and area. Every unconditional v0.2 action goes into a
   rule of the `baseline` level; every `$Config` switch becomes one or more
   rules; the 17 ASR rules are separate rules with a mode parameter that require `defender.asr`;
   the applications from `$AppsToRemove` are one rule with an `appx` action (a list) plus the ability to
   disable individual applications through parameters (to decide: a list of check-box parameters or separate rules).
3. For each rule: `summary`, `effect`, `risk` (if any), `versions`, `verify`, `rollback`,
   `doc` with a link to the reference card; texts are condensed from `docs/technical/reference/`.
4. Dependencies per section 17 of the reference: ASR → `defender.asr`; three cloud ASR rules →
   `defender.cloud`; `logging.powershell` → `logging.eventlog-sizes`; `update.defer-feature` →
   does not conflict with `privacy.telemetry` (DiagTrack Manual); `accounts.password-never-expires` →
   `accounts.starter`, etc.
5. `core/catalog.py`: models, `load_catalog(path)`, `CatalogError`, integrity verification, search index.
6. `tests/test_catalog.py`: loading the real catalog; faulty catalogs in a temporary folder.
7. `tests/v02_actions.py` and `tests/test_coverage_v02.py`: semantic golden per `04-testing.md`, section 2.

## Acceptance criteria

- The integrity verification of the real catalog reports no errors.
- Semantic golden: all v0.2 actions are covered; the list of catalog actions outside v0.2 is empty or deliberate.
- Every rule has `summary`, `effect`, `doc`; `doc` links point to existing files.

## Implementer notes

25.09.2026: all sections of `Setup-System.ps1`, `Setup-User.ps1`, `Post-OOBE.ps1` and the XML elements
of v0.2 have been transferred. The loader and the integrity verification are written, the catalog tests pass. The semantic golden
(`tests/test_coverage_v02.py`) is implemented in basic form for the `reg`, `reg-remove`, `service`, `exe` actions;
`ps` fragments are compared by the presence of key strings. See the `python -m unittest` result in README.
