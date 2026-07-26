# Automatic Vocabulary Sync Architecture Review

## Review Status

- Product phase: Phase 4.2 — External User Validation
- Execution state: Automatic Vocabulary Sync Architecture Implementation
  Preparation
- Architecture Review: `OWNER_APPROVED_FOR_PHASE_0`
- Synthetic unattended Codex feasibility: PASS
- Synthetic timeout: 60 seconds
- Production baseline:
  `5b08e4bb73db3bffe2a3787cf090d88bdcb4d7be`
- Application runtime implementation: not started by this review
- Real Notion calls / writes during this review: 0 / 0
- External-user sessions: 0
- External readiness: `NOT_READY_FOR_EXTERNAL_USERS`

This review records the Owner-approved minimum architecture. It does not claim
that automatic synchronization, scheduler installation, or unattended
production publishing is implemented or accepted.

## Product Requirement

The user's only vocabulary-capture action is:

```text
Add a pink highlight to exact text in a Podcast learning page.
```

The user does not say “高亮完成” or “同步生词”, provide a page ID, or run a
command. After the page has stopped changing for the quiet period, the system
detects the new highlight, enriches it, validates it, and eventually publishes
it through the protected Vocabulary workflow.

Human pink highlight remains the only Vocabulary source of truth. AI may
explain the selection but must never replace, expand, merge, normalize, or
infer the target.

## Current State

```text
User pink highlight
↓
Explicit targeted sync request
↓
Read one Podcast page
↓
Codex artifact enrichment
↓
Python validation
↓
Target Binding
↓
Vocabulary upsert
```

The targeted workflow has passed protected internal acceptance, but its
explicit user trigger no longer satisfies the approved product requirement.

The repository also contains an inactive `--run-vocabulary-agent` path. It is
not approved for unattended activation because it currently:

- stores global JSON checkpoint state rather than target-group-scoped SQLite;
- treats normalized word text as identity;
- lowercases, strips punctuation, and applies plural normalization;
- can merge separate occurrences of the same highlighted text;
- relies on a strict `last_edited_time` checkpoint without an overlap
  watermark;
- performs enrichment and Vocabulary writes in the same scan cycle;
- has no quiet-period state machine or bounded scheduler lifecycle;
- has no isolated unattended Codex execution proof.

Phase 0 does not activate or repair that runtime path. Phase 1 will build a
read-only detection foundation with the approved identity and state model.

## Required State

```text
macOS LaunchAgent
↓
Start one bounded polling process
↓
Validate configured target group
↓
Query only target Podcast Library pages with overlap watermark
↓
Recursively read all paginated blocks
↓
Extract exact pink highlight occurrences
↓
Observe unchanged occurrence for 90-second quiet period
↓
Compare with target-group-scoped SQLite state
↓
Create isolated Codex enrichment request
↓
Run unattended Codex with sanitized environment and finite timeout
↓
Validate schema + exact word/context/source identity
↓
Revalidate Target Binding
↓
Fingerprint-idempotent Vocabulary upsert
↓
Commit state and reconcile
↓
Exit
```

Every invocation is finite. The scheduler starts a new bounded process; it
does not host an infinite Python loop.

## Considered Options

### Explicit User Trigger

Safe and already accepted internally, but rejected as the default product
experience because it asks the user to remember a command after highlighting.
It remains a protected Developer/recovery path until automatic sync is
implemented and accepted.

### Local-First Scheduled Polling

Approved as the Phase 4.2 minimum. It keeps Notion credentials local, reuses
Python Target Binding and persistence, and can be installed and removed using
standard macOS lifecycle controls.

### Long-Running Local Daemon

Not approved. Infinite loops complicate upgrades, crash recovery, duplicate
run prevention, power behavior, and observability. DEC-020 continues to forbid
background infinite loops.

### Hosted Webhook

Deferred and not approved. It could reduce polling latency, but requires a
hosted service, public callback lifecycle, OAuth or equivalent authorization,
cloud credential storage, multi-user isolation, and operational ownership.

## Local Polling Versus Hosted Webhook

| Dimension | Local scheduled polling | Hosted webhook |
|---|---|---|
| Phase 4.2 approval | Approved minimum | Deferred, not approved |
| Notion credential location | User's Mac | Hosted secret store required |
| User account/OAuth | Not required beyond local integration | Required for a safe multi-user product |
| Infrastructure | LaunchAgent + bounded Python process | Public service, queue, database, monitoring |
| Detection latency | Poll interval + quiet period | Event delivery + quiet period |
| Offline behavior | Retries when the Mac resumes | Service remains online |
| Multi-user scale | One local installation per user | Better long-term scale, much higher initial risk |
| Failure isolation | Local target-group SQLite | Tenant isolation must be designed and audited |

## Recommended Minimum Architecture

The approved minimum consists of:

1. a macOS LaunchAgent that starts one bounded command on a configurable
   interval;
2. a process lock that prevents overlapping cycles;
3. Target Binding before any target-group read that could lead to a future
   write;
4. paginated, recursive block traversal scoped to the configured Podcast
   Library;
5. exact occurrence extraction with no linguistic normalization;
6. target-group-scoped SQLite observation and processing state;
7. a 90-second default quiet period;
8. isolated unattended Codex enrichment with finite timeout and sanitized
   environment;
9. Python schema and exact-intent validation;
10. Target Binding immediately before each future production write;
11. fingerprint-based idempotency, retry, and reconciliation;
12. structured, redacted cycle reports.

The scheduler cadence is separate from the quiet period. Its production
default must be selected and accepted during implementation; it must remain
bounded and configurable.

## Trigger Model

The trigger is not a comment, command, page ID, or normalized word. It is a new
pink-highlight occurrence discovered in the configured Podcast Library.

An occurrence becomes eligible only when:

- its annotation color is `pink` or `pink_background`;
- it belongs to the configured target Podcast Library;
- exact text and exact context are non-empty;
- the page/occurrence has remained unchanged for the quiet period;
- it is not a first-enable baseline occurrence;
- its fingerprint is not already completed or in a valid active lease;
- Target Binding remains valid.

## Quiet-Period Model

The default quiet period is 90 seconds.

Each observation stores:

- first observed time;
- last observed time;
- last changed time;
- exact content fingerprint;
- current eligibility state.

When exact text, context, position, color, or source identity changes, the
quiet timer restarts for that occurrence. A page-level edit timestamp may
prioritize inspection, but it is not sufficient proof that one highlight is
stable.

The bounded cycle never sleeps for 90 seconds. It records observations and
exits. A later scheduled cycle promotes unchanged observations whose quiet
period has elapsed.

## Target-Group Isolation

State identity is scoped by:

```text
workspace fingerprint
+ target-group fingerprint
+ source Podcast page identity
+ exact highlight occurrence fingerprint
```

The target-group fingerprint is a one-way digest derived from the configured
parent and four Data Source roles. Raw identifiers are not included in logs or
reports.

Only the configured current target group may be scanned or written. Historical
database groups are never scanned, reconciled, or modified. A target-binding
change creates a separate namespace and cannot inherit completion state from
another group.

## Exact Highlight Fingerprint

Fingerprint version 1 includes:

- workspace fingerprint;
- target-group fingerprint;
- source page ID;
- block ID;
- rich-text item position, or table/row/cell/rich-text position;
- exact highlighted text;
- exact context;
- annotation color;
- fingerprint version.

The canonical structure is serialized deterministically and hashed with
SHA-256. Reports expose only a short irreversible fingerprint.

Identity must not:

- lowercase text;
- stem plurals;
- strip punctuation;
- collapse distinct positions;
- merge separate occurrences of the same word;
- use a complete table cell as the vocabulary target.

Context supports enrichment only. The `word` field must always equal the exact
highlighted rich-text item.

## State Model

The proposed SQLite store is synchronization metadata, not learning data. It
contains conceptual tables for:

### Target Namespace

- workspace fingerprint;
- target-group fingerprint;
- binding version;
- created and last-seen timestamps.

### Page Observation

- target namespace;
- page fingerprint;
- Notion edit watermark;
- overlap-window cursor;
- last successful read;
- last read outcome.

### Highlight Occurrence

- exact occurrence fingerprint;
- source page and block fingerprints;
- exact position descriptor;
- exact text and context digests;
- color;
- first observed, last changed, and quiet-eligible timestamps;
- baseline flag.

### Processing Attempt

- occurrence fingerprint;
- request artifact digest;
- output artifact digest;
- status;
- lease owner and expiry;
- attempt count;
- last error code;
- next retry time.

### Publish Reconciliation

- occurrence fingerprint;
- target Vocabulary record fingerprint;
- planned action;
- confirmed action;
- post-write verification state.

No Token, complete Notion identifier, private URL, or learning content is
written to logs. SQLite may retain the exact text/context required for
recovery only when local file permissions and lifecycle controls are accepted.

## Duplicate and Idempotency Model

Detection dedupe uses exact occurrence fingerprint only. Separate occurrences
remain separate events even when their visible text is identical.

An attempt lease prevents two bounded cycles from enriching the same
occurrence concurrently. A completed occurrence is not enriched again unless
its exact fingerprint changes.

Before production activation, the write phase must prove:

- an occurrence fingerprint maps deterministically to one publish intent;
- a retry cannot create a second Vocabulary record for the same intent;
- state loss does not silently duplicate writes;
- multiple same-word occurrences remain traceable without losing the user's
  exact context;
- no non-target or historical-group write can occur.

The current word-only Vocabulary publisher is not sufficient evidence for
these guarantees by itself. Phase 1 therefore remains read-only.

## Retry and Recovery Model

Processing states are finite and explicit:

```text
observed
→ quiet_pending
→ eligible
→ enrichment_pending
→ validated
→ publish_pending
→ published
→ reconciled
```

Failures transition to a retryable or terminal state with a fixed redacted
error code. Retries use bounded exponential backoff with a maximum attempt
count and no infinite in-process waiting.

Recovery rules:

- expired leases may be reclaimed;
- incomplete Codex output is discarded or regenerated by digest;
- malformed output never reaches the publisher;
- Target Binding failure stops the cycle;
- ambiguous or duplicate Notion identity stops before write;
- unknown write outcome requires read-only reconciliation before retry;
- checkpoint advancement occurs only after the relevant read/state
  transaction succeeds.

## Credential Security

The Notion token remains local and is loaded only by the Python process that
performs approved Notion reads/writes.

The Codex child environment is allowlisted and removes:

- every Notion-related environment variable;
- `OPENAI_API_KEY`;
- unrelated configuration and secrets.

Codex receives only the minimum enrichment request artifact. It does not
receive the Notion token, Data Source identifiers, complete private URLs, or
raw workspace configuration. Python alone performs Target Binding and Notion
writes.

## Unattended Codex Boundary

Phase 0 uses an isolated synthetic experiment, not the production runtime. The
experiment verifies:

- Codex executable resolution;
- non-interactive `codex exec`;
- ephemeral, read-only execution with approval policy `never`;
- a finite child-process timeout;
- schema-conformant Vocabulary JSON;
- exact word and context preservation;
- non-zero exit, timeout, and malformed-output handling;
- child-environment sanitization;
- absence of Notion variables and `OPENAI_API_KEY`.

The deprecated OpenAI provider remains compatibility-only and must not become
the unattended default.

The Phase 0 synthetic run passed with exit code 0, exact word/context
preservation, schema validation, a 60-second finite timeout, and no Notion or
OpenAI API credential exposure. This is feasibility evidence, not production
activation approval.

Production activation additionally requires resource-use limits,
installation lifecycle, retry/reconciliation, process locking, and acceptance
against Fake/Mock clients before any real write gate.

## Future Multi-User Implications

Local-first polling is intentionally single-user and single-machine. Each
installation owns its scheduler, state database, Codex session access, and
Notion credentials.

A future hosted product would require a separate Owner decision covering:

- OAuth and token revocation;
- encrypted cloud secret storage;
- tenant-isolated state and queues;
- webhook verification and replay protection;
- per-user rate limits and cost controls;
- hosted observability and deletion;
- regional privacy and retention policy.

No Phase 4.2 implementation should pre-empt those decisions.

## Installation and Lifecycle

The future local installation flow must:

1. validate the complete project and `.venv`;
2. validate target binding without writing;
3. create target-scoped SQLite state with restrictive permissions;
4. run a read-only baseline cycle;
5. install a versioned LaunchAgent only after explicit product acceptance;
6. expose status, last success, and fixed error codes without secrets.

Upgrade must preserve compatible state or perform a documented local
migration. Uninstall must unload the LaunchAgent and leave user learning data
untouched. Resetting state must require an explicit recovery action because it
can affect idempotency.

No LaunchAgent is installed in Phase 0 or Phase 1.

## Implementation Phases

### Phase 0 — Architecture and Feasibility

- synchronize canonical documents;
- record durable decisions;
- run isolated synthetic unattended Codex feasibility;
- test timeout, non-zero exit, malformed output, exact intent, schema, and
  credential isolation;
- make 0 real Notion calls/writes.

### Phase 1 — Read-Only Detection Foundation

- recursive paginated highlight reader;
- exact occurrence fingerprint;
- target-group-scoped SQLite;
- overlap watermark;
- page observation and 90-second quiet state;
- first-enable baseline;
- process lock;
- bounded dry-run cycle;
- Fake/Mock or strictly read-only Notion client only.

Phase 1 does not call the Vocabulary publisher, install a LaunchAgent, or add a
production automatic-write entry.

### Future Controlled Write Phase

Requires a new exact-HEAD review and acceptance gate. It may connect validated
eligible occurrences to isolated Codex enrichment and the protected
Vocabulary publisher only after idempotency, reconciliation, resource, and
credential boundaries pass.

### Future Scheduler Activation

Requires accepted installation/uninstall behavior, production diagnostics,
fresh Owner confirmation for any real Notion write acceptance, and exact retry
evidence. Hosted Webhook remains outside this path.

## Acceptance Criteria

### Phase 0

- architecture and decisions are consistent;
- synthetic Codex invocation exits 0;
- existing enrichment schema validates;
- exact word/context are unchanged;
- timeout, non-zero exit, and malformed output fail closed;
- child environment contains no Notion variable or `OPENAI_API_KEY`;
- real Notion calls/writes are 0/0.

### Phase 1

- nested and paginated blocks are completely read;
- distinct occurrences remain distinct;
- 90-second quiet transitions are deterministic;
- overlap scans cannot miss boundary edits;
- first enable baselines historical highlights;
- target-group namespaces do not cross;
- duplicate processes cannot overlap;
- dry-run performs no publisher or Notion write;
- reports contain only counts, booleans, short fingerprints, and fixed codes.

### Production Activation

- unattended Codex resource and retry limits pass;
- Target Binding passes before every write;
- first publish and exact retry are idempotent by occurrence fingerprint;
- non-target and historical-group writes remain 0;
- no manually maintained content is overwritten ambiguously;
- Owner acceptance passes before External User Session #1.

## Migration Impact

Phase 0 changes documentation and isolated experiment code only.

Phase 1 will replace, not activate, unsafe assumptions in the dormant automatic
agent:

- global JSON state → target-group-scoped SQLite;
- normalized word identity → exact occurrence fingerprint;
- strict checkpoint → overlap watermark;
- immediate processing → quiet observation state;
- combined read/write cycle → read-only bounded detection.

The protected targeted Vocabulary workflow remains available for Developer
recovery during migration. Podcast, Expression, Weekly, Notion Schema, and
historical database groups are unchanged.

## Known Limitations and Open Gates

- The default scheduler interval is not yet accepted.
- macOS LaunchAgent installation and removal are not implemented.
- Phase 1 read-only detection is not implemented.
- The production Vocabulary publisher does not yet carry occurrence
  fingerprints.
- Multiple occurrences of the same word need a lossless write/reconciliation
  contract before live activation.
- Offline, sleep/wake, rate-limit, and long-running resource behavior require
  acceptance evidence.
- Unattended Codex feasibility does not by itself approve production
  activation.
- External User Session #1 remains blocked.
- Hosted Webhook remains deferred and not approved.
