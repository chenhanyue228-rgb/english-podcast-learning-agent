# Podcast-to-Notion Owner Acceptance Harness

This one-time harness validates the complete podcast publisher as a black box.
It depends on the behavior under review in PR #9:

```text
depends_on_pr_9=true
initial_pr_9_head=7a0d240cfb3c8ccf935ebc96bf7b671994e332ef
reviewed_pr_9_head=3a667afbe9c07b406ef21f9b1afb5e068fd541f3
integrated_main_head=a93c92ebc29ebbf1392f4e8089c99ac3326d9f78
PR #9 status=MERGED
final_pr_9_integration_verified=true
```

It does not replace the production workflow or reproduce PR #9's recovery and
idempotency implementation. The harness imports and invokes the existing
`publish_complete_learning_materials` entry point twice with exactly the same
payload.

The initial PR #9 HEAD is retained as the historical construction baseline.
The reviewed recovery HEAD was merged, and this Harness branch was rebased
onto the production main SHA recorded above. These values identify code
integration only; external-user sessions remain at zero and real Owner
Acceptance remains blocked until a separately authorized live session.

## Safety model

The runner:

- requires `EPLA_NOTION_SETUP_STATE=complete`;
- requires four distinct configured data sources;
- retrieves and validates all four schemas before any publish call;
- never prints configuration values;
- accepts only Apple Podcasts, podcast RSS, or local-audio identity inputs;
- accepts an existing transcript JSON and an existing analysis artifact;
- never downloads, transcribes, or processes audio;
- snapshots all four data sources through read-only queries;
- keeps page identity and normalized record contents in memory only;
- writes counts-only temporary snapshot evidence and removes it in `finally`;
- emits only fixed status labels, booleans, and aggregate counts.

The Guard allows:

- `data_sources.retrieve`;
- `data_sources.query`;
- `blocks.children.list`;
- `pages.create` only in Podcast Library or Expression Database and only for
  the expected target identity;
- `pages.update` only for the target Podcast/Expression scope.

The Guard blocks:

- database creation;
- data-source or database schema mutation;
- Vocabulary Database writes;
- Weekly Review writes;
- page/block deletion;
- page archival or trash operations;
- updates outside the target Podcast/Expression scope;
- block append operations.

If the configured Expression Database is missing required schema, validation
stops before the production publisher can attempt its compatibility migration.

## Verification contract

The pre-publish, first-publish, and second-publish snapshots compare:

- the target Podcast business identity (URL, or Title + Source Type);
- complete Podcast properties;
- exactly one Summary, Expressions, Highlight Legend, and Highlighted
  Transcript top-level section;
- the deduplicated expected Expression identity set (title, category, and
  Source Podcast relation);
- Expression Commonness and `Review Status=New`;
- unchanged unrelated Podcast and Expression records;
- unchanged Vocabulary Database and Weekly Review records;
- no missing, newly archived, or newly trashed records.

The default mode requires the target Podcast not to exist before the first
publish and verifies a `+1` Podcast delta. `--allow-partial-recovery` is only
for a known PR #9 partial-publish retry: it permits one existing target Podcast
and a unique subset of expected Expressions, then requires the final complete
state and a zero-addition second publish.

## Future live command

Do not run this command during Fake/Mock verification. A future authorized
owner-acceptance session may run:

```bash
python scripts/acceptance/run_podcast_owner_acceptance.py \
  --source "<supported source>" \
  --title "<podcast title>" \
  --transcript-json "<existing transcript.json>" \
  --analysis-json "<existing analysis.json>" \
  --confirmation OWNER_ACCEPTANCE_WRITES_TO_NOTION
```

For a known partial-publish recovery, add `--allow-partial-recovery`.

The command is intentionally explicit because it performs two calls to the
formal production Podcast publisher. It must only be used against the owner's
configured acceptance workspace after separate authorization.
