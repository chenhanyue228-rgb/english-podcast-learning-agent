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

**Execution stage:** Phase 4.1C — Owner Acceptance

**Status:** `OWNER_ACCEPTANCE_BLOCKED`

The current stable release remains **v1.1.0**, built from release commit
`80cbab01ea266e487a0359ddbec562959070d8a0`. The current production `main`
includes PR #6 through merge commit
`87b96d9f68ad65d3356943b1f8196eeea8f9f3ee`.

Release status:

- v1.1.0 is released and tagged locally and remotely
- the production architecture and workflow boundaries are stable
- production workflows and CLI behavior are verified
- PR #4 merged the Phase 4.1B onboarding fixes into `main`
- PR #5 merged the guided first-time-use flow into `main`
- PR #6 merged the one-action/one-confirmation Notion guidance into `main`
- 440 tests pass with 3 expected compatibility-provider deprecation warnings
- external-user sessions: 0
- Owner Acceptance started
- Skill installation passed
- continuing in the installation conversation passed without a restart
- the one-action/one-confirmation conversation mechanism passed
- Owner Acceptance is blocked by current Notion data source schema
  compatibility and local secure-input feedback issues

Phase 4.1C is running in the owner's real Codex environment. The first
acceptance attempt confirmed Skill installation, immediate continuation in the
same conversation, and the reply-gated guidance mechanism. Real setup then
revealed that the current Notion UI uses “连接” in the developer dashboard and
“集成” on a normal page, while the local setup used an obsolete database
creation payload. Four database containers were created but their data source
fields and relations were incomplete. Their saved identifiers must be reused;
they must not be deleted or recreated. External-user testing has not started.

The formal user flow continues in the current conversation after installation.
A new conversation is not mandatory, and restarting Codex is only the second
Skill-refresh fallback. The user does not need to memorize commands, locate the
project directory, type `cd`, create `.venv`, or run the primary workflow.

Codex locates or safely acquires the complete project and advances onboarding
one visible action at a time. The user confirms each Notion action before
Codex proceeds. Only after the user confirms the page link is copied may Codex
prepare the local runtime and start the safe setup tool. The user enters the
hidden token and complete page URL only in the local window.

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

- Notion first-time setup is a P1 Owner Acceptance blocker because the current
  SDK data source creation contract differs from the legacy top-level
  `properties` request.
- Existing empty database containers require an idempotent in-place schema
  reconciliation path that preserves their identifiers and unknown fields.
- Relation properties must use `data_source_id` with `single_property`.
- The local safe-input window must confirm both hidden inputs without exposing
  the token, page URL, page ID, or database IDs.
- The merged artifact handoff has not yet been exercised in the owner's full
  learning journey.
- External-user session count remains 0.
- Learning-asset usefulness has not been validated with external users.

## Historical Milestones

### Phase 3 — Product Stabilization / Post v1.1

Phase 3 established the safe v1.1 release baseline, aligned documentation and
runtime contracts, protected private and generated artifacts, verified the
full regression suite, and completed the reviewed v1.1.0 release.

## Immediate Milestone

Fix and review the current Notion data source creation/reconciliation contract,
align the real “连接”/“集成” UI path, and improve the two-step hidden local
input. After the fix is merged, resume setup against the same saved four
database identifiers and the same Notion page. Do not start external-user
testing. External-user sessions remain 0.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md` and
`skill/SKILL.md` before changing runtime behavior.
