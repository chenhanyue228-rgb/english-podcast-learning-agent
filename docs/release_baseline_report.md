# v1.1 Release Baseline Report

## Executive Summary

The local English Audio Learning Agent repository is ready for human review
before push. Completed v1.1 implementation, tests, documentation, and repository
hygiene are organized into four local commits on a dedicated branch. No remote
push, tag, or GitHub release was created.

The working tree is intentionally not completely clean. Four ambiguous or
outdated diagnostic/design files remain untracked as `REVIEW_REQUIRED`; they
were preserved and excluded instead of being deleted or committed
automatically.

## Branch

`chore/v1.1-release-baseline`

The branch was created from `main` at `564cced`. Existing working-tree changes
were preserved without stash, reset, clean, or checkout-based restoration.

## Repository Inventory

Initial inventory:

- 36 tracked files with local modifications
- 94 compact untracked entries reported by `git status`
- 117 actual untracked files reported by `git ls-files --others`
- 153 actual changed files inspected

Final classification:

- 149 files committed as completed v1.1 work
- 4 files left untracked as `REVIEW_REQUIRED`
- generated and private runtime directories remain local and ignored
- no staged or committed secret-bearing file was detected

Committed categories:

- production and compatibility runtime: 77 files
- tests and read-only diagnostics: 51 files
- canonical and historical documentation: 19 files
- environment template and repository hygiene: 2 files

Experimental and legacy code was retained when it was already part of the
tested v1.1 implementation or imported by compatibility commands. It is not
presented as the production path.

## Commit Summary

- `f7c0aa7` `feat(runtime): finalize v1.1 Codex skill workflows`
  - Codex artifact runtime, Podcast/Vocabulary/Weekly Reflection workflows,
    Notion publishing, schemas, prompts, and explicit compatibility providers.
- `03b7dc4` `test: cover stable v1.1 workflows`
  - Regression tests, smoke scripts, and read-only diagnostic tools. A copied
    personal Notion page ID was replaced with a synthetic test ID.
- `69c4add` `docs: synchronize v1.1 product and architecture baseline`
  - Product context, architecture, decisions, Skill contract, current task,
    onboarding direction, and historical documentation alignment.
- `a173e57` `chore(repo): establish release baseline hygiene`
  - Safe environment-variable template and conventional ignore rules for
    private and generated files.

This report is added in the final local documentation commit after the four
baseline commits above so it can record their stable hashes.

## Architecture Status

**Stable**

The release baseline preserves the accepted runtime:

```text
Codex Skill
↓
Generated artifact
↓
Python validation and workflow execution
↓
Notion publishing
```

No architecture, Notion schema, prompt contract, or production workflow was
redesigned during release preparation.

## Documentation Status

- `PROJECT_CONTEXT.md`: synchronized
- `ARCHITECTURE.md`: synchronized and concise source of truth
- `CURRENT_TASK.md`: v1.1 release baseline preparation
- `CHANGELOG.md`: v1.1 scope and 344-test result recorded
- `DECISION_LOG.md`: historical decisions preserved
- `README.md`: user-oriented production workflow
- `skill/SKILL.md`: production Codex Skill contract
- `docs/current_architecture.md`: synchronized implementation reference
- `docs/codex_skill_contract.md`: artifact responsibility contract
- `docs/weekly_reflection_product_contract.md`: accepted product boundary
- `docs/stabilization_report.md`: preserved pre-release audit snapshot
- `docs/next_steps.md`: Phase 4 Product Validation handoff

## Test Results

Command:

```bash
./.venv/bin/python -m pytest -q
```

Result:

- 344 passed
- 0 failed
- 3 expected deprecation warnings
- runtime: 0.59 seconds

The warnings come from tests that explicitly select deprecated OpenAI
compatibility providers. Production provider factories continue to default to
Codex artifacts.

## Product-Scope Verification

- Codex is the production reasoning and generation runtime.
- Python performs deterministic processing, validation, orchestration, and
  Notion synchronization.
- Podcast episode URLs, Podcast RSS feeds, and local audio files are the
  supported v1 inputs.
- YouTube is experimental and is not presented as a supported v1 input.
- Vocabulary follows Human Highlight + AI Processing.
- Weekly Reflection is a learning compounding note, not a data-heavy report.

## Excluded Local Files

The following local/private categories remain ignored and were not committed:

- `.env` and environment-specific variants
- `.venv/` and other virtual environments
- Python and pytest caches
- `data/` downloaded audio, transcripts, requests, and analysis artifacts
- `output/` generated reflection and pipeline artifacts
- `logs/` runtime logs
- cookie files and partial downloader output
- coverage, editor, and operating-system metadata

No local generated file was deleted during this task.

## Review Required

The following files remain untracked and were not committed:

- `skill/schemas/weekly_review_v2_schema.json`
  - Unreferenced pre-curation database/page design schema that conflicts with
    the accepted Weekly Reflection product contract.
- `src/weekly_review/models.py`
  - Unreferenced legacy dataclasses for the pre-curation WeeklyReview shape.
- `src/notion/debug_network.py`
  - Read-only diagnostic module with stale `NotionConfig` attribute names.
- `tests/debug_notion_connection.py`
  - Standalone diagnostic script using the old `databases.query()` SDK path and
    printing broad live response details.

The repository owner should decide whether to repair, archive, or delete these
files in a separate task. They must not be force-added to this baseline.

## Remaining Technical Risks

1. Vocabulary duplicate lookup may treat a Notion query error as no match,
   permitting a duplicate create in a failure case.
2. Weekly extraction counts per-page failures without retaining detailed error
   causes.
3. ReflectionContext may be resolved more than once in the Weekly Reflection
   orchestration path.
4. Legacy comment sync retains extensive diagnostic output.
5. Experimental YouTube code and deprecated OpenAI providers remain as
   compatibility paths and add maintenance surface.

These risks are deferred intentionally. None blocked the regression suite, and
none was expanded into unscheduled refactoring during baseline preparation.

## Recommended Human Review

- [ ] Inspect all four baseline commits by purpose.
- [ ] Review `main...chore/v1.1-release-baseline` for scope and private data.
- [ ] Confirm the four `REVIEW_REQUIRED` files should remain excluded.
- [ ] Run the full test suite in the owner's terminal.
- [ ] Verify README and Skill first-use instructions from a new-user viewpoint.
- [ ] Approve the branch before any push or tag.

## Recommended Release Command Sequence

Run only after human approval:

```bash
git log --oneline main..chore/v1.1-release-baseline
git diff --stat main...chore/v1.1-release-baseline
git diff --check main...chore/v1.1-release-baseline
./.venv/bin/python -m pytest -q
git push -u origin chore/v1.1-release-baseline
```

After branch review and merge, create the `v1.1.0` tag only with explicit owner
confirmation. No push, tag, or release action was executed during baseline
preparation.
