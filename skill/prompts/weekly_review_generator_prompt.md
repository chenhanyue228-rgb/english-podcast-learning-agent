# Objective

Create a curated weekly note titled "Ideas and Expressions Worth Compounding".
The note is not a weekly report, database dump, or podcast recap. It must preserve
the few ideas and expressions that deserve repeated use.

# Input

- `reflection_context`: analyzed learning signals
- `weekly_learning_context`: source expressions and compact source references
- `schema`: required JSON contract

# Output

Return one JSON object matching `weekly_review_generator_schema.json` exactly.

# Curation rules

1. Produce one core idea, not one summary per podcast.
2. Include a mindset shift only when `reflection_context` contains credible before/after evidence; otherwise return `null`.
3. Select 2-4 transferable ideas maximum.
4. Select 3-5 natural, reusable, professionally useful expressions maximum.
5. Do not include the week's vocabulary collection. Vocabulary Database remains the detailed vocabulary store.
6. Never select a proper name as a language asset without an explicit learning reason.
7. Do not invent cross-content synthesis for a single-source week.
8. For every expression include contextual meaning, one natural reusable example, and the idea or communication function it supports.
9. `language_thinking_connection` is mandatory. Explain how language provides a mental frame or improves precision, not merely that an expression is useful.
10. Produce exactly one `next_week_application` with a concrete scenario, exact behavior, phrase to use, and observable completion condition.
11. Do not expose scores, confidence, IDs, raw dictionaries, escaped formatting, or pipeline metadata in user-facing prose.
12. Avoid generic AI wording and repeated ideas across sections.
13. Keep the complete page readable in 3-5 minutes.

# Quality examples

Bad core idea: "This episode discusses negotiation."

Good core idea: "Disagreement becomes more productive when both sides treat the problem, rather than each other, as the object of attention."

Bad application: "Practice these expressions at work."

Good application:

```json
{
  "scenario": "A stakeholder challenges the proposed launch sequence",
  "behavior": "Restate the shared outcome before discussing constraints",
  "phrase_to_use": "Let's treat this as joint problem solving",
  "completion_condition": "Use the phrase once and note whether the discussion moves from positions to options"
}
```
