# Changelog

All notable product and architecture changes are recorded here. Historical
entries must be appended or clarified, not removed.

## Unreleased — Phase 4 Product Validation

### Phase 4.1C Owner Acceptance Closure

- Completed Setup / Notion workspace recovery and Target Binding validation.
- Passed Automated Podcast Owner Acceptance, including first publish and exact
  retry.
- Passed targeted Vocabulary Acceptance: first publish created 2 and exact
  retry created 0.
- Passed Weekly Reflection Acceptance: first publish created 1 and exact retry
  created 0.
- Confirmed 0 non-target database changes and 0 historical database group
  changes across acceptance.
- Recorded Owner Acceptance as `OWNER_ACCEPTANCE_PASS`.
- Accepted the core internal release as
  `OWNER_ACCEPTED_CORE_INTERNAL_RELEASE_WITH_NON_BLOCKING_ISSUES`.
- External-user sessions: 0.
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`.
- Kept Architecture stable; no Architecture Review is required for closure.
- Merged PR #16 so future Expression Database creation assigns semantic colors
  to existing Category, Commonness, and Review Status option names.
- Preserved existing databases without automatic color rewrites. Existing
  option colors may be changed manually in the Notion UI only; options must not
  be deleted, recreated, or renamed.
- Moved Podcast and Weekly TOCs, the parent-page usage guide, improved Skill
  `同步生词` interaction, full-scan highlight state namespacing, and existing
  Expression Database manual color adjustment into a separate non-blocking
  backlog.
- Kept the Notion AI-assisted workflow and Podcast-page Expression
  synchronization cancelled and outside the roadmap.
- Entered Phase 4.2 External User Validation with a target of 3 real sessions,
  at least 2 unassisted core-flow completions, time-to-first-value measurement,
  and evidence-based tracking of confusion, failures, and recovery.

### Phase 4.1C Podcast Acceptance and Vocabulary Handoff

This subsection records an intermediate Phase 4.1C checkpoint. The completed
acceptance state is recorded in the closure entry above.

- Merged PR #9 for partial Podcast/Expression publish recovery.
- Merged PR #10 for the protected Podcast Owner Acceptance Harness.
- Merged PR #11 for fail-closed Notion target-group binding.
- Merged PR #14 for the protected Vocabulary Acceptance Harness.
- Completed independent Harness review with all identified P0/P1 false-pass
  paths closed, including source identity, empty live runs, artifact mutation,
  and persisted-payload drift.
- Passed 19 targeted Harness tests and the complete regression with 569 tests;
  the 3 existing compatibility-provider deprecation warnings remain.
- Passed `compileall` and `git diff --check`.
- Made 0 real Notion calls and 0 real Notion writes during Harness
  implementation and review.
- Switched the five local target settings to the intended database group
  without changing the Notion token.
- Passed the read-only Target Binding Diagnosis.
- Passed protected Automated Podcast Owner Acceptance in the intended group:
  the first publish created 1 Podcast and 19 Expressions, and the exact retry
  created 0 Podcast and 0 Expressions.
- Preserved the historical database group and left Vocabulary Database and
  Weekly Review unchanged during Podcast acceptance.
- Recorded that Vocabulary was outside the Podcast acceptance scope and that
  Harness readiness is not Vocabulary workflow acceptance. The targeted
  Vocabulary dry-run, candidate and enrichment inspection, confirmed publish,
  data-quality inspection, exact retry, and Owner visual review remain
  pending. Vocabulary Acceptance is `NOT RUN`.
- Recorded that the full-scan highlight checkpoint and processed-highlight
  state are not currently scoped by target group.
- Recorded the Owner visual-review finding that Expression Database Select
  options lack semantic colors for Category, Commonness, and Review Status.
- Confirmed that Podcast body bolding, semantic highlights, Highlight Legend,
  and Highlighted Transcript are working and are not affected by the Select
  color defect.
- Added pending requirements for conversational `同步生词`, Podcast TOC,
  Weekly TOC, and the deferred parent-page usage guide.
- Cancelled the proposed Notion AI-assisted page workflow and Podcast-page
  Expression synchronization before implementation. Neither remains in the
  active roadmap.
- External-user sessions remain 0 and the product remains
  `NOT_READY_FOR_EXTERNAL_USERS`.

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
- Recorded an initial P1 guidance blocker: the first Notion instruction
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

### Phase 4.1C Notion Target Binding

- Confirmed two complete Notion database groups with identical visible names.
- Preserved the historical group, including one BE 598 Podcast and 19 related
  Expressions; no cleanup or migration was performed.
- Verified the intended `英语音频学习助手` group through read-only access:
  four unique databases, complete schemas, three internal single-property
  relations, no cross-group relations, and zero records.
- Added `NOTION_TARGET_PARENT_PAGE_ID` as the production write boundary.
- Added a shared validator for Data Source, database, direct parent, schema,
  and internal relation binding.
- Protected Podcast, Vocabulary, Weekly Reflection, legacy publisher, and
  example-data write paths before any mutation.
- Strengthened the Owner Acceptance Harness so binding validation precedes
  snapshots and publisher calls.
- Added a permanently read-only, redacted target-binding diagnosis CLI.
- Kept Owner Acceptance blocked and external-user sessions at 0 pending review,
  coordinated configuration switch, diagnosis PASS, and a new Podcast run.

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
- Hardened relation recovery so existing `dual_property` relations and
  relations with a different target stop without mutation.
- Added final semantic validation for all three relation targets and one-way
  relation modes.
- Added explicit Fake Notion evidence that schema reconciliation does not
  create, update, or delete page records.
- Removed Data Source IDs and other configuration values from developer CLI
  output and API failure summaries.
- Merged PR #7 with Create a merge commit
  (`68cf0db509600862c002c66659478522ff290e35`).
- Production verification completed with 453 passing tests and 3 expected
  compatibility-provider deprecation warnings.
- Completed protected real Notion in-place recovery with the existing four
  Data Source IDs.
- Created no new databases and preserved the parent page, existing records,
  unknown fields, and all four Data Source identities.
- Verified all required fields and three single-property relations.
- Advanced the setup state from `in_progress` to `complete`.
- Real recovery evidence was reviewed and accepted by the AI Tech Lead.
- Recovery result: PASS.
- PR #8 records the accepted recovery evidence.
- Merged PR #8 with Create a merge commit
  (`4e3ed60b1aeac9b4b43ef20302ae270a4e3dddf3`).
- Confirmed a P1 partial-publish recovery defect before the real Podcast
  journey: when Expression creation fails after the Podcast page is created,
  an exact retry updates the Podcast page but does not restore missing
  Expression pages.
- Paused the real podcast-to-Notion journey until the partial-publish recovery
  repair is reviewed and merged.
- Added pre-write Expression schema validation, three-field Expression
  identity checks, full reconciliation, duplicate-conflict stops, and
  retry-safe creation of only missing Expression pages.
- Verified the repair branch with 463 passing tests and 3 expected
  compatibility-provider deprecation warnings.
- Kept Owner Acceptance blocked pending the podcast-to-Notion journey.
- External-user sessions remain 0.

Owner Acceptance remains pending until the podcast-to-Notion journey is
completed.

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
