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

Phase 4.1C — Owner Acceptance

Status: `READY_FOR_OWNER_ACCEPTANCE`

External-user sessions: 0

## Goal

Verify the merged onboarding flow in the owner's real Codex and Notion
environment:

```text
Codex Skills UI installation
↓
Skill discovery
↓
Four-database Notion setup
↓
Complete learning flow
```

## Current Tasks

1. Install the Skill through the Codex Skills UI.
2. Restart Codex or open a new task.
3. Verify `$english-audio-learning-agent` discovery.
4. Create a disposable Notion parent page and share it with the integration.
5. Run `python -m src.notion.setup_workspace --parent-page-id "<id>"`.
6. Run `python -m src.notion.check_workspace`.
7. Complete one full supported audio-to-artifact-to-Notion learning flow.
8. Record results, failures, timing, and evidence.

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

- The Skill is installed through the documented Codex Skills UI path.
- `$english-audio-learning-agent` is discovered after restart or a new task.
- All four Notion databases are created and pass `check_workspace`.
- One complete supported learning flow publishes successfully to Notion.
- No real credentials are committed.
- Owner Acceptance results are recorded.
- No external-user readiness claim is made.

External-user validation remains a later activity and has not started.

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
