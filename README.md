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

### 1. Create the Python environment

From the repository root, create the project virtual environment and install
dependencies:

```bash
python3 -m venv .venv
./.venv/bin/python scripts/bootstrap_environment.py
```

Project dependencies include a local FFmpeg runtime through `imageio-ffmpeg`,
so Homebrew is optional for supported audio conversion.

If you only want dependencies:

```bash
./.venv/bin/python scripts/bootstrap_environment.py --skip-tests
```

### 2. Install the Codex Skill

In Codex, use the supported Skill installer with this exact request:

```text
Use $skill-installer to install english-audio-learning-agent from https://github.com/chenhanyue228-rgb/english-podcast-learning-agent/tree/main/skill
```

The installer copies the repository's `skill/` directory into the Codex user
Skill directory. The Skill becomes available on the next Codex turn. If it is
not discovered, fully quit and reopen Codex, then start a new task.

Verify discovery with:

```text
Use $english-audio-learning-agent to list supported inputs
```

Codex should list Apple Podcasts episode URLs, podcast RSS feeds, and local
audio files.

#### Developer-only local fallback

Repository contributors who need local edits to appear immediately may expose
the working tree with a symbolic link:

```bash
mkdir -p "$HOME/.codex/skills"
ln -s "$(pwd)/skill" "$HOME/.codex/skills/english-audio-learning-agent"
```

This symlink is not the primary end-user installation path. Inspect an existing
destination before replacing it.

### 3. Configure Notion

Copy environment variables:

```bash
cp .env.example .env
```

Create a Notion internal integration and copy its token. Then create a parent
page, share that page with the integration, and set the token in `.env`:

```bash
NOTION_TOKEN=
```

Initialize the workspace with the copied parent page URL or ID:

```bash
./.venv/bin/python -m src.notion.setup_workspace \
  --parent-page-id "<notion-parent-page-url-or-id>"
```

The command creates and connects four databases:

- Podcast Library
- Expression Database
- Weekly Review (stores the Weekly Reflection learning note)
- Vocabulary Database

It writes the parent page ID and all four database IDs into `.env`. Validate
the completed workspace with:

```bash
./.venv/bin/python -m src.notion.check_workspace
```

See [docs/Notion_Onboarding.md](docs/Notion_Onboarding.md) for the complete
Notion setup checklist. `NOTION_WEEKLY_REVIEW_DATABASE_ID` remains accepted
only as a legacy compatibility alias.

## First Use

For a podcast or audio source:

```bash
./.venv/bin/python src/main.py "<source>"
```

This creates the intermediate transcript and analysis-request artifacts.

Then use `$english-audio-learning-agent` to generate the AI JSON artifact.
Python validates it and publishes the final Notion page:

```bash
./.venv/bin/python src/main.py "<source>" \
  --transcript-json data/transcripts/<file>.json \
  --analysis-json data/analysis/<file>.json
```

Reusing the transcript JSON avoids running audio extraction and Whisper a
second time.

For weekly reflection:

```bash
./.venv/bin/python src/main.py --weekly-reflection
```

On the first pass Python may report a required Codex artifact. Codex reads the
generated request, writes the requested JSON output, and reruns the same
command. Reflection uses:

- `output/reflection_context_request.json` -> `output/reflection_context.json`
- `output/weekly_review_request.json` -> `output/weekly_review.json`

For a dry run:

```bash
./.venv/bin/python src/main.py --weekly-reflection --dry-run
```

## Supported Workflows

Supported v1 inputs are:

- Apple Podcasts episode URL
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

- `./.venv/bin/python src/main.py "<source>"`
- `./.venv/bin/python src/main.py "<source>" --transcript-json data/transcripts/<file>.json --analysis-json data/analysis/<file>.json`
- `./.venv/bin/python src/main.py --weekly-reflection`
- `./.venv/bin/python src/main.py --weekly-reflection --dry-run`
- `./.venv/bin/python src/main.py --publish-highlight-vocab PAGE_ID`
- `./.venv/bin/python -m pytest`

Legacy compatibility commands such as `--weekly-review` and
`--sync-vocab-comments` remain available for existing local workflows, but
they are not part of the primary v1 user journey. Pink highlight capture is
the production Vocabulary workflow.

## Documentation

- [Skill manifest](skill/SKILL.md)
- [Current architecture](docs/current_architecture.md)
- [Codex Skill contract](docs/codex_skill_contract.md)
- [Next steps](docs/next_steps.md)
