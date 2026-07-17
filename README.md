# English Podcast Learning Agent

Codex Skill for turning English podcasts, YouTube videos, direct audio links,
or local audio files into structured English learning materials in Notion.

The project has two layers:

- Python handles source detection, audio download, transcription, JSON
  validation, and Notion publishing.
- Codex handles AI learning analysis with local prompt and schema files. Python
  does not call OpenAI or any external LLM API directly.

Execution modes:

- If you run the local Python CLI or tests, the project behaves like a normal
  backend app and only uses the files and APIs you already configured.
- If you ask Codex to fetch real podcast URLs, download audio, or publish to
  Notion from inside the Codex environment, that action may trigger Codex
  approval checks. Those checks are about the runtime environment, not the
  project code.
- If an approval check fails, it usually means the Codex/OpenAI organization
  permissions are not ready yet, or the approval path has not propagated. The
  local project may still work normally when you run it directly in your own
  terminal.

## Current Flow

```text
User source
-> Source router
-> Source resolver / audio downloader
-> Audio validation
-> Whisper transcript
-> Codex AI analysis request JSON
-> Codex-generated analysis JSON
-> Complete Notion Podcast Library page
-> Linked Expression Database pages
```

Supported user inputs:

- YouTube URL
- Apple Podcasts episode URL
- Podcast RSS URL
- Direct audio URL
- Local audio file

Generic podcast platform pages are not supported yet. Podcast page URL support
currently means Apple Podcasts episode URLs.

## Setup

Install dependencies:

```bash
python3 scripts/bootstrap_environment.py
```

To only install dependencies:

```bash
python3 scripts/bootstrap_environment.py --skip-tests
```

Copy the environment template:

```bash
cp .env.example .env
```

Fill in Notion values:

```bash
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
NOTION_PODCAST_LIBRARY_DATABASE_ID=
NOTION_EXPRESSION_DATABASE_ID=
NOTION_WEEKLY_REVIEW_DATABASE_ID=
```

`NOTION_PARENT_PAGE_ID` is only needed when creating the workspace. It accepts a
raw Notion page ID or a copied Notion page URL.

## Notion Workspace

Initialize the Notion databases:

```bash
python3 -m src.notion.setup_workspace --parent-page-id <notion_page_url_or_id>
```

The initializer creates:

- `Podcast Library`
- `Expression Database`
- `Weekly Review`

It prints the database IDs and saves them into `.env`.

Validate the workspace:

```bash
python3 -m src.notion.check_workspace
```

Expected output:

```text
✓ Podcast Library
✓ Expression Database
✓ Weekly Review

Missing:
None
```

Create sample learning data:

```bash
python3 -m src.notion.create_example_data
```

## Run The Main Pipeline

Step 1: extract audio, transcribe, and create a Codex analysis request.

```bash
python3 src/main.py "<source>"
```

This writes:

- transcript JSON under `data/transcripts/`
- analysis request JSON under `data/analysis_requests/`

It does not create a partial Notion learning page. A Notion page should only be
created after Codex has produced complete AI analysis JSON.

Step 2: Codex reads the generated analysis request, uses the Skill prompts and
schema, and saves analysis JSON under `data/analysis/`.

Relevant files:

- `skill/prompts/metadata_prompt.md`
- `skill/prompts/summary_prompt.md`
- `skill/prompts/expression_prompt.md`
- `skill/schemas/ai_analysis_schema.json`

Step 3: publish the complete learning page.

```bash
python3 src/main.py "<source>" \
  --transcript-json data/transcripts/<file>.json \
  --analysis-json data/analysis/<file>.json
```

Using `--transcript-json` avoids rerunning audio extraction and Whisper.

## Weekly Review Workflow

Generate a Weekly Review request from the current week of Notion data:

```bash
python3 src/main.py --weekly-review
```

This creates a request file under `data/weekly_review_requests/` for Codex to
turn into `weekly_review.json`.

After Codex generates the weekly review JSON, publish it to Notion:

```bash
python3 src/main.py --weekly-review \
  --weekly-review-json data/analysis/<week>.json
```

The Weekly Review workflow uses the existing `Weekly Review` database schema.
No schema migration is needed for this phase.

## Notion Data Model

`Podcast Library` properties:

- `Title`
- `URL`
- `Source Type`
- `Date`
- `Topic`
- `Difficulty`
- `Short Summary`

Podcast page body order:

1. `Summary`
2. `Expressions`
3. `Highlight Legend`
4. `Highlighted Transcript`

`Expression Database` properties:

- `Expression`
- `Category`
- `Commonness`
- `Source Podcast`
- `Review Status`

Expression page body:

- `Meaning`
- `Chinese Meaning`
- `Usage Context`
- `Commonness`
- `Context Sentence`
- `Example`
- `Highlight Color`

`Weekly Review` exists in the workspace schema for future review features, but
the current main pipeline does not update it.

See [docs/Notion_Data_Model.md](docs/Notion_Data_Model.md) for the full schema
contract.

## Developer Notes

Run tests:

```bash
python3 -m pytest
```

Print runtime configuration without secrets:

```bash
python3 src/main.py --print-config
```

Use the legacy precomputed publisher only for development fixtures:

```bash
python3 -m src.workflow.podcast_pipeline \
  --title "AI Transformation in Business" \
  --source-type Podcast \
  --source-url "https://example.com/podcast" \
  --topic "AI Transformation" \
  --difficulty Intermediate \
  --transcript-file transcript.json \
  --analysis-file learning.json
```

The canonical user-facing entrypoint is `python3 src/main.py`.
