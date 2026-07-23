# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- v1.1.0 release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Production `main`: `e87d6e41c6b8d2a98a4ef1db43ed685a937ba4d2`
- PR #4: merged
- Tests: 351 passed
- Architecture: Stable

## Current Sprint

Phase 4.1C — Owner Acceptance Preparation

Status: `READY_FOR_ONBOARDING_PR`

External-user sessions: 0

## Goal

Complete and verify a first-time setup flow in which a normal user does not
need to locate the project directory, type `cd`, or run primary commands
manually.

```text
Installation handoff in the current conversation
↓
Guided Notion authorization
↓
Safe local setup
↓
Codex-operated podcast-to-Notion flow
```

## Current Tasks

1. Keep the current conversation as the primary post-install continuation.
2. Make a new conversation and restart fallback-only actions.
3. Add the Chinese user guide and complete path comparison.
4. Add secure local token and parent-page URL input.
5. Add the macOS one-click setup entry.
6. Let Codex locate the project and prepare the runtime.
7. Automatically create or validate all four Notion databases.
8. Let Codex actively prompt for the first podcast after setup.
9. Lock the onboarding contract with regression tests.
10. Make interrupted database creation safely resumable.
11. Prepare the branch for onboarding review without starting Owner Acceptance.

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
- The token and complete parent-page URL are entered in a local safe interface.
- Codex prepares the runtime and starts the setup flow.
- Codex and Python create and validate the four databases.
- Interrupted setup resumes from saved database IDs without creating duplicates.
- Existing database IDs are checked before reuse.
- Relations and schema validation pass before setup is marked complete.
- Codex actively prompts for a podcast after setup.
- Codex operates the podcast-to-Notion workflow.
- No unresolved P0 or P1 onboarding blocker remains in the implementation.
- No real credentials are committed.
- No external-user readiness claim is made.

Owner Acceptance and external-user validation have not started.

## Current State

- PR #4 is merged.
- The Phase 4.1C documentation branch exists.
- The user interaction contract is being completed.
- The safe first-time setup tool and its interruption recovery are implemented.
- Safe per-database setup recovery and dependency verification are implemented.
- The Notion plugin is documented as optional and outside the production write path.
- Owner Acceptance has not started.
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
