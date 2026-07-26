---
name: english-audio-learning-agent
description: Install and set up English Audio Learning Agent; configure and validate its Notion workspace; analyze Apple Podcasts episodes, podcast RSS feeds, and local English audio; generate learning artifacts; sync highlighted vocabulary; and publish learning notes and weekly reflections.
---

# English Audio Learning Agent Skill

## 1. Skill Identity

### Skill Name

English Audio Learning Agent

### Purpose

Turn English learning inputs such as Apple Podcasts episode URLs, podcast RSS feeds,
local audio files, and user-highlighted vocabulary into structured learning
assets stored in Notion.

### Target User

This Skill is for users who want to learn English from podcasts and save the
results into Notion with minimal manual work.

### Supported Inputs

- Apple Podcasts episode URL
- Podcast RSS feed
- Local audio file
- Highlight vocabulary input

### Out of Scope for v1

YouTube is intentionally excluded from the v1 product. The Skill focuses on
stable audio sources and does not promise platform-specific video downloading,
authentication, or anti-bot compatibility. Experimental implementation may
remain in the repository for future evaluation, but Codex must not present it
as a supported v1 input.

## 2. Skill Activation Rules

### When to Use This Skill

Use this Skill when the user asks to:

- install the English Audio Learning Agent
- complete first-time setup
- configure or validate the Notion workspace
- "Analyze this podcast"
- "Create English learning notes"
- "Extract useful expressions"
- "Generate weekly reflection"
- publish a learning page

Use this Skill when the user provides:

- an Apple Podcasts episode URL
- a podcast RSS feed
- a local audio file
- a Notion page containing vocabulary highlights

### When Not to Use This Skill

Do not use this Skill when the user asks for:

- general web browsing without learning extraction
- unrelated code generation
- generic Notion admin work not tied to learning content
- direct OpenAI API integration work

If the request is unclear, ask one concise clarifying question before running
the workflow.

### Automatic Vocabulary Runtime

The production Vocabulary trigger is an exact pink highlight followed by
bounded automatic synchronization:

```text
Exact Pink Highlight
↓
60-Second Scheduled Check
↓
90-Second Quiet Period
↓
Isolated Codex Enrichment
↓
Strict Python Validation
↓
Target-Bound Vocabulary Upsert
```

The user does not say “同步生词”, provide a page ID, or run a command. The
highlighted rich-text item is the exact vocabulary target; context is
enrichment context only.

The first scheduler cycle baselines existing highlights and does not backfill
them. The explicit targeted command remains Developer/recovery only.

## 3. Guided Onboarding Contract

### Installation Request

The supported Chinese installation request is:

```text
请从下面的项目安装英语音频学习助手：

https://github.com/chenhanyue228-rgb/english-podcast-learning-agent

安装成功后，请直接在当前对话中带我继续第一次设置。
```

The repository URL is used only during installation. First-time setup and
daily podcast processing must not require the user to provide it again.

### Installation Handoff

After installation, continue in the current conversation first. Codex must
display:

```text
英语音频学习助手已经安装完成。

现在可以在当前对话中继续第一次设置。

是否现在继续？
```

When the user replies `继续`, begin first-time setup immediately.

Do not require a new conversation. If the current conversation has not
discovered the newly installed Skill, a new conversation is the first
fallback. If the new conversation still cannot discover it, restarting Codex
is the second fallback.

The optional setup trigger is:

```text
请使用英语音频学习助手，带我完成第一次设置。
```

The user does not need to memorize this instruction.

### Locate or Acquire the Complete Project

Before first-time setup, Codex must check whether the active workspace contains
all of:

- `README.md`
- `skill/`
- `scripts/`
- `src/`
- `requirements.txt`
- `.env.example`

If present, continue with that project. If absent, Codex should acquire:

```text
https://github.com/chenhanyue228-rgb/english-podcast-learning-agent
```

The suggested destination is `~/EnglishAudioLearningAgent`.

- Clone only when the destination does not exist.
- If it exists, verify it is the correct repository before using it.
- Do not place the production project in macOS protected `Documents`,
  `Desktop`, or `Downloads` folders. A LaunchAgent may be denied access even
  when an interactive terminal can run the same command.
- Never overwrite an unrelated directory or delete user files.
- Never write a Notion token into the repository or a command.
- Request user approval for necessary downloads, local execution, or network
  access.
- Do not require the user to find the project folder or type `cd`.

### User-Visible Notion Conversation Contract

The following Chinese copy is the canonical first-time setup conversation.
Codex must show exactly one action at a time and wait for the specified reply
before showing the next action. Codex must not combine these steps into a
single authorization request.

#### Step 1: Open the Developer Dashboard

Codex must display:

```text
英语音频学习助手需要一个只访问你指定页面的 Notion 私人连接。

现在请打开 Notion 开发者后台：

https://www.notion.so/developers

打开后，请回复：

开发者页面已打开
```

Codex must wait for `开发者页面已打开`.

#### Step 2: Open the Connection List

After the user replies `开发者页面已打开`, Codex must display:

```text
请点击开发者后台左侧栏的“连接”。

这里会显示你已经创建的 Notion 连接。

打开后，请回复：

连接列表已打开
```

Codex must wait for `连接列表已打开`.

#### Step 3: Open or Create a Connection

After the user replies `连接列表已打开`, Codex must display:

```text
请查看列表中是否已经有用于英语音频学习助手的连接。

如果已经有，请直接打开它。

如果没有，请创建一个新的连接，名称建议填写：

英语音频学习助手

请选择你用于保存学习资料的工作空间。

打开连接配置页面后，请回复：

连接页面已打开
```

An existing connection may have a different name, such as
`English podcast learning`; Codex must not require renaming it.
Codex must wait for `连接页面已打开`.

#### Step 4: Confirm Content Permissions

After the user replies `连接页面已打开`, Codex must display:

```text
请在当前连接的“配置”页面中，确认以下内容权限已经开启：

- 读取内容
- 更新内容
- 插入内容

这些权限只用于读取和保存英语学习资料。

确认完成后，请回复：

权限已确认
```

Codex must wait for `权限已确认`.

#### Step 5: Save the Access Token

After the user replies `权限已确认`, Codex must display:

```text
请在同一个连接配置页面找到“访问令牌”。

点击复制按钮，安全保存完整令牌。

访问令牌相当于私人密码：

- 不要发送到聊天
- 不要截图分享
- 不要写入公开文档
- 不要提交到 GitHub

保存好后，请回复：

密钥已保存
```

Codex must wait for `密钥已保存`.

#### Step 6: Open Notion and Create the Learning Page

After the user replies `密钥已保存`, Codex must display:

```text
接下来，我会带你在 Notion 中创建一个新页面，用来存放英语学习资料。

这个操作不会修改你已有的页面，也不会把页面公开到互联网。

现在请打开自己的 Notion 工作空间。

打开后，请回复：

已打开 Notion
```

Codex must wait for `已打开 Notion`.

After the user replies `已打开 Notion`, Codex must display:

```text
请在 Notion 左侧栏点击“新建页面”。

页面名称填写：

英语音频学习助手

请选择空白页面，不要手动添加数据库或其他内容。

创建完成后，请回复：

页面已创建
```

Codex must wait for `页面已创建`.

#### Step 7: Add the Integration to the Page

After the user replies `页面已创建`, Codex must display:

```text
现在请允许英语音频学习助手访问这个页面。

操作步骤：

1. 打开刚创建的“英语音频学习助手”页面。
2. 点击页面右上角的“•••”。
3. 找到“集成”。
4. 点击“集成”。
5. 选择你刚才打开或创建的英语音频学习助手连接。

如果你的连接名称不同，请选择你为这个项目使用的连接。

完成后，请回复：

集成已添加
```

Codex must wait for `集成已添加`.

If the user cannot find the integration control, Codex must display:

```text
请先确认你正在查看刚创建的 Notion 页面。

然后：

1. 点击页面右上角的“•••”。
2. 向下查找“集成”。
3. 选择你的英语音频学习助手连接。

如果仍然找不到，请告诉我页面右上角现在有哪些按钮，或发送一张不包含密钥的截图。
```

#### Step 8: Copy the Page Link

After the user replies `集成已添加`, Codex must display:

```text
现在请复制这个 Notion 页面的链接。

操作步骤：

1. 点击页面右上角的“共享”。
2. 点击“复制链接”。

请先保留这个链接，不要发送到聊天。

稍后我会打开一个本地安全窗口，让你在那里粘贴：

- Notion 访问密钥
- 刚复制的页面链接

复制完成后，请回复：

链接已复制
```

Codex must wait for `链接已复制`. Only after this reply may Codex prepare the
local runtime and launch the safe setup tool.

### First-Time Setup Responsibilities

Before the user replies `链接已复制`, Codex must not launch
`scripts/first_time_setup.py`, `start_setup.command`, environment preparation,
or any local setup command.

After the user replies `链接已复制`, Codex must:

1. Locate or safely acquire the complete project.
2. Prepare or reuse the project-local `.venv`.
3. Automatically launch `scripts/first_time_setup.py` with safe interactive
   input.
4. Ask the user to enter the hidden Notion access token and the complete page
   URL only in the local safe window.
5. Never ask the user to send the token, page URL, page ID, or database IDs in
   chat.
6. Let Python validate the token and page access, create or validate all four
   databases, wire relations, and report the result. The user is not
   responsible for deciding whether technical validation succeeded.

The Codex Notion plugin is not required. Database creation, validation, and
learning-content writes use local Python with the user's own Notion internal
integration. The plugin is optional for search, read, and assisted viewing
only:

- plugin authorization is not passed to local Python
- it does not replace `NOTION_TOKEN` or the `setup_workspace` first-time setup
- it must not introduce a second production write path
- never let the plugin and local setup create separate database sets

If safe interactive input is unavailable, try to open `start_setup.command`.
If that also fails, open the project directory in Finder and ask the user only
to double-click `start_setup.command`. Terminal instructions are the final
fallback.

After success, actively prompt the user for an Apple Podcasts episode URL,
podcast RSS feed, or local audio file.

### Owner Acceptance Prompt Boundary

Owner-acceptance prompts may define test goals, evidence, pass/fail criteria,
and issue severity. They must not rewrite or override the user-visible copy in
this conversation contract. Internal phrases such as test page, disposable
page, parent page, or acceptance environment belong only in developer reports
and must not be shown as user instructions.

### Daily Podcast Trigger

```text
请使用英语音频学习助手处理这个播客：

<播客链接>
```

Codex must check the input, run the local transcript/request flow, generate the
analysis artifact, rerun Python validation and publishing, and return the final
Notion page URL. Do not ask the user to copy the internal command sequence.

## 4. Runtime Architecture

This project is a Codex Skill, not a standalone Python AI application.

### Codex

Codex is responsible for:

- analyzing language
- generating reasoning artifacts
- creating structured JSON outputs
- turning learning signals into reflection and vocabulary artifacts

### Python

Python is responsible for:

- downloading and processing source data
- extracting transcripts
- validating artifacts
- executing workflows
- publishing content to Notion

### Notion

Notion is responsible for:

- storing knowledge assets
- presenting Podcast Library pages
- storing Vocabulary Database records
- storing Weekly Reflection pages

### Runtime Rule

The Skill runtime path does not require direct OpenAI API calls.

Python should be used for orchestration, validation, and publishing.
Codex should be used for reasoning and content generation.

## 5. User Quick Start

### Step 1: Install the Skill

Use the installation request above. After installation, the current
conversation is the primary continuation path. A new conversation and restart
are fallbacks only when Skill discovery has not refreshed.

### Step 2: Configure the Environment

Codex locates the complete project, prepares the local environment, guides the
Notion authorization, and starts the safe setup tool. The user enters the
token and complete parent-page URL only in the local interface.

Python creates or validates Podcast Library, Expression Database, Vocabulary
Database, and Weekly Review. Weekly Review stores the Weekly Reflection
learning note.

### Step 3: Provide Podcast Input

Give Codex an Apple Podcasts episode URL, podcast RSS feed, local audio file,
or a Notion highlight source.

### Step 4: Run the Analysis Workflow

Codex runs the source pipeline to create the intermediate analysis request
artifact.

### Step 5: Generate Artifacts

Codex reads the request artifact, produces structured JSON, and saves it to the
appropriate output directory.

### Step 6: Publish to Notion

Codex runs the publish step so Python validates the generated artifact and
writes the final page to Notion.

## 6. Command Catalog

These commands are an execution contract for Codex and a Developer/recovery
reference. Normal users are not expected to run them manually.

| Command | Purpose | Required Input | Generated Artifacts | Expected Output | Next Action |
|---|---|---|---|---|---|
| `./.venv/bin/python src/main.py "<source>"` | Extract audio, transcribe, and create a Codex analysis request | Apple Podcasts episode URL, podcast RSS feed, or local audio path | `data/transcripts/<file>.json`, `data/analysis_requests/<file>.json` | A Codex analysis request file path | Codex generates analysis JSON |
| `./.venv/bin/python src/main.py "<source>" --analysis-json data/analysis/<file>.json` | Publish a complete Podcast Library page | Source plus Codex-generated analysis JSON | Podcast page in Notion | Created Notion Podcast Library page | Move to vocabulary or weekly workflows if needed |
| `./.venv/bin/python src/main.py --weekly-reflection` | Run the Weekly Reflection pipeline | Weekly learning context from the current period | `output/weekly_learning_context.json`, `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Weekly Reflection page, or dry-run output if configured | Review result in Notion or rerun with dry-run |
| `./.venv/bin/python src/main.py --weekly-reflection --dry-run` | Run the Weekly Reflection pipeline without Notion publish | Weekly learning context | `output/reflection_context.json`, `output/weekly_review.json`, `output/pipeline_run.json` | Validation and quality output only | Inspect artifacts, then publish if ready |
| `./.venv/bin/python src/main.py --weekly-review` | Build a Weekly Review request from Notion learning data | Current Notion learning data | `data/weekly_review_requests/<week>.json` | Weekly Review request file path | Codex generates Weekly Review JSON |
| `./.venv/bin/python src/main.py --publish-highlight-vocab PAGE_ID` | Developer/recovery only: publish exact user-selected pink-highlight vocabulary from one Notion page | Notion page ID | Vocabulary preview / publish artifacts | Updated Vocabulary Database entries | Do not present this as the default user trigger |
| `./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py status` | Inspect the bounded automatic Vocabulary scheduler | Installed local runtime | None | Installed/loaded state and interval | Diagnose before changing scheduler state |
| `./.venv/bin/python scripts/run_automatic_vocabulary_once.py` | Developer/recovery only: run one finite automatic Vocabulary cycle | Configured target group | Target-scoped state and enrichment artifacts | Redacted bounded-cycle report | Do not loop this command |
| `./.venv/bin/python src/main.py --sync-vocab-comments` | Legacy compatibility: sync comment-triggered vocabulary captures | Podcast Library pages with historical comment triggers | Sync state + vocabulary records | Vocabulary sync summary | Prefer the pink-highlight workflow for v1 use |
| `./.venv/bin/python -m pytest` | Run the full test suite | None | Test reports | Pass/fail summary | Fix issues before publishing |

Automatic Vocabulary scheduler lifecycle:

```bash
./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py install \
  --confirmation INSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT

./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py status

./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py uninstall \
  --confirmation UNINSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT
```

Install and uninstall are Developer/Codex operations. Normal users only add a
pink highlight. Uninstall preserves synchronization state and learning data.

## 7. Workflow Contracts

### 7.1 Podcast Analysis

#### Flow

```text
Input
↓
Transcript
↓
Codex analysis
↓
Validation
↓
Notion publish
```

#### Inputs

- Apple Podcasts episode URL
- podcast RSS feed
- local audio file
- transcript JSON if available

#### Artifacts

Intermediate:

- `data/transcripts/`
- `data/analysis_requests/`

Final:

- `data/analysis/`
- Notion Podcast Library page

#### Responsibilities

Codex:

- analyze transcript content
- generate summary and learning items

Python:

- extract audio
- transcribe
- create analysis request artifact
- validate generated JSON
- publish to Notion

### 7.2 Vocabulary Capture

The automatic workflow is the production path. Explicit targeted publishing
remains a protected Developer/recovery path.

#### Flow

```text
Exact Pink Highlight
↓
Bounded Scheduled Detection
↓
90-Second Quiet Period
↓
Codex Enrichment Artifact
↓
Strict Python Validation and Target Binding
↓
Vocabulary Database
```

#### Inputs

- pink highlight input
- highlight vocabulary source page

#### Artifacts

Intermediate:

- vocabulary preview JSON
- enrichment JSON

Final:

- Vocabulary Database page

#### Responsibilities

Codex:

- interpret the highlighted vocabulary
- generate meaning and usage context

Artifact handoff:

- Python writes a private target-scoped request artifact.
- Isolated Codex writes one schema-conformant enrichment artifact.
- Python independently validates exact word, exact context, and every schema
  constraint before publishing.

Python:

- detect the exact occurrence
- enforce the 90-second quiet period
- maintain target-scoped SQLite state
- validate the vocabulary payload
- validate Target Binding
- upsert to Notion with an occurrence fingerprint
- reconcile exact retry without duplicate records or body sections

### 7.3 Weekly Reflection

#### Flow

```text
WeeklyLearningContext.json
↓
ReflectionContext.json
↓
WeeklyReview.json
↓
Quality Gate
↓
Notion
```

#### Inputs

- `output/weekly_learning_context.json`

#### Artifacts

Intermediate:

- `output/reflection_context_request.json`
- `output/reflection_context.json`
- `output/weekly_review_request.json`
- `output/weekly_review.json`
- `output/pipeline_run.json`

Final:

- Weekly Reflection page in Notion

#### Responsibilities

Codex:

- derive weekly theme
- identify mindset shifts
- synthesize learning patterns
- create reflection output

Python:

- build the weekly learning context
- validate reflection and review artifacts
- run quality checks
- publish to Notion

## 8. Artifact Contract

### Input Artifacts

- `data/analysis_requests/`
- `output/weekly_learning_context.json`
- highlight-derived vocabulary previews

### Output Artifacts

- `data/analysis/`
- `output/reflection_context.json`
- `output/weekly_review.json`
- `output/pipeline_run.json`

### Naming Conventions

- podcast analysis request:
  - `data/analysis_requests/<slug>.json`
- podcast analysis output:
  - `data/analysis/<slug>.json`
- reflection context:
  - `output/reflection_context.json`
- weekly review:
  - `output/weekly_review.json`

### Artifact Types

Intermediate artifacts:

- analysis requests
- reflection context
- weekly review draft
- pipeline run metadata

Final knowledge outputs:

- Podcast Library page
- Vocabulary Database page
- Weekly Reflection page

## 9. Error Handling

### Invalid URL

Detect:

- source router cannot classify input

Report:

- clear error message with supported input types

Recovery:

- ask the user for a supported source

### Transcript Failure

Detect:

- audio download fails
- transcription fails

Report:

- the failing stage and input source

Recovery:

- retry with a valid source or inspect the audio file

### Missing Artifact

Detect:

- expected request or output JSON is absent

Report:

- the missing file path

Recovery:

- rerun the previous stage

### Invalid JSON

Detect:

- generated artifact is malformed or missing required fields

Report:

- schema validation error

Recovery:

- regenerate the artifact with Codex

### Notion Publishing Failure

Detect:

- Notion API request fails
- Notion runtime connectivity fails

Report:

- the exact publish step and error message

Recovery:

- verify runtime connectivity and Notion configuration

### Environment Configuration Error

Detect:

- missing Notion token
- missing database IDs
- missing required environment variables

Report:

- which variable is missing

Recovery:

- rerun the local safe setup flow
- enter credentials only in the local hidden-input window
- never ask the user to edit `.env` or send credentials in chat
- rerun the failed deterministic step after configuration validates

### Automatic Vocabulary Scheduler Failure

Detect:

- scheduler status is not installed or loaded
- the bounded runtime report returns `SAFE_STOP`
- launchd stderr reports a macOS file-access denial

Report:

- installed/loaded state
- redacted stable error code
- whether any Codex or Vocabulary publisher call occurred

Recovery:

- keep the project at `~/EnglishAudioLearningAgent`
- never use `Documents`, `Desktop`, or `Downloads` as the production runtime
  directory
- inspect status, then reinstall only with the exact install confirmation
- preserve target-scoped state and never delete learning data during recovery

## 10. Quality Rules

### Analysis Quality

- focus on practical expressions
- prioritize business language
- include useful sentence patterns
- avoid weak or obvious items

### Vocabulary Quality

- preserve exact user intent
- use contextual meaning
- include realistic usage examples
- avoid generic dictionary output

### Reflection Quality

- identify learning patterns
- explain professional insights
- connect learning to work behavior
- avoid podcast recaps

## 11. Architecture Freeze Notes

### Frozen

- Notion schema
- workflow boundaries
- validation contracts

### Experimental

- deprecated direct OpenAI compatibility providers

### Provider Selection

Production defaults:

- `ENRICHMENT_PROVIDER=codex`
- `WEEKLY_REFLECTION_PROVIDER=codex`
- `WEEKLY_REVIEW_PROVIDER=codex`

`placeholder` is for deterministic tests. `openai` is deprecated compatibility
only. The production Skill does not require `OPENAI_API_KEY`.

### Reference Documents

- `docs/current_architecture.md`
- `docs/codex_skill_contract.md`

## 12. Operating Principle

Codex reasons. Python orchestrates and validates. Notion stores the knowledge
assets.

That separation is the current production contract for this Skill.
