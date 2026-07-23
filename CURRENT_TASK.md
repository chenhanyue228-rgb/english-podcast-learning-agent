# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- v1.1.0 release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Production `main`: `4e3ed60b1aeac9b4b43ef20302ae270a4e3dddf3`
- PR #7: merged with Create a merge commit
- PR #8: merged with Create a merge commit
- Production verification: 453 passed, 3 expected warnings
- Architecture: Stable

## Current Sprint

Phase 4.1C — Owner Acceptance

Status: `OWNER_ACCEPTANCE_BLOCKED`

External-user sessions: 0

## Goal

Fix partial Podcast publishing recovery before starting the protected real
podcast-to-Notion Owner Acceptance journey.

```text
PR #8 merged
↓
Repair partial Podcast / Expression publishing recovery
↓
Review and merge the repair
↓
Resume the protected podcast-to-Notion journey
```

## Current Tasks

1. Make Expression schema validation complete before any Podcast page write.
2. Reconcile existing and missing Expression pages on every complete Podcast
   publish.
3. Make partial Expression creation safely recoverable without duplicate
   Podcast or Expression pages.
4. Keep the existing four Data Source IDs and parent page unchanged.
5. Keep the real podcast-to-Notion Owner Acceptance journey paused until this
   P1 repair is reviewed and merged.
6. Keep Vocabulary and Weekly Review outside the podcast write unless the
   accepted workflow explicitly requires them.
7. Keep external-user testing paused.

## Out of Scope

- new major features
- architecture redesign
- YouTube support
- cloud hosting
- user accounts
- payment
- Web UI
- automatic Vocabulary discovery
- Weekly Reflection redesign

## Completion Criteria

- The current conversation can continue directly after installation.
- A new conversation is not mandatory.
- The user does not need to memorize an instruction.
- The user does not locate the project directory or type `cd`.
- The token and complete page URL are entered in a local safe interface.
- Codex prepares the runtime and starts the setup flow.
- Codex and Python create only missing databases and reconcile existing data
  source fields in place.
- Interrupted setup resumes from saved database IDs without creating duplicates.
- Existing database IDs are checked before reuse.
- Resumed setup safely stops before any operation if the parent page differs.
- Existing unknown fields and records are preserved.
- Type conflicts stop safely without deleting properties.
- Relations use `data_source_id` and `single_property`.
- Relations and schema validation pass before setup is marked complete.
- Codex actively prompts for a podcast after setup.
- Codex operates the podcast-to-Notion workflow.
- No unresolved P0 or P1 onboarding blocker remains in the implementation.
- No real credentials are committed.
- No external-user readiness claim is made.

Owner Acceptance started and reached real first-time setup. Skill installation,
Skill discovery, and the reply-gated guidance mechanism passed. Real setup
created four database containers and saved all four Data Source IDs. Field and
Relation recovery passed with the original Data Sources and no new database.
The podcast-to-Notion journey has not started. External-user validation has
not started.

## Current State

- PR #5 is merged.
- Skill installation passed in the owner's real Codex environment.
- The installation conversation discovered the Skill on the next turn without
  a new conversation or restart.
- The reply-gated Notion conversation mechanism passed Owner Acceptance.
- Real setup created four database containers and saved their identifiers.
- PR #7 is merged into production `main`.
- Real Notion in-place recovery passed with the existing four Data Sources.
- New databases created: 0.
- Required fields and all three single-property relations passed validation.
- Unknown fields and existing records were preserved.
- Setup state is `complete`.
- Real recovery evidence was reviewed and accepted by the AI Tech Lead.
- PR #8 was merged with merge commit
  `4e3ed60b1aeac9b4b43ef20302ae270a4e3dddf3`.
- A new P1 was confirmed: a retry after partial Expression publishing updates
  the existing Podcast page but does not restore missing Expression pages.
- The P1 repair is implemented on
  `fix/phase-4.1c-podcast-partial-publish-recovery` and awaits review and merge.
- The real podcast-to-Notion journey is paused until the P1 repair is reviewed
  and merged.
- The next uncompleted Owner Acceptance gate remains the podcast-to-Notion
  journey.
- The existing databases must not be deleted or recreated.
- The safe first-time setup tool and its interruption recovery are implemented.
- Safe per-database setup recovery and dependency verification are implemented.
- Parent-page consistency protection is implemented for setup recovery.
- The real Notion UI terminology requires “连接” in the developer dashboard
  and “集成” on the learning page.
- The Notion plugin is documented as optional and outside the production write path.
- Owner Acceptance is `OWNER_ACCEPTANCE_BLOCKED`.
- External-user sessions: 0.

## Completed Phase 4.1 Milestones

- Phase 4.1 clean-clone technical audit
- Phase 4.1B onboarding fixes for PV-001 through PV-005
- Codex Skills UI installation contract
- four-database Notion onboarding flow
- isolated `.venv` setup
- complete Codex artifact handoff output
- Apple Podcasts episode URL scope clarification
- PR #4 merge into production `main`
- merged-main regression verification: 351 passed, 3 expected warnings

## Completed Phase 3 Milestones

- Pure Codex Runtime migration
- Weekly Reflection redesign and product acceptance
- Notion publishing stabilization and idempotent PATCH verification
- Podcast/RSS/Local Audio input validation
- Human Highlight + AI Processing vocabulary workflow
- Input scope freeze
- Codex Skill and artifact contract documentation
- stabilization and release-baseline audits
- documentation consistency review
- v1.1.0 release verification: 345 tests, CLI smoke check, annotated tag

## Stable Product Boundary

```text
Human Highlight
↓
AI Processing
↓
Vocabulary Database
```

The user decides what is personally worth learning. AI enriches, structures,
and stores that selection; it must not automatically discover vocabulary as
the primary workflow.

## Next Decision

After Product Validation evidence is collected, choose one:

A. Continue improving Skill onboarding

B. Prioritize Learning Asset Reuse

C. Prepare a broader beta

D. Request an Architecture Decision

## Handoff

Read in this order:

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `CURRENT_TASK.md`
4. `docs/product_validation_plan.md`
5. `skill/SKILL.md`
6. `docs/codex_skill_contract.md`
7. `DECISION_LOG.md`
