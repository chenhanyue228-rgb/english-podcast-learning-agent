# English Podcast Learning Agent

AI agent for converting English podcasts into structured English learning
materials stored in Notion.

## Notion Setup

The project supports two onboarding modes:

- **Mode 1: Guided Local Setup** is the recommended path for users who want to
  run the Python CLI independently. It uses the official Notion API SDK and a
  `NOTION_TOKEN` stored in `.env`.
- **Mode 2: Codex Assisted Setup** is useful while working inside Codex with the
  Notion plugin connected. Codex can help create or inspect the workspace, but
  the local Python project still needs `.env` values for independent CLI runs.

The Notion plugin and the Python `notion-client` SDK are different layers. The
plugin helps Codex act on your workspace interactively. The SDK is what this
project uses when you run commands such as `python -m src.notion.setup_workspace`
or `python -m src.workflow...`.

Data model principle:

- Database properties store metadata for filtering, relations, and statistics.
- Long transcript content lives in the podcast page body, not in database properties.
- Highlighted expressions, business phrases, and industry terms are annotated in
  the transcript body with Notion background colors.
- Expression records remain in `Expression Database` so they can be reviewed,
  counted, and related across podcasts.
- Expression page properties are limited to review metadata. Meaning, context
  sentence, example, and highlight color live in the expression page body.

Canonical databases:

- `Podcast Library`
  - Properties: `Title`, `URL`, `Source Type`, `Date`, `Topic`, `Difficulty`, `Short Summary`
  - Body order: `Summary`, `Expressions`, `Media`, `Highlight Legend`, `Highlighted Transcript`
  - `Short Summary` is a compact database-level summary for scanning.
  - Body `Summary` is the structured article-level summary.
  - `Media` is reserved for the source audio/video file or URL.
  - `Expressions` is rendered as one table per category. Category headings carry
    the same highlight color used in the transcript.
- `Expression Database`
  - Properties: `Expression`, `Category`, `Source Podcast`, `Review Status`
  - Body: `Meaning`, `Usage Context`, `Context Sentence`, `Example`, `Highlight Color`
  - `Context Sentence` means the local sentence where the expression appears,
    not the full transcript.
- `Weekly Review`
  - Properties: `Week`, `Date`, `Podcasts`, `Expression Count`, `Vocabulary Count`, `AI Summary`

See [docs/Notion_Data_Model.md](docs/Notion_Data_Model.md) for the full data
model contract used by setup, validation, sample data, and the podcast
pipeline.

### Mode 1: Guided Local Setup

#### 1. Install dependencies

```bash
pip install -r requirements.txt
```

#### 2. Create a Notion integration

Create an internal Notion integration, copy its secret token, and share the
parent Notion page with that integration. The initializer creates databases
inside that parent page.

#### 3. Configure environment variables

Copy the example file and fill in your token:

```bash
cp .env.example .env
```

Required before initialization:

```bash
NOTION_TOKEN=
```

You can also add the parent page ID to `.env`:

```bash
NOTION_PARENT_PAGE_ID=
```

`NOTION_PARENT_PAGE_ID` accepts either a raw Notion page ID or the full copied
Notion page URL. You can also pass it directly on the command line.

#### 4. Initialize the Notion workspace

```bash
python -m src.notion.setup_workspace --parent-page-id <notion_page_url_or_id>
```

The script creates:

- Podcast Library
- Expression Database
- Weekly Review

After creation, the script prints the database IDs and saves them into `.env`:

```bash
NOTION_PODCAST_LIBRARY_DATABASE_ID=
NOTION_EXPRESSION_DATABASE_ID=
NOTION_WEEKLY_REVIEW_DATABASE_ID=
```

#### 5. Validate the Notion workspace

Run the read-only workspace checker after initialization:

```bash
python -m src.notion.check_workspace
```

Expected successful output:

```text
✓ Podcast Library
✓ Expression Database
✓ Weekly Review

Missing:
None
```

#### 6. Create sample learning data

Create one sample podcast and three linked expressions:

```bash
python -m src.notion.create_example_data
```

The script creates a podcast titled `AI Transformation in Business` and links
these expressions to it:

- `take ownership`
- `move the needle`
- `operational leverage`

### Mode 2: Codex Assisted Setup

Use this path when you are developing inside Codex and have connected the Notion
plugin.

1. Connect the Notion plugin in Codex.
2. Ask Codex to create or inspect the English Podcast Learning workspace.
3. Let Codex create the three Notion databases and validate their properties.
4. Copy the resulting database IDs into `.env` if you want to run the local CLI.
5. Run `python -m src.notion.check_workspace` to confirm the local project can
   access the same workspace.

You can print the onboarding checklist from the CLI:

```bash
python -m src.notion.setup_workspace --print-onboarding
```

### Load Notion Configuration In Code

Use the shared config module for all Notion integrations:

```python
from src.notion.config import load_notion_config

config = load_notion_config()
database_ids = config.database_mapping
```

The mapping format is:

```python
{
    "podcast_database_id": "...",
    "expression_database_id": "...",
    "weekly_database_id": "...",
}
```

If required values are missing, the config module raises a clear
`NotionConfigError` with the missing variable name and next step.

## Transcript Highlight Mapping

Use the analyzer highlight mapper to convert extracted expressions into Notion
rich text:

```python
from src.analyzer.highlight_mapper import map_highlights_to_rich_text

rich_text = map_highlights_to_rich_text(
    "Companies need to take ownership of AI adoption.",
    [{"text": "take ownership", "type": "Business Phrase", "color": "blue"}],
)
```

The mapper supports multiple phrases, preserves the original transcript, avoids
embedded substring matches, and returns rich text items that can be passed to
Notion block/page APIs.

## Podcast Pipeline CLI

Run the modular podcast-to-Notion workflow with precomputed transcript and
analysis JSON:

```bash
python -m src.workflow.podcast_pipeline \
  --title "AI Transformation in Business" \
  --source-type Podcast \
  --source-url "https://example.com/podcast" \
  --topic "AI Transformation" \
  --difficulty Intermediate \
  --transcript-file transcript.json \
  --analysis-file learning.json
```

`transcript.json`:

```json
{
  "text": "Companies need to take ownership of AI adoption."
}
```

`learning.json`:

```json
{
  "summary": "A business English podcast about AI adoption.",
  "expressions": [
    {
      "text": "take ownership",
      "type": "Business Phrase",
      "meaning": "Accept responsibility",
      "usage_context": "Used when accepting accountability for a task or outcome.",
      "color": "blue"
    }
  ]
}
```

The pipeline publishes the podcast page body, creates expression entries,
relates each expression back to its source podcast, and creates or updates the
weekly review page.
