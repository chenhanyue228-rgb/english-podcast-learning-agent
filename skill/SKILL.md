# English Podcast Learning Agent Skill

## Purpose

Convert English podcasts, YouTube videos, or local audio files into structured
English learning materials stored in Notion.

## Architecture Rule

This project is a Codex Skill, not a standalone Python AI application.

Do not add external LLM API calls to Python code. In particular, do not add:

- `OPENAI_API_KEY`
- OpenAI SDK dependencies
- direct OpenAI API calls

AI reasoning should happen in the Codex agent execution environment. Python is
responsible for source extraction, transcription, JSON validation, and Notion
publishing.

Execution mode note:

- Local terminal runs and tests use your configured Python environment.
- Codex-assisted network actions may trigger Codex approval checks because the
  runtime is different from the local terminal.
- If approval fails, it is usually an environment or organization permission
  issue rather than a bug in the project code.

## First-Time Setup

Prepare the local Python environment:

```bash
python3 scripts/bootstrap_environment.py
```

To install dependencies without running smoke tests:

```bash
python3 scripts/bootstrap_environment.py --skip-tests
```

Then configure Notion in `.env`:

```bash
NOTION_TOKEN=
NOTION_PODCAST_LIBRARY_DATABASE_ID=
NOTION_EXPRESSION_DATABASE_ID=
NOTION_WEEKLY_REVIEW_DATABASE_ID=
```

## Supported Inputs

- YouTube URL
- Apple Podcasts URL
- Podcast RSS URL
- Direct audio URL
- Local audio file

## Default User Workflow

When the user provides a source URL or local audio path, run:

```bash
python3 src/main.py "<source>"
```

This performs:

```text
Source
-> Audio extraction
-> Whisper transcript
-> Transcript JSON saved under data/transcripts/
-> Codex AI analysis request saved under data/analysis_requests/
```

Do not ask the user to provide `--analysis-json`. Treat the generated analysis
request as an internal handoff file for the Codex agent.

## Codex AI Handoff

After `python3 src/main.py "<source>"` finishes, Codex must continue the flow:

1. Read the generated file from `data/analysis_requests/`.
2. Use the Codex agent execution environment to analyze the transcript with:

- `skill/prompts/metadata_prompt.md`
- `skill/prompts/summary_prompt.md`
- `skill/prompts/expression_prompt.md`
- `skill/schemas/ai_analysis_schema.json`

3. Save the generated JSON under `data/analysis/`.

4. Publish the complete Notion learning page with:

```bash
python3 src/main.py "<source>" --analysis-json data/analysis/<file>.json
```

Python validates the generated JSON and creates one complete Notion Podcast
Library page. Never create a Podcast Library page without AI analysis content.

## AI Analysis Output

The generated JSON must include:

- `summary.english`
- `summary.chinese`
- `summary.key_points`
- `podcast_metadata.title`
- `podcast_metadata.topic`
- `podcast_metadata.difficulty`
- `podcast_metadata.short_summary`
- `learning_items`
  - each item should include `commonness` as `High`, `Medium`, or `Low`

Allowed learning item categories must match the Notion Expression Database:

- `Native Expression`
- `Business Phrase`
- `Industry Term`
- `Collocation`
- `Sentence Pattern`

Color mapping:

- Green = Native expressions
- Blue = Business phrases
- Yellow = Industry terms
- Purple = Collocations
- Orange = Sentence patterns

Commonness values:

- High
- Medium
- Low

Use `commonness` to capture how often the expression is likely to appear in real
English and how reusable it is for learners.

## Notion Output

Podcast Library page:

- Title
- URL
- Source Type
- Date
- Topic
- Difficulty
- Short Summary
- Summary section
- Expressions grouped by category
- Highlight Legend
- Highlighted Transcript

Expression Database pages:

- Expression
- Category
- Commonness
- Review Status = New
- Source Podcast relation
- Meaning
- Chinese Meaning
- Usage Context
- Context Sentence
- Example
- Highlight Color

## Quality Rules

- Do not only translate.
- Prefer useful expressions over simple vocabulary.
- Do not optimize for item count alone. Optimize for both learning value and appropriate coverage.
- Avoid basic expressions that intermediate learners already know.
- Select expressions that are reusable, non-obvious, natural, and worth reviewing.
- Extract all genuinely valuable learning items from the transcript, but do not add weak items just to increase volume.
- Scan the full transcript and include valuable expressions from the middle and later sections, not only the opening portion.
- Ignore ads, sponsor messages, intros, outros, and subscription reminders when possible.
- Each learning item should include meaning, Chinese meaning, usage context, original context sentence, and a realistic example.
- The learning item text should appear in the transcript or in its context sentence.
