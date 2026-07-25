# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- Release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Phase 4.1C closure base:
  `de9f088a47b58ad54de9ef281ddf427c994dbf0a`
- PR #9: merged
- PR #10: merged
- PR #11: merged
- PR #14 Vocabulary Acceptance Harness: merged
- PR #16 Expression Select semantic colors: merged
- PR #20 Parent Page Guide: merged and accepted
- PR #21 Podcast TOC regression fix: merged
- Production main: `5b08e4bb73db3bffe2a3787cf090d88bdcb4d7be`
- Architecture: Stable
- Architecture Review: `OWNER_APPROVED_FOR_PHASE_0`

## Current Sprint

**Phase 4.2 — External User Validation**

**Execution state:** Automatic Vocabulary Sync Architecture Implementation
Preparation

Current status:

- Phase 4.1C: COMPLETED
- Setup / Notion workspace recovery: PASS
- Target Binding: PASS
- Automated Podcast Owner Acceptance: PASS
- Podcast first publish: PASS
- Podcast exact retry: PASS
- Targeted Vocabulary Acceptance: PASS
- Vocabulary first publish: created 2
- Vocabulary exact retry: created 0
- Weekly Reflection Acceptance: PASS
- Weekly first publish: created 1
- Weekly exact retry: created 0
- Non-target database changes: 0
- Historical database group changes: 0
- Owner Acceptance: `OWNER_ACCEPTANCE_PASS`
- Internal release:
  `OWNER_ACCEPTED_CORE_INTERNAL_RELEASE_WITH_NON_BLOCKING_ISSUES`
- External-user sessions: 0
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`
- External User Session #1: BLOCKED
- Automatic Vocabulary Sync runtime: NOT IMPLEMENTED
- Isolated unattended Codex synthetic feasibility: PASS

`NOT_READY_FOR_EXTERNAL_USERS` is the canonical readiness token. Do not use a
space-separated variant in active project status.

Internal release acceptance does not imply external-user readiness.

## Completed Gates

- PR #9 partial Podcast/Expression publish recovery merged.
- PR #10 protected Owner Acceptance Harness merged.
- PR #11 Notion target binding merged.
- Five local target settings switched to the intended group.
- Notion token preserved.
- Read-only Target Binding Diagnosis passed.
- Protected Automated Podcast Owner Acceptance passed.
- First publish created 1 Podcast and 19 Expressions.
- Exact retry created 0 Podcast and 0 Expressions.
- Vocabulary and Weekly databases remained unchanged.
- Historical database group remained unchanged.
- PR #14 protected Vocabulary Acceptance Harness merged after independent
  review closed all identified P0/P1 false-pass paths.
- Targeted Vocabulary acceptance passed: first publish created 2 and exact
  retry created 0.
- Weekly Reflection acceptance passed: first publish created 1 and exact retry
  created 0.
- All acceptance runs preserved non-target databases and the historical
  database group.
- PR #16 added semantic Select colors to future Expression Database creation
  while preserving all option names and existing databases.

## Current Tasks

1. Complete Phase 0 architecture documentation and unattended Codex synthetic
   feasibility.
2. Independently review and accept the exact Phase 0 PR HEAD.
3. Build Phase 1 read-only automatic detection on target-group-scoped SQLite,
   exact occurrence fingerprints, a 90-second quiet period, overlap watermark,
   first-enable baseline, and bounded execution.
4. Do not connect Phase 1 to the Vocabulary publisher.
5. Resume External User Session #1 preparation only after the automatic
   Vocabulary journey is implemented and accepted.

## External Validation Journey

The core journey under observation is:

```text
Install and configure
↓
Process a supported audio source
↓
Publish Podcast learning assets
↓
Automatically capture exact pink-highlight Vocabulary
↓
Produce Weekly Reflection when enough learning data exists
```

Session evidence must distinguish a user-facing failure from an environment
problem and must not include secrets or private Notion identifiers.

The old explicit “同步生词” step is suspended as the default external-user
journey. Do not ask a participant for a page ID or command while automatic
sync remains under implementation.

## Deferred Non-Blocking Backlog

Podcast and Weekly page tables of contents are existing output contracts.
Every newly generated page must begin with exactly one navigable table of
contents; they are not deferred backlog items.

- manual color adjustment for the existing Expression Database

PR #16 gives newly created Expression databases semantic colors. Existing
databases are not automatically rewritten and may still show gray options.
Existing option colors may be changed manually in the Notion UI only. Do not
delete, recreate, or rename existing options.

This backlog is separate from the core external-validation journey and is not
a release blocker.

## Cancelled Requirements

The following are not active requirements and require no Architecture Review:

- Notion AI-assisted page workflow;
- Podcast-page Expression synchronization into Expression Database.

They must not reappear in the active roadmap, blockers, or user guide.

## Out of Scope

- architecture redesign
- Notion schema redesign
- background daemon or infinite polling
- Hosted Webhook, OAuth, cloud credential storage, or multi-tenant backend
- production automatic Vocabulary writes before protected acceptance
- LaunchAgent installation during Phase 0 or Phase 1
- YouTube support
- cloud hosting
- user accounts or payment
- historical TOC backfill
- external-user readiness claims

## Handoff

Read in this order:

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `CURRENT_TASK.md`
4. `skill/SKILL.md`
5. `docs/codex_skill_contract.md`
6. `DECISION_LOG.md`
