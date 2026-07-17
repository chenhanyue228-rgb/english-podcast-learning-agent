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
3. `Highlight Legend`
4. `Highlighted Transcript`

`Short Summary` is a compact database-level summary for scanning. Body
`Summary` is the structured article-level summary.

`Expressions` is rendered as one table per category. Each category heading is
highlighted with its category color. Each table has:

- `Expression`
- `Meaning`
- `Usage Context`
- `Commonness`

## Expression Database

Properties:

- `Expression`
- `Category`
- `Commonness`
- `Source Podcast`
- `Review Status`

Page body order:

1. `Meaning`
2. `Usage Context`
3. `Commonness`
4. `Context Sentence`
5. `Example`
6. `Highlight Color`

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

Weekly Review is kept in the workspace schema for future review features. The
current main pipeline does not write weekly review pages.

## Highlight Colors

- Green: Native expressions
- Blue: Business phrases
- Yellow: Industry terms
- Purple: Collocations
- Orange: Sentence patterns

The Podcast `Highlight Legend` should show all five categories so it matches
the Expression Database categories and transcript highlights.

## Implementation Files

- `src/notion/schema.py`: canonical database names, properties, categories, and
  colors.
- `src/notion/renderers.py`: canonical Notion page body renderers.
- `src/notion/check_workspace.py`: validates real Notion databases against the
  canonical schema.
- `src/notion/create_example_data.py`: creates sample data using the canonical
  schema and renderers.
- `src/notion/learning_publisher.py`: creates complete Podcast Library pages
  and linked Expression Database pages.
- `src/main.py`: canonical CLI entrypoint for extraction, transcription, Codex
  analysis handoff, and complete Notion publishing.
