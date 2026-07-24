# English Audio Learning Agent Architecture

This document records the current production architecture. It describes what
is implemented after the v1.1 runtime migration, not a future target design.

## 1. Architecture Status

- Stable baseline: v1.1.0
- Stable baseline commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Product phase: Phase 4 — Product Validation
- Production AI runtime: Codex Artifact Runtime
- Python role: deterministic orchestration and validation
- Persistence layer: Notion
- Supported v1 inputs: Podcast episode URL, Podcast RSS feed, local audio file
- Out of scope for v1: YouTube

Direct OpenAI providers may remain importable as deprecated compatibility
paths. They are not the default production reasoning runtime and
`OPENAI_API_KEY` is not required for the Codex Skill workflow.

Phase 4 does not introduce an architecture change. The v1.1.0 architecture is
frozen during initial Product Validation. User feedback may produce future
proposals, but a proposal is not accepted until it passes Product and
Architecture review.

## 2. System Purpose

English Audio Learning Agent is an AI-powered English audio learning system
that transforms podcasts, RSS feeds, and audio files into reusable ideas,
expressions, vocabulary memory, and personal learning reflections.

## 3. Runtime Responsibilities

### User

The user owns only non-delegable actions:

- Notion account and workspace authorization
- entering the Notion token in the local hidden-input interface
- providing the complete Notion parent-page URL
- selecting audio sources and vocabulary highlights
- approving necessary local execution and network access

### Codex

Codex is the reasoning layer. It is responsible for:

- installation handoff and user guidance
- locating or safely acquiring the complete local project
- preparing and operating the project-local runtime
- language understanding
- podcast learning analysis
- expression extraction
- vocabulary enrichment
- reflection analysis
- Weekly Review generation
- generating schema-conformant JSON artifacts
- advancing workflows and reporting results

### Python

Python is the orchestration and validation layer. It is responsible for:

- source detection and audio resolution
- download, normalization, and transcription
- request artifact creation
- schema validation
- deterministic workflow execution
- state and artifact persistence
- Notion synchronization and idempotent updates

Python does not perform production AI reasoning.

Local Python execution is required, but manual terminal operation by the user
is not. Codex starts the deterministic tools; Python validates formats and
writes to Notion.

### Notion

Notion is the knowledge storage layer. It stores:

- Podcast Library learning pages
- Expression Database records
- Vocabulary Database records
- Weekly Review / Weekly Reflection records

Notion's current API model separates the storage container from its schema:

- a **Database** is the page-level container created under the user's learning
  page
- a **Data Source** owns properties and records inside that container
- database creation supplies initial fields through
  `initial_data_source.properties`
- later property retrieval and updates use the data source API
- relations target a `data_source_id`, not a database container ID
- the production workspace uses one-way `single_property` relations

First-time setup persists each returned data source ID immediately. Recovery
reuses those IDs, adds only missing known properties, preserves unknown user
properties and records, and stops safely on a property type conflict. This is
an API compatibility correction; the four-database product model is unchanged.

Relation recovery is intentionally conservative. A missing relation, missing
target, or missing mode may be repaired to the approved one-way relation. A
relation that points to another Data Source or contains `dual_property` stops
before any relation update. Converting an existing two-way relation requires a
separate migration decision because it can affect the reverse property.

Final workspace validation checks both the relation target and relation mode
for Expression Database, Vocabulary Database, and Weekly Review. A field is not
accepted merely because its Notion type is `relation`.

## 4. Codex Artifact Runtime

The production runtime can be summarized as:

```text
Codex Skill
↓
Artifact Generation
↓
Python Validation
↓
Workflow Execution
↓
Notion Publishing
```

The detailed request/output handoff is:

```text
Codex Skill
↓
Request Artifact
↓
Codex-generated JSON
↓
Python Validation
↓
Python Workflow
↓
Notion
```

The artifact boundary keeps reasoning separate from persistence. Codex writes
only the requested structured output. Python validates that output before any
Notion write occurs.

Responsibility boundary:

- User: account authorization, safe secret entry, content selection, and
  permission approval
- Codex: reasoning, analysis, and content generation
- Codex also handles installation handoff, local workflow operation, recovery,
  and result reporting
- Python: orchestration, validation, deterministic processing, and Notion
  writing
- Notion: storage, memory, and knowledge management

## 5. Core Workflows

### 5.1 Podcast Learning

```text
Podcast URL / RSS Feed / Local Audio
↓
Audio Extraction and Validation
↓
Whisper Transcript
↓
Podcast Analysis Request Artifact
↓
Codex Analysis JSON
↓
Python Schema Validation
↓
Podcast Library + Expression Database
```

Podcast Library remains the primary learning record. A complete page is
published only after transcript and analysis artifacts pass validation.

### 5.2 Vocabulary Memory

```text
User Pink Highlight
↓
Explicit Vocabulary Sync Trigger
↓
Vocabulary Enrichment Request Artifact
↓
Codex Enrichment JSON
↓
Python Validation and Dedupe
↓
Vocabulary Database Upsert
```

The exact pink-highlighted rich-text item is the vocabulary target. Context is
used only for enrichment; Python must not infer, expand, or merge the target.

Podcast publishing and Vocabulary synchronization are separate workflows.
Podcast publishing does not implicitly scan or populate Vocabulary Database.
An empty Vocabulary Database after a Podcast publish is not evidence of a
Vocabulary defect.

The immediate Vocabulary acceptance path is:

```text
Targeted dry-run
↓
Targeted publish
↓
Exact retry with zero new records
```

The current full-scan checkpoint and processed-highlight state are global.
They must be namespaced by target group before full-scan synchronization is
trusted across historical and current database groups.

The older block-comment trigger implementation remains as legacy compatibility
code. It is not the primary v1.1 Vocabulary capture path and must not be invoked
by default.

### 5.3 Weekly Reflection

```text
Podcast Library Learning Records
↓
WeeklyLearningContext.json
↓
Reflection Analysis Request
↓
ReflectionContext.json
↓
Weekly Review Request
↓
WeeklyReview.json
↓
Quality Gate
↓
Idempotent Notion Publish
```

Weekly Reflection is a compounding learning note. It turns weekly learning into
mindset shifts, cross-content patterns, language growth, and professional
actions. It is not a podcast recap or a raw data aggregation page.

## 6. Artifact Contracts

Important artifact locations include:

- `data/transcripts/`: deterministic transcript artifacts
- `data/analysis_requests/`: Podcast Analysis requests for Codex
- `data/analysis/`: validated Podcast Analysis outputs
- `data/vocabulary_enrichment_requests/`: vocabulary requests for Codex
- `data/vocabulary_enrichment/`: vocabulary enrichment outputs
- `output/weekly_learning_context.json`: weekly learning facts
- `output/reflection_context_request.json`: reflection request
- `output/reflection_context.json`: validated reflection intelligence
- `output/weekly_review_request.json`: Weekly Review request
- `output/weekly_review.json`: final presentation artifact
- `output/pipeline_run.json`: deterministic run metadata

Schemas under `skill/schemas/` define the handoff contracts. Python must reject
missing or invalid artifacts before publishing.

## 7. Data Ownership

### Podcast Library

- Owns the complete source learning page.
- Stores metadata, summary, insights, expressions, highlight legend, and
  highlighted transcript.

### Expression Database

- Receives only Codex-analyzed learning expressions.
- Preserves meaning, context, examples, category, and source relation.
- Must not receive user vocabulary items.

### Vocabulary Database

- Receives only vocabulary explicitly selected by the user through pink
  highlights.
- Must not receive expressions, automatic transcript extraction, or Weekly
  Review output.

### Weekly Review Database

- Stores the final Weekly Reflection.
- Consumes existing learning assets without rewriting source records.
- Uses deterministic identity and updates an existing period with PATCH.

## 8. Reliability Boundaries

The following behavior is stable and should remain protected:

- strict Apple Podcast episode resolution
- streaming audio download and validation
- transcript persistence
- Codex/Python artifact contracts
- Podcast Library page structure
- exact pink-highlight vocabulary intent
- Vocabulary and Expression ownership separation
- Weekly Reflection output contract and quality gate
- Notion schema and idempotent publishing

### Presentation Enhancements

Podcast and Weekly page tables of contents are approved as low-risk
presentation enhancements:

- place the TOC at the beginning of each newly created page;
- exact retry must not duplicate the TOC;
- existing page body contracts remain intact;
- historical automatic backfill is not approved.

The complete parent-page usage guide is deferred until Vocabulary acceptance,
TOC behavior, and related user instructions are stable.

## 9. Experimental and Legacy Paths

- Direct OpenAI providers are deprecated compatibility paths.
- YouTube extraction code is experimental and outside v1 product scope.
- Comment-trigger vocabulary sync is legacy compatibility code.
- Debug commands must remain read-only unless their command explicitly states a
  write operation.

Experimental code must not be presented as the default production workflow.

## 10. Product Validation Boundary

The current priority is Phase 4.1C targeted Vocabulary Acceptance and closure
of the remaining Owner visual-review findings. The architecture remains
unchanged.

Allowed during Phase 4:

- onboarding documentation improvement
- usability fixes supported by observed user evidence
- localized error-message improvement
- diagnostic visibility
- low-risk bug fixes supported by user evidence

Not allowed without an explicit Architecture Decision:

- new runtime providers
- a new storage layer
- automatic Vocabulary discovery as the primary workflow
- returning YouTube to the v1 core scope
- schema redesign
- major workflow rewrites
- Web application or cloud backend development

The following proposal was cancelled before implementation and is not part of
the active roadmap:

- Notion AI-assisted page workflow;
- Podcast-page Expression synchronization into Expression Database.

No pending Architecture Review remains for this cancelled proposal.

Phase 3 stabilization remains a completed historical milestone. Product
Validation findings may inform later proposals, but new feature development is
not the default Phase 4 action.

## 11. References

- `README.md`: user-facing setup and workflows
- `skill/SKILL.md`: Codex runtime contract
- `docs/codex_skill_contract.md`: detailed artifact responsibility contract
- `docs/current_architecture.md`: extended developer architecture reference
- `PROJECT_CONTEXT.md`: handoff context
- `CURRENT_TASK.md`: current execution priority
- `DECISION_LOG.md`: durable product and architecture decisions
