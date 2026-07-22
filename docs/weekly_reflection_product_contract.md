# Weekly Reflection Product Contract

## Product Definition

Weekly Reflection is a curated compounding note. It preserves the few ideas and
expressions that deserve repeated use; it is not a weekly metadata report or a
copy of Podcast, Expression, or Vocabulary databases.

The production path is:

```text
WeeklyLearningContext
  -> ReflectionContext
  -> WeeklyReview
  -> Quality Gate
  -> weekly_reflection_writer
  -> Notion Weekly Review database
```

`src/notion/weekly_review_publisher.py` is a legacy compatibility path and is
not the publisher used by the production `weekly-reflection` command.

## WeeklyReview Artifact

The final artifact contains:

- one `core_idea`;
- an optional evidence-supported `mindset_shift`;
- 2-4 `ideas_worth_compounding`;
- 3-5 `expressions_worth_reusing`;
- one mandatory `language_thinking_connection`;
- exactly one `next_week_application`;
- compact `sources` and source IDs for traceability.

It must not contain a weekly vocabulary dump, all extracted expressions,
podcast-by-podcast summaries, counts, quality scores, or pipeline metadata as
user-facing content.

## Notion Presentation

The page has one native table of contents followed by numbered headings:

1. This Week's Core Idea
2. How My Thinking Changed (only when supported)
3. Ideas Worth Compounding
4. Expressions Worth Reusing
5. Language-Thinking Connection
6. One Application for Next Week
7. Sources

The main database view displays only `Week`, `Date`, and `Podcasts`.
Historical properties remain in the workspace until the user chooses to remove
them; the production writer no longer writes them.
