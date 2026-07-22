# Phase 4.1 Clean-Clone Onboarding Report

## Audit Type

Technical agent audit — not an external-user session.

This audit simulated a first-time technical user from a fresh remote clone. It
did not reuse an existing virtual environment, `.env`, generated artifact,
cache, credential, or project-author configuration.

## Baseline

- Remote main commit: `8cdb5aa39c271f9de7cb9191b4b438a2e3e93fb7`
- Stable release: `v1.1.0`
- v1.1.0 tag target: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Audit date: 2026-07-22
- Clone location in this report: `<CLEAN_CLONE>`

## Audit Environment

- Operating system: macOS (Darwin)
- CPU architecture: arm64
- System Python: 3.9.6
- Git: 2.39.5 (Apple Git-154)
- Python isolation: `<CLEAN_CLONE>/.venv`
- Existing project environment reused: no
- Existing credentials reused: no

## Journey Results

| Step | Documented action | Actual action | Result | Duration | Extra help required |
|---|---|---|---|---:|---|
| Clone | Obtain the repository | Cloned remote `main` into `$TMP` | PASS; clean HEAD matched the required commit | 3.92 s | No |
| Read entry documentation | Read README and linked references | Read README, linked architecture/contract/next-steps documents, then `skill/SKILL.md` | PASS with inconsistencies recorded | Included in observed elapsed time | Yes; linked documents contain stale release status |
| Isolate Python | Not documented | Ran `python3 -m venv .venv` | PASS | 1.09 s | Yes; this was an undocumented safety step |
| Bootstrap | `python3 scripts/bootstrap_environment.py` | Used the same script through `./.venv/bin/python` | PASS; dependencies installed and 9 smoke tests passed | About 30.1 s | Yes; interpreter substitution was needed to preserve isolation |
| Environment template | Copy `.env.example` to `.env` | Copied it and left all credentials and IDs blank | PASS | Less than 0.1 s | No |
| CLI help | Use the project CLI | Ran `./.venv/bin/python -m src.main --help` | PASS, exit 0 | 0.06 s | No |
| Configuration diagnostics | Inspect non-secret configuration | Ran `--print-config` | PASS, exit 0; output did not expose values | 0.06 s | No, but diagnostics cover only part of the Notion ID set |
| Notion onboarding | Not linked from README | Discovered and ran `src.notion.setup_workspace --print-onboarding` | PASS, exit 0 | Less than 0.1 s | Yes; discovery required knowledge outside the README journey |
| Workspace validation | Validate Notion workspace | Ran with intentionally blank configuration | Expected failure, exit 1; named `NOTION_TOKEN`, gave a next action, no stack trace | Less than 0.1 s | No |
| Missing source | Run CLI without a source | Ran `./.venv/bin/python -m src.main` | Expected failure, exit 1; concise usage message | Less than 0.1 s | No |
| Artifact request | Reuse an existing transcript | Supplied a synthetic transcript JSON and no analysis JSON | PASS; request artifact created, exit 0 | 0.06 s | Yes; output artifact path and exact next command were not printed |
| Input classification | Check supported source routing without network | Classified representative Apple Podcast, RSS, local audio, and YouTube values | PASS | Less than 0.1 s | No |
| Full regression | Run the full suite | Ran `./.venv/bin/python -m pytest -q` | PASS: 345 passed, 3 expected warnings | 1.22 s | No |
| Diff validation | Verify no tracked runtime changes | Ran `git diff --check` | PASS | Less than 0.1 s | No |

## Metrics

- Clone duration: 3.92 seconds
- Virtual environment creation duration: 1.09 seconds
- Bootstrap duration: approximately 30.1 seconds
- Direct clone + environment command runtime: approximately 35.1 seconds
- Observed time to the safe artifact-request milestone: 3 minutes 50 seconds
  from temporary audit creation; this includes documentation reading and
  command orchestration
- Time to first successful Notion page: not measured; external Notion access
  was intentionally excluded
- Technical commands attempted: 15
- Expected diagnostic commands returning non-zero: 3
- Unexpected command failures: 0
- Undocumented or undiscoverable setup steps: 4
- User questions asked: 0 (agent audit)
- Onboarding ambiguities/issues recorded: 9
- Full test result: 345 passed, 0 failed, 3 expected warnings

## Bootstrap Result

The documented bootstrap script works when invoked through an isolated Python
interpreter. It installs dependencies, runs the router smoke test, and ends
with a clear success message.

Observed concerns:

- README does not create or activate a virtual environment.
- The bootstrap script installs into whichever interpreter invokes it and does
  not warn when that interpreter is a system Python.
- `yt-dlp` is installed even though YouTube is outside the v1 product scope.
- The pip upgrade warning is non-blocking.

## Environment Template Result

The template correctly uses:

- `NOTION_TOKEN`
- `NOTION_PODCAST_LIBRARY_DATABASE_ID`
- `NOTION_EXPRESSION_DATABASE_ID`
- `NOTION_VOCABULARY_DATABASE_ID`
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
- optional `NOTION_PARENT_PAGE_ID`
- legacy `NOTION_WEEKLY_REVIEW_DATABASE_ID`

Codex is the default provider and no production path requires
`OPENAI_API_KEY`.

The README presents `NOTION_PARENT_PAGE_ID` in the list of required settings,
while the template labels it optional for setup when supplied on the command
line.

## Safe Artifact-Handoff Result

A synthetic transcript containing only:

> This is a clean-clone onboarding validation transcript.

successfully produced:

`data/analysis_requests/clean_clone_onboarding_test.json`

No audio download, Whisper execution, Codex generation, Notion request, or
external service call occurred.

The CLI printed only the request path. It did not print:

- the expected output path under `data/analysis/`
- the exact command to rerun
- an explicit instruction that Codex must now generate the artifact

The Skill contract contains enough information for a knowledgeable Codex
operator to infer the next step, but the terminal handoff is not independently
self-explanatory.

## Supported-Input Classification Result

| Representative input | Classification | v1 status |
|---|---|---|
| Apple Podcast episode URL | `apple_podcast` | Supported |
| Podcast RSS URL | `podcast_rss` | Supported |
| Local `.mp3` path | `local_audio` | Supported |
| YouTube URL | `youtube` | Experimental/legacy, outside v1 |

No remote availability check or download was performed.

The router supports Apple Podcast page URLs, RSS URLs, direct audio URLs, and
local audio paths. README's broader phrase "Podcast episode URL" does not make
the Apple-only page-URL boundary explicit.

## Documentation Consistency Result

| Area | Status | Evidence |
|---|---|---|
| Installation command | CONFIRMED discrepancy | README runs bootstrap with `python3` but does not establish an isolated environment |
| Supported Python version | CONFIRMED omission | No supported version or range is documented; Python 3.9.6 passed this audit |
| Bootstrap behavior | CONFIRMED working | Dependencies installed and 9 router smoke tests passed |
| Supported inputs | CONFIRMED ambiguity | Router page-URL support is Apple-specific; README says Podcast episode URL |
| Environment names | CONFIRMED consistent | `.env.example` and `src.notion.config` agree on four canonical database IDs |
| Notion database count | CONFIRMED discrepancy | Implementation creates four databases; `docs/Notion_Onboarding.md` describes three |
| README Notion setup | CONFIRMED blocker | README asks users to fill IDs but does not link or show the workspace creation command |
| Workspace setup behavior | CONFIRMED by code/tests only | Setup creates four databases and writes IDs; real Notion execution was excluded |
| Workspace validation behavior | CONFIRMED for missing config | Missing token error is actionable and does not leak data |
| Podcast artifact handoff | CONFIRMED incomplete | Request path is printed; output path and rerun command are omitted |
| Transcript reuse | CONFIRMED working | Transcript-only request creation succeeded without audio or Whisper |
| Vocabulary dry run | NOT_TESTABLE_WITHOUT_EXTERNAL_CREDENTIALS | Code avoids publisher writes but still requires Notion read access |
| Human Highlight ownership | CONFIRMED by implementation/tests | Pink rich-text target is preserved as the candidate word |
| Weekly Reflection command | CONFIRMED by CLI/tests | Command exists; real Notion flow was excluded |
| Legacy versus production commands | CONFIRMED noisy | CLI help exposes legacy/debug commands alongside the v1 path |
| Linked status documents | CONFIRMED stale | `docs/current_architecture.md` reports 344 tests and `docs/next_steps.md` still describes pre-release work |

## What Could Not Be Tested

- real Notion integration creation and page sharing
- real Notion workspace creation
- real Notion database validation
- real Podcast or RSS download
- real audio extraction and normalization
- real Whisper transcription or model download
- actual Codex artifact generation
- final Notion learning-page publishing
- real pink-highlight Vocabulary reading and publishing
- Vocabulary dry-run behavior against a real page
- Weekly Reflection with real user data
- end-user interpretation and perceived learning value

## Overall Technical Onboarding Status

**TECHNICAL_ONBOARDING_BLOCKED**

The isolated Python runtime, deterministic pipeline, source classification,
artifact request creation, and full test suite are healthy. A new user still
lacks two required bridges for the full product journey:

1. an executable Codex Skill installation/discovery step
2. a discoverable and internally consistent Notion workspace setup path

These are onboarding blockers rather than architecture or runtime failures.

## Recommended Next Step

Fix the evidence-backed P1 onboarding issues before counting external setup
sessions. Then run a disposable Notion setup test with non-production data and
credentials.
