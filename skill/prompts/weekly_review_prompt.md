# Objective
Generate a weekly English learning review from Podcast Library pages and related
Expression Database entries collected during the current week.

The output must be a structured JSON object that helps a learner understand
what happened this week, which ideas mattered most, and what to review next.

# Input format

The input to Codex should include:

- week label
- date
- podcast items for the current week
- expression items linked to those podcasts

Podcast item fields:

- title
- topic
- difficulty
- short_summary

Expression item fields:

- expression
- category
- meaning
- usage_context
- review_status

# Output JSON schema

Return a single JSON object with this structure:

```json
{
  "week": "2026-W29",
  "date": "2026-07-17",
  "statistics": {
    "podcast_count": 2,
    "expression_count": 18,
    "category_distribution": {
      "Native Expression": 6,
      "Business Phrase": 5,
      "Industry Term": 3,
      "Collocation": 2,
      "Sentence Pattern": 2
    }
  },
  "summary": {
    "english": "This week focused on leadership, negotiation, and practical AI adoption.",
    "chinese": "本周内容主要围绕领导力、谈判和 AI 落地展开。"
  },
  "key_learning_points": [
    "AI adoption works best when teams take ownership of the process.",
    "Negotiation language is more effective when it is concrete and low-friction."
  ],
  "recommended_review": [
    {
      "expression": "take ownership",
      "reason": "High-frequency business phrase that appeared in a leadership context and is useful for accountability discussions."
    }
  ]
}
```

# Extraction rules

1. Summarize the week like an English coach, not a logbook.
2. Do not simply list every podcast or every expression.
3. Group similar ideas into themes.
4. Prefer the expressions that are most reusable in real speaking and writing.
5. Keep the summary short, clear, and instructional.
6. If the week is empty, return empty statistics and a brief empty-week summary.

# Examples

Example 1: A week with one AI leadership podcast and several expressions should
produce a summary about leadership, adoption, and accountability, not a flat
recap of transcript sentences.

Example 2: A week with multiple podcasts about negotiation and communication
should surface repeated patterns across episodes, and the recommended review
items should focus on the expressions that are both common and actionable.
