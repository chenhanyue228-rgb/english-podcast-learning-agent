# Current Architecture

This document describes the current, real architecture of the project as a
Codex Skill system.

It is the developer reference for understanding the runtime boundary between
Codex, Python, and Notion, and it should stay aligned with:

- `skill/SKILL.md`
- `docs/codex_skill_contract.md`
- `README.md`

## System Overview

English Audio Learning Agent is an AI English Learning Knowledge Agent. Its
purpose is to transform stable podcast and local-audio learning input into
structured learning and reflection assets stored in Notion.

The system currently has three major layers:

- Podcast learning and vocabulary capture
- Weekly reflection intelligence
- Notion publishing and persistence

The architecture is Skill-first and artifact-driven. Legacy OpenAI-backed
providers remain importable for compatibility, but no production factory
selects them unless a user explicitly opts in.

Current state:

- Skill architecture foundation is complete
- Podcast, Weekly Reflection, and Automatic Vocabulary pipelines are accepted
- Codex artifact providers are the production default
- OpenAI providers are deprecated compatibility paths
- Notion runtime publishing and idempotent updates are verified
- the bounded 60-second Automatic Vocabulary scheduler is active
- engineering is ready for external-user testing
- external-user sessions remain 0

Supported v1 inputs are Podcast episode URLs, podcast RSS feeds, and local
audio files. YouTube is intentionally out of scope; any remaining downloader
implementation is experimental and is not part of the production contract.

## Architecture Diagram

```text
Codex Skill
↓
Local Python scripts
↓
Generated artifacts
↓
Validation
↓
Notion
```

## Runtime Responsibilities

### Codex

Codex is the reasoning layer.

Codex is responsible for:

- language understanding
- content generation
- reflection synthesis
- structured JSON output generation

### Python

Python is the orchestration and validation layer.

Python is responsible for:

- source detection
- source download and transcription
- artifact creation and persistence
- schema validation
- workflow execution
- Notion synchronization

### Notion

Notion is the knowledge storage layer.

Notion is responsible for:

- storing Podcast Library records
- storing Vocabulary Database records
- storing Weekly Reflection records
- presenting the learning knowledge base

## Data Layers

### 1. Learning Fact Layer

Files:

- `data/analysis_requests/*`
- `output/weekly_learning_context.json`

Contains:

- podcasts
- expressions
- vocabulary
- highlights

This layer captures the factual learning input from Notion or source
transcription.

### 2. Reflection Intelligence Layer

Files:

- `output/reflection_context.json`

Contains:

- weekly_theme
- mindset_shifts
- cross_content_patterns
- professional_actions

This layer transforms learning facts into reflection signals.

### 3. Presentation Layer

Files:

- `output/weekly_review.json`

Contains:

- one core idea
- an optional evidence-supported mindset shift
- 2-4 ideas worth compounding
- 3-5 expressions worth reusing
- one language-thinking connection
- exactly one next-week application
- compact source references

This layer turns reflection signals into a curated compounding note. It does
not reproduce the weekly vocabulary collection, all extracted expressions,
counts, scores, or pipeline metadata. See
`docs/weekly_reflection_product_contract.md`.

## Current Notion Layer

### Databases

- `Podcast Library`
- `Expression Database`
- `Vocabulary Database`
- `Weekly Review`

### Current Purpose

The Notion workspace stores the final knowledge assets:

- podcast learning records
- expression learning records
- vocabulary memory
- weekly reflection records

### Important Database Notes

The current Weekly Review database is the final storage layer for Weekly
Reflection. The existing schema is treated as the stable storage contract for
the current phase.

The Vocabulary Database is the user-owned memory store for highlight-driven
vocabulary captures.

## Skill Boundary

The project is a Codex Skill, not a standalone Python AI application.

That means:

- Codex should reason about learning content
- Python should do deterministic processing and validation
- Notion should store the results

The production path does not call an LLM from Python. Provider factories default
to Codex request/output artifacts:

- Podcast: `data/analysis_requests/` -> `data/analysis/`
- Vocabulary: `data/vocabulary_enrichment_requests/` -> `data/vocabulary_enrichment/`
- Reflection: `output/reflection_context_request.json` -> `output/reflection_context.json`
- Weekly Review: `output/weekly_review_request.json` -> `output/weekly_review.json`

Placeholder providers are deterministic test support. OpenAI providers remain
deprecated compatibility paths selected only with an explicit `openai` value.

## Important Source Files

### Skill

- `skill/SKILL.md`
- `skill/prompts/`
- `skill/schemas/`

### Workflow

- `src/workflow/weekly_reflection_pipeline.py`
- `src/workflow/weekly_learning_context_pipeline.py`
- `src/workflow/vocabulary_learning_pipeline.py`
- `src/workflow/highlight_vocabulary_pipeline.py`
- `src/workflow/pipeline_run.py`

### Reflection

- `src/weekly_review/reflection_analyzer.py`
- `src/weekly_review/generator.py`
- `src/weekly_review/quality_checker.py`

### Notion

- `src/notion/weekly_reflection_writer.py`
- `src/notion/vocabulary_publisher.py`
- `src/notion/learning_publisher.py`
- `src/notion/config.py`
- `src/notion/schema.py`

### CLI

- `src/main.py`

## Commands

### Generate Weekly Reflection

```bash
python -m src.main weekly-reflection
```

### Dry Run

```bash
python -m src.main weekly-reflection --dry-run
```

### Podcast Analysis

```bash
python3 src/main.py "<source>"
```

### Publish Podcast Learning Page

```bash
python3 src/main.py "<source>" --analysis-json data/analysis/<file>.json
```

### Legacy Comment Vocabulary Sync

```bash
python3 src/main.py --sync-vocab-comments
```

This command is retained for compatibility. It is not the production
Vocabulary path.

### Automatic Vocabulary Runtime

```bash
./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py status
./.venv/bin/python scripts/run_automatic_vocabulary_once.py
```

Normal users only add an exact pink highlight. The bounded scheduler detects
the new occurrence, waits for the 90-second quiet period, runs isolated Codex
enrichment, validates the artifact, and upserts Vocabulary through the
target-bound publisher.

`--publish-highlight-vocab PAGE_ID` remains a Developer/recovery command.

The production project must live outside macOS protected `Documents`,
`Desktop`, and `Downloads` folders. The supported default is
`~/EnglishAudioLearningAgent`.

### Run Tests

```bash
python3 -m pytest
```

## Environment Variables

Required:

- `NOTION_TOKEN`
- `NOTION_PODCAST_LIBRARY_DATABASE_ID`
- `NOTION_EXPRESSION_DATABASE_ID`
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
- `NOTION_VOCABULARY_DATABASE_ID`

Compatibility:

- `NOTION_WEEKLY_REVIEW_DATABASE_ID`

Provider-related environment variables may still exist for compatibility.
The normal Skill path already defaults to Codex artifacts and does not require
direct OpenAI API access.

## Current Implementation vs Target Behavior

### Current Implementation

- Production AI factories default to artifact-driven Codex handoffs.
- Direct OpenAI-backed providers remain explicit, deprecated compatibility
  implementations.
- Notion publishing is isolated and stable.
- Automatic Vocabulary uses target-scoped SQLite state, exact occurrence
  fingerprints, a 90-second quiet period, strict Codex artifact validation,
  process locking, and a bounded macOS LaunchAgent.

### Target Behavior

- Keep Codex as the reasoning layer.
- Keep Python responsible for orchestration and validation.
- Keep generated artifacts as the production AI output contract.
- Keep Notion as the persistence and presentation layer.
- Validate the accepted automatic journey with real external users.

## Testing Status

Current test result:

- `344 passed`

## Remaining Work

The remaining work is not core pipeline logic.

Pending items:

- establish a clean repository release baseline
- validate the end-to-end Skill user experience
- refine product onboarding
- improve reuse of existing learning assets without changing frozen schemas
