# Decision Log

This file records durable product and architecture decisions. New decisions
must be appended; previous records must not be removed.

## DEC-001: Use Codex as the Production Reasoning Runtime

- Date: 2026-07-22
- Status: Accepted

### Decision

Use Codex as the production reasoning runtime. Codex generates structured JSON
artifacts; Python validates and persists them.

### Reason

The product requires a ChatGPT/Codex subscription experience without requiring
users to create or fund a separate OpenAI API account.

### Architecture Impact

- Production workflows do not require `OPENAI_API_KEY`.
- Python remains deterministic and does not own AI reasoning.
- Direct OpenAI providers are deprecated compatibility paths only.
- Artifact schemas are stable contracts between Codex and Python.

## DEC-002: Remove YouTube from v1 Core Input Scope

- Date: 2026-07-22
- Status: Accepted

### Decision

Exclude YouTube from the supported v1 input scope. Supported inputs are Podcast
episode URLs, Podcast RSS feeds, and local audio files.

### Reason

YouTube creates external platform dependency, authentication and anti-bot
constraints, downloader maintenance, and operational variability outside the
core value of English audio learning.

### Consequences

- Product documentation must not advertise YouTube as supported.
- Existing YouTube implementation remains experimental and may be removed or
  revisited in a later product decision.
- Notion historical schema values are preserved for backward compatibility.

### Final Scope

- Podcast URL
- RSS Feed
- Local Audio

## DEC-003: Weekly Reflection Is a Compounding Learning Note

- Date: 2026-07-22
- Status: Accepted

### Decision

Define Weekly Reflection as a compounding learning note, not a weekly data
aggregation report or collection of podcast summaries.

### Reason

The product should create long-term learning value by capturing changes in
understanding, transferable insights, language growth, and concrete
professional applications.

### Consequences

- Reflection Analysis creates themes, mindset shifts, cross-content patterns,
  evidence, and professional actions.
- Weekly Review presents these signals without re-analyzing source material.
- The quality gate rejects summary leakage, generic actions, and empty language
  growth.
- Weekly Reflection schema and Notion presentation remain frozen during
  post-v1.1 stabilization.

## DEC-004: Vocabulary DB Uses Human Highlight + AI Processing

- Date: 2026-07-22
- Status: Accepted

### Decision

Use Human Highlight + AI Processing as the Vocabulary Database workflow.

```text
User Highlight
↓
Detection
↓
AI Enrichment
↓
Notion Vocabulary Database
```

### Reason

Users should decide which words or expressions are personally valuable. AI
should enrich, structure, and store the selected learning assets.

### Architecture Impact

- Vocabulary selection is owned by the user.
- AI enrichment runs only after an explicit user highlight.
- Python handles detection, validation, dedupe, and Notion persistence.
- Automatic vocabulary discovery must not become the primary workflow.

## DEC-005: Enter Phase 4 Product Validation After v1.1.0

- Date: 2026-07-22
- Status: Accepted

### Decision

After releasing and verifying v1.1.0, move the project from Product
Stabilization to Product Validation.

### Reason

The core technical workflows, architecture, documentation baseline, and tests
are stable. The main remaining uncertainty is whether new users can install,
understand, and obtain value from the product without developer assistance.

### Consequences

- Architecture remains frozen during initial validation.
- New feature development is not the default priority.
- Onboarding and first-user evidence take precedence.
- Product changes must be based on observed user problems.
- Major workflow or architecture changes still require explicit review.

### Exit Condition

Phase 4 ends only after external-user evidence supports the next product
direction.

## DEC-006: Use Codex Skills UI as the Primary Installation Path

- Date: 2026-07-23
- Status: Provisional (pending owner validation)

### Decision

Use the Codex Skills UI as the primary user-facing installation path. The user
opens Skills, chooses Create, uploads the local `skill/` directory, saves the
Skill, and restarts Codex or opens a new task before verifying
`$english-audio-learning-agent`.

The symbolic-link method under `~/.codex/skills/` remains a Developer-only
fallback and is not the default onboarding contract.

### Reason

The primary installation path must use the supported Codex product surface and
must not claim that an internal helper or filesystem copy proves end-to-end
product installation.

### Acceptance Condition

This decision becomes Accepted only after the owner completes installation and
discovery in the real Codex Skills UI. External-user validation is separate
and has not started.

## DEC-007: Preserve Weekly Review Database Naming

- Date: 2026-07-23
- Status: Accepted

### Decision

Keep `Weekly Review` as the Notion database container name. Store the
`Weekly Reflection` compounding learning note as its product content.

### Reason

This naming preserves the existing production database, relations, environment
compatibility, and idempotent publishing behavior without a schema migration.

### Consequences

- No live Notion database rename or migration is required.
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID` remains the canonical environment
  variable.
- `NOTION_WEEKLY_REVIEW_DATABASE_ID` remains a legacy compatibility alias.
