# Product Validation Plan

## 1. Purpose

Validate whether English Audio Learning Agent can deliver its core value to a
new user without project-author assistance.

## 2. Stable Baseline

- Release: v1.1.0
- Main commit: `80cbab01ea266e487a0359ddbec562959070d8a0`
- Architecture: stable Codex Artifact Runtime
- Verification: 345 passing tests and CLI smoke check
- Supported inputs: Podcast episode URL, Podcast RSS feed, local audio file
- Vocabulary: Human Highlight + AI Processing
- Weekly Reflection: stable learning-compounding contract

## 3. Target User

The primary initial user:

- already uses ChatGPT or Codex
- uses or is willing to use Notion
- wants to learn English from Podcasts or audio
- is not expected to understand the Python source code

The initial target is not a general consumer mobile-app user.

## 4. Core Product Hypotheses

### H1: Product Understanding

A new user can understand what the product does from the repository entry
documentation.

### H2: Independent Setup

A new user can complete local and Notion setup without direct help from the
project author.

### H3: First Learning Page

A new user can produce the first complete Notion learning page from a Podcast,
RSS Feed, or Local Audio source.

### H4: Compounding Learning Value

The generated Vocabulary, Expressions, and Reflection assets provide more
long-term value than a one-time ChatGPT summary.

### H5: User-Controlled Vocabulary

Human Highlight + AI Processing feels controllable and personally relevant.

## 5. Validation Journey

1. Discover the project.
2. Read the Quick Start.
3. Clone the repository.
4. Bootstrap the environment.
5. Configure Notion.
6. Process one supported source.
7. Complete the Codex artifact handoff.
8. Publish the first learning page.
9. Highlight one Vocabulary item.
10. Preview and publish Vocabulary.
11. Review the resulting learning assets.

Weekly Reflection may be tested separately after sufficient learning data
exists.

## 6. Test Scenarios

### Scenario A: Clean Installation and Configuration

Observe whether a new user can clone the repository, bootstrap dependencies,
configure non-secret environment values, and validate the Notion workspace.

### Scenario B: First Learning Page

Process one Podcast or Local Audio source through artifact generation,
validation, and Notion publishing.

### Scenario C: Human Highlight Vocabulary

Run the pink-highlight Vocabulary dry run and publish flow. Confirm that the
exact user-selected text remains the vocabulary target.

### Scenario D: Error Recovery

Observe recovery from a missing artifact or missing configuration without
project-author intervention.

### Scenario E: Learning-Asset Usefulness

Review whether Podcast notes, Expressions, Vocabulary, and later Weekly
Reflection are understandable, reusable, and worth revisiting.

## 7. Metrics

Record:

- setup completion rate
- time to environment-ready state
- time to first successful Notion page
- number of undocumented manual steps
- number of user questions
- number of failed commands
- recovery success rate
- perceived usefulness of each learning asset
- willingness to use the workflow again

Do not invent successful metric values. This document defines what should be
measured.

## 8. Issue Severity

### P0

Security issue, data loss, credential exposure, or destructive behavior.

### P1

User cannot complete the core journey.

### P2

User can complete the journey only with a confusing workaround or author help.

### P3

Polish, wording, layout, or a non-blocking convenience problem.

## 9. Initial Beta Size

Test with three external users. Prefer users who:

- learn English from audio
- use Notion
- are comfortable using ChatGPT or Codex
- are not contributors to the repository

## 10. Phase 4 Exit Criteria

- Three external-user sessions are completed.
- At least two users complete the core flow without developer intervention.
- No P0 issue remains open.
- No P1 onboarding blocker remains open.
- Actual time-to-first-value is recorded.
- Repeated confusion points are documented.
- The next sprint is chosen from user evidence.
- Architecture changes, if any, are proposed separately.

## 11. Evidence Log Template

For every session, record:

- tester profile
- date
- source type
- setup duration
- first-value duration
- completed steps
- failed steps
- questions asked
- observed confusion
- severity
- workaround
- output usefulness
- willingness to reuse
- recommended action

Do not include real tokens, private Notion IDs, or personal audio/transcript
content in committed evidence.

## 12. Not in Scope

- Web UI
- cloud deployment
- multi-user accounts
- billing
- mobile app
- YouTube core support
- automatic Vocabulary discovery
- architecture redesign
- large refactoring

## 13. Next Sprint Decision

After evidence collection, recommend one:

- Skill onboarding improvement
- Learning Asset Reuse
- broader beta preparation
- localized reliability fixes
- Architecture Decision review
