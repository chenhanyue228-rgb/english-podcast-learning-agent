# Current Task

## Phase

Phase 4.2 - External User Validation

## Stable Baseline

- Release: v1.2.0
- Phase 3 runtime baseline:
  `156b37f08290aa9b985112269d2a373de51c48d2`
- PR #23 Phase 1 read-only detection: merged
- PR #24 Phase 2 enrichment and protected publishing: merged
- PR #25 Phase 3A bounded runtime and scheduler: merged
- Architecture: Stable
- Architecture Review: not required

## Current Sprint

**Execution state:** External User Session #1 preparation

**Engineering status:**
`ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING`

Current facts:

- Setup / Notion workspace recovery: PASS
- Target Binding: PASS
- Automated Podcast Owner Acceptance: PASS
- Targeted Vocabulary Acceptance: PASS
- Weekly Reflection Acceptance: PASS
- Automatic Vocabulary real Owner Acceptance: PASS
- Automatic Vocabulary first publish: created 1
- Automatic Vocabulary exact retry: created 0, updated 0
- Automatic scheduler: installed and loaded
- Scheduler interval: 60 seconds
- First scheduler cycle: BASELINED
- Second scheduler cycle: NO_WORK
- Expression / Weekly / schema / historical writes during automatic
  acceptance: 0
- External-user sessions: 0
- External-user validation: NOT RUN

`ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING` means the engineering
gate is complete. Do not report `EXTERNAL_USER_VALIDATION_PASS` before real
session evidence exists.

## Completed Gates

- Phase 0 architecture and isolated unattended Codex feasibility.
- Phase 1 target-scoped SQLite detection, exact occurrence identity,
  first-enable baseline, overlap watermark, and 90-second quiet period.
- Phase 2 isolated Codex enrichment, strict artifact validation, Target
  Binding, protected Vocabulary upsert, retry, and reconciliation.
- Phase 3A one-shot worker, process lock, redacted logs, protected Owner
  Acceptance Harness, and bounded macOS LaunchAgent lifecycle.
- Phase 3B protected dry-run and real Notion Owner Acceptance.
- Exact word, exact context, full properties, full body, source relation,
  occurrence fingerprint, and exact retry validation.
- Production LaunchAgent activation from the supported non-protected project
  location.

## Current Tasks

1. Recruit External User Session #1 using the merged Session Kit.
2. Verify the participant uses a project location outside macOS protected
   `Documents`, `Desktop`, and `Downloads` folders.
3. Observe the complete journey without developer intervention:

```text
Install and configure
↓
Process a supported audio source
↓
Publish Podcast learning assets
↓
Add one exact pink highlight
↓
Automatic Vocabulary enrichment and publish
↓
Produce Weekly Reflection when enough learning data exists
```

4. Record time-to-environment-ready, time-to-first-Notion-page,
   time-to-first-value, questions, failures, and recovery.
5. Keep external-user session count at 0 until a real participant starts.

## Automatic Vocabulary Operations

Normal users only add a pink highlight. They do not provide a page ID, run a
command, or say "同步生词".

Developer/recovery operations:

```bash
./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py status
./.venv/bin/python scripts/run_automatic_vocabulary_once.py
```

Install and uninstall require the exact confirmations documented in
`skill/SKILL.md` and `docs/USER_GUIDE_ZH.md`.

## Deferred Non-Blocking Backlog

- manual color adjustment for the existing Expression Database

The Parent Page Guide and Podcast/Weekly tables of contents are accepted
contracts, not backlog items.

## Cancelled Requirements

- Notion AI-assisted page workflow
- Podcast-page Expression synchronization into Expression Database

They must not reappear in the active roadmap, blockers, or user guide.

## Out of Scope

- architecture or Notion schema redesign
- Hosted Webhook, OAuth, cloud credential storage, or multi-tenant backend
- infinite polling daemon
- YouTube support
- historical Vocabulary backfill
- historical database-group access
- external-user validation claims without session evidence

## Handoff

Read in this order:

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `CURRENT_TASK.md`
4. `skill/SKILL.md`
5. `docs/codex_skill_contract.md`
6. `DECISION_LOG.md`
