# Current Task

## Phase

Phase 3 — Product Stabilization / Post v1.1

## Current Task

Create a safe, reviewable local v1.1 release baseline. Classify the accumulated
working tree, exclude private and generated files, organize completed work into
logical local commits, and prepare a human-review report. Do not push or tag.

## Completed

- Pure Codex Runtime migration
- Weekly Reflection redesign
- Notion publishing stabilization
- Podcast/RSS/Local Audio input validation
- Human Highlight + AI Processing vocabulary workflow
- Input scope freeze
- Codex Skill and artifact contract documentation
- Night stabilization audit
- Documentation consistency review
- 344-test regression verification

## Next Phase

Phase 4 — Product Validation

## Future Priorities

1. Skill UX validation
2. Product onboarding refinement
3. Learning asset reuse improvement

## Vocabulary Database Strategy

```text
Human Highlight
↓
AI Processing
↓
Vocabulary Database
↓
Future Review / Reuse
```

The user decides what is personally worth learning. AI enriches, structures,
and stores that selection; it must not automatically discover vocabulary as
the primary workflow.

## Stabilization Scope

- Classify source, tests, documentation, generated artifacts, local-only files,
  experimental code, and ambiguous files.
- Audit all commit candidates for secrets and personal learning data.
- Create logical local commits on the release-baseline branch.
- Keep runtime documentation aligned with the actual Codex Artifact Runtime.
- Identify duplicate or legacy modules without removing them prematurely.
- Preserve the accepted Podcast, Vocabulary, Weekly Reflection, and Notion
  behavior.
- Produce `docs/release_baseline_report.md` before any push or tag.

## Do Not Change During Stabilization

- Notion database schema
- Weekly Reflection output and page structure
- Codex artifact schemas
- Podcast Library page structure
- exact pink-highlight vocabulary capture behavior
- production provider defaults
- supported v1 input scope

## Definition of Done

- Repository status is understood and local artifacts are protected.
- Completed v1.1 work is represented by reviewable local commits.
- Documentation names one production runtime and one set of supported inputs.
- Remaining compatibility paths are labeled clearly.
- Full regression tests pass at the verified baseline.
- The release baseline report documents exclusions and review-required files.

## Handoff

Read in this order:

1. `PROJECT_CONTEXT.md`
2. `ARCHITECTURE.md`
3. `skill/SKILL.md`
4. `docs/codex_skill_contract.md`
5. `DECISION_LOG.md`
