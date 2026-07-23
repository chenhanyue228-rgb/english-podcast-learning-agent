# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- v1.1.0 release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Pre-PR #7 production baseline:
  `87b96d9f68ad65d3356943b1f8196eeea8f9f3ee`
- PR #6: merged
- Production baseline tests: 407 passed, 3 expected warnings
- Architecture: Stable

## PR #7 Merge Candidate

- PR #7 remediation implementation reviewed
- Branch: `fix/phase-4.1c-notion-api-and-setup-ux`
- Candidate verification: 453 passed, 3 expected warnings
- Review result: `READY_TO_MERGE`
- Existing four Data Source IDs must be reused
- Real Owner Acceptance remains pending
- External-user sessions: 0

## Current Sprint

Phase 4.1C — Owner Acceptance

Status: `OWNER_ACCEPTANCE_BLOCKED`

External-user sessions: 0

## Goal

Fix the P1 Notion data source field and relation compatibility blocker
discovered during Owner Acceptance, then resume setup against the already
created databases without creating duplicates.

```text
Saved data source IDs
↓
In-place schema reconciliation
↓
Single-property relations
↓
Full validation
↓
Resume Owner Acceptance
```

## Current Tasks

1. Pin the Notion SDK version verified for the current data source API.
2. Create database containers with `initial_data_source.properties`.
3. Persist and reuse returned `data_source_id` values.
4. Reconcile all four existing data source schemas in place.
5. Rename the sole title property without creating a second title.
6. Preserve unknown user properties and stop on type conflicts.
7. Configure Expression, Vocabulary, and Weekly Review relations with
   `single_property`.
8. Fix the database creation, validation, and reporting order.
9. Replace the `已有`/`没有` split with one guided connection path.
10. Distinguish developer-dashboard “连接” from page-level “集成”.
11. Hide both token and page-link input and confirm each is received.
12. Stop safely when an existing relation uses `dual_property` or points to a
    different data source.
13. Validate all three relation targets and one-way modes before setup can be
    marked complete.
14. Re-review and merge the fix before resuming real setup.

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
Relation recovery has not yet passed real acceptance, and the podcast-to-Notion
journey has not started. External-user validation has not started.

## Current State

- PR #5 is merged.
- Skill installation passed in the owner's real Codex environment.
- The installation conversation discovered the Skill on the next turn without
  a new conversation or restart.
- The reply-gated Notion conversation mechanism passed Owner Acceptance.
- Real setup created four database containers and saved their identifiers.
- The current API rejected legacy relation payloads and left data source
  fields incomplete.
- The existing databases must be repaired in place; they must not be deleted
  or recreated.
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
