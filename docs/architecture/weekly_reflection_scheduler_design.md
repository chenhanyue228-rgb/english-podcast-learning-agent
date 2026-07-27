# Weekly Reflection Scheduler Focused Design

## Status

This document describes the implementation proposed by the Weekly Reflection
Scheduler pull request. Repository implementation, tests, merge, production
installation, and Owner Acceptance are separate gates. The document does not
claim that the scheduler is installed or active in a user's environment.

## Product Contract

- Default schedule: Saturday at 10:00.
- Time basis: the current Mac local timezone.
- User controls: choose the default, set another weekday/time, pause, resume,
  or query status through natural language.
- Normal users do not use Terminal, edit `.env`, provide Notion IDs, or manage
  LaunchAgent files.
- Every invocation is finite. There is no resident Python polling loop.

## Components

```text
Codex Skill
↓
Confirmed local schedule
↓
Weekly Reflection LaunchAgent
↓
One bounded Python runtime
↓
Fresh WeeklyLearningContext
↓
Isolated Reflection Codex child
↓
Strict ReflectionContext validation
↓
Isolated Weekly Review Codex child
↓
Strict WeeklyReview validation + Quality Gate
↓
Target Binding + Weekly-only Notion publish
↓
Target-scoped completion state
```

The LaunchAgent label is
`com.english-audio-learning-agent.weekly-reflection`. It is independent from
the Automatic Vocabulary LaunchAgent.

## Schedule Configuration

The local, non-sensitive configuration is stored under
`data/weekly_reflection/schedule.json`, which is ignored by Git.

Fields:

- `enabled`
- `weekday`
- `hour`
- `minute`
- `timezone_mode`
- `schema_version`
- `effective_at`

The file and generated runtime artifacts are owner-only. Writes use a private
temporary file, `fsync`, and atomic replacement. LaunchAgent replacement is
transactional: a failed unload, plist write, or load restores the prior
schedule, plist, and loaded state. Mutating lifecycle commands also share a
non-blocking local management lock, so concurrent configuration attempts fail
closed.

The plist contains no Notion credential, Data Source identifier, private URL,
or learning text. The production project root must not be under `Documents`,
`Desktop`, or `Downloads`.

## Trigger and Retry Model

The LaunchAgent uses:

- `StartCalendarInterval` for the configured weekly time;
- a 15-minute `StartInterval` recovery wake-up.

The recovery wake-up does not create extra Weekly Reflections. Each process
first applies deterministic due and completion checks, then exits. It exists
so a temporary Codex or Notion failure can retry during the same period and so
a Mac that slept through the calendar time can catch up.

The runtime selects only the latest scheduled period that is less than one
full schedule cycle old. It never loops over or backfills multiple historical
periods. A schedule's `effective_at` timestamp prevents an installation or
configuration change from retroactively running an earlier period.

## Current Weekly Period Semantics

This feature preserves the accepted extractor behavior:

- the local scheduled date becomes `period_end`;
- `period_start` is `period_end - 7 days`;
- Podcast Library is queried by its `Date` property within those bounds;
- the local ISO week of the scheduled date is the runtime completion key;
- learning expressions, AI highlights, and user pink highlights are extracted
  from the selected Podcast pages;
- Vocabulary Database is not queried as an independent primary source.

Both date-filter bounds are inclusive, so the current implementation can
include Podcast records from eight calendar date labels (`end - 7 days`
through `end`). Existing documentation often calls this a rolling seven-day
period; that naming drift is recorded rather than silently corrected here.
This feature does not redefine the accepted code/test contract as Monday
through Sunday.

## Data Sufficiency

The unattended runtime requires:

- at least one successfully extracted Podcast;
- at least one learning asset across expressions, AI highlights, and user
  vocabulary;
- zero page-extraction failures.

Insufficient data returns `SKIPPED_INSUFFICIENT_DATA`, performs zero Codex
calls, and performs zero Notion writes. A partial extraction returns a
retryable failure instead of publishing an incomplete reflection.

## Codex Isolation

Both reasoning stages reuse `src/skill_runtime/codex_cli.py`.

The child process is:

- finite and timeout-bounded;
- approval `never`;
- ephemeral;
- read-only sandboxed;
- stripped of Notion variables and `OPENAI_API_KEY`;
- run with browser, web, shell, MCP, plugin, computer-use, and other tools
  disabled.

Codex writes only a candidate JSON artifact. Python recursively validates
types, required fields, arrays, item limits, `oneOf`, and
`additionalProperties=false`, then validates exact period and source identity.
Only a valid candidate is atomically promoted. The strict Codex output is
stored separately from the final compatibility-enriched `WeeklyReview`
artifact, so a later retry can safely reuse the original validated artifact.

Before any Weekly write, the runtime invokes the frozen Weekly pipeline in
dry-run mode and enforces the production Quality Gate threshold. Only that
validated result may enter a second pipeline invocation with publishing
enabled; both providers reuse the same trusted artifacts, so the second pass
does not make additional Codex calls.

## Idempotency and Recovery

State is namespaced by an irreversible fingerprint of the configured four
Data Sources. Historical database groups are neither read nor written.

Before Codex runs, the runtime queries the current Weekly Review Data Source:

- no page for the period: generation may continue;
- one page with the exact Podcast relation and a matching target-scoped local
  publish-intent fingerprint: verify body integrity and reconcile as
  completed;
- an exact-identity page without matching local publish intent: fail closed
  as owner-managed content;
- a same-period relation conflict or multiple pages: fail closed.

Reconciliation requires exactly one first-position table of contents, one of
each required generated section, the exact Podcast relation, and unchanged
ReflectionContext/strict WeeklyReview generation artifact fingerprints. This
handles a crash after Notion publish but before local state commit without
another Codex call, a duplicate page, or new Notion schema properties.

After first publish, the same checks must produce exactly one complete page
before local completion state is committed. A same-period exact retry returns
`ALREADY_COMPLETED`, calls Codex zero times, and does not invoke the writer.

The unattended pipeline receives a capability-limited Notion proxy. It allows
at most one `pages.create` whose parent is the configured Weekly Data Source.
It blocks page updates, block append/update/delete, schema mutation, and
non-Weekly creates. The frozen writer's identity query is also fail-closed:
query failure cannot be interpreted as “page does not exist.”

## Safety Boundary

Development validation uses Fake/Mock Notion only.

Allowed production mutation after later Owner Acceptance:

- at most one create in the configured Weekly Review Data Source for the due
  period, through the frozen Weekly writer; exact existing identities are
  reconciled read-only and unattended updates remain blocked.

Forbidden:

- Podcast, Expression, or Vocabulary mutation;
- schema changes;
- page delete/archive/trash;
- historical database-group access;
- `.env` changes;
- blank or template-only Weekly pages;
- Quality Gate bypass.

Structured runtime output contains statuses, counts, booleans, schedule
values, and fixed error codes only. It excludes IDs, URLs, credentials, and
learning content.

## Lifecycle

Codex uses `scripts/manage_weekly_reflection_scheduler.py` internally for:

- `install`
- `status`
- `configure`
- `pause`
- `resume`
- `uninstall`

Every persistent mutation requires the corresponding exact internal
confirmation after the user confirms the natural-language schedule. Uninstall
removes only the Weekly LaunchAgent and preserves schedule, state, artifacts,
and learning data.

## Acceptance Gates

Implementation completion may report only:

`WEEKLY_SCHEDULER_IMPLEMENTATION_READY_FOR_REVIEW`

Production acceptance additionally requires merge, production-root sync,
Target Binding verification, confirmed LaunchAgent installation, one
protected real Weekly run, exact retry, and Notion result inspection.
