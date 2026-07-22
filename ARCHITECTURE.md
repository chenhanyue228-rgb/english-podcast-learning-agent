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

### Codex

Codex is the reasoning layer. It is responsible for:

- language understanding
- podcast learning analysis
- expression extraction
- vocabulary enrichment
- reflection analysis
- Weekly Review generation
- generating schema-conformant JSON artifacts

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

### Notion

Notion is the knowledge storage layer. It stores:

- Podcast Library learning pages
- Expression Database records
- Vocabulary Database records
- Weekly Review / Weekly Reflection records

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

- Codex: reasoning, analysis, and content generation
- Python: orchestration, validation, and deterministic processing
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
Pink Highlight Reader
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

## 9. Experimental and Legacy Paths

- Direct OpenAI providers are deprecated compatibility paths.
- YouTube extraction code is experimental and outside v1 product scope.
- Comment-trigger vocabulary sync is legacy compatibility code.
- Debug commands must remain read-only unless their command explicitly states a
  write operation.

Experimental code must not be presented as the default production workflow.

## 10. Product Validation Boundary

The current priority is Phase 4 clean-clone onboarding and first-user journey
validation. The architecture remains unchanged.

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
