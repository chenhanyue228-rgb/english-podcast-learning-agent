# Notion Target Binding

## Why This Check Exists

Notion can contain multiple database groups with exactly the same visible
names. Matching `Podcast Library`, `Expression Database`, `Vocabulary
Database`, and `Weekly Review` by name or schema does not prove that they are
the intended production targets.

Phase 4.1C found two complete, same-name groups:

- the current local configuration points to the historical group under
  `English Podcast Learning Agent`;
- the intended group is under `英语音频学习助手`.

Only safe SHA256 fingerprints are recorded:

| Group | Parent fingerprint | Group fingerprint |
| --- | --- | --- |
| Current configured group | `213e9492` | `8b0ff792` |
| Intended group | `e19e65ab` | `f80be05b` |

The intended group is accessible. Its four schemas and three internal
single-property relations passed read-only validation, and all four databases
were empty at diagnosis time.

## Historical Data Boundary

The historical group remains unchanged:

- BE 598 Podcast records: 1
- related Expression records: 19

The project does not automatically move, delete, archive, merge, or clean
historical records. Switching the production target does not imply a data
migration.

## Authoritative Parent

`NOTION_TARGET_PARENT_PAGE_ID` identifies the one parent page authorized for
production writes. Before any page or schema mutation, the shared validator
proves:

1. all four configured Data Sources exist;
2. each belongs to the correct database role;
3. all four databases have the same direct parent page;
4. that parent matches `NOTION_TARGET_PARENT_PAGE_ID`;
5. all required schemas are complete;
6. Expression, Vocabulary, and Weekly relations target the configured Podcast
   Data Source;
7. every relation uses `single_property`, with no cross-group relation.

The Notion connection must be added to the intended parent page. A connection
available elsewhere in the workspace does not establish this binding.

## Required Configuration Switch

The local token remains unchanged. A later, explicitly authorized operation
must switch these five values together:

1. `NOTION_PODCAST_LIBRARY_DATABASE_ID`
2. `NOTION_EXPRESSION_DATABASE_ID`
3. `NOTION_VOCABULARY_DATABASE_ID`
4. `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
5. `NOTION_TARGET_PARENT_PAGE_ID`

Do not mix values from the two groups.

## Read-Only Diagnosis

After configuration is switched, run:

```bash
./.venv/bin/python scripts/notion/diagnose_target_binding.py
```

The command is permanently read-only. It emits only fixed statuses, booleans,
and eight-character fingerprints. It never prints a token, full ID, URL, or
raw Notion response.

Exit codes:

- `0`: binding valid
- `2`: configuration incomplete
- `3`: target mismatch
- `4`: target access unavailable
- `5`: ambiguous target
- `1`: other safe validation failure

No real write is allowed until diagnosis returns `0`.

## Remaining Acceptance Gate

After a successful diagnosis, select a Podcast that does not already exist in
the intended Podcast Library and run the separately authorized Owner
Acceptance Harness. Owner Acceptance remains blocked until that live run and
the owner's visual review both pass.
