# External User Session Guide

## Purpose

This guide prepares Phase 4.2 external-user sessions for English Audio Learning
Agent. It is an observation protocol, not a product tutorial or a substitute
for the product's own guidance.

Preparing this kit does not count as an external-user session. At the time of
publication:

- External-user sessions: 0
- External-user readiness: `NOT_READY_FOR_EXTERNAL_USERS`

## Current Activation Gate

External User Session #1 is blocked. The Owner-approved Vocabulary journey is:
pink highlight only, followed by bounded automatic synchronization after a
quiet period. The implementation has not yet passed production acceptance.

Do not recruit or start a session using the former explicit “同步生词” trigger.
Do not substitute a page ID, terminal command, full-workspace scan, or
developer workaround. This guide becomes active again only after the automatic
Vocabulary workflow is implemented and accepted.

## Target Participant

A suitable participant:

- uses a Mac;
- has a Notion account and workspace they control;
- has access to a Codex or ChatGPT environment that supports Skills;
- wants to learn professional English from audio;
- can provide an Apple Podcasts episode, Podcast RSS feed, or local audio file
  that contains no sensitive information;
- has not contributed to this repository and does not already know its internal
  workflow;
- does not need a technical or programming background.

Do not recruit someone whose first session would require private company audio,
confidential transcripts, production Notion data, or another person's account.

## Pre-Session Preparation

Before the participant arrives:

1. Assign an anonymous Session number.
2. Reserve 45-60 minutes.
3. Confirm the participant has a Mac, Notion, and a supported Codex or ChatGPT
   environment.
4. Ask the participant to choose a non-sensitive English audio source.
5. Prepare the current published Skill installation path; do not prepare hidden
   developer shortcuts.
6. Open the evidence template and a timer.
7. If recording or screen sharing is planned, obtain consent before it starts.
8. Confirm the observer will not collect credentials, private URLs, complete
   Notion identifiers, or learning-content transcripts.

The observer must not preconfigure the participant's environment in a way that
hides a real onboarding problem.

## Privacy and Credential Boundary

The participant must never send or expose:

- a Notion access token;
- a complete Notion page, database, or Data Source identifier;
- a private Notion URL;
- confidential audio, transcript text, or learning-page content;
- account passwords, authentication codes, or other credentials.

Notion credentials and page links must be entered only through the product's
local secure setup flow. Pause screen sharing or recording while the
participant enters sensitive values.

Evidence may contain timings, counts, boolean outcomes, short error labels,
participant questions, and redacted screenshots. It must not contain secrets
or private learning content.

## Observer Help Boundary

The observer may:

- read the next user task exactly as written in the session script;
- ask the participant to think aloud;
- ask what the participant expected to happen;
- repeat a task without adding instructions;
- keep time and record observations;
- remind the participant not to share credentials or private information;
- stop the session when a safety condition is reached.

The observer must not:

- tell the participant which button to click unless the product itself provides
  that instruction;
- provide a terminal command, Git command, directory path, configuration value,
  or internal identifier;
- edit a file or environment setting for the participant;
- take control of the keyboard or mouse to complete a task;
- explain repository architecture, acceptance harnesses, or internal recovery
  paths;
- bypass a failed product step with a developer-only workaround;
- repair code, Schema, Notion data, or generated artifacts during the session.

## Developer Intervention

Count one developer intervention each time the observer or another technical
person materially advances the participant by:

- supplying an undisclosed command, path, configuration, or exact click
  sequence;
- operating the participant's computer;
- manually fixing environment, dependency, artifact, or Notion state;
- using repository knowledge to bypass product guidance;
- restarting the journey from an internal checkpoint unavailable to a normal
  user.

Repeating the scripted task, asking a neutral research question, protecting a
secret, or stopping an unsafe action is not developer intervention.

Record every intervention separately, including the blocked step, what help was
given, and whether the participant could continue afterward.

## Session Timing

Record:

- start time;
- time-to-environment-ready;
- time-to-first-Notion-page;
- time-to-first-value;
- end time.

Time-to-first-value is the time from session start until the participant can
identify a useful learning asset they personally value in Notion, such as a
Podcast insight, Expression, or successfully synchronized Vocabulary item.

## Stop Conditions

Stop the session immediately if:

- a credential or private identifier is exposed;
- the flow risks deleting, overwriting, migrating, or publishing sensitive
  data;
- a P0 or P1 issue is observed;
- the participant is asked to perform a destructive or unexplained action;
- the participant cannot proceed without developer intervention at a core
  step;
- the participant asks to stop or withdraws consent;
- the selected source is sensitive or not owned/authorized for use.

Also stop the affected task after 10 minutes without meaningful progress.
Record the failure and recovery evidence; do not improvise a hidden workaround
during the session.

Weekly Reflection is conditional. If the workspace does not contain enough
real learning data, mark Weekly validation as deferred. Do not manufacture
Podcast, Expression, Vocabulary, or Weekly data to force completion.

## Session Completion Classification

These classifications are reserved for sessions started after the activation
gate is removed.

Classify the session as:

- **Unassisted core completion:** the participant completes setup, first
  Podcast learning page, and targeted Vocabulary synchronization without
  developer intervention.
- **Assisted core completion:** the participant completes the same journey with
  one or more developer interventions.
- **Core journey incomplete:** one or more core steps remain incomplete.

Weekly Reflection is reported separately as completed, failed, or deferred
because real learning data was insufficient.
