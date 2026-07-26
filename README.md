# English Audio Learning Agent

English Audio Learning Agent is a **Codex Skill** for turning podcast episodes,
podcast RSS feeds, local audio files, and user-highlighted vocabulary into
structured English learning knowledge in Notion.

This repository is designed for a Skill-first workflow:

- **Codex** provides reasoning, language analysis, and content generation
- **Python** handles orchestration, validation, file processing, and Notion
  synchronization
- **Notion** stores the learning assets

The production architecture is:

```text
Codex Skill
↓
Local Python scripts
↓
Generated artifacts
↓
Validation
↓
Notion
```

Current state:

- Pure Codex Skill artifact runtime is the production default
- the pipeline and Notion publishing are stable
- direct OpenAI providers are deprecated compatibility paths only
- `OPENAI_API_KEY` is not required for the production Skill workflow
- Podcast, targeted Vocabulary, Weekly Reflection, and Automatic Vocabulary
  Owner Acceptance all pass
- adding an exact pink highlight is the only normal Vocabulary capture action
- a bounded macOS scheduler checks for new highlights every 60 seconds
- new highlights wait for a 90-second quiet period before Codex enrichment
- exact occurrence state, Target Binding, strict validation, and idempotent
  publishing are active
- the engineering status is
  `ENGINEERING_COMPLETE_READY_FOR_EXTERNAL_USER_TESTING`
- external-user sessions remain 0
- external-user validation has not started

For the production runtime contract, read:

- [skill/SKILL.md](skill/SKILL.md)
- [docs/current_architecture.md](docs/current_architecture.md)
- [docs/codex_skill_contract.md](docs/codex_skill_contract.md)

## What This Skill Does

The Skill helps a user:

1. analyze a podcast or audio source
2. extract learning-friendly expressions
3. capture vocabulary from user highlights
4. generate weekly reflection artifacts
5. publish the final knowledge assets into Notion

## 中文用户入口

普通用户请先阅读：

- [英语音频学习助手用户指南](docs/USER_GUIDE_ZH.md)
- [Notion 首次设置](docs/Notion_Onboarding.md)

## 安装与第一次设置

第一次安装时，把下面这段话发送给 Codex：

```text
请从下面的项目安装英语音频学习助手：

https://github.com/chenhanyue228-rgb/english-podcast-learning-agent

安装成功后，请直接在当前对话中带我继续第一次设置。
```

仓库地址只用于第一次安装。安装完成后，Codex 应在当前对话中直接询问：

```text
英语音频学习助手已经安装完成。

现在可以在当前对话中继续第一次设置。

是否现在继续？
```

用户回复“继续”即可。当前对话优先继续，不强制新建对话，也不要求用户记住
操作指令。

如果当前对话尚未刷新新安装的技能，新建对话作为第一次备用；如果新对话仍
未识别，重启 Codex 作为第二次备用。

备用指令：

```text
请使用英语音频学习助手，带我完成第一次设置。
```

只安装 `skill/` 文件夹不能代替完整本地运行环境。Codex 会自动获取或定位
完整项目，准备项目内 `.venv`，并启动本地安全设置工具。普通用户：

- 不需要寻找项目目录
- 不需要输入 `cd`
- 不需要手动创建虚拟环境
- 不需要手动编辑 `.env`
- 不需要手动运行数据库初始化或验证命令
- 不需要手动提取 Notion 页面编号

macOS 自动词汇同步要求完整项目位于系统保护目录之外。默认安装位置是
`~/EnglishAudioLearningAgent`；不要把正式运行目录放在 `Documents`、
`Desktop` 或 `Downloads` 中。

Notion 设置使用一条统一路径，一次只显示一个操作，用户完成并确认后才进入
下一步。开发者后台中的入口名称是“连接”，普通 Notion 页面中的授权入口名称是
“集成”。用户依次打开或创建连接、确认内容权限、保存访问令牌、创建
“英语音频学习助手”页面、把集成添加到页面并复制页面链接。访问密钥和页面链接
只输入本地安全窗口，不得发送到 Codex 对话。

### Notion 连接边界

使用英语音频学习助手不需要安装 Codex 的 Notion 插件。数据库创建、验证和
学习内容写入，由本地 Python 程序通过用户自己的 Notion 内部连接完成。
Notion 插件只是可选的搜索、读取和辅助查看工具。

- 插件授权不会传递给本地 Python。
- 插件不能代替 `NOTION_TOKEN` 或 `setup_workspace` 第一次设置流程。
- 正式写入只有“Codex artifact → 本地 Python → Notion”一条路径。
- 不要让插件和本地设置分别创建数据库，以免出现两套工作区。

安全设置会自动创建或验证：

- Podcast Library（播客资料库）
- Expression Database（表达资料库）
- Vocabulary Database（词汇资料库）
- Weekly Review（每周复盘资料库，存放 Weekly Reflection 每周复盘内容）

## 日常使用

设置完成后，用户直接发送：

```text
请使用英语音频学习助手处理这个播客：

<粘贴播客链接>
```

Codex 自动推进音频获取、文字稿生成、分析 artifact 生成、Python 验证和
Notion 发布，并返回最终页面链接。用户不需要复制后台执行清单或手动运行主要
流程命令。

## Supported Workflows

Supported v1 inputs are:

- Apple Podcasts episode URL
- Podcast RSS feed
- Local audio file

## Out of Scope for v1

YouTube support is intentionally excluded from the v1 product. The Skill
focuses on stable English audio sources and avoids platform authentication,
anti-bot behavior, and downloader maintenance. Experimental YouTube code may
remain in the repository for possible future evaluation, but it is not part of
the supported runtime contract.

### Podcast Analysis

```text
Source
↓
Transcript
↓
Codex analysis
↓
Validation
↓
Notion publish
```

### Vocabulary Capture

```text
Exact Pink Highlight
↓
Bounded Scheduled Detection
↓
90-Second Quiet Period
↓
Codex Enrichment
↓
Strict Python Validation
↓
Vocabulary Database
```

The user highlights exactly the word or phrase they want to learn. The system
does not expand it from context or merge it with nearby text. Existing
highlights are baselined on first enablement and are not backfilled.

### Weekly Reflection

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

## Basic Troubleshooting

- If a command fails, check the error message first. The pipeline stages are
  intentionally separated, so failures are usually localizable.
- If Notion publishing fails, verify the environment variables and runtime
  connectivity.
- If target binding fails, do not retry a writer. Run the read-only diagnosis
  and verify that all five target values belong to one parent page.
- If scheduler status is loaded but its stderr reports a macOS permission
  denial, use the supported project location `~/EnglishAudioLearningAgent`.
  Do not run the production scheduler from `Documents`, `Desktop`, or
  `Downloads`.
- If an artifact is missing, rerun the previous stage rather than manually
  editing generated files.
- If you are unsure which command to use, start with the Skill manifest:
  [skill/SKILL.md](skill/SKILL.md)

## Advanced / Developer and Recovery Commands

The commands below are for repository development or final recovery when Codex
automation and `start_setup.command` cannot continue. They are not required in
the normal user journey.

Prepare a local environment:

```bash
python3 -m venv .venv
./.venv/bin/python scripts/bootstrap_environment.py --skip-tests
```

Run the safe first-time setup:

```bash
./.venv/bin/python scripts/first_time_setup.py
```

Developer-only Skill symlink:

```bash
mkdir -p "$HOME/.codex/skills"
ln -s "$(pwd)/skill" "$HOME/.codex/skills/english-audio-learning-agent"
```

Workflow commands:

- `./.venv/bin/python src/main.py "<source>"`
- `./.venv/bin/python src/main.py "<source>" --transcript-json data/transcripts/<file>.json --analysis-json data/analysis/<file>.json`
- `./.venv/bin/python src/main.py --weekly-reflection`
- `./.venv/bin/python src/main.py --weekly-reflection --dry-run`
- `./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py status`
- `./.venv/bin/python scripts/run_automatic_vocabulary_once.py`
- `./.venv/bin/python -m pytest`

Install the bounded scheduler:

```bash
./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py install \
  --confirmation INSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT
```

Stop the scheduler without deleting state or learning data:

```bash
./.venv/bin/python scripts/manage_automatic_vocabulary_scheduler.py uninstall \
  --confirmation UNINSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT
```

Read-only Notion target diagnosis:

```bash
./.venv/bin/python scripts/notion/diagnose_target_binding.py
```

Legacy compatibility commands such as `--weekly-review` and
`--sync-vocab-comments` remain available for existing local workflows, but
they are not part of the primary v1 user journey.
`--publish-highlight-vocab PAGE_ID` remains a Developer/recovery command.
Automatic exact pink-highlight capture is the production Vocabulary workflow.

## Documentation

- [Chinese user guide](docs/USER_GUIDE_ZH.md)
- [Notion onboarding](docs/Notion_Onboarding.md)
- [Skill manifest](skill/SKILL.md)
- [Current architecture](docs/current_architecture.md)
- [Codex Skill contract](docs/codex_skill_contract.md)
- [Next steps](docs/next_steps.md)
- [Notion target binding](docs/acceptance/notion_target_binding.md)
