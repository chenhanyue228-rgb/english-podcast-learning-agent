# Changelog

All notable product and architecture changes are recorded here. Historical
entries must be appended or clarified, not removed.

## Unreleased — Phase 4 Product Validation

### Phase 4.1B Onboarding Fixes

- Merged PR #4 with evidence-backed fixes for PV-001 through PV-005.
- Added valid Codex Skill manifest frontmatter and discovery regression
  coverage.
- Defined the Codex Skills UI as the primary user installation path while
  retaining symbolic-link setup as Developer-only.
- Standardized onboarding around an isolated project `.venv`.
- Unified Notion onboarding around one setup command that creates Podcast
  Library, Expression Database, Weekly Review, and Vocabulary Database.
- Preserved Weekly Review as the database container for Weekly Reflection
  content.
- Improved Podcast Analysis artifact handoff output with request path, expected
  output path, canonical `$english-audio-learning-agent` instruction, and exact
  rerun command.
- Clarified supported Apple Podcasts episode URL input.
- Verified merged `main`: 351 tests passed with 0 failures and 3 expected
  compatibility-provider deprecation warnings.

### Phase 4.1C Owner Acceptance

- Started Owner Acceptance from a clean clone of merge commit
  `60de7aab6fa4904a5b5576e351d28cc70ff672df`.
- Verified Skill installation and same-conversation continuation without a new
  conversation or Codex restart.
- Recorded a P1 blocker before real Notion setup: the first Notion instruction
  combined multiple actions and used internal acceptance terminology that a
  normal user could not independently follow.
- Changed the Notion first-time conversation to one action and one confirmation
  at a time.
- Added complete `已有` and `没有` connection paths with explicit reply gates.
- Removed internal test terminology from normal-user guidance.
- Added regression coverage for conversation order, forbidden copy, reply
  gates, and the local-setup launch boundary.
- Kept Owner Acceptance blocked and external-user sessions at 0 until this fix
  is reviewed, merged, and reinstalled.
- Made first-time Notion database creation resumable with per-database
  progress persistence and safe retry.
- Bound resumed setup to the original Notion parent page so missing databases
  cannot be created under a different page.
- Verified the parent-page consistency closure with 407 passing tests and 3
  expected compatibility-provider deprecation warnings.
- Added existing-database access checks and mandatory relation rewiring before
  setup completion.
- Made the macOS setup entry verify the complete project dependency set.
- Clarified that the Codex Notion plugin is optional and is not a second
  authentication, setup, or write path.
- Added a complete Chinese user guide for installation, Notion authorization,
  first-time setup, daily use, and recovery.
- Made the current conversation the primary continuation after installation.
- Limited new-conversation and restart guidance to Skill-refresh fallbacks.
- Added the full user-path and runtime-path comparison table.
- Added automatic project location and safe acquisition rules for Codex.
- Added one macOS first-time setup entry.
- Added hidden Notion token input and complete parent-page URL support.
- Removed the normal-user requirement to locate a project directory, type
  `cd`, edit `.env`, create `.venv`, run primary commands, or extract a page
  ID manually.
- Added automatic four-database creation/validation and partial-configuration
  duplicate protection.
- Added the post-setup prompt for the user's first podcast.
- Added first-time setup and Skill onboarding contract regression tests.
- Verified the resumable setup closure with 401 passing tests and 3 expected
  compatibility-provider deprecation warnings.
- Prepared Owner Acceptance with status `READY_FOR_ONBOARDING_PR`.
- External-user testing has not started; external-user session count remains 0.

### Phase 4.1C Notion API and Setup Remediation

- Recorded the real Owner Acceptance finding that Notion's current UI uses
  “连接” in the developer dashboard and “集成” on a normal page.
- Replaced the `已有`/`没有` preclassification with one guided connection
  path.
- Migrated database creation to
  `initial_data_source.properties` for the current Notion data source API.
- Pinned `notion-client` to the locally verified `3.1.0` release.
- Added idempotent in-place schema reconciliation for saved data source IDs.
- Preserved unknown fields and existing records, and added safe stops for
  property type conflicts.
- Fixed all three workspace relations to use `data_source_id` with
  `single_property`.
- Changed both token and page-link collection to hidden local input with
  immediate non-sensitive receipt confirmation.
- Fixed the formal database order to Podcast Library, Expression Database,
  Vocabulary Database, and Weekly Review.
- Verified the remediation with 440 passing tests and 3 expected
  compatibility-provider deprecation warnings.
- Kept Owner Acceptance blocked and external-user sessions at 0 pending review
  and merge of this remediation.

Owner Acceptance resumes only after this remediation is reviewed, merged, and
installed from the latest `main`.

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
