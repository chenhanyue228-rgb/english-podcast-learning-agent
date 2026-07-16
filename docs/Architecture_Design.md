# Architecture Design


## 1. System Overview



User

↓

URL/Input

↓

English Learning Agent


↓

Audio Extractor

↓

Speech Recognition

↓

Learning Analyzer

↓

Notion Publisher

↓

Weekly Report Generator



---

# 2. Technology Stack


Language:

Python


Core:


- faster-whisper
- OpenAI API
- Notion API
- yt-dlp
- feedparser
- APScheduler


---

# 3. Components



## Extractor


Responsibilities:

- Detect URL type
- Download audio


Input:

URL


Output:

audio file



---

## Transcriber


Responsibilities:

Convert audio to text


Output:


transcript.json



---

## Analyzer


Responsibilities:


Extract:


- Summary
- Expressions
- Vocabulary
- Patterns


Output:


learning.json



---

## Highlight Engine


Responsibilities:


Match extracted terms with transcript.


Output:


highlighted transcript blocks



---

## Notion Publisher


Responsibilities:


Create Notion pages.


---

## Weekly Reporter


Responsibilities:


Aggregate weekly learning data.

Generate report.



---

# 4. Data Flow



Audio

↓

Transcript

↓

Learning Analysis

↓

Highlight Mapping

↓

Notion Blocks


