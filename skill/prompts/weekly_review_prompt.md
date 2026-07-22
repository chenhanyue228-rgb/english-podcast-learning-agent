# Objective
Generate a weekly English learning review from Podcast Library pages and related
Expression Database entries collected during the current week.

The output must be a structured JSON object that helps a learner understand
what changed this week, which expressions are worth revisiting, and what to
practice next.

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

Vocabulary memory fields:

- word
- context
- meaning
- professional_category
- my_usage
- review_status

# Output JSON schema

Return a single JSON object with this structure:

```json
{
  "week": "2026-W29",
  "executive_summary": {
    "overview": "This week focused on negotiation, communication, and AI leadership.",
    "takeaway": "The strongest learning signal was how to turn ideas into usable professional language.",
    "highlights": [
      "Negotiation as relationship management",
      "Practical communication patterns"
    ]
  },
  "knowledge_insights": [
    {
      "what_happened": "Several episodes repeated themes around ownership and clarity.",
      "why_it_matters": "It shows how professional communication depends on framing and timing.",
      "my_interpretation": "The week is less about memorizing facts and more about learning how to speak in context.",
      "application": "Use the same framing language when explaining work updates or decisions."
    }
  ],
  "expression_upgrade": [
    {
      "expression": "take ownership",
      "meaning": "Accept responsibility",
      "context": "Useful in leadership, project ownership, and execution conversations.",
      "example": "We need to take ownership of the rollout and own the next steps."
    }
  ],
  "vocabulary_memory": [
    {
      "word": "leverage",
      "context": "Companies can leverage AI...",
      "meaning": "Use resources effectively",
      "professional_category": "Word",
      "my_usage": "We can leverage AI tools to save time.",
      "review_status": "New"
    }
  ],
  "career_reflection": {
    "questions": [
      "What changed my thinking this week?",
      "What can I apply immediately at work?"
    ],
    "possible_applications": [
      "Use the upgraded expressions in status updates and planning meetings."
    ]
  },
  "next_learning_direction": [
    "Review the highest-value expressions in short speaking drills.",
    "Revisit the negotiation and communication episodes for reusable patterns."
  ]
}
```

# Extraction rules

1. Summarize the week like an English coach, not a logbook.
2. Do not simply list every podcast or every expression.
3. Group similar ideas into themes.
4. Prefer transferable expressions that are useful in real speaking and writing.
5. Avoid metadata summaries such as podcast titles, episode numbers, or author names.
6. Write from the learner's perspective and explain why the items matter.
7. `expression_upgrade` must contain only high-value professional expressions.
8. `knowledge_insights` must include `what_happened`, `why_it_matters`, `my_interpretation`, and `application`.
9. `career_reflection` should encourage thought and future action, not summary repetition.
10. Include only user-triggered vocabulary memory records in `vocabulary_memory`.
    Do not infer or auto-extract new vocabulary from transcript highlights.
11. If the week is empty, return empty lists and a minimal summary object.

# Examples

Example 1: A week with one AI leadership podcast and several expressions should
produce a summary about leadership, adoption, and accountability, not a flat
recap of transcript sentences.

Example 2: A week with multiple podcasts about negotiation and communication
should surface repeated patterns across episodes, and the recommended review
items should focus on the expressions that are both common and actionable.

Example 3: Avoid repeating podcast titles in the summary. Describe what changed in
the learner's language exposure instead.
