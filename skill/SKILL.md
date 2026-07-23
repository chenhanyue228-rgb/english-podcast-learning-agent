---
name: english-audio-learning-agent
description: Install and set up English Audio Learning Agent; configure and validate its Notion workspace; analyze Apple Podcasts episodes, podcast RSS feeds, and local English audio; generate learning artifacts; sync highlighted vocabulary; and publish learning notes and weekly reflections.
---

# English Audio Learning Agent Skill

## 1. Skill Identity

### Skill Name

English Audio Learning Agent

### Purpose

Turn English learning inputs such as Apple Podcasts episode URLs, podcast RSS feeds,
local audio files, and user-highlighted vocabulary into structured learning
assets stored in Notion.

### Target User

This Skill is for users who want to learn English from podcasts and save the
results into Notion with minimal manual work.

### Supported Inputs

- Apple Podcasts episode URL
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

- install the English Audio Learning Agent
- complete first-time setup
- configure or validate the Notion workspace
- "Analyze this podcast"
- "Create English learning notes"
- "Extract useful expressions"
- "Sync vocabulary"
- "Generate weekly reflection"
- publish a learning page

Use this Skill when the user provides:

- an Apple Podcasts episode URL
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

## 3. Guided Onboarding Contract

### Installation Request

The supported Chinese installation request is:

```text
请从下面的项目安装英语音频学习助手：

https://github.com/chenhanyue228-rgb/english-podcast-learning-agent

安装成功后，请直接在当前对话中带我继续第一次设置。
```

The repository URL is used only during installation. First-time setup and
daily podcast processing must not require the user to provide it again.

### Installation Handoff

After installation, continue in the current conversation first. Codex must
display:

```text
英语音频学习助手已经安装完成。

现在可以在当前对话中继续第一次设置。

是否现在继续？
```

When the user replies `继续`, begin first-time setup immediately.

Do not require a new conversation. If the current conversation has not
discovered the newly installed Skill, a new conversation is the first
fallback. If the new conversation still cannot discover it, restarting Codex
is the second fallback.

The optional setup trigger is:

```text
请使用英语音频学习助手，带我完成第一次设置。
```

The user does not need to memorize this instruction.

### Locate or Acquire the Complete Project

Before first-time setup, Codex must check whether the active workspace contains
all of:

- `README.md`
- `skill/`
- `scripts/`
- `src/`
- `requirements.txt`
- `.env.example`

If present, continue with that project. If absent, Codex should acquire:

```text
https://github.com/chenhanyue228-rgb/english-podcast-learning-agent
```

The suggested destination is `~/EnglishAudioLearningAgent`.

- Clone only when the destination does not exist.
- If it exists, verify it is the correct repository before using it.
- Never overwrite an unrelated directory or delete user files.
- Never write a Notion token into the repository or a command.
- Request user approval for necessary downloads, local execution, or network
  access.
- Do not require the user to find the project folder or type `cd`.

### First-Time Setup Responsibilities

For the setup trigger, Codex must:

1. Locate or safely acquire the complete project.
2. Prepare or reuse the project-local `.venv`.
3. Direct the user to the official Notion resources:
   - https://www.notion.so/developers
   - https://developers.notion.com/guides/get-started/internal-connections
   - https://www.notion.com/help/create-your-first-page
   - https://www.notion.com/help/share-your-work
4. Guide the user to create an internal connection and an empty parent page.
5. Guide the user to add the connection to the parent page.
6. Remind the user that the access token must not be sent to the Codex chat.
7. Automatically launch `scripts/first_time_setup.py` with safe interactive
   input.
8. Ask the user to enter only the hidden token and the complete parent-page
   URL in the local interface.
9. Never require manual page-ID extraction.
10. Let Python create or validate all four databases.
11. Report the four database results.

If safe interactive input is unavailable, try to open `start_setup.command`.
If that also fails, open the project directory in Finder and ask the user only
to double-click `start_setup.command`. Terminal instructions are the final
fallback.

After success, actively prompt the user for an Apple Podcasts episode URL,
podcast RSS feed, or local audio file.

### Daily Podcast Trigger

```text
请使用英语音频学习助手处理这个播客：

<播客链接>
```

Codex must check the input, run the local transcript/request flow, generate the
analysis artifact, rerun Python validation and publishing, and return the final
Notion page URL. Do not ask the user to copy the internal command sequence.

## 4. Runtime Architecture

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
- storing Weekly Reflection pages

### Runtime Rule

The Skill runtime path does not require direct OpenAI API calls.

Python should be used for orchestration, validation, and publishing.
Codex should be used for reasoning and content generation.

## 5. User Quick Start

### Step 1: Install the Skill

Use the installation request above. After installation, the current
conversation is the primary continuation path. A new conversation and restart
are fallbacks only when Skill discovery has not refreshed.

### Step 2: Configure the Environment

Codex locates the complete project, prepares the local environment, guides the
Notion authorization, and starts the safe setup tool. The user enters the
token and complete parent-page URL only in the local interface.

Python creates or validates Podcast Library, Expression Database, Weekly
Review, and Vocabulary Database. Weekly Review stores the Weekly Reflection
learning note.

### Step 3: Provide Podcast Input

Give Codex an Apple Podcasts episode URL, podcast RSS feed, local audio file,
or a Notion highlight source.

### Step 4: Run the Analysis Workflow

Codex runs the source pipeline to create the intermediate analysis request
artifact.

### Step 5: Generate Artifacts

Codex reads the request artifact, produces structured JSON, and saves it to the
appropriate output directory.

### Step 6: Publish to Notion

Codex runs the publish step so Python validates the generated artifact and
writes the final page to Notion.

## 6. Command Catalog

These commands are an execution contract for Codex and a Developer/recovery
reference. Normal users are not expected to run them manually.

| Command | Purpose | Required Input | Generated Artifacts | Expected Output | Next Action |
|---|---|---|---|---|---|
| `./.venv/bin/python src/main.py "<source>"` | Extract audio, transcribe, and create a Codex analysis request | Apple Podcasts episode URL, podcast RSS feed, or local audio path | `data/transcripts/<file>.json`, `data/analysis_requests/<file>.json` | A Codex analysis request file path | Codex generates analysis JSON |
| `./.venv/bin/python src/main.py "<source>" --analysis-json data/analysis/<file>.json` | Publish a complete Podcast Library page | Source plus Codex-generated analysis JSON | Podcast page in Notion | Created Notion Podcast Library page | Move to vocabulary or weekly workflows if needed |
| `./.venv/bin/python src/main.py --weekly-reflection` | Run the Weekly Reflection pipeline | Weekly learning context from the current period | `output/weekly_learning_context.json`, `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Weekly Reflection page, or dry-run output if configured | Review result in Notion or rerun with dry-run |
| `./.venv/bin/python src/main.py --weekly-reflection --dry-run` | Run the Weekly Reflection pipeline without Notion publish | Weekly learning context | `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Validation and quality output only | Inspect artifacts, then publish if ready |
| `./.venv/bin/python src/main.py --weekly-review` | Build a Weekly Review request from Notion learning data | Current Notion learning data | `data/weekly_review_requests/<week>.json` | Weekly Review request file path | Codex generates Weekly Review JSON |
| `./.venv/bin/python src/main.py --publish-highlight-vocab PAGE_ID` | Publish exact user-selected pink-highlight vocabulary from a Notion page | Notion page ID | Vocabulary preview / publish artifacts | Updated Vocabulary Database entries | Verify vocabulary entries in Notion |
| `./.venv/bin/python src/main.py --sync-vocab-comments` | Legacy compatibility: sync comment-triggered vocabulary captures | Podcast Library pages with historical comment triggers | Sync state + vocabulary records | Vocabulary sync summary | Prefer the pink-highlight workflow for v1 use |
| `./.venv/bin/python -m pytest` | Run the full test suite | None | Test reports | Pass/fail summary | Fix issues before publishing |

## 7. Workflow Contracts

### 7.1 Podcast Analysis

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

- Apple Podcasts episode URL
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

### 7.2 Vocabulary Capture

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

### 7.3 Weekly Reflection

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

## 8. Artifact Contract

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

## 9. Error Handling

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

## 10. Quality Rules

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

## 11. Architecture Freeze Notes

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

## 12. Operating Principle

Codex reasons. Python orchestrates and validates. Notion stores the knowledge
assets.

That separation is the current production contract for this Skill.
