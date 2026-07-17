# Expression Prompt

## Objective

Extract high-value English learning items from a podcast transcript.

The output should help learners understand and reuse natural English,
professional business language, industry terminology, common collocations, and
sentence patterns.

## Input Format

```json
{
  "title": "Podcast title",
  "transcript": "Full English transcript text"
}
```

## Output JSON Schema

Return valid JSON only:

```json
{
  "learning_items": [
    {
      "text": "Exact expression, phrase, term, collocation, or sentence pattern",
      "category": "Native Expression",
      "meaning": "English meaning",
      "chinese_meaning": "中文含义",
      "usage_context": "When and how learners can use it",
      "context_sentence": "Original sentence or closest original sentence from the transcript",
      "example_sentence": "A new practical example sentence",
      "commonness": "High",
      "highlight_color": "green",
      "confidence": 0.9
    }
  ],
  "learning_notes": [
    {
      "title": "Short note title",
      "note": "English learning note",
      "chinese_note": "中文学习说明"
    }
  ]
}
```

Allowed `category` values must match the Notion schema exactly:

```json
[
  "Native Expression",
  "Business Phrase",
  "Industry Term",
  "Collocation",
  "Sentence Pattern"
]
```

Recommended highlight colors:

```json
{
  "Native Expression": "green",
  "Business Phrase": "blue",
  "Industry Term": "yellow",
  "Collocation": "purple",
  "Sentence Pattern": "orange"
}
```

## Extraction Rules

- Output JSON only. Do not include Markdown, comments, or extra text.
- Extract only items that appear in the transcript.
- Preserve the exact item text from the transcript when possible.
- Do not extract generic single words unless they are meaningful industry terms.
- Do not extract easy phrases that most intermediate learners already know, such as basic greetings, simple verbs, or literal everyday phrases.
- Do not fill a fixed quota. The number of items should depend on transcript quality and learning density.
- Aim for both high quality and sufficient coverage: extract all genuinely valuable learning items, but do not add weak items just to increase volume.
- A good item should be reusable, non-obvious, natural, and worth reviewing later.
- Scan the entire transcript before selecting items. Do not over-sample from the introduction or first half.
- Include valuable items from the middle and later sections when they exist.
- Avoid duplicates and near-duplicates.
- `context_sentence` must come from the transcript or be the closest complete sentence around the item.
- `example_sentence` must be newly written, practical, and different from the transcript sentence.
- `usage_context` should explain when a learner can use the item in real communication.
- `confidence` must be a number between 0 and 1.
- Use `Native Expression` for idioms, phrasal expressions, and natural spoken English.
- Use `Business Phrase` for workplace, leadership, strategy, meetings, management, and operational language.
- Use `Industry Term` for technical, business, AI, finance, product, or domain-specific terminology.
- Use `Collocation` for natural word combinations that learners should memorize together.
- Use `Sentence Pattern` for reusable sentence structures, not one-off complete sentences.
- Prioritize quality and appropriate coverage. The final list should feel complete for the transcript, not artificially short or artificially long.

## Selection Priority

Prioritize items in this order:

1. Natural spoken expressions that are hard to produce actively.
2. Reusable sentence patterns for meetings, interviews, storytelling, explanations, and presentations.
3. Collocations that sound native and are common in professional communication.
4. Business or communication phrases that transfer to real work situations.
5. Domain terms only when they are truly useful for understanding the episode.

## Quality Rating Rules

- Set `commonness` to `High`, `Medium`, or `Low`.
- `High` means the item is broadly useful and likely to appear often in real English.
- `Medium` means the item is useful but more context-specific.
- `Low` means the item is more niche, but still worth keeping if it is genuinely valuable.
- Prefer `High` and `Medium` items. Use `Low` only when the transcript contains a rare but highly educational phrase.
- Do not mark basic or weak items as `High` just to increase the count.

Reject items when:

- The meaning is obvious from the individual words.
- The phrase is too basic to be worth reviewing.
- The item is only interesting because of the episode topic but is not reusable.
- The transcript sentence is too noisy to provide a reliable context.

## Examples

Input:

```json
{
  "title": "AI Transformation in Business",
  "transcript": "Companies need to take ownership of AI adoption and move the needle through operational leverage. What we're seeing is a leadership gap in the era of AI."
}
```

Output:

```json
{
  "learning_items": [
    {
      "text": "take ownership",
      "category": "Business Phrase",
      "meaning": "Accept responsibility for something and actively manage it.",
      "chinese_meaning": "承担责任，主动负责",
      "usage_context": "Use this when talking about accountability for a project, decision, or result.",
      "context_sentence": "Companies need to take ownership of AI adoption and move the needle through operational leverage.",
      "example_sentence": "The product team needs to take ownership of the launch timeline.",
      "highlight_color": "blue",
      "commonness": "High",
      "confidence": 0.95
    },
    {
      "text": "move the needle",
      "category": "Native Expression",
      "meaning": "Create a meaningful or noticeable impact.",
      "chinese_meaning": "产生实质性影响",
      "usage_context": "Use this when describing work or decisions that produce visible results.",
      "context_sentence": "Companies need to take ownership of AI adoption and move the needle through operational leverage.",
      "example_sentence": "The new pricing strategy finally moved the needle on revenue growth.",
      "highlight_color": "green",
      "commonness": "High",
      "confidence": 0.94
    },
    {
      "text": "operational leverage",
      "category": "Industry Term",
      "meaning": "The ability to improve output or efficiency without increasing costs at the same rate.",
      "chinese_meaning": "运营杠杆，通过效率提升放大业务产出",
      "usage_context": "Use this in business, operations, finance, or strategy discussions.",
      "context_sentence": "Companies need to take ownership of AI adoption and move the needle through operational leverage.",
      "example_sentence": "Automation gave the company more operational leverage as it scaled.",
      "highlight_color": "yellow",
      "commonness": "Medium",
      "confidence": 0.92
    },
    {
      "text": "leadership gap",
      "category": "Collocation",
      "meaning": "A shortage or weakness in effective leadership.",
      "chinese_meaning": "领导力缺口",
      "usage_context": "Use this when describing an organization that lacks the leadership needed for change.",
      "context_sentence": "What we're seeing is a leadership gap in the era of AI.",
      "example_sentence": "The failed transformation revealed a leadership gap across the organization.",
      "highlight_color": "purple",
      "commonness": "Medium",
      "confidence": 0.88
    },
    {
      "text": "What we're seeing is...",
      "category": "Sentence Pattern",
      "meaning": "A structure used to introduce an observed trend, issue, or situation.",
      "chinese_meaning": "用于引出观察到的趋势、问题或现象。",
      "usage_context": "Use this in meetings, analysis, presentations, and discussion.",
      "context_sentence": "What we're seeing is a leadership gap in the era of AI.",
      "example_sentence": "What we're seeing is a shift from manual work to AI-assisted workflows.",
      "highlight_color": "orange",
      "commonness": "High",
      "confidence": 0.93
    }
  ],
  "learning_notes": [
    {
      "title": "Business transformation language",
      "note": "The transcript uses language that contrasts surface-level tool adoption with deeper operational change.",
      "chinese_note": "这段内容的表达重点是区分表层工具采用和深层业务变革。"
    }
  ]
}
```
