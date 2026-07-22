# Phase 4.1B Onboarding Fix Report

## Audit Baseline

The Phase 4.1 clean-clone audit recorded:

- P0: 0
- P1: 2
- P2: 3
- P3: 4
- external-user sessions: 0
- technical onboarding state: blocked by Skill discovery and Notion setup

The audit ran from a clean clone and did not use production credentials,
personal learning data, or a live Notion workspace.

## Branch Baseline

- stable release: `v1.1.0`
- main baseline merged into this branch: `447608f21d97b317d966c8e61620d8e9701ce4c9`
- working branch: `fix/phase-4.1-onboarding-blockers`
- branch state before synchronization: ahead by 2, behind by 2
- synchronization method: ordinary merge from `origin/main`; no rebase or
  force push
- preserved evidence:
  - `phase4_1_clean_clone_report.md`
  - `phase4_1_issue_log.md`

## Fix Scope

### PV-001: Skill installation and discovery

- Added valid Skill frontmatter and regression coverage.
- Made `$skill-installer` the primary user-facing installation route.
- Added explicit next-turn/restart guidance and the
  `$english-audio-learning-agent` discovery check.
- Moved the local symbolic-link method to a Developer-only fallback.

### PV-002: Four-database Notion onboarding

- Linked one copyable setup path from the README and Skill manifest.
- Documented integration creation, parent-page sharing, setup, and validation.
- Aligned onboarding around Podcast Library, Expression Database, Weekly
  Review, and Vocabulary Database.

### PV-003: Isolated Python environment

- Made `.venv` creation and `.venv/bin/python` the default onboarding path.

### PV-004: Podcast Analysis artifact handoff

- Added the request path, expected output path, explicit Skill invocation, and
  shlex-safe rerun command to CLI output.
- Preserved transcript reuse, path derivation, return codes, and publishing
  behavior.

### PV-005: Supported Podcast URL wording

- Clarified that the supported page URL is an Apple Podcasts episode URL.
- Retained Podcast RSS and local audio as supported alternatives.

## Files Changed

- `README.md`
- `skill/SKILL.md`
- `docs/Notion_Onboarding.md`
- `src/main.py`
- `src/notion/setup_workspace.py`
- `tests/test_main.py`
- `tests/test_notion_setup_workspace.py`
- `tests/test_skill_manifest.py`
- `docs/product_validation/phase4_1_onboarding_fix_report.md`

Canonical status files were not modified. `ARCHITECTURE.md` was inspected and
already states that Weekly Review stores the final Weekly Reflection, so no
architecture edit was required.

## Skill Installation Decision and Evidence

The current Codex environment includes the system `$skill-installer`. Its
documented helper supports installation from a GitHub repository path.

The helper was executed through Python against this repository's `skill/`
directory on `fix/phase-4.1-onboarding-blockers`, using a temporary destination
and the name `english-audio-learning-agent`. Installation completed and the
installed manifest passed `quick_validate.py`.

Equivalent helper invocation used for the technical check:

```text
python $CODEX_HOME/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo chenhanyue228-rgb/english-podcast-learning-agent --path skill --ref fix/phase-4.1-onboarding-blockers --dest <temporary-directory> --name english-audio-learning-agent
```

This is technical installation evidence, not Owner Acceptance. The README
uses the product-level `$skill-installer` invocation rather than exposing the
internal helper. The owner must still install from merged `main`, start the
next Codex turn or restart Codex, and verify explicit Skill discovery.

## Weekly Review and Weekly Reflection Naming Contract

- canonical Notion database container title: `Weekly Review`
- stored product output: `Weekly Reflection`
- canonical environment variable:
  `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
- legacy compatibility alias: `NOTION_WEEKLY_REVIEW_DATABASE_ID`

Setup, onboarding output, docs, and tests use this contract. No live Notion
database was called, renamed, migrated, or otherwise modified.

## Validation Results

### Targeted tests

Command:

```text
./.venv/bin/python -m pytest -q tests/test_skill_manifest.py tests/test_main.py tests/test_notion_setup_workspace.py tests/test_notion_config.py
```

Result: **43 passed, 0 failed**.

### Full regression

Command:

```text
./.venv/bin/python -m pytest -q
```

Result: **351 passed, 0 failed, 3 expected compatibility-provider deprecation
warnings**.

### Repository checks

- `git diff --check`: **PASS** on the committed branch
- final clean-worktree check: **PASS** after the closure commit
- committed-state full regression: **351 passed, 0 failed, 3 expected warnings**

## Remaining Owner Acceptance Steps

1. Install `english-audio-learning-agent` from merged `main` through
   `$skill-installer`.
2. Start the next Codex turn or restart Codex and verify
   `$english-audio-learning-agent` discovery.
3. Create a disposable, non-production Notion parent page.
4. Run the four-database setup and `check_workspace`.
5. Complete one non-sensitive artifact-to-Notion learning journey.
6. Record evidence and resolve any P0/P1 owner-acceptance blocker.

Owner Acceptance is not complete. No external-user validation has occurred.
External-user session count remains **0**.

## Architecture Impact

None. The stable runtime remains:

```text
Codex Skill
-> structured artifacts
-> Python validation and workflow
-> Notion
```

No schema, provider, product-scope, Vocabulary-intent, Weekly Reflection, or
live Notion behavior was changed.

## Readiness

**READY_FOR_PR**

This state means the branch is ready for review. It does not mean
`READY_FOR_OWNER_ACCEPTANCE` or `READY_FOR_EXTERNAL_USERS`.
