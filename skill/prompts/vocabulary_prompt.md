# Vocabulary Prompt

## Goal

Extract business vocabulary, industry terminology, and useful sentence patterns
from an English podcast transcript.

The output should help learners understand professional English in context and
reuse important terms or patterns in their own speaking and writing.

## Input Format

```json
{
  "title": "Podcast title",
  "transcript": "Full English transcript text"
}
```

## Output Format

Return valid JSON only:

```json
{
  "learning_items": [
    {
      "text": "term or phrase",
      "category": "Industry Term",
      "meaning": "English meaning",
      "chinese_meaning": "中文含义",
      "usage_context": "When and how to use it",
      "context_sentence": "Original sentence from transcript",
      "example_sentence": "New example sentence",
      "highlight_color": "yellow",
      "confidence": 0.9
    }
  ],
  "sentence_patterns": [
    {
      "pattern": "What we're seeing is...",
      "meaning": "English explanation",
      "chinese_meaning": "中文解释",
      "usage_context": "When to use this pattern",
      "context_sentence": "Original sentence from transcript",
      "example_sentence": "New example sentence",
      "highlight_color": "orange",
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

Allowed `learning_items` categories:

```json
[
  "Business Phrase",
  "Industry Term"
]
```

Highlight colors:

```json
{
  "Business Phrase": "blue",
  "Industry Term": "yellow",
  "Sentence Pattern": "orange"
}
```

## Rules

- Output JSON only. Do not include Markdown.
- Extract only terms, phrases, and sentence patterns that appear in the transcript.
- Do not include generic words that are not useful for learning.
- Prefer high-value business, leadership, technology, finance, management, and communication language.
- `context_sentence` must come from the transcript.
- `example_sentence` must be newly written and practical.
- Sentence patterns should be reusable structures, not one-off sentences.
- Avoid duplicates across `learning_items` and `sentence_patterns`.
- `learning_notes` should explain broader learning points, not repeat definitions.
- `confidence` should be a number between 0 and 1.

## Examples

Input:

```json
{
  "title": "AI Transformation in Business",
  "transcript": "Most companies are bolting on AI tools for functional tasks, but never touching the business core. What we're seeing is a leadership gap in the era of AI."
}
```

Output:

```json
{
  "learning_items": [
    {
      "text": "functional tasks",
      "category": "Business Phrase",
      "meaning": "Specific work activities within a business function.",
      "chinese_meaning": "职能性任务，具体业务职能中的工作任务",
      "usage_context": "Use this when discussing operations, teams, or business processes.",
      "context_sentence": "Most companies are bolting on AI tools for functional tasks, but never touching the business core.",
      "example_sentence": "Automation can handle many functional tasks in finance and customer support.",
      "highlight_color": "blue",
      "confidence": 0.88
    },
    {
      "text": "business core",
      "category": "Industry Term",
      "meaning": "The central activities, systems, or decisions that drive a business.",
      "chinese_meaning": "业务核心，决定企业运转和增长的关键部分",
      "usage_context": "Use this when talking about strategy, operations, or transformation.",
      "context_sentence": "Most companies are bolting on AI tools for functional tasks, but never touching the business core.",
      "example_sentence": "True digital transformation changes the business core, not just the user interface.",
      "highlight_color": "yellow",
      "confidence": 0.9
    }
  ],
  "sentence_patterns": [
    {
      "pattern": "What we're seeing is...",
      "meaning": "A pattern used to describe an observed trend or situation.",
      "chinese_meaning": "用于描述观察到的趋势或现象。",
      "usage_context": "Useful in meetings, analysis, presentations, and discussions.",
      "context_sentence": "What we're seeing is a leadership gap in the era of AI.",
      "example_sentence": "What we're seeing is a shift from manual work to AI-assisted workflows.",
      "highlight_color": "orange",
      "confidence": 0.93
    }
  ],
  "learning_notes": [
    {
      "title": "Business transformation language",
      "note": "This transcript uses language that contrasts surface-level tool adoption with deeper business change.",
      "chinese_note": "这段内容的表达重点是区分表层工具采用和深层业务变革。"
    }
  ]
}
```
