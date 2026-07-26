# Project Context

## Product

**Name:** English Audio Learning Agent

English Audio Learning Agent transforms Apple Podcasts episodes, podcast RSS
feeds, and local audio files into reusable English learning assets:

- Podcast learning notes
- professional expressions
- user-selected vocabulary
- compounding Weekly Reflections

## Current Phase

**Phase:** Phase 4.2 - External User Validation

**Execution stage:** Automatic Vocabulary engineering complete

**Engineering status:**
`ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING`

**Release:** v1.2.0

The Phase 3 runtime baseline is production `main`
`156b37f08290aa9b985112269d2a373de51c48d2`.

Current release and acceptance evidence:

- Setup / Notion workspace recovery: PASS.
- Target Binding: PASS.
- Automated Podcast Owner Acceptance: PASS.
- Podcast first publish and exact retry: PASS.
- Targeted Vocabulary Acceptance: PASS.
- Weekly Reflection Acceptance: PASS.
- Automatic Vocabulary Phase 0 feasibility: PASS.
- Phase 1 read-only detection foundation: PASS.
- Phase 2 isolated Codex enrichment and protected publishing: PASS.
- Phase 3A bounded runtime and LaunchAgent: PASS.
- Phase 3B protected real Notion Owner Acceptance: PASS.
- Automatic Vocabulary first publish: Podcast created 1, controlled pink
  highlight added 1, Vocabulary created 1.
- Automatic Vocabulary exact retry: Vocabulary created 0, updated 0.
- Exact word, exact context, full body, full properties, source relation, and
  occurrence fingerprint: PASS.
- Expression, Weekly, schema, delete/archive, and historical-group writes: 0.
- Automatic scheduler: installed and loaded at a 60-second interval.
- Scheduler activation: first cycle BASELINED; next cycle NO_WORK; Vocabulary
  publisher calls 0.
- Notion AI dependency: none.
- External-user sessions: 0.
- External-user validation: NOT RUN.
- External-user readiness:
  `ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING`.

This readiness token means the engineering journey is ready to be tested by
external users. It does not mean `EXTERNAL_USER_VALIDATION_PASS`.

## Runtime Model

### Codex: Reasoning and Generation

Codex performs language understanding and creates schema-conformant artifacts
for Podcast Analysis, Vocabulary enrichment, Reflection Analysis, and Weekly
Review generation.

### Python: Orchestration and Validation

Python performs source processing, transcription, artifact validation,
deterministic workflow execution, exact occurrence state management, bounded
scheduling, and Notion synchronization.

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

New Podcast pages begin with exactly one Notion table of contents and preserve
the accepted Summary, Expressions, Highlight Legend, and Highlighted
Transcript order.

### Vocabulary Memory

```text
User Pink Highlight
↓
Bounded 60-Second Scheduled Detection
↓
90-Second Quiet Period
↓
Target-Scoped Exact Occurrence State
↓
Isolated Codex Enrichment
↓
Strict Python Validation and Target Binding
↓
Fingerprint-Idempotent Vocabulary Upsert
```

The exact pink-highlighted rich-text item is the vocabulary target. Context is
used only for enrichment. The runtime does not infer, expand, normalize, or
merge the user's target.

The first enablement cycle baselines existing highlights and does not publish
them. Each later invocation is finite, overlap-safe, restart-safe, and
retry-safe. The older explicit targeted command remains a Developer/recovery
path. Comment-trigger synchronization remains legacy compatibility code.

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

## Production Scheduler

The macOS LaunchAgent runs one bounded worker about every 60 seconds. It is not
an infinite Python daemon.

The production project must live outside macOS protected user folders such as
`Documents`, `Desktop`, and `Downloads`. The supported default location is:

```text
~/EnglishAudioLearningAgent
```

This avoids `launchd` file-access denial while keeping the runtime local. The
LaunchAgent stores no Notion credential in its plist. Runtime logs are
structured and redacted.

## Notion Target Binding

All production writers are bound to one configured parent and one internally
consistent four-Data-Source group. Target validation checks role, schema,
common parent, single-property relations, and cross-group isolation before
writes.

Historical database groups are never scanned or written by Automatic
Vocabulary Sync.

## Expression Select Colors

Future Expression Database creation assigns semantic Select colors to
Category, Commonness, and Review Status while preserving option names.
Existing databases are not automatically rewritten. Existing option colors
may be changed manually in the Notion UI only; options must not be deleted,
recreated, or renamed.

## Phase 4.2 Validation Goals

The next evidence-gathering stage will:

- complete 3 real external-user sessions;
- have at least 2 users complete the core flow without developer intervention;
- record time-to-first-value;
- record confusion, failed steps, and recovery outcomes;
- avoid speculative large-scale refactoring before evidence is collected.

External-user sessions remain 0 until a real participant starts the merged
journey.

## Deferred Non-Blocking Backlog

- manual color adjustment for the existing Expression Database

Podcast and Weekly tables of contents are accepted output contracts, not
deferred polish. The Parent Page Guide is accepted.

## Cancelled Proposal

The following remain cancelled and outside the roadmap:

- Notion AI-assisted page workflow
- synchronization of Podcast-page Expressions into Expression Database

## Frozen Boundaries

- Codex Artifact -> Python Validation -> Notion architecture
- four-database product model
- Podcast and Weekly page body contracts
- artifact JSON contracts
- Vocabulary/Expression ownership separation
- exact pink-highlight vocabulary intent
- Weekly Reflection product structure
- Notion idempotent publishing and target binding
- bounded local scheduling and target-scoped occurrence state

## Immediate Milestone

Run External User Session #1 with the merged Session Kit. Collect evidence
before changing product behavior.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md`,
`skill/SKILL.md`, `docs/architecture/automatic_vocabulary_sync_architecture_review.md`,
and `DECISION_LOG.md`.
