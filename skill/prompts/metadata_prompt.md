# Metadata Prompt

## Objective

Generate concise podcast metadata for the Notion Podcast Library.

The metadata should help learners quickly understand the topic, difficulty, and
short value of a podcast episode before reading the full learning material.

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
  "podcast_metadata": {
    "title": "Clean podcast episode title",
    "topic": "A short topic label",
    "difficulty": "Beginner | Intermediate | Advanced",
    "short_summary": "One concise sentence summarizing the episode."
  }
}
```

## Extraction Rules

- Output JSON only. Do not include Markdown, comments, or extra text.
- `title` should be the clean episode title. If the input title is already meaningful, preserve it.
- `topic` should be short enough for a Notion select property.
- Use a practical topic label such as `AI`, `Business`, `Leadership`, `Communication`, `Technology`, `Career`, or another transcript-based label.
- `difficulty` must be one of: `Beginner`, `Intermediate`, `Advanced`.
- Choose `Beginner` for simple everyday English and slow, direct content.
- Choose `Intermediate` for normal podcast conversation with some useful expressions.
- Choose `Advanced` for dense business, technical, academic, or abstract discussion.
- `short_summary` should be one sentence and should not exceed 25 words.
- Do not include transcript details that are not clearly supported by the input.

## Examples

Input:

```json
{
  "title": "AI Transformation in Business",
  "transcript": "Companies need to take ownership of AI adoption and move the needle through operational leverage."
}
```

Output:

```json
{
  "podcast_metadata": {
    "title": "AI Transformation in Business",
    "topic": "AI",
    "difficulty": "Intermediate",
    "short_summary": "A discussion about how companies can take responsibility for AI adoption and create operational impact."
  }
}
```
