# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- Main commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Tests: 345 passed
- Architecture: Stable

## Current Sprint

Phase 4.1 — Clean-Clone Onboarding Validation

## Goal

Determine whether a new user can independently complete:

```text
Repository access
↓
Environment setup
↓
Notion setup
↓
First audio input
↓
Codex artifact generation
↓
Notion learning-page publishing
```

## Current Tasks

1. Test installation from a clean clone.
2. Record every undocumented dependency or manual step.
3. Validate Notion workspace setup.
4. Validate the first Podcast or Local Audio journey.
5. Measure time to the first successful Notion learning page.
6. Create a first-user issue log.
7. Prioritize only evidence-backed UX fixes.

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

- A clean clone can bootstrap successfully.
- First-use instructions match actual behavior.
- No real credentials are committed.
- At least three external users are tested.
- At least two users complete the core flow without developer intervention.
- No unresolved P0 or P1 usability blocker remains.
- Findings are recorded before the next feature sprint.

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
