# Phase 4.1 Clean-Clone Issue Log

## Audit Boundary

This log comes from a technical agent audit of a clean remote clone. It is not
an external-user session. No real token, database ID, personal audio,
transcript, or Notion content was used.

## Summary

- P0: 0
- P1: 2
- P2: 3
- P3: 4
- Total: 9
- Highest severity: P1 — the documented journey does not independently connect
  a clean clone to an installed Codex Skill and configured Notion workspace

## Confirmed Issues

### PV-001 — Codex Skill installation has no executable onboarding step

- Journey step: Install Skill
- Observation: README installs Python dependencies but never explains how the
  repository's `skill/SKILL.md` becomes discoverable by Codex.
- Evidence: `skill/SKILL.md` says "Install the Skill" without a command,
  location, or verification step. The bootstrap script installs only Python
  dependencies.
- Expected behavior: A new user has a copyable install command and a command or
  interaction that confirms Codex discovered the Skill.
- Actual behavior: The user reaches a working Python environment but cannot
  independently establish the Codex reasoning runtime from documented steps.
- Severity: P1
- Confidence: CONFIRMED
- User impact: The core Codex artifact-generation journey cannot be completed
  without repository knowledge or project-author guidance.
- Workaround: Manual Skill registration by a knowledgeable Codex user; no
  verified workaround is documented in the repository.
- Likely fix area: README onboarding and Skill installation packaging.
- Recommended next action: Define and validate one supported Skill installation
  path and discovery check.

### PV-002 — Notion workspace setup is not discoverable and its guide is stale

- Journey step: Configure Notion
- Observation: README lists a token, parent page, and database IDs but does not
  link to workspace setup or show the setup command.
- Evidence: `src.notion.setup_workspace --print-onboarding` is actionable but
  undiscoverable from README. `docs/Notion_Onboarding.md` describes three
  databases while implementation and `.env.example` use four, including
  Vocabulary Database.
- Expected behavior: The entry journey explains integration creation, page
  sharing, four-database setup, ID persistence, and validation.
- Actual behavior: A new user is told to fill IDs they do not yet have, and the
  unlinked detailed guide describes an outdated database count.
- Severity: P1
- Confidence: CONFIRMED
- User impact: The first Notion learning page cannot be reached independently.
- Workaround: Discover and run `python -m src.notion.setup_workspace
  --print-onboarding`, then use `--parent-page-id`; this workaround was not
  executed against Notion during the audit.
- Likely fix area: README and `docs/Notion_Onboarding.md`.
- Recommended next action: Make the current four-database onboarding path the
  single linked setup sequence.

### PV-003 — Virtual-environment isolation is undocumented

- Journey step: Install dependencies
- Observation: README invokes bootstrap with `python3` directly.
- Evidence: The bootstrap script installs into `sys.executable` and does not
  create a venv or warn when running under system Python. The audit added
  `python3 -m venv .venv` before bootstrap.
- Expected behavior: Installation is isolated by default or the documentation
  explicitly creates and uses a project venv.
- Actual behavior: A literal first run may install into system/user Python or
  fail due to permissions and environment policy.
- Severity: P2
- Confidence: CONFIRMED
- User impact: The journey requires an undocumented safety workaround and may
  create dependency conflicts.
- Workaround: Create `.venv` and invoke bootstrap through
  `./.venv/bin/python`.
- Likely fix area: README and bootstrap diagnostics.
- Recommended next action: Document and validate the isolated command sequence.

### PV-004 — Podcast Analysis artifact handoff is not self-explanatory

- Journey step: Codex artifact generation
- Observation: Transcript-only request creation succeeds, but CLI output prints
  only the request path.
- Evidence: The synthetic run printed
  `data/analysis_requests/clean_clone_onboarding_test.json`; it did not name the
  expected output path or exact rerun command.
- Expected behavior: CLI reports the request, expected output, Codex action,
  validation boundary, and next command.
- Actual behavior: A user must infer the output basename and combine README and
  Skill contract placeholders.
- Severity: P2
- Confidence: CONFIRMED
- User impact: The core journey pauses at the Codex/Python boundary without an
  obvious recovery action.
- Workaround: Save schema-conformant output to the matching `data/analysis/`
  filename and rerun with both `--transcript-json` and `--analysis-json`.
- Likely fix area: Podcast request CLI reporting and onboarding examples.
- Recommended next action: Print the exact expected output path and rerun
  command when returning an analysis request.

### PV-005 — Podcast page URL support is narrower than entry wording

- Journey step: Select input
- Observation: README says "Podcast episode URL" without naming supported page
  platforms.
- Evidence: The public router accepts Apple Podcast page URLs, RSS URLs, direct
  audio URLs, and local audio paths. It rejects generic non-Apple platform
  pages.
- Expected behavior: Supported page-URL platforms are explicit before a user
  starts processing.
- Actual behavior: A user may reasonably supply another podcast platform URL
  and encounter an unsupported-source error.
- Severity: P2
- Confidence: CONFIRMED
- User impact: The user needs a workaround such as RSS, Apple Podcasts, or local
  audio after an avoidable failed first attempt.
- Workaround: Use an Apple Podcast episode URL, Podcast RSS URL, direct audio,
  or local audio file.
- Likely fix area: README and Skill supported-input wording.
- Recommended next action: Name Apple Podcast page URLs explicitly and retain
  RSS/local alternatives.

### PV-006 — Supported Python version is not documented

- Journey step: Prepare environment
- Observation: No minimum, maximum, or tested Python version is stated.
- Evidence: Python 3.9.6 successfully bootstrapped and passed all 345 tests in
  this audit, but that compatibility must be inferred.
- Expected behavior: Entry documentation states the tested Python range.
- Actual behavior: Users cannot determine compatibility before installation.
- Severity: P3
- Confidence: CONFIRMED omission; cross-version impact is SUSPECTED
- User impact: Potential avoidable setup attempts on unsupported runtimes.
- Workaround: Use Python 3.9.6, the version verified in this audit.
- Likely fix area: README prerequisites.
- Recommended next action: Establish the tested range before documenting it.

### PV-007 — Bootstrap installs an out-of-scope YouTube dependency

- Journey step: Install dependencies
- Observation: `yt-dlp` is installed in every default bootstrap.
- Evidence: `requirements.txt` contains `yt-dlp>=2025.10.14` and bootstrap
  installed it, while v1 documentation excludes YouTube.
- Expected behavior: Core installation contains only dependencies needed by
  supported v1 workflows, or experimental extras are clearly separated.
- Actual behavior: A platform-specific experimental dependency is installed
  for all users.
- Severity: P3
- Confidence: CONFIRMED
- User impact: Additional download size and product-scope confusion; no runtime
  failure was observed.
- Workaround: None needed for successful setup.
- Likely fix area: Future dependency packaging decision.
- Recommended next action: Evaluate separating experimental dependencies after
  onboarding blockers are resolved.

### PV-008 — Linked status documents contain stale release state

- Journey step: Understand current project state
- Observation: README links documents that still describe pre-release work.
- Evidence: `docs/current_architecture.md` reports 344 tests and release
  baseline work; `docs/next_steps.md` asks for review before push/tag even
  though v1.1.0 is released and 345 tests are verified.
- Expected behavior: Linked current-state documents agree with the canonical
  Phase 4 baseline.
- Actual behavior: A new user sees contradictory release status.
- Severity: P3
- Confidence: CONFIRMED
- User impact: Non-blocking confusion about maturity and next actions.
- Workaround: Treat `PROJECT_CONTEXT.md` and `CURRENT_TASK.md` as current.
- Likely fix area: Linked current architecture and next-steps documents.
- Recommended next action: Correct only current-state sections in a later
  evidence-backed documentation fix.

### PV-009 — CLI diagnostics expose a noisy and incomplete onboarding surface

- Journey step: Diagnose configuration and choose a command
- Observation: `--help` mixes primary, legacy, and debug commands;
  `--print-config` reports only the Podcast database ID among four required
  database IDs.
- Evidence: Help includes an experimental YouTube source-type option and legacy
  comment commands. The transcript JSON help implies it is useful only with an
  analysis JSON, although request-only transcript reuse works.
- Expected behavior: First-use commands and all required configuration states
  are easy to distinguish from compatibility/debug surfaces.
- Actual behavior: Diagnostics are safe but require prior architecture
  knowledge to interpret completely.
- Severity: P3
- Confidence: CONFIRMED
- User impact: Non-blocking command-selection and recovery confusion.
- Workaround: Use README/Skill primary commands and
  `src.notion.check_workspace` for complete Notion validation.
- Likely fix area: CLI help grouping and non-secret config reporting.
- Recommended next action: Improve visibility without changing command
  compatibility.

## Suspected Risks

- Notion permissions, API behavior, and database creation remain unverified in
  a disposable external workspace.
- The setup implementation creates four databases, but real Data Sources API
  behavior was intentionally not exercised.
- A Python version outside 3.9.6 may expose dependency compatibility issues.
- A real Codex installation may have additional discovery or permission steps
  not represented in this repository.

## Untested External-Service Steps

- Notion integration creation
- Notion page sharing and permissions
- Notion workspace/database creation
- Notion schema validation against real data sources
- Podcast/RSS resolution and download
- audio conversion and validation
- Whisper model download and transcription
- Codex generation of Podcast Analysis JSON
- final Podcast Library and Expression Database publish
- real pink-highlight Vocabulary read and upsert
- Weekly Reflection generation and Notion publish with real user data

These are recorded as `NOT_TESTABLE_WITHOUT_EXTERNAL_CREDENTIALS` or excluded
network operations, not as successful validations.

## Recommended Fix Order

1. P1: Define the executable Codex Skill installation and discovery path.
2. P1: Link and correct one four-database Notion onboarding sequence.
3. P2: Make isolated Python setup the documented default.
4. P2: Print an explicit Podcast Analysis artifact handoff and rerun command.
5. P2: Clarify Apple Podcast page URL versus general RSS/local inputs.
6. P3: Align linked status documents and diagnostics.
7. P3: Evaluate Python-version declaration and experimental dependency split.
