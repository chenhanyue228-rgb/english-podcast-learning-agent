# Product Requirement Document

Project:

English Audio Learning Agent


Version:

v1.0


---

# 1. Product Vision


Build an AI agent that converts English podcasts into structured learning materials stored in Notion.


---

# 2. Target Users


Primary:

English learners who consume:

- Podcasts
- Business audio content
- Local English audio


---

# 3. User Journey


Input:

Podcast URL


Process:


Audio extraction

↓

Speech recognition

↓

AI learning analysis

↓

Notion generation


Output:

Learning document


---

# 4. Functional Requirements


# Feature 1

## Audio Source Processing


Input:

- Podcast URL
- Podcast RSS Feed
- Audio file


Output:

Audio file


## Out of Scope for v1

YouTube support is intentionally excluded. The product focuses on stable audio
sources and avoids platform authentication, anti-bot behavior, and downloader
maintenance.


---

# Feature 2

## Transcript Generation


Technology:

Whisper


Output:


Transcript JSON


Example:


{
"time":"00:05:20",
"text":"Companies need to take ownership"
}


---

# Feature 3

## English Learning Analysis


AI extracts:


## Summary

English summary

Chinese explanation


## Native Expressions


Example:


Expression:

move the needle


Meaning:

create meaningful impact


Context:

Business strategy


---

## Business Vocabulary


Example:


Term:

operational leverage


Meaning:

运营杠杆


---

## Sentence Patterns


Example:


Pattern:

What we're seeing is...


Usage:

Describe trends


---

# Feature 4

## Transcript Highlight


Important expressions must be highlighted inside original transcript.


Highlight categories:


Green:

Native expressions


Blue:

Business vocabulary


Yellow:

Industry terminology


Example:


The company needs to

[green]
move the needle
[/green]


---

# Feature 5

## Notion Integration


Create:


Podcast Learning Database


Each page contains:


- Summary
- Transcript
- Highlighted expressions
- Vocabulary
- Sentence patterns


---

# Feature 6

## Weekly Learning Review


Automatically generate:


Weekly Summary


Including:


- Podcasts completed
- New expressions
- Important vocabulary
- Learning trends
- Recommended review


---

# 5. Non Goals


Not included in V1:


- Audio player
- Subtitle synchronization
- ChatGPT learning agent
- Web application


---

# 6. Success Metrics


After one month:


User can:


- Process 20 podcasts
- Accumulate 300+ expressions
- Review weekly learning reports




# Risks and Recommendations
Key missing decisions:
Whether Notion stores expressions as page blocks only, or as a separate reusable vocabulary database.
How to handle duplicate expressions across podcasts.
Whether transcript highlighting should preserve timestamps.
Whether weekly review is generated from local files, Notion queries, or both.
How to recover from partial failures, such as transcription succeeds but Notion publishing fails.
Whether OpenAI output must be strictly schema-validated before publishing.
Recommendations:
Use Pydantic models early. This project has many handoffs, so typed contracts will prevent messy downstream bugs.
Treat Notion publishing as the final projection layer, not the source of truth during processing.
Save intermediate artifacts locally: audio, transcript.json, learning.json, highlighted.json.
Start with one complete happy path: local audio file to Notion page.
Use separate Notion databases for long-term learning if review quality matters: Podcasts, Expressions, Vocabulary, and Weekly Reviews.
