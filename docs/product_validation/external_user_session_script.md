# External User Session Script

## Activation Hold

Do not start External User Session #1 yet. Automatic Vocabulary Sync is
Owner-approved for Phase 0 architecture and feasibility but is not implemented
or accepted. External-user sessions remain 0 and readiness remains
`NOT_READY_FOR_EXTERNAL_USERS`.

The former explicit “同步生词” journey below is suspended. It must not be read
to a participant or used to count a completed core session.

## Moderator Opening

Read this to the participant:

> 今天我们想了解你第一次使用“英语音频学习助手”的真实体验。请像平时一样操作，并把你的想法说出来。这里没有正确答案，我们测试的是产品，不是你。
>
> 整个过程大约需要 45-60 分钟。请使用不敏感的音频内容。不要把任何密钥、密码、私人 Notion 链接或私人学习内容发送给我。遇到不清楚的地方，请先按你自己的理解继续。

Start the session timer after the participant agrees.

## Task 1: Install and Discover the Skill

Tell the participant:

> 请安装“英语音频学习助手”，然后让它告诉你目前支持哪些音频输入。

Do not tell the participant where a repository directory is located, what
command to run, or how Skill discovery works internally.

Record:

- whether installation completed;
- whether the Skill was discoverable in the current conversation;
- participant questions;
- any restart or new-conversation requirement;
- time-to-environment-ready when the Skill and local environment are usable.

## Task 2: Set Up Notion

Tell the participant:

> 请让英语音频学习助手带你完成第一次 Notion 设置。请按照它一次给出的一个步骤操作。

Do not combine or paraphrase the product's Notion instructions. Do not ask the
participant to send a token, page link, or identifier to the observer.

Record:

- whether the participant understood each step;
- whether setup completed without outside explanation;
- whether the four learning databases were created and validated by the
  product;
- any point where the participant expected different behavior.

## Task 3: Process One Audio Source

Tell the participant:

> 请选择一个不包含私人或公司敏感信息的英语音频。可以使用 Apple Podcasts 单集链接、Podcast RSS，或本地音频文件。请让英语音频学习助手把它整理成学习内容并保存到 Notion。

The participant chooses the source. Do not substitute a fixture, sample
artifact, or fabricated transcript.

Record:

- source type only;
- whether the product accepted the source;
- any waiting or recovery step;
- whether a Podcast learning page appeared in Notion;
- time-to-first-Notion-page.

## Task 4: Inspect Learning Assets

Tell the participant:

> 请在新生成的学习页面里浏览内容，找到一条对你有价值的 Podcast 学习观点，并查看至少一个你可能在工作中使用的 Expression。

Then ask:

> 哪一项内容对你最有价值？为什么？

Do not suggest which insight or Expression to choose. Do not record the
learning text verbatim.

Record time-to-first-value when the participant identifies a personally useful
learning asset.

## Task 5: Select Personal Vocabulary

**Suspended until automatic synchronization is implemented and accepted.**

Tell the participant:

> 请在这个 Podcast 学习页面中，把至少一个你想学习的英文单词或表达设为粉色高亮。只高亮你真正想保存的文字。

Do not suggest a word, expand the participant's selection, or interpret a
larger phrase from the surrounding sentence.

Record:

- whether the participant found the pink highlight action;
- number of selected targets, not their private content;
- any confusion about what would be saved.

## Task 6: Synchronize Vocabulary

**Suspended. Do not tell the participant to say “同步生词”, provide a page ID,
or run a command.**

The replacement journey will be published only after bounded automatic
detection, quiet-period handling, exact occurrence identity, isolated Codex
enrichment, and idempotent Notion publishing pass implementation and
acceptance. Do not invent interim instructions.

## Task 7: Conditional Weekly Reflection

First determine only from the product's normal behavior whether the workspace
contains enough real learning data for a Weekly Reflection.

If data is sufficient, tell the participant:

> 请让英语音频学习助手生成本周学习复盘，并在 Notion 中查看结果。请告诉我它是否帮助你理解这一周学到了什么。

If data is insufficient, tell the participant:

> 当前真实学习数据还不足以形成有意义的本周复盘。我们会把这一项记录为后续验证，不会为了测试而创建虚假学习数据。

Do not add fake Podcasts, Expressions, Vocabulary, or dates. Record Weekly as:

- completed;
- failed;
- deferred because real learning data was insufficient.

## Closing Questions

Ask:

1. 哪一步最容易？
2. 哪一步最让你困惑？
3. 如果明天再次使用，你觉得自己能独立完成吗？
4. 你最希望产品先解决什么问题？
5. 你愿意再次使用这个助手吗？为什么？

Thank the participant and stop the timer. Remind them that no credentials or
private learning content will be included in the report.
