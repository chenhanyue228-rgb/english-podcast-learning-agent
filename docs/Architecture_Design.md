# Architecture Design

## System Overview

English Audio Learning Agent is a Codex Skill plus a small Python backend.

Python is responsible for deterministic work:

- input detection
- source resolution
- audio download
- audio validation
- speech-to-text
- JSON validation
- Notion publishing

Codex is responsible for AI reasoning:

- content summary
- metadata
- expression extraction
- learning notes

Python must not call an external LLM API directly. The AI handoff is a generated
JSON request file that Codex reads and turns into validated analysis JSON.

## Main Flow

```text
User Input
(Apple Podcasts / RSS / Local Audio)
↓
Source Router
↓
Source Resolver
↓
Audio Downloader
↓
Audio File
↓
Audio Validator
↓
Whisper Transcriber
↓
Transcript JSON
↓
Codex AI Analysis Request
↓
Codex AI Analysis JSON
↓
Notion Learning Publisher
↓
Podcast Library Page + Expression Database Pages
```

The Notion page is created only after analysis JSON is available. This prevents
partial Podcast Library pages with empty Topic, Difficulty, Short Summary, or
Expressions.

## Supported Inputs

- Apple Podcasts episode URL
- Podcast RSS URL
- Local audio file

## Out of Scope for v1

YouTube is intentionally excluded from the supported product. The v1 runtime
focuses on stable audio sources without platform login, anti-bot, or video
downloader dependencies. Existing YouTube extraction modules are experimental
and retained only for possible future evaluation.

Generic podcast platform page support is intentionally outside the current MVP.
For now, "Podcast Page URL" means Apple Podcasts episode URL.

## Components

### Source Router

Module:

- `src/extractor/router.py`

Responsibilities:

- detect supported input type
- reject unsupported URLs with a clear error
- avoid network calls and downloads

Output:

- normalized source type
- original source value

### Source Resolver

Modules:

- `src/extractor/podcast_resolver.py`
- `src/extractor/apple_podcast_resolver.py`
- `src/extractor/podcast.py`

Responsibilities:

- resolve Apple Podcasts episode URLs into RSS enclosure audio URLs
- parse RSS feeds
- never fallback to the first RSS episode when matching fails
- return diagnostic errors when a requested episode cannot be located reliably

Apple Podcasts matching uses:

- episode ID when available
- normalized title match
- title similarity
- publication date similarity

### Audio Downloader

Module:

- `src/extractor/audio_downloader.py`

Responsibilities:

- stream large audio downloads
- retry transient failures
- reuse existing downloaded files
- support mp3, m4a, wav, and configured local audio formats
- raise clean `AudioDownloadError` messages

### Audio Validator

Module:

- `src/pipeline/validators.py`

Responsibilities:

- verify file exists
- verify minimum file size
- validate duration with `ffprobe` when available
- warn and continue when `ffprobe` is unavailable

### Transcriber

Module:

- `src/transcriber/whisper.py`

Responsibilities:

- run `faster-whisper`
- produce timestamped English transcript JSON
- preserve segment start/end times

### Codex AI Analysis Handoff

Modules and files:

- `src/analyzer/learning_analyzer.py`
- `src/analyzer/ai_client.py`
- `src/analyzer/validators.py`
- `skill/prompts/metadata_prompt.md`
- `skill/prompts/summary_prompt.md`
- `skill/prompts/expression_prompt.md`
- `skill/schemas/ai_analysis_schema.json`

Responsibilities:

- prepare transcript input and prompt instructions
- save an analysis request JSON under `data/analysis_requests/`
- validate Codex-generated analysis JSON from `data/analysis/`

Despite the historical module name, `src/analyzer/ai_client.py` is a Skill
handoff helper. It does not call an LLM provider.

### Notion Publisher

Modules:

- `src/notion/learning_publisher.py`
- `src/notion/renderers.py`
- `src/notion/schema.py`
- `src/notion/uploader.py`

Responsibilities:

- create complete Podcast Library pages
- fill Topic, Difficulty, and Short Summary properties
- render Summary, Expressions, Highlight Legend, and Highlighted Transcript
- create Expression Database pages
- link expressions back to the source podcast

The current main pipeline does not update Weekly Review.

## Weekly Review Flow

```text
Current week Notion data
↓
Weekly Review request JSON
↓
Codex Skill weekly_review.json
↓
Weekly Review Publisher
↓
Weekly Review page in Notion
```

This workflow is independent from the podcast pipeline and does not change the
Podcast Library or Expression Database schemas.

Python is responsible for:

- collecting current-week Podcast Library and Expression Database records
- writing `data/weekly_review_requests/<week>.json`
- validating Codex-generated `weekly_review.json`
- publishing or updating the Weekly Review page in Notion

Codex is responsible for:

- summarizing the week
- identifying main themes
- recommending the most useful expressions for review

The generated weekly review JSON is validated in Python before publishing. The
existing Weekly Review database schema is reused as-is; no Notion schema
migration is required for this phase.

## Notion Data Boundary

Database properties are intentionally lean:

- use properties for scanning, filtering, review status, and relations
- keep long summaries, transcript text, meanings, usage notes, and examples in
  page body blocks

Podcast Library does not expose an `Expressions` relation property. Expressions
are shown in the Podcast page body and linked from Expression Database pages
through `Source Podcast`.

## Entry Points

Primary user entrypoint:

```bash
python3 src/main.py "<source>"
```

Publish from existing transcript and analysis:

```bash
python3 src/main.py "<source>" \
  --transcript-json data/transcripts/<file>.json \
  --analysis-json data/analysis/<file>.json
```

Weekly Review:

```bash
python3 src/main.py --weekly-review
```

This writes a weekly review request JSON and stops so Codex can generate
`weekly_review.json`. After Codex produces that file, publish it with:

```bash
python3 src/main.py --weekly-review \
  --weekly-review-json data/analysis/<week>.json
```

Workspace setup:

```bash
python3 -m src.notion.setup_workspace --parent-page-id <notion_page_url_or_id>
```

Workspace validation:

```bash
python3 -m src.notion.check_workspace
```

## Non-Goals For Current Phase

- generic podcast platform page resolver
- weekly review generation
- chat interface
- Python-side OpenAI API integration
- automatic browser UI control
