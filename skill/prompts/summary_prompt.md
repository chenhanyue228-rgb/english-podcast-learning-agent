# Summary Prompt

## Objective

Generate a learning-oriented content summary from an English podcast transcript.

The summary should help an English learner understand the main message, the
speaker's logic, and the practical meaning of the episode.

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
  "summary": {
    "english": "A concise English summary of the content.",
    "chinese": "中文解释，说明内容主旨、逻辑和现实意义。",
    "key_points": [
      "Key point 1",
      "Key point 2",
      "Key point 3"
    ]
  }
}
```

## Extraction Rules

- Output JSON only. Do not include Markdown, comments, or extra text.
- Do not invent facts that are not supported by the transcript.
- The English summary should be natural, concise, and useful for an English learner.
- The Chinese explanation should explain the overall meaning, not translate sentence by sentence.
- `key_points` should contain 3 to 7 important points.
- Keep each key point specific and grounded in the transcript.
- If the transcript is repetitive or conversational, summarize the underlying ideas clearly.
- Preserve important business, leadership, communication, technology, and real-world context when relevant.

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
  "summary": {
    "english": "The episode argues that companies should actively lead AI adoption and use it to create meaningful operational impact.",
    "chinese": "这段内容强调，企业不能只是被动使用 AI 工具，而需要主动承担 AI 转型的责任，并通过运营效率提升产生真正的业务影响。",
    "key_points": [
      "Companies need to take ownership of AI adoption.",
      "AI should produce measurable business impact.",
      "Operational leverage is an important part of transformation."
    ]
  }
}
```
