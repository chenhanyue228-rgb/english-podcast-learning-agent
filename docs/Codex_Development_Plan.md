# Codex Development Plan


## Development Principle


Document-driven development.


Never ask Codex to build the whole project.


Develop module by module.



---

# Phase 1

## Project Setup


Tasks:


- Create repository
- Setup Python environment
- Setup configuration


Estimated:

3 hours


---

# Phase 2

## Audio Pipeline


Modules:


src/extractor


Tasks:


- Podcast URL and RSS extractor
- Local audio loader


Estimated:

8 hours


---

# Phase 3

## Transcription


Module:


src/transcriber


Tasks:


- faster-whisper integration
- timestamp output


Estimated:

8 hours


---

# Phase 4

## AI Analyzer


Module:


src/analyzer


Tasks:


- Summary
- Expression extraction
- Vocabulary extraction


Estimated:

15 hours


---

# Phase 5

## Highlight Engine


Tasks:


- Mapping expressions
- Generate Notion rich text colors


Estimated:

10 hours


---

# Phase 6

## Notion Integration


Tasks:


- Database creation
- Page generation


Estimated:

10 hours


---

# Phase 7

## Weekly Report


Tasks:


- Scheduler
- Weekly aggregation


Estimated:

8 hours


---

Total:

60-90 hours

4-6 weeks

---

# Out of Scope for v1

YouTube extraction is intentionally excluded. Any existing implementation is
experimental future work and is not part of the supported product.
