# English Audio Learning Agent Architecture

This document records the current production architecture. It describes what
is implemented after the v1.1 runtime migration, not a future target design.

## 1. Architecture Status

- Product phase: Phase 3 — Product Stabilization / Post v1.1
- Production AI runtime: Codex Artifact Runtime
- Python role: deterministic orchestration and validation
- Persistence layer: Notion
- Supported v1 inputs: Podcast episode URL, Podcast RSS feed, local audio file
- Out of scope for v1: YouTube

Direct OpenAI providers may remain importable as deprecated compatibility
paths. They are not the default production reasoning runtime and
`OPENAI_API_KEY` is not required for the Codex Skill workflow.

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

## 10. Current Development Direction

The current priority is creating a safe local v1.1 release baseline.
Appropriate work includes:

- excluding generated and local-only artifacts without deleting user data
- classifying experimental and legacy paths without changing behavior
- keeping documentation and runtime contracts aligned
- organizing completed v1.1 work into reviewable local commits

New learning features, schema expansion, or Weekly Reflection redesign are not
part of the stabilization phase. After the release baseline is reviewed, the
next product phase is Phase 4 — Product Validation.

## 11. References

- `README.md`: user-facing setup and workflows
- `skill/SKILL.md`: Codex runtime contract
- `docs/codex_skill_contract.md`: detailed artifact responsibility contract
- `docs/current_architecture.md`: extended developer architecture reference
- `PROJECT_CONTEXT.md`: handoff context
- `CURRENT_TASK.md`: current execution priority
- `DECISION_LOG.md`: durable product and architecture decisions
