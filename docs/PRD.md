# Product Requirement Document

Project:

English Podcast Learning Agent


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
- Youtube interviews
- Business content


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

- Youtube URL
- Podcast URL
- Audio file


Output:

Audio file


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
