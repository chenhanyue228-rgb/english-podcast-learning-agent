# English Audio Learning Agent Skill

## 1. Skill Identity

### Skill Name

English Audio Learning Agent

### Purpose

Turn English learning inputs such as podcast episode URLs, podcast RSS feeds,
local audio files, and user-highlighted vocabulary into structured learning
assets stored in Notion.

### Target User

This Skill is for users who want to learn English from podcasts and save the
results into Notion with minimal manual work.

### Supported Inputs

- Podcast URL
- Podcast RSS feed
- Local audio file
- Highlight vocabulary input

### Out of Scope for v1

YouTube is intentionally excluded from the v1 product. The Skill focuses on
stable audio sources and does not promise platform-specific video downloading,
authentication, or anti-bot compatibility. Experimental implementation may
remain in the repository for future evaluation, but Codex must not present it
as a supported v1 input.

## 2. Skill Activation Rules

### When to Use This Skill

Use this Skill when the user asks to:

- "Analyze this podcast"
- "Create English learning notes"
- "Extract useful expressions"
- "Sync vocabulary"
- "Generate weekly reflection"

Use this Skill when the user provides:

- a podcast URL
- a podcast RSS feed
- a local audio file
- a Notion page containing vocabulary highlights

### When Not to Use This Skill

Do not use this Skill when the user asks for:

- general web browsing without learning extraction
- unrelated code generation
- generic Notion admin work not tied to learning content
- direct OpenAI API integration work

If the request is unclear, ask one concise clarifying question before running
the workflow.

## 3. Runtime Architecture

This project is a Codex Skill, not a standalone Python AI application.

### Codex

Codex is responsible for:

- analyzing language
- generating reasoning artifacts
- creating structured JSON outputs
- turning learning signals into reflection and vocabulary artifacts

### Python

Python is responsible for:

- downloading and processing source data
- extracting transcripts
- validating artifacts
- executing workflows
- publishing content to Notion

### Notion

Notion is responsible for:

- storing knowledge assets
- presenting Podcast Library pages
- storing Vocabulary Database records
- storing Weekly Reflection / Weekly Review pages

### Runtime Rule

The Skill runtime path does not require direct OpenAI API calls.

Python should be used for orchestration, validation, and publishing.
Codex should be used for reasoning and content generation.

## 4. User Quick Start

### Step 1: Install the Skill

Install the Skill in the Codex environment so Codex can read `skill/SKILL.md`,
`skill/prompts/`, and `skill/schemas/`.

### Step 2: Configure the Environment

Prepare the local Python environment and add the required Notion values in
`.env`.

FFmpeg is supplied by the project dependency set when no system installation
is present.

### Step 3: Provide Podcast Input

Give Codex a podcast URL, podcast RSS feed, local audio file, or a Notion
highlight source.

### Step 4: Run the Analysis Workflow

Run the source pipeline to create the intermediate analysis request artifact.

### Step 5: Generate Artifacts

Codex reads the request artifact, produces structured JSON, and saves it to the
appropriate output directory.

### Step 6: Publish to Notion

Run the publish command so Python validates the generated artifact and writes
the final page to Notion.

## 5. Command Catalog

| Command | Purpose | Required Input | Generated Artifacts | Expected Output | Next Action |
|---|---|---|---|---|---|
| `python3 src/main.py "<source>"` | Extract audio, transcribe, and create a Codex analysis request | Podcast URL, podcast RSS feed, or local audio path | `data/transcripts/<file>.json`, `data/analysis_requests/<file>.json` | A Codex analysis request file path | Codex generates analysis JSON |
| `python3 src/main.py "<source>" --analysis-json data/analysis/<file>.json` | Publish a complete Podcast Library page | Source plus Codex-generated analysis JSON | Podcast page in Notion | Created Notion Podcast Library page | Move to vocabulary or weekly workflows if needed |
| `python3 src/main.py --weekly-reflection` | Run the Weekly Reflection pipeline | Weekly learning context from the current period | `output/weekly_learning_context.json`, `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Weekly Reflection page, or dry-run output if configured | Review result in Notion or rerun with dry-run |
| `python3 src/main.py --weekly-reflection --dry-run` | Run the Weekly Reflection pipeline without Notion publish | Weekly learning context | `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Validation and quality output only | Inspect artifacts, then publish if ready |
| `python3 src/main.py --weekly-review` | Build a Weekly Review request from Notion learning data | Current Notion learning data | `data/weekly_review_requests/<week>.json` | Weekly Review request file path | Codex generates Weekly Review JSON |
| `python3 src/main.py --publish-highlight-vocab PAGE_ID` | Publish exact user-selected pink-highlight vocabulary from a Notion page | Notion page ID | Vocabulary preview / publish artifacts | Updated Vocabulary Database entries | Verify vocabulary entries in Notion |
| `python3 src/main.py --sync-vocab-comments` | Legacy compatibility: sync comment-triggered vocabulary captures | Podcast Library pages with historical comment triggers | Sync state + vocabulary records | Vocabulary sync summary | Prefer the pink-highlight workflow for v1 use |
| `python3 -m pytest` | Run the full test suite | None | Test reports | Pass/fail summary | Fix issues before publishing |

## 6. Workflow Contracts

### 6.1 Podcast Analysis

#### Flow

```text
Input
↓
Transcript
↓
Codex analysis
↓
Validation
↓
Notion publish
```

#### Inputs

- podcast URL
- podcast RSS feed
- local audio file
- transcript JSON if available

#### Artifacts

Intermediate:

- `data/transcripts/`
- `data/analysis_requests/`

Final:

- `data/analysis/`
- Notion Podcast Library page

#### Responsibilities

Codex:

- analyze transcript content
- generate summary and learning items

Python:

- extract audio
- transcribe
- create analysis request artifact
- validate generated JSON
- publish to Notion

### 6.2 Vocabulary Capture

#### Flow

```text
Highlight
↓
Vocabulary artifact
↓
Validation
↓
Vocabulary Database
```

#### Inputs

- pink highlight input
- highlight vocabulary source page

#### Artifacts

Intermediate:

- vocabulary preview JSON
- enrichment JSON

Final:

- Vocabulary Database page

#### Responsibilities

Codex:

- interpret the highlighted vocabulary
- generate meaning and usage context

Artifact handoff:

- Python writes `data/vocabulary_enrichment_requests/<word>.json`
- Codex writes `data/vocabulary_enrichment/<word>.json`
- Codex reruns the same publish command

Python:

- collect the highlight
- validate the vocabulary payload
- upsert to Notion

### 6.3 Weekly Reflection

#### Flow

```text
WeeklyLearningContext.json
↓
ReflectionContext.json
↓
WeeklyReview.json
↓
Quality Gate
↓
Notion
```

#### Inputs

- `output/weekly_learning_context.json`

#### Artifacts

Intermediate:

- `output/reflection_context_request.json`
- `output/reflection_context.json`
- `output/weekly_review_request.json`
- `output/weekly_review.json`
- `output/pipeline_run.json`

Final:

- Weekly Reflection page in Notion

#### Responsibilities

Codex:

- derive weekly theme
- identify mindset shifts
- synthesize learning patterns
- create reflection output

Python:

- build the weekly learning context
- validate reflection and review artifacts
- run quality checks
- publish to Notion

## 7. Artifact Contract

### Input Artifacts

- `data/analysis_requests/`
- `output/weekly_learning_context.json`
- highlight-derived vocabulary previews

### Output Artifacts

- `data/analysis/`
- `output/reflection_context.json`
- `output/weekly_review.json`
- `output/pipeline_run.json`

### Naming Conventions

- podcast analysis request:
  - `data/analysis_requests/<slug>.json`
- podcast analysis output:
  - `data/analysis/<slug>.json`
- reflection context:
  - `output/reflection_context.json`
- weekly review:
  - `output/weekly_review.json`

### Artifact Types

Intermediate artifacts:

- analysis requests
- reflection context
- weekly review draft
- pipeline run metadata

Final knowledge outputs:

- Podcast Library page
- Vocabulary Database page
- Weekly Reflection page

## 8. Error Handling

### Invalid URL

Detect:

- source router cannot classify input

Report:

- clear error message with supported input types

Recovery:

- ask the user for a supported source

### Transcript Failure

Detect:

- audio download fails
- transcription fails

Report:

- the failing stage and input source

Recovery:

- retry with a valid source or inspect the audio file

### Missing Artifact

Detect:

- expected request or output JSON is absent

Report:

- the missing file path

Recovery:

- rerun the previous stage

### Invalid JSON

Detect:

- generated artifact is malformed or missing required fields

Report:

- schema validation error

Recovery:

- regenerate the artifact with Codex

### Notion Publishing Failure

Detect:

- Notion API request fails
- Notion runtime connectivity fails

Report:

- the exact publish step and error message

Recovery:

- verify runtime connectivity and Notion configuration

### Environment Configuration Error

Detect:

- missing Notion token
- missing database IDs
- missing required environment variables

Report:

- which variable is missing

Recovery:

- update `.env` and rerun the command

## 9. Quality Rules

### Analysis Quality

- focus on practical expressions
- prioritize business language
- include useful sentence patterns
- avoid weak or obvious items

### Vocabulary Quality

- preserve exact user intent
- use contextual meaning
- include realistic usage examples
- avoid generic dictionary output

### Reflection Quality

- identify learning patterns
- explain professional insights
- connect learning to work behavior
- avoid podcast recaps

## 10. Architecture Freeze Notes

### Frozen

- Notion schema
- workflow boundaries
- validation contracts

### Experimental

- deprecated direct OpenAI compatibility providers

### Provider Selection

Production defaults:

- `ENRICHMENT_PROVIDER=codex`
- `WEEKLY_REFLECTION_PROVIDER=codex`
- `WEEKLY_REVIEW_PROVIDER=codex`

`placeholder` is for deterministic tests. `openai` is deprecated compatibility
only. The production Skill does not require `OPENAI_API_KEY`.

### Reference Documents

- `docs/current_architecture.md`
- `docs/codex_skill_contract.md`

## 11. Operating Principle

Codex reasons. Python orchestrates and validates. Notion stores the knowledge
assets.

That separation is the current production contract for this Skill.
