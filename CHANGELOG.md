# Changelog

All notable product and architecture changes are recorded here. Historical
entries must be appended or clarified, not removed.

## Unreleased — Phase 4 Product Validation

- Clean-clone onboarding validation.
- First-user journey measurement.
- External-user feedback collection.
- Evidence-based UX improvement planning.

These activities are planned validation work, not completed product changes.

## [v1.1.0] - 2026-07-22

### Release Finalization

- Release: v1.1.0
- Release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- 345 tests passed with 0 failures and 3 expected deprecation warnings.
- Clean-worktree verification passed.
- CLI help smoke check passed.
- Annotated tag `v1.1.0` was created and pushed.

### Added

- Pure Codex Artifact Runtime as the default production reasoning path.
- Structured request/output artifact contracts for Podcast Analysis,
  Vocabulary Enrichment, Reflection Analysis, and Weekly Review generation.
- Weekly Reflection intelligence flow using `WeeklyLearningContext`,
  `ReflectionContext`, quality validation, and final Notion publishing.
- Pipeline run metadata, dry-run support, failure tracking, and structured
  workflow logging.

### Changed

- Migrated the production AI runtime from direct OpenAI API dependency to the
  Codex Skill Runtime.
- Redesigned Weekly Reflection as a compounding learning note focused on
  mindset shifts, cross-content patterns, professional actions, and language
  growth.
- Standardized Notion publishing around deterministic identity and idempotent
  create/update behavior.
- Renamed the product definition to English Audio Learning Agent.
- Froze v1 supported inputs to Podcast episode URLs, Podcast RSS feeds, and
  local audio files.
- Confirmed the Vocabulary Database workflow as Human Highlight + AI
  Processing; automatic vocabulary discovery is not the primary product flow.
- Synchronized the canonical product, architecture, Skill, and release
  documentation for the v1.1 baseline.

### Removed from v1 Scope

- YouTube input support. Experimental implementation remains for possible
  future evaluation but is not part of the production contract.

### Validated

- Input compatibility for Podcast URL, RSS feed, and local audio.
- Notion page creation and repeat-run PATCH behavior.
- Pure Codex default runtime without an `OPENAI_API_KEY` requirement.
- Full regression suite after runtime and documentation alignment.
- Pre-finalization release-baseline regression result: 344 passed with 3
  expected deprecation warnings from explicitly selected OpenAI compatibility
  providers. Final release validation passed 345 tests as recorded above.

## Earlier v1 Milestones

- Implemented strict Podcast source resolution, streaming audio download,
  validation, Whisper transcription, and transcript persistence.
- Implemented Podcast Library and Expression Database publishing.
- Implemented user-driven vocabulary capture and Vocabulary Database upsert.
- Established the Codex/Python/Notion responsibility boundary.
