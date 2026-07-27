# Decision Log

This file records durable product and architecture decisions. New decisions
must be appended; previous records must not be removed. Status statements
inside earlier decisions describe the project at the time of that decision;
later accepted decisions supersede them when the current state changes.

## DEC-001: Use Codex as the Production Reasoning Runtime

- Date: 2026-07-22
- Status: Accepted

### Decision

Use Codex as the production reasoning runtime. Codex generates structured JSON
artifacts; Python validates and persists them.

### Reason

The product requires a ChatGPT/Codex subscription experience without requiring
users to create or fund a separate OpenAI API account.

### Architecture Impact

- Production workflows do not require `OPENAI_API_KEY`.
- Python remains deterministic and does not own AI reasoning.
- Direct OpenAI providers are deprecated compatibility paths only.
- Artifact schemas are stable contracts between Codex and Python.

## DEC-002: Remove YouTube from v1 Core Input Scope

- Date: 2026-07-22
- Status: Accepted

### Decision

Exclude YouTube from the supported v1 input scope. Supported inputs are Podcast
episode URLs, Podcast RSS feeds, and local audio files.

### Reason

YouTube creates external platform dependency, authentication and anti-bot
constraints, downloader maintenance, and operational variability outside the
core value of English audio learning.

### Consequences

- Product documentation must not advertise YouTube as supported.
- Existing YouTube implementation remains experimental and may be removed or
  revisited in a later product decision.
- Notion historical schema values are preserved for backward compatibility.

### Final Scope

- Podcast URL
- RSS Feed
- Local Audio

## DEC-003: Weekly Reflection Is a Compounding Learning Note

- Date: 2026-07-22
- Status: Accepted

### Decision

Define Weekly Reflection as a compounding learning note, not a weekly data
aggregation report or collection of podcast summaries.

### Reason

The product should create long-term learning value by capturing changes in
understanding, transferable insights, language growth, and concrete
professional applications.

### Consequences

- Reflection Analysis creates themes, mindset shifts, cross-content patterns,
  evidence, and professional actions.
- Weekly Review presents these signals without re-analyzing source material.
- The quality gate rejects summary leakage, generic actions, and empty language
  growth.
- Weekly Reflection schema and Notion presentation remain frozen during
  post-v1.1 stabilization.

## DEC-004: Vocabulary DB Uses Human Highlight + AI Processing

- Date: 2026-07-22
- Status: Accepted

### Decision

Use Human Highlight + AI Processing as the Vocabulary Database workflow.

```text
User Highlight
↓
Detection
↓
AI Enrichment
↓
Notion Vocabulary Database
```

### Reason

Users should decide which words or expressions are personally valuable. AI
should enrich, structure, and store the selected learning assets.

### Architecture Impact

- Vocabulary selection is owned by the user.
- AI enrichment runs only after an explicit user highlight.
- Python handles detection, validation, dedupe, and Notion persistence.
- Automatic vocabulary discovery must not become the primary workflow.

## DEC-005: Enter Phase 4 Product Validation After v1.1.0

- Date: 2026-07-22
- Status: Accepted

### Decision

After releasing and verifying v1.1.0, move the project from Product
Stabilization to Product Validation.

### Reason

The core technical workflows, architecture, documentation baseline, and tests
are stable. The main remaining uncertainty is whether new users can install,
understand, and obtain value from the product without developer assistance.

### Consequences

- Architecture remains frozen during initial validation.
- New feature development is not the default priority.
- Onboarding and first-user evidence take precedence.
- Product changes must be based on observed user problems.
- Major workflow or architecture changes still require explicit review.

### Exit Condition

Phase 4 ends only after external-user evidence supports the next product
direction.

## DEC-006: Use Codex Skills UI as the Primary Installation Path

- Date: 2026-07-23
- Status: Provisional (pending owner validation)

### Decision

Use the Codex Skills UI as the primary user-facing installation path. The user
opens Skills, chooses Create, uploads the local `skill/` directory, saves the
Skill, and restarts Codex or opens a new task before verifying
`$english-audio-learning-agent`.

The symbolic-link method under `~/.codex/skills/` remains a Developer-only
fallback and is not the default onboarding contract.

### Reason

The primary installation path must use the supported Codex product surface and
must not claim that an internal helper or filesystem copy proves end-to-end
product installation.

### Acceptance Condition

This decision becomes Accepted only after the owner completes installation and
discovery in the real Codex Skills UI. External-user validation is separate
and has not started.

## DEC-007: Preserve Weekly Review Database Naming

- Date: 2026-07-23
- Status: Accepted

### Decision

Keep `Weekly Review` as the Notion database container name. Store the
`Weekly Reflection` compounding learning note as its product content.

### Reason

This naming preserves the existing production database, relations, environment
compatibility, and idempotent publishing behavior without a schema migration.

### Consequences

- No live Notion database rename or migration is required.
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID` remains the canonical environment
  variable.
- `NOTION_WEEKLY_REVIEW_DATABASE_ID` remains a legacy compatibility alias.

## DEC-008: Continue First-Time Setup in the Installation Conversation

- Date: 2026-07-23
- Status: 项目所有者验收阶段采用

### Decision

After installation, the installing Codex asks in the current conversation
whether the user wants to continue first-time setup. A new conversation is
only the first Skill-refresh fallback. Restarting Codex is the second fallback.

### Reason

Installation and setup should feel like one product journey. Requiring a new
conversation adds an unnecessary handoff and makes the user remember a command.

## DEC-009: Normal Users Do Not Locate the Project Directory

- Date: 2026-07-23
- Status: 项目所有者验收阶段采用

### Decision

Codex locates or safely acquires the complete project and operates the local
runtime. Normal users are not responsible for the project path, `cd`, `.venv`,
or primary terminal commands.

### Reason

These are execution details owned by Codex and Python, not learning tasks owned
by the user.

## DEC-010: Use One Safe First-Time Setup Entry

- Date: 2026-07-23
- Status: 采用

### Decision

Use one Codex-launched local setup flow for the Notion token and complete
parent-page URL. The token must not be accepted through chat, command
arguments, or plaintext shell commands.

### Reason

A single hidden-input path reduces configuration errors and keeps the secret
out of conversation history, process arguments, and logs.

## DEC-011: Short Instructions Trigger Complete User Flows

- Date: 2026-07-23
- Status: 项目所有者验收阶段采用

### Decision

First-time setup may be triggered with:

```text
请使用英语音频学习助手，带我完成第一次设置。
```

Podcast processing may be triggered with:

```text
请使用英语音频学习助手处理这个播客。
```

The detailed background sequence belongs to the Skill contract and is not
copied by the user.

### Reason

Users should express intent while Codex handles orchestration details.

## DEC-012: Use Step-by-Step Confirmation for Notion First-Time Setup

- Date: 2026-07-23
- Status: Superseded by DEC-015 after real Notion UI validation

### Decision

Normal users receive exactly one visible Notion action at a time. Codex waits
for the required completion reply before displaying the next action.

The canonical existing-connection sequence is:

```text
已打开 Notion
↓
页面已创建
↓
连接已添加
↓
链接已复制
```

Users without a connection first complete:

```text
开发者页面已打开
↓
连接已创建
↓
密钥已保存
```

Internal test and acceptance terminology must not override the canonical
user-visible copy in `skill/SKILL.md`.

### Reason

Phase 4.1C Owner Acceptance showed that a combined authorization instruction
required normal users to interpret internal concepts and decide whether a
technical setup state was complete. This is a P1 onboarding blocker.

### Consequences

- Codex owns conversation state and only advances after each reply gate.
- Local setup cannot start before `链接已复制`.
- Users do not send the token or page link in chat.
- Python, not the user, determines whether access and database validation
  succeed.
- Owner Acceptance remains blocked until the fix is merged and revalidated.

## DEC-013: Separate Notion Database Containers from Data Source Schemas

- Date: 2026-07-23
- Status: Accepted for Owner Acceptance remediation

### Decision

Treat a Notion Database as the page-level container and its Data Source as the
owner of properties and records. Create initial fields through
`initial_data_source.properties`, then retrieve and update fields through the
data source API.

### Reason

Owner Acceptance used `notion-client 3.1.0`, whose database-create endpoint
does not send legacy top-level `properties`. Mixing the old and current models
created empty database containers.

## DEC-014: Use One-Way Notion Relations

- Date: 2026-07-23
- Status: Accepted

### Decision

Expression Database `Source Podcast`, Vocabulary Database `Source`, and Weekly
Review `Podcasts` target the Podcast Library data source with:

```text
data_source_id + single_property
```

Do not send `database_id` or `dual_property`.

During recovery, an existing `dual_property` relation is a migration conflict,
not a repair candidate. Setup must stop without changing it. A relation that
points to a different Data Source must also stop without mutation. Final
workspace validation checks both the target and the one-way mode before setup
can be marked complete.

### Reason

The product needs one-way source traceability. A two-way relation would add
schema and product behavior that has not been approved.

## DEC-015: Use One Unified Notion Connection Path

- Date: 2026-07-23
- Status: Accepted for Owner Acceptance remediation

### Decision

Do not ask users to classify themselves as having or not having a connection.
Guide everyone through the developer dashboard connection list, where they
open an existing connection or create one in the same step.

Developer-dashboard UI uses “连接”. Normal Notion page authorization uses
“集成”.

### Reason

The real Notion UI exposes the same practical path for both users, and the
preclassification question added cognitive work without improving safety.

## DEC-016: Hide Both Local Setup Inputs

- Date: 2026-07-23
- Status: Accepted

### Decision

Collect both the Notion access token and the complete learning-page URL through
hidden local input. Display a numbered step before each input and a
non-sensitive receipt confirmation immediately after Enter.

### Reason

The access token is a secret, and the page URL contains a private identifier.
Neither value should appear in chat, terminal echo, screenshots, or detailed
error output.

## DEC-017: Fix the Workspace Database Order

- Date: 2026-07-23
- Status: Accepted

### Decision

Use one creation, validation, and reporting order:

1. Podcast Library
2. Expression Database
3. Vocabulary Database
4. Weekly Review

### Reason

The order follows the dependency graph: Podcast Library is the relation target,
Expression and Vocabulary are learning assets, and Weekly Review is the
downstream reflection container.

## DEC-018: Do Not Auto-Migrate Existing Two-Way Relations

- Date: 2026-07-23
- Status: Accepted for PR #7 safety hardening

### Decision

Do not silently convert an existing Notion `dual_property` relation into
`single_property`. Stop recovery before any relation update and require a
separate migration decision. Continue to repair only missing targets or missing
relation modes when no two-way relation exists.

### Reason

Changing a two-way relation can alter or remove its reverse property. That is a
data migration, not deterministic schema repair, and is outside the current
Owner Acceptance remediation.

## DEC-019: Run Vocabulary Acceptance Before Defect Classification

- Date: 2026-07-24
- Status: Accepted for Owner Acceptance

### Decision

Do not classify an empty Vocabulary Database after Podcast acceptance as proof
that the Vocabulary sync script is broken. Podcast publishing and Vocabulary
synchronization remain separate workflows.

Run, in order:

1. targeted Vocabulary dry-run;
2. targeted Vocabulary publish;
3. exact retry;
4. original-word, context, source-relation, and status verification.

### Reason

The protected Podcast acceptance intentionally wrote only Podcast and
Expression records. A core-script diagnosis requires evidence from the
Vocabulary workflow itself.

## DEC-020: Scope Highlight State by Target Group

- Date: 2026-07-24
- Status: Accepted for Phase 4.1C

### Decision

Namespace full-scan checkpoints and processed-highlight state by the configured
target group. State from a historical database group must not suppress
highlights in another group.

Do not add a background daemon or infinite polling loop.

### Reason

Highlight processing state is synchronization metadata. Its identity boundary
must match the Notion target binding boundary.

## DEC-021: Add Podcast and Weekly Page Tables of Contents

- Date: 2026-07-24
- Status: Accepted as a low-risk presentation enhancement

### Decision

New Podcast and Weekly pages should begin with a navigable table of contents.
Exact retry must not duplicate it, and existing page body contracts remain
intact.

Historical automatic backfill is deferred.

### Reason

Long learning pages need navigation, but adding TOCs must not change data
ownership, page identity, idempotency, or historical content without a
separate approval.

## DEC-022: Defer the Parent-Page Usage Guide

- Date: 2026-07-24
- Status: Accepted

### Decision

Add the complete parent-page usage guide only after Vocabulary acceptance,
Podcast and Weekly TOCs, and related user instructions are stable.

### Reason

Deferral avoids repeated live-page rewrites and prevents instructions from
describing behavior that is still being accepted.

## DEC-023: Cancel the Notion AI and Expression Synchronization Proposal

- Date: 2026-07-24
- Status: Cancelled before implementation

### Decision

Notion AI page assistance is not an active product requirement. Synchronizing
Podcast-page Expressions into Expression Database as a separate workflow is
also not an active product requirement.

No implementation, Architecture Review, blocker, roadmap item, or user-guide
commitment remains active for this proposal.

### Reason

The accepted product already has clear ownership boundaries: Codex produces
reasoning artifacts, Python validates and orchestrates, Podcast publishing
owns analyzed Expressions, and explicit pink-highlight sync owns Vocabulary.
The cancelled proposal added complexity without an accepted user need.

## DEC-024: Treat the Vocabulary Harness as an Acceptance Boundary

- Date: 2026-07-24
- Status: Accepted for Phase 4.1C

### Decision

Merge the protected Vocabulary Acceptance Harness only after independent
review closes all identified P0/P1 false-pass paths. The merged Harness wraps
the existing Vocabulary workflow; it does not introduce a new trigger,
enrichment path, publisher, schema, or state model.

Harness test and review success does not mean the real Vocabulary workflow has
passed acceptance. Vocabulary Acceptance remains `NOT RUN` until the targeted
dry-run, candidate and enrichment inspection, confirmed publish, data-quality
inspection, and exact retry have completed.

The real targeted dry-run remains gated by synchronization of the canonical
project documents with the merged production baseline. Any real Vocabulary
write still requires the exact human confirmation defined by the Harness.

### Reason

The Harness can prove that unsafe or ambiguous runs stop, but only the
protected real workflow can establish product acceptance and record quality.
Separating Harness readiness from workflow acceptance prevents a test result
from being reported as production evidence.

This intermediate gate was subsequently completed; DEC-025 records the final
Phase 4.1C acceptance state.

## DEC-025: Accept the Core Internal Release and Close Phase 4.1C

- Date: 2026-07-24
- Status: Accepted

### Decision

Close Phase 4.1C with:

- Owner Acceptance: `OWNER_ACCEPTANCE_PASS`;
- internal release:
  `OWNER_ACCEPTED_CORE_INTERNAL_RELEASE_WITH_NON_BLOCKING_ISSUES`;
- External-user sessions: 0;
- external readiness: `NOT_READY_FOR_EXTERNAL_USERS`;
- Architecture: Stable;
- Phase 4.1C Architecture Review: closed without further action.

The decision is supported by passing Setup recovery, Target Binding, Podcast,
targeted Vocabulary, and Weekly Reflection acceptance. Podcast first publish
and exact retry passed. Vocabulary first publish created 2 and exact retry
created 0. Weekly first publish created 1 and exact retry created 0.
Non-target database changes and historical database group changes were both 0.

### Reason

The protected core flows are reliable enough for internal release. External
readiness requires real external-user evidence and is a separate gate.

## DEC-026: Enter Phase 4.2 External User Validation

- Date: 2026-07-24
- Status: Accepted

### Decision

Phase 4.2 will:

1. complete 3 real external-user sessions;
2. require at least 2 users to finish the core flow without developer
   intervention;
3. record time-to-first-value;
4. record confusion, failed steps, and recovery outcomes;
5. avoid speculative large-scale refactoring before repeated evidence exists.

Podcast and Weekly TOCs remain accepted output contracts under DEC-021. The
parent-page usage guide, improved Skill `同步生词` interaction, full-scan
highlight state namespacing, and manual adjustment of existing Expression
Select colors remain a separate non-blocking backlog.

### Reason

The next product risk is user usability, not unverified architecture work.
Separating polish from the core journey keeps validation evidence interpretable.

## DEC-027: Apply Expression Select Colors Only to Future Creation

- Date: 2026-07-24
- Status: Accepted

### Decision

PR #16 adds semantic colors to Category, Commonness, and Review Status when a
future Expression Database is created. Existing option names remain unchanged.
Existing databases are not automatically rewritten and may still display gray
options.

Existing colors may be adjusted manually in the Notion UI only. Do not delete,
recreate, or rename existing options.

### Reason

The Notion API does not support safely rewriting the color of existing Select
options. Preserving option identity avoids data migration and compatibility
risk.

## DEC-028: Keep Cancelled Requirements Out of Phase 4.2

- Date: 2026-07-24
- Status: Reaffirmed

### Decision

The Notion AI-assisted workflow and Podcast-page Expression synchronization
into Expression Database remain cancelled. They must not re-enter the roadmap,
external-validation journey, or release blockers.

### Reason

Neither requirement is needed to validate the accepted core product, and both
would expand scope without external-user evidence.

## DEC-029: Automatic Vocabulary Sync Trigger and Lifecycle

- Date: 2026-07-26
- Status: Owner Approved for Phase 0

### Decision

Human pink highlight remains the only user selection signal for Vocabulary.
The explicit “同步生词” request is no longer the default product trigger.

The approved Phase 4.2 minimum architecture is local-first macOS scheduled
polling with one bounded process per invocation. A highlight becomes eligible
only after a default 90-second quiet period; this value may be configured
internally after implementation testing.

Synchronization state must be scoped by workspace, configured target group,
source page, and exact highlight occurrence. Historical database groups are
never scanned or written.

Hosted Webhook is deferred and not approved. Background infinite loops remain
disallowed. DEC-020 remains valid for target-group isolation and for its ban on
an infinite polling loop; it is superseded only where “background execution”
could be read as forbidding the approved bounded scheduler.

### Reason

The accepted explicit workflow preserves safety but does not meet the product
requirement that highlighting is the user's only action. A bounded local
scheduler provides automation without introducing hosted credentials, OAuth,
multi-tenant infrastructure, or a long-running daemon.

## DEC-030: Unattended Codex Vocabulary Enrichment Runtime

- Date: 2026-07-26
- Status: Owner Approved for Phase 0 Feasibility

### Decision

Codex remains the production reasoning layer for automatic Vocabulary
enrichment. Python creates request artifacts, validates output artifacts,
manages synchronization state, validates Target Binding, and alone performs
Notion writes.

Unattended Codex feasibility must pass before production activation. The Codex
child process must never receive the Notion token or other Notion-related
environment variables. It also must not depend on `OPENAI_API_KEY`; the
deprecated OpenAI provider remains compatibility-only and does not become the
default.

Production activation requires accepted limits for timeout, retry count,
resource use, malformed output, non-zero exit, process overlap, and credential
isolation.

### Reason

Automatic execution must preserve the Codex/Python/Notion responsibility
boundary. Isolating credentials and failing closed at the artifact boundary
allows feasibility to be tested without granting an AI child process access to
Notion persistence.

## DEC-031: Activate the Accepted Automatic Vocabulary Runtime

- Date: 2026-07-27
- Status: Accepted

### Decision

Complete Automatic Vocabulary delivery with:

- a target-group-scoped SQLite detection and processing state;
- exact occurrence fingerprints without linguistic normalization;
- a 90-second quiet period;
- isolated, finite Codex enrichment;
- strict Python artifact validation;
- Target Binding before every Notion write;
- fingerprint-idempotent Vocabulary upsert and exact reconciliation;
- one bounded macOS LaunchAgent invocation every 60 seconds;
- a non-blocking process lock and redacted structured logs.

The exact pink-highlighted rich-text item remains the user's only Vocabulary
selection action. Normal users do not say "同步生词", provide a page ID, run a
command, or use Notion AI.

Protected real Owner Acceptance passed with one controlled Podcast, one new
pink highlight, and one Vocabulary create. Exact retry created and updated
zero Vocabulary records. Expression, Weekly, schema, delete/archive, and
historical-group writes were zero.

The supported macOS production project location is
`~/EnglishAudioLearningAgent`. Do not install the LaunchAgent against
`Documents`, `Desktop`, or `Downloads`, because launchd can be denied access
to those protected folders even when interactive Python succeeds.

The resulting engineering status is
`ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING`. External-user sessions
remain 0, and this decision does not claim `EXTERNAL_USER_VALIDATION_PASS`.

### Reason

The accepted runtime gives the user the intended one-action learning loop
while preserving the Codex/Python/Notion responsibility boundary, target
isolation, restart safety, and fail-closed publishing. The production-location
constraint records an observed macOS launchd behavior and avoids embedding
credentials in the LaunchAgent plist.

## DEC-032: Add an Independent Bounded Weekly Reflection Schedule

- Date: 2026-07-27
- Status: Product Requirement Accepted; Implementation Pending Review

### Decision

Weekly Reflection should run automatically at Saturday 10:00 in the current
Mac local timezone after the user explicitly confirms installation. The user
may choose another weekly weekday/time, pause, resume, or inspect the schedule
through natural language.

The implementation must use an independent macOS LaunchAgent and one finite
Python process per invocation. It reuses the frozen Weekly Reflection
pipeline, existing isolated Codex runtime, strict artifact validation, Quality
Gate, Target Binding, and Notion writer. It must not introduce a cloud
scheduler, daemon, new AI provider, schema change, historical backfill, or a
second Notion write path.

The latest due period may run once after sleep or a transient failure.
Completed periods reconcile without additional Codex calls or duplicate
Notion content. Insufficient real learning data is skipped without creating a
blank page.

### Reason

Weekly Reflection should compound learning without requiring a repeated
weekly prompt. A separate bounded local scheduler meets that product behavior
while preserving the accepted Codex/Python/Notion boundaries and keeping
Automatic Vocabulary independent.

Feature-branch implementation, tests, and documentation do not constitute
production installation or Owner Acceptance. Those gates remain required
after independent review and merge.
