# Project Context

## Product

**Name:** English Audio Learning Agent

English Audio Learning Agent transforms podcasts, RSS feeds, and local audio
files into reusable English learning assets:

- Podcast learning notes
- professional expressions
- user-selected vocabulary
- compounding Weekly Reflections

## Current Phase

**Phase:** Phase 4.2 — External User Validation

**Execution stage:** Automatic Vocabulary Sync Architecture Implementation
Preparation

**Status:** `OWNER_ACCEPTED_CORE_INTERNAL_RELEASE_WITH_NON_BLOCKING_ISSUES`

The stable release remains **v1.1.0**, built from release commit
`80cbab01ea266e487a0359ddbec562959070d8a0`. The Phase 4.1C closure starts
from production `main` `de9f088a47b58ad54de9ef281ddf427c994dbf0a`.
The current production `main` is
`5b08e4bb73db3bffe2a3787cf090d88bdcb4d7be`.

Current release and acceptance evidence:

- PR #9 merged the partial Podcast/Expression publish recovery.
- PR #10 merged the protected Podcast Owner Acceptance Harness.
- PR #11 merged fail-closed Notion target-group binding.
- PR #14 implemented, independently reviewed, and merged the protected
  Vocabulary Acceptance Harness after all identified P0/P1 false-pass paths
  were closed.
- PR #16 added semantic Select colors for future Expression Database creation
  without changing option names or rewriting existing databases.
- PR #20 added and accepted the protected Parent Page Guide.
- PR #21 restored the accepted Podcast table-of-contents output contract.
- The five local target settings now point to the intended database group.
- The Notion token did not change during the target switch.
- Setup / Notion workspace recovery: PASS.
- Read-only Target Binding Diagnosis: PASS.
- Automated Podcast Owner Acceptance: PASS.
- Podcast first publish: PASS.
- Podcast exact retry: PASS.
- Targeted Vocabulary Acceptance: PASS.
- Vocabulary first publish: created 2.
- Vocabulary exact retry: created 0.
- Weekly Reflection Acceptance: PASS.
- Weekly first publish: created 1.
- Weekly exact retry: created 0.
- Non-target database changes: 0.
- Historical database group changes: 0.
- Owner Acceptance: `OWNER_ACCEPTANCE_PASS`.
- Internal release decision:
  `OWNER_ACCEPTED_CORE_INTERNAL_RELEASE_WITH_NON_BLOCKING_ISSUES`.
- External-user sessions: 0.
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`.
- Architecture: Stable.
- Architecture Review: `OWNER_APPROVED_FOR_PHASE_0`.
- Automatic Vocabulary Sync application runtime: not implemented.
- Isolated unattended Codex synthetic feasibility: PASS.
- External User Session #1: blocked pending implementation and acceptance.

The internal release decision confirms the core flow for internal use. It does
not mean the product is `READY_FOR_EXTERNAL_USERS`.

## Runtime Model

### Codex: Reasoning and Generation

Codex performs language understanding and creates schema-conformant artifacts
for Podcast Analysis, Vocabulary enrichment, Reflection Analysis, and Weekly
Review generation.

### Python: Orchestration and Validation

Python performs source processing, transcription, artifact validation,
deterministic workflow execution, dedupe, state management, and Notion
synchronization.

### Notion: Long-Term Knowledge Memory

Notion stores:

- Podcast Library
- Expression Database
- Vocabulary Database
- Weekly Review

## Production Artifact Flow

```text
Codex Skill
↓
Request Artifact
↓
Codex-generated JSON
↓
Python Validation
↓
Workflow
↓
Notion
```

The production Skill path does not require `OPENAI_API_KEY`. Direct OpenAI
providers remain deprecated compatibility paths only.

## Supported v1 Inputs

- Apple Podcasts episode URL
- Podcast RSS feed
- Local audio file

YouTube is outside v1 product scope.

## Accepted Workflows

### Podcast Learning

```text
Audio Source
↓
Transcript
↓
Codex Podcast Analysis
↓
Python Validation
↓
Podcast Library + Expression Database
```

The protected automated acceptance against the intended target group passed:

- Podcast first delta: 1
- Podcast second delta: 0
- Expression first delta: 19
- Expression second delta: 0
- Vocabulary Database: unchanged
- Weekly Review: unchanged
- historical database group: unchanged

Podcast body bolding, semantic highlights, Highlight Legend, and Highlighted
Transcript are working. They are not part of the current visual defect.

### Vocabulary Memory

```text
User Pink Highlight
↓
Approved automatic detection after a 90-second quiet period
↓
Target-group-scoped exact occurrence state
↓
Isolated Codex Enrichment
↓
Python Validation, Target Binding, and Idempotent Upsert
```

Podcast publishing and Vocabulary synchronization are separate workflows. An
empty Vocabulary Database after Podcast acceptance does not prove that the
Vocabulary sync script is broken.

This automatic path is Owner-approved for Phase 0 architecture and feasibility
only. It is not implemented or active. The previously accepted explicit
targeted sync remains a Developer/recovery path, but “同步生词” is suspended as
the default user journey.

Accurate current Vocabulary status:

- the protected targeted acceptance passed;
- the first publish created 2 Vocabulary records;
- the exact retry created 0 new records;
- non-target and historical database groups remained unchanged;
- the current global full-scan checkpoint and normalized highlight identity
  are not safe for the approved automatic workflow;
- Phase 1 must replace them with target-group-scoped SQLite and exact
  occurrence fingerprints before automatic detection can be activated.

### Weekly Reflection

```text
Podcast Library
↓
WeeklyLearningContext
↓
ReflectionContext
↓
WeeklyReview
↓
Quality Gate
↓
Weekly Review Database
```

Weekly Reflection is a compounding learning note, not a podcast recap.

Protected Weekly acceptance passed. The first publish created 1 Weekly page,
the exact retry created 0, and Podcast, Expression, Vocabulary, and historical
database groups remained unchanged.

## Notion Target Binding

All production writers are bound to one configured parent and one internally
consistent four-Data-Source group. Target validation checks role, schema,
common parent, single-property relations, and cross-group isolation before
writes.

The coordinated local switch changed only:

- Podcast Data Source
- Expression Data Source
- Vocabulary Data Source
- Weekly Data Source
- target parent page

The token and historical group were preserved.

## Expression Select Colors

PR #16 added semantic Select colors for future Expression Database creation
for:

- Category
- Commonness
- Review Status

Existing option names remain unchanged. Existing databases are not
automatically rewritten and may still display gray options. Their colors may
be changed manually in the Notion UI only; existing options must not be
deleted, recreated, or renamed.

## Phase 4.2 Validation Goals

Phase 4.2 will validate the accepted internal release with real external users
after the automatic Vocabulary trigger passes implementation and acceptance:

- complete 3 real external-user sessions;
- have at least 2 users complete the core flow without developer intervention;
- record time-to-first-value;
- record confusion, failed steps, and recovery outcomes;
- avoid speculative large-scale refactoring before evidence is collected.

External User Session #1 must not start during architecture preparation.

## Deferred Non-Blocking Backlog

Podcast and Weekly page tables of contents are accepted output contracts under
DEC-021, not deferred polish. Every newly generated Podcast or Weekly page must
begin with exactly one navigable table of contents.

The following polish is separate from the automatic Vocabulary implementation:

- manual color adjustment for the existing Expression Database.

The Parent Page Guide is accepted. Automatic trigger replacement and
target-group state isolation are active architecture work, not deferred polish.

## Cancelled Proposal

The following proposal was cancelled before implementation and is not part of
the active goals, blockers, risks, or roadmap:

- Notion AI-assisted page workflow;
- synchronization of Podcast-page Expressions into Expression Database.

No Architecture Review or user-guide commitment remains active for this
proposal.

## Frozen Boundaries

- Codex Artifact → Python Validation → Notion architecture
- four-database product model
- Podcast page body contracts
- artifact JSON contracts
- Vocabulary/Expression ownership separation
- exact pink-highlight vocabulary intent
- Weekly Reflection product structure
- Notion idempotent publishing and target binding

## Immediate Milestone

Complete Automatic Vocabulary Sync Phase 0 architecture/feasibility, then
build the separately reviewed Phase 1 read-only detection foundation.
External-user sessions remain at 0 until the automatic Vocabulary journey is
implemented and accepted.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md`,
`docs/architecture/automatic_vocabulary_sync_architecture_review.md`,
`skill/SKILL.md`, and `DECISION_LOG.md` before changing runtime behavior.
