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
`80cbab01ea266e487a0359ddbec562959070d8a0`. Production `main` includes PR #8
through merge commit `4e3ed60b1aeac9b4b43ef20302ae270a4e3dddf3`.

Release status:

- v1.1.0 is released and tagged locally and remotely
- the production architecture and workflow boundaries are stable
- production workflows and CLI behavior are verified
- PR #4 merged the Phase 4.1B onboarding fixes into `main`
- PR #5 merged the guided first-time-use flow into `main`
- PR #6 merged the one-action/one-confirmation Notion guidance into `main`
- PR #7 merged the Notion API and setup remediation into `main`
- PR #8 merged the accepted real recovery evidence into `main`
- production verification: 453 tests passed with 3 expected
  compatibility-provider deprecation warnings
- real Notion in-place recovery: PASS
- the existing four Data Source IDs were reused
- new databases created: 0
- required fields and three single-property relations: PASS
- unknown fields and existing records preserved: PASS
- setup state: `complete`
- recovery evidence reviewed and accepted
- a P1 partial-publish recovery defect was found before the real
  podcast-to-Notion journey: retries did not restore missing Expression pages
- the repair is implemented on a dedicated review branch and is not yet in
  production `main`
- the real podcast-to-Notion journey is paused pending that repair
- external-user sessions: 0
- Owner Acceptance started
- Skill installation passed
- continuing in the installation conversation passed without a restart
- the one-action/one-confirmation conversation mechanism passed
- Owner Acceptance is blocked pending the remaining podcast-to-Notion
  end-to-end journey

Phase 4.1C is running in the owner's real Codex environment. The first
acceptance attempt confirmed Skill installation, immediate continuation in the
same conversation, and the reply-gated guidance mechanism. Real setup then
revealed that the current Notion UI uses “连接” in the developer dashboard and
“集成” on a normal page, while the local setup used an obsolete database
creation payload. Four database containers were created in the first attempt.
The protected in-place recovery reused them, completed their fields and
one-way relations, and preserved existing records and unknown fields. They
must not be deleted or recreated. External-user testing has not started.

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

Resolved during Phase 4.1C:

- legacy Database / Data Source API mismatch
- empty database schema reconciliation requirement
- relation `single_property` compatibility
- hidden input feedback issue
- final relation target and mode validation
- safe stop for existing `dual_property` relations

Current risks:

1. Partial Podcast publishing cannot yet recover missing Expression pages when
   a retry finds the Podcast page already exists.
2. The recovered production workspace has not yet completed a real
   podcast-to-Notion journey.
3. Real Podcast Library and Expression Database output has not yet been
   reviewed after recovery.
4. End-to-end retry and idempotency have not yet been verified in the
   recovered owner workspace.
5. External-user sessions remain 0.
6. Learning-asset usefulness has not been validated with external users.

## Historical Milestones

### Phase 3 — Product Stabilization / Post v1.1

Phase 3 established the safe v1.1 release baseline, aligned documentation and
runtime contracts, protected private and generated artifacts, verified the
full regression suite, and completed the reviewed v1.1.0 release.

## Immediate Milestone

- Repair and review partial Podcast / Expression publishing recovery.
- Keep the real podcast-to-Notion Owner Acceptance journey paused until the
  repair is merged.
- Then run one protected real podcast-to-Notion Owner Acceptance journey
  against the existing workspace.
- Review output quality, database placement, relation behavior, and
  idempotency.
- Do not start external-user testing.

Start with `CURRENT_TASK.md`, then consult `ARCHITECTURE.md` and
`skill/SKILL.md` before changing runtime behavior.
