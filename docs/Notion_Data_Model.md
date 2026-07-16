# Notion Data Model

This document is the source of truth for how English Podcast Learning Agent
stores learning material in Notion.

## Design Principles

- Database properties are for filtering, review state, relations, and weekly
  statistics.
- Long learning content belongs in page body blocks, not database properties.
- Podcast transcript is stored only in the Podcast page body.
- Expression explanations are stored in Expression page bodies.
- `Context Sentence` means the local sentence where the expression appears, not
  the full transcript.

## Podcast Library

Properties:

- `Title`
- `URL`
- `Source Type`
- `Date`
- `Topic`
- `Difficulty`
- `Short Summary`

Page body order:

1. `Summary`
2. `Expressions`
3. `Media`
4. `Highlight Legend`
5. `Highlighted Transcript`

`Short Summary` is a compact database-level summary for scanning. Body
`Summary` is the structured article-level summary.

`Expressions` is rendered as one table per category. Each category heading is
highlighted with its category color. Each table has:

- `Expression`
- `Meaning`
- `Usage Context`

`Media` is reserved for the source audio/video file or URL. If unavailable, it
shows `Not provided yet`.

## Expression Database

Properties:

- `Expression`
- `Category`
- `Source Podcast`
- `Review Status`

Page body order:

1. `Meaning`
2. `Usage Context`
3. `Context Sentence`
4. `Example`
5. `Highlight Color`

`Source Podcast` is the only relation needed between Expression records and the
Podcast Library. The Podcast page body already displays extracted expressions,
so Podcast Library does not need an `Expressions` relation property.

## Weekly Review

Properties:

- `Week`
- `Date`
- `Podcasts`
- `Expression Count`
- `Vocabulary Count`
- `AI Summary`

Weekly review statistics are written by the workflow. They are not rollups from
Podcast Library because Podcast pages intentionally do not expose expression
relations as properties.

## Highlight Colors

- Green: Native expressions
- Blue: Business phrases
- Yellow: Industry terms
- Purple: Collocations
- Orange: Sentence patterns

Only Green, Blue, and Yellow are shown in the default Podcast `Highlight Legend`
for now, because those are the primary transcript highlight categories.

## Implementation Files

- `src/notion/schema.py`: canonical database names, properties, categories, and
  colors.
- `src/notion/renderers.py`: canonical Notion page body renderers.
- `src/notion/check_workspace.py`: validates real Notion databases against the
  canonical schema.
- `src/notion/create_example_data.py`: creates sample data using the canonical
  schema and renderers.
- `src/workflow/podcast_pipeline.py`: orchestrates podcast processing and
  delegates all page layout to the renderers.
