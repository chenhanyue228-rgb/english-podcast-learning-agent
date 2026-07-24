# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- Release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Production `main`: `b315f1fd4b08bf7ed0f9446b6cf31aec2f77d8ce`
- PR #9: merged
- PR #10: merged
- PR #11: merged
- Latest regression: 550 passed, 3 existing deprecation warnings
- Architecture: Stable

## Current Sprint

**Phase 4.1C — Vocabulary Acceptance and Owner Visual Review Closure**

Current status:

- Automated Podcast Owner Acceptance: PASS
- Vocabulary Acceptance: NOT RUN
- Owner visual review: CHANGES_REQUIRED
- External-user sessions: 0
- External-user readiness: `NOT READY_FOR_EXTERNAL_USERS`

## Completed Gates

- PR #9 partial Podcast/Expression publish recovery merged.
- PR #10 protected Owner Acceptance Harness merged.
- PR #11 Notion target binding merged.
- Five local target settings switched to the intended group.
- Notion token preserved.
- Read-only Target Binding Diagnosis passed.
- Protected Automated Podcast Owner Acceptance passed.
- First publish created 1 Podcast and 19 Expressions.
- Exact retry created 0 Podcast and 0 Expressions.
- Vocabulary and Weekly databases remained unchanged.
- Historical database group remained unchanged.

## Current Tasks

1. Run a targeted Vocabulary dry-run on the accepted BE 598 Podcast page.
2. Verify detected pink highlights and approved/rejected candidates.
3. Run targeted Vocabulary publish.
4. Run an exact retry and require zero new records.
5. Verify original word preservation, context, source relation, and status.
6. Determine whether a real Vocabulary core-script defect exists.
7. Namespace highlight state by target group.
8. Add the Skill `同步生词` interaction.
9. Fix semantic Select option colors for future database creation.
10. Document the manual live-database color adjustment.
11. Add the Podcast page table of contents.
12. Add the Weekly page table of contents.
13. Implement the final parent-page usage guide after the above behavior is
    stable.
14. Complete Owner visual review.

## Vocabulary Acceptance Rule

Podcast publishing and Vocabulary synchronization are separate workflows.
The Podcast acceptance intentionally did not write Vocabulary records.

An empty Vocabulary Database is not evidence of a broken sync script. Defect
classification requires:

```text
Targeted dry-run
↓
Targeted publish
↓
Exact retry
↓
Record and relation verification
```

The current full-scan highlight checkpoint and processed-highlight state are
global. They must be namespaced by target group so historical-group state
cannot suppress work in another group.

## Owner Visual Review Finding

Expression Database Select options currently lack semantic colors for:

- Category
- Commonness
- Review Status

Podcast body bolding, semantic highlights, Highlight Legend, and Highlighted
Transcript are working and are outside this defect.

## Presentation Enhancements

- New Podcast pages should begin with a navigable table of contents.
- New Weekly pages should begin with a navigable table of contents.
- Exact retries must not duplicate either TOC.
- Existing body contracts remain intact.
- Historical automatic backfill is not approved.
- The parent-page usage guide remains deferred until Vocabulary, TOC, and
  related instructions are stable.

## Cancelled Requirements

The following are not active requirements and require no Architecture Review:

- Notion AI-assisted page workflow;
- Podcast-page Expression synchronization into Expression Database.

They must not reappear in the active roadmap, blockers, or user guide.

## Out of Scope

- architecture redesign
- Notion schema redesign
- background daemon or infinite polling
- automatic Vocabulary discovery as the primary workflow
- YouTube support
- cloud hosting
- user accounts or payment
- historical TOC backfill
- external-user readiness claims

## Handoff

Read in this order:

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `CURRENT_TASK.md`
4. `skill/SKILL.md`
5. `docs/codex_skill_contract.md`
6. `DECISION_LOG.md`
