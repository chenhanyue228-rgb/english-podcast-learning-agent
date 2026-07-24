# Current Task

## Phase

Phase 4 — Product Validation

## Stable Baseline

- Release: v1.1.0
- Release commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Production `main`: `987c7aa95f68b07b2a258b65166584f468425047`
- PR #9: merged
- PR #10: merged
- PR #11: merged
- PR #14 Vocabulary Acceptance Harness: merged
- Harness targeted tests: 19 passed
- Latest regression: 569 passed, 3 existing deprecation warnings
- `compileall`: PASS
- `git diff --check`: PASS
- Architecture: Stable

## Current Sprint

**Phase 4.1C — Owner Acceptance**

Current status:

- Automated Podcast Owner Acceptance: PASS
- Vocabulary Acceptance Harness: MERGED
- Vocabulary Acceptance: NOT RUN
- Owner visual review: NOT COMPLETE
- External-user sessions: 0
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`

`NOT_READY_FOR_EXTERNAL_USERS` is the canonical readiness token. Do not use a
space-separated variant in active project status.

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
- PR #14 protected Vocabulary Acceptance Harness merged after independent
  review closed all identified P0/P1 false-pass paths.
- Harness validation passed: 19 targeted tests, 569 full regression tests,
  `compileall`, and `git diff --check`.
- Harness development made 0 real Notion calls and 0 real Notion writes.

## Current Tasks

1. From a clean latest-main acceptance worktree, run the protected targeted
   Vocabulary dry-run on the accepted BE 598 Podcast page.
2. Inspect exact pink highlights, approved/rejected candidates, enrichment,
   and planned writes.
3. Obtain exact human confirmation before any real write.
4. Run targeted Vocabulary publish.
5. Inspect original word preservation, context, source relation, status, and
   other Vocabulary data quality.
6. Run an exact retry and require zero new records.
7. Make the Vocabulary acceptance decision.
8. Determine whether a real Vocabulary core-script defect exists.
9. Namespace highlight state by target group.
10. Add the Skill `同步生词` interaction.
11. Fix semantic Select option colors for future database creation.
12. Document the manual live-database color adjustment.
13. Add the Podcast page table of contents.
14. Add the Weekly page table of contents.
15. Implement the final parent-page usage guide after the above behavior is
    stable.
16. Complete Owner visual review.

## Vocabulary Acceptance Rule

Podcast publishing and Vocabulary synchronization are separate workflows.
The Podcast acceptance intentionally did not write Vocabulary records.

The merged Harness is a protected acceptance boundary around the existing
Vocabulary workflow. Its tests and independent review prove the Harness can
fail closed; they do not prove that real Vocabulary Acceptance has passed.

An empty Vocabulary Database is not evidence of a broken sync script. Defect
classification requires:

```text
Targeted dry-run
↓
Candidate and enrichment inspection
↓
Exact human confirmation
↓
Targeted publish
↓
Data-quality inspection
↓
Exact retry
↓
Acceptance decision
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
