# Objective

Analyze weekly learning material to identify the few reflection signals worth
compounding. Do not summarize each podcast and do not inventory all language assets.

# Input

`WeeklyLearningContext.json`, containing podcasts, learning expressions,
AI highlights, and user vocabulary.

# Output

Return `ReflectionContext.json` matching the existing reflection context schema.

# Rules

1. Identify one coherent weekly theme.
2. Generate at most one mindset shift, and only when source evidence supports a genuine before-to-now change.
3. Keep evidence compact and traceable through `source` and `supporting_concept`.
4. Extract only 2-4 high-value transferable patterns.
5. Produce one concrete professional action candidate.
6. Do not treat podcast titles, guest names, counts, or metadata as insight.
7. Do not turn all expressions or vocabulary into reflection content.
8. For a single-source week, leave cross-content patterns empty rather than fabricating synthesis.
9. Avoid generic statements such as "apply this at work" or "practice the expressions".
10. Keep internal confidence available for validation, but never expose it in the final Notion page.

# Good reflection signal

Before: I treated disagreement as a contest between positions.

After: I now frame disagreement as joint problem solving around a shared object.

Evidence: A source concept explicitly connects negotiation with relationship management and shared problem solving.
