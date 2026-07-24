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

**Phase:** Phase 4.1C — Owner Acceptance

**Execution stage:** Protected targeted Vocabulary dry-run

**Status:** `VOCABULARY_ACCEPTANCE_DRY_RUN_READY`

The stable release remains **v1.1.0**, built from release commit
`80cbab01ea266e487a0359ddbec562959070d8a0`. Production `main` is
`987c7aa95f68b07b2a258b65166584f468425047`.

Current release and acceptance evidence:

- PR #9 merged the partial Podcast/Expression publish recovery.
- PR #10 merged the protected Podcast Owner Acceptance Harness.
- PR #11 merged fail-closed Notion target-group binding.
- PR #14 implemented, independently reviewed, and merged the protected
  Vocabulary Acceptance Harness after all identified P0/P1 false-pass paths
  were closed.
- Vocabulary Harness targeted tests: 19 passed.
- Latest complete regression: 569 passed with 3 existing
  compatibility-provider deprecation warnings.
- `compileall`: PASS.
- `git diff --check`: PASS.
- The five local target settings now point to the intended database group.
- The Notion token did not change during the target switch.
- Read-only Target Binding Diagnosis: PASS.
- Automated Podcast Owner Acceptance: PASS.
- Vocabulary Acceptance: NOT RUN.
- Owner visual review: NOT COMPLETE.
- External-user sessions: 0.
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`.

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
Explicit Vocabulary Sync
↓
Codex Enrichment
↓
Python Validation and Dedupe
↓
Vocabulary Database Upsert
```

Podcast publishing and Vocabulary synchronization are separate workflows. An
empty Vocabulary Database after Podcast acceptance does not prove that the
Vocabulary sync script is broken.

Accurate current Vocabulary status:

- the protected Vocabulary Acceptance Harness is implemented, independently
  reviewed, and merged;
- Harness readiness does not mean the Vocabulary workflow has passed
  acceptance;
- the intended-group targeted dry-run has not run;
- the intended-group targeted publish has not run;
- the exact retry has not run;
- Vocabulary record data quality has not been inspected;
- Owner visual review has not completed;
- therefore Vocabulary Acceptance is `NOT RUN`;
- full-scan highlight checkpoints and processed-highlight state are currently
  global rather than scoped by target group.

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

## Current Visual Review Finding

The Expression Database Select Property options are gray for:

- Category
- Commonness
- Review Status

This is a semantic presentation defect for future database creation and a
manual live-database adjustment. It does not affect Podcast body formatting,
semantic text highlights, the Highlight Legend, or the Highlighted Transcript.

## Pending Requirements

In execution order:

1. targeted Vocabulary dry-run;
2. inspect highlights, candidate decisions, enrichment, and planned writes;
3. obtain exact human confirmation;
4. targeted Vocabulary publish;
5. inspect Vocabulary record data quality;
6. exact Vocabulary retry with zero new records;
7. make the Vocabulary acceptance decision;
8. target-group-scoped highlight state;
9. conversational `同步生词`;
10. semantic Select option colors for future database creation;
11. documented manual color adjustment for the live database;
12. Podcast page table of contents;
13. Weekly page table of contents;
14. parent-page usage guide after these workflows stabilize;
15. complete Owner visual review.

Podcast and Weekly TOCs are presentation enhancements. New pages should place
the TOC at the beginning, exact retry must not duplicate it, existing body
contracts remain intact, and historical automatic backfill is not approved.

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

Run the protected targeted Vocabulary dry-run against BE 598 from a clean
latest-main acceptance worktree. Continue through inspection, exact human
confirmation, publish, data-quality review, exact retry, and the acceptance
decision before classifying a core-script defect. External-user testing
remains paused.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md`,
`skill/SKILL.md`, and `DECISION_LOG.md` before changing runtime behavior.
