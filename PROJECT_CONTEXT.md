# Project Context

## Product

**Name:** English Audio Learning Agent

English Audio Learning Agent is an AI-powered English audio learning system
that transforms podcasts, RSS feeds, and local audio files into reusable
learning assets, including:

- vocabulary
- expressions
- ideas
- reflections

The system helps users build long-term personal English learning memory.

## Current Phase

**Phase 4 — Product Validation**

The current stable release is **v1.1.0**, built from merge commit
`80cbab01ea266e487a0359ddbec562959070d8a0`.

Release status:

- v1.1.0 is released and tagged locally and remotely
- the production architecture and workflow boundaries are stable
- production workflows and CLI behavior are verified
- 345 tests pass with 3 expected compatibility-provider deprecation warnings
- Product Validation is now the priority

Phase 4 validates whether a new user can independently transform an English
audio source into useful, reusable Notion learning assets. The immediate
priority is clean-clone onboarding and first-user journey validation.

## Runtime Model

### Codex: Reasoning and Generation Layer

Codex performs language understanding and generates structured artifacts for:

- Podcast Analysis
- vocabulary enrichment
- Reflection Analysis
- Weekly Review generation

### Python: Execution, Orchestration, and Validation Layer

Python performs deterministic work:

- source processing and transcription
- request artifact creation
- schema validation
- workflow orchestration
- dedupe and idempotency
- Notion synchronization

### Notion: Long-Term Knowledge Memory Layer

Notion stores the long-term learning system:

- Podcast Library
- Expression Database
- Vocabulary Database
- Weekly Review Database

## Production Artifact Flow

```text
Codex Skill
↓
Request Artifact
↓
Codex-generated JSON
↓
Python Validation
↓
Workflow
↓
Notion
```

The production Skill flow does not require `OPENAI_API_KEY`. Direct OpenAI
providers are deprecated compatibility paths only.

## Supported v1 Inputs

- Podcast episode URL
- Podcast RSS feed
- Local audio file

YouTube is intentionally outside v1 product scope. Remaining implementation is
experimental and must not be advertised as a supported input.

## Product Principles

1. The user owns learning selection.
2. AI transforms user-selected content into reusable knowledge assets.
3. The system optimizes for long-term learning compounding, not content
   aggregation.

## Accepted Product Workflows

### Podcast Learning

Audio is resolved, validated, transcribed, analyzed by Codex through artifacts,
validated by Python, and published to Podcast Library and Expression Database.

### Vocabulary Memory

The user marks an exact vocabulary target with a pink highlight. Codex enriches
the resulting artifact, and Python validates, deduplicates, and upserts it into
Vocabulary Database.

### Weekly Reflection

Weekly learning facts are transformed into ReflectionContext and WeeklyReview
artifacts, checked by a quality gate, and idempotently published to Notion.
Weekly Reflection is a compounding learning note rather than a recap.

## Frozen Boundaries

- Podcast Library and Notion schema
- Podcast page content structure
- artifact JSON contracts
- Vocabulary/Expression ownership separation
- exact pink-highlight vocabulary intent
- Weekly Reflection product structure
- Notion idempotent publishing

## Current Product Risks

- Setup may still require too much technical knowledge.
- First-time Notion configuration has not been tested by external users.
- The Codex artifact handoff may be unclear to a new user.
- The first-use path has not been measured.
- Learning-asset usefulness has not been validated with external users.

## Historical Milestones

### Phase 3 — Product Stabilization / Post v1.1

Phase 3 established the safe v1.1 release baseline, aligned documentation and
runtime contracts, protected private and generated artifacts, verified the
full regression suite, and completed the reviewed v1.1.0 release.

## Immediate Milestone

Complete Phase 4.1 clean-clone onboarding validation: observe new users setting
up the environment and Notion, processing a first supported audio source,
completing the Codex artifact handoff, and publishing a first learning page.
Record evidence before scheduling product or architecture changes.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md` and
`skill/SKILL.md` before changing runtime behavior.
