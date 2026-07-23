# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- v1.1.0 release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Production `main`: `60de7aab6fa4904a5b5576e351d28cc70ff672df`
- PR #5: merged
- Tests: 407 passed
- Architecture: Stable

## Current Sprint

Phase 4.1C — Owner Acceptance

Status: `OWNER_ACCEPTANCE_BLOCKED`

External-user sessions: 0

## Goal

Fix the P1 Notion first-time guidance blocker discovered during Owner
Acceptance, then restart the acceptance flow from the post-install handoff.

```text
One understandable Notion action
↓
User confirmation
↓
Next understandable Notion action
↓
Safe local setup
↓
Codex-operated podcast-to-Notion flow
```

## Current Tasks

1. Make `skill/SKILL.md` the canonical user-visible Notion conversation.
2. Require the `已有` path to wait for `已打开 Notion`, `页面已创建`,
   `连接已添加`, and `链接已复制` in order.
3. Require the `没有` path to wait for `开发者页面已打开`, `连接已创建`,
   and `密钥已保存` before the page flow.
4. Prevent local setup from starting before `链接已复制`.
5. Remove internal acceptance terminology from normal-user instructions.
6. Add recovery copy for a missing Notion connection menu.
7. Add sequence, reply-gate, forbidden-copy, and launch-timing tests.
8. Review and merge the focused fix.
9. Reinstall the Skill from the latest `main`.
10. Restart Owner Acceptance without starting external-user testing.

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
- Resumed setup safely stops before any operation if the parent page differs.
- Relations and schema validation pass before setup is marked complete.
- Codex actively prompts for a podcast after setup.
- Codex operates the podcast-to-Notion workflow.
- No unresolved P0 or P1 onboarding blocker remains in the implementation.
- No real credentials are committed.
- No external-user readiness claim is made.

Owner Acceptance started and is blocked before real Notion setup. External-user
validation has not started.

## Current State

- PR #5 is merged.
- Skill installation passed in the owner's real Codex environment.
- The installation conversation discovered the Skill on the next turn without
  a new conversation or restart.
- The first Notion instruction exposed a P1 usability blocker.
- No real Notion setup or database creation was attempted.
- The safe first-time setup tool and its interruption recovery are implemented.
- Safe per-database setup recovery and dependency verification are implemented.
- Parent-page consistency protection is implemented for setup recovery.
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
