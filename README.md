# English Audio Learning Agent

English Audio Learning Agent is a **Codex Skill** for turning podcast episodes,
podcast RSS feeds, local audio files, and user-highlighted vocabulary into
structured English learning knowledge in Notion.

This repository is designed for a Skill-first workflow:

- **Codex** provides reasoning, language analysis, and content generation
- **Python** handles orchestration, validation, file processing, and Notion
  synchronization
- **Notion** stores the learning assets

The production architecture is:

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

Current state:

- Pure Codex Skill artifact runtime is the production default
- the pipeline and Notion publishing are stable
- direct OpenAI providers are deprecated compatibility paths only
- `OPENAI_API_KEY` is not required for the production Skill workflow

For the production runtime contract, read:

- [skill/SKILL.md](skill/SKILL.md)
- [docs/current_architecture.md](docs/current_architecture.md)
- [docs/codex_skill_contract.md](docs/codex_skill_contract.md)

## What This Skill Does

The Skill helps a user:

1. analyze a podcast or audio source
2. extract learning-friendly expressions
3. capture vocabulary from user highlights
4. generate weekly reflection artifacts
5. publish the final knowledge assets into Notion

## Installation

Install dependencies:

```bash
python3 scripts/bootstrap_environment.py
```

Project dependencies include a local FFmpeg runtime through `imageio-ffmpeg`,
so Homebrew is optional for supported audio conversion.

If you only want dependencies:

```bash
python3 scripts/bootstrap_environment.py --skip-tests
```

Copy environment variables:

```bash
cp .env.example .env
```

Fill in the required Notion settings:

```bash
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
NOTION_PODCAST_LIBRARY_DATABASE_ID=
NOTION_EXPRESSION_DATABASE_ID=
NOTION_WEEKLY_REVIEW_DATABASE_ID=
NOTION_VOCABULARY_DATABASE_ID=
```

## First Use

For a podcast or audio source:

```bash
python3 src/main.py "<source>"
```

This creates the intermediate transcript and analysis-request artifacts.

Then Codex generates the AI JSON artifact, and Python publishes the final
Notion page:

```bash
python3 src/main.py "<source>" --analysis-json data/analysis/<file>.json
```

For weekly reflection:

```bash
python3 src/main.py --weekly-reflection
```

On the first pass Python may report a required Codex artifact. Codex reads the
generated request, writes the requested JSON output, and reruns the same
command. Reflection uses:

- `output/reflection_context_request.json` -> `output/reflection_context.json`
- `output/weekly_review_request.json` -> `output/weekly_review.json`

For a dry run:

```bash
python3 src/main.py --weekly-reflection --dry-run
```

## Supported Workflows

Supported v1 inputs are:

- Podcast episode URL
- Podcast RSS feed
- Local audio file

## Out of Scope for v1

YouTube support is intentionally excluded from the v1 product. The Skill
focuses on stable English audio sources and avoids platform authentication,
anti-bot behavior, and downloader maintenance. Experimental YouTube code may
remain in the repository for possible future evaluation, but it is not part of
the supported runtime contract.

### Podcast Analysis

```text
Source
↓
Transcript
↓
Codex analysis
↓
Validation
↓
Notion publish
```

### Vocabulary Capture

```text
Highlight
↓
Vocabulary artifact
↓
Validation
↓
Vocabulary Database
```

Vocabulary enrichment requests are stored under
`data/vocabulary_enrichment_requests/`; Codex writes matching outputs under
`data/vocabulary_enrichment/` before Python validates and publishes them.

### Weekly Reflection

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

## Basic Troubleshooting

- If a command fails, check the error message first. The pipeline stages are
  intentionally separated, so failures are usually localizable.
- If Notion publishing fails, verify the environment variables and runtime
  connectivity.
- If an artifact is missing, rerun the previous stage rather than manually
  editing generated files.
- If you are unsure which command to use, start with the Skill manifest:
  [skill/SKILL.md](skill/SKILL.md)

## Core Commands

- `python3 src/main.py "<source>"`
- `python3 src/main.py "<source>" --analysis-json data/analysis/<file>.json`
- `python3 src/main.py --weekly-reflection`
- `python3 src/main.py --weekly-reflection --dry-run`
- `python3 src/main.py --publish-highlight-vocab PAGE_ID`
- `python3 -m pytest`

Legacy compatibility commands such as `--weekly-review` and
`--sync-vocab-comments` remain available for existing local workflows, but
they are not part of the primary v1 user journey. Pink highlight capture is
the production Vocabulary workflow.

## Documentation

- [Skill manifest](skill/SKILL.md)
- [Current architecture](docs/current_architecture.md)
- [Codex Skill contract](docs/codex_skill_contract.md)
- [Next steps](docs/next_steps.md)
