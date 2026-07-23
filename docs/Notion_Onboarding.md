# Notion 首次设置

本文档说明 English Audio Learning Agent（英语音频学习助手）的唯一正式 Notion
首次设置流程：

```text
用户完成人工授权
↓
Codex 自动推进
↓
本地 Python 确定性执行
↓
四个数据库创建与验证
```

普通用户不需要寻找项目目录，不需要输入 `cd`，不需要手动编辑 `.env`，也不
需要手动提取 Notion 页面编号。

## 1. 用户创建内部连接

官方入口：

- https://www.notion.so/developers
- https://developers.notion.com/guides/get-started/internal-connections

1. 登录 Notion。
2. 创建新的内部连接。
3. 名称建议填写“英语音频学习助手”。
4. 选择目标工作空间。
5. 确认读取、插入和更新内容权限。
6. 复制访问密钥。

访问密钥不得发送到 Codex 对话，不得写入普通终端命令，不得提交到 GitHub。
后续只在本地安全输入界面粘贴。

## 2. 用户创建父页面

官方说明：

- https://www.notion.com/help/create-your-first-page

1. 在 Notion 中创建空白页面。
2. 名称建议填写“英语音频学习助手”。
3. 不要手动创建数据库。

## 3. 用户把内部连接添加到父页面

1. 打开父页面。
2. 点击右上角三个点。
3. 找到“连接”或同等含义的入口。
4. 添加“英语音频学习助手”内部连接。
5. 确认连接可以访问当前页面和子页面。

新连接默认没有页面权限。跳过本步骤会导致数据库创建失败。

## 4. 用户复制完整父页面链接

官方说明：

- https://www.notion.com/help/share-your-work

打开父页面，点击“共享”和“复制链接”。不需要公开页面，不需要从链接中截取
编号。本地程序直接接收完整链接并自动提取页面编号。

## 5. Codex 自动启动安全设置

用户回复“继续”后，Codex：

1. 获取或定位完整项目。
2. 自动准备项目内 `.venv`。
3. 自动启动 `scripts/first_time_setup.py`。
4. 如果当前环境不能安全读取隐藏输入，尝试打开 `start_setup.command`。
5. 如果仍无法自动打开，在访达中打开正确项目目录，只要求用户双击
   `start_setup.command`。

用户只在本地界面输入：

- Notion 访问密钥，输入内容不可见。
- Notion 父页面完整链接。

手动终端命令只属于最终备用方案。

## 6. 本地 Python 创建和验证工作区

安全设置程序：

1. 原子更新 `.env`，并保留已有配置。
2. 把 `.env` 权限限制为当前用户可读写。
3. 检查数据库编号配置状态。
4. 在四个编号全部为空时创建数据库。
5. 在四个编号全部存在时跳过创建并直接验证。
6. 在部分编号存在时安全停止，避免重复数据库。
7. 运行现有工作区验证逻辑。

创建的数据库：

- `Podcast Library`（播客资料库）
- `Expression Database`（表达资料库）
- `Weekly Review`（每周复盘资料库）
- `Vocabulary Database`（词汇资料库）

`Weekly Review` 存储 `Weekly Reflection`（每周复盘内容）。

规范环境变量：

- `NOTION_PODCAST_LIBRARY_DATABASE_ID`
- `NOTION_EXPRESSION_DATABASE_ID`
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
- `NOTION_VOCABULARY_DATABASE_ID`

`NOTION_WEEKLY_REVIEW_DATABASE_ID` 仅作为旧配置兼容别名保留。

## 7. 正式写入路径

Notion 连接器不是当前正式写入路径。正式路径仍是：

```text
Codex 生成结构化内容
↓
本地 Python 验证
↓
本地 Python 调用 Notion 接口
↓
Notion 数据库
```

## 8. 成功结果

设置成功后，Codex 应报告四个数据库均已通过验证，并主动提示用户发送：

- 苹果播客单集链接
- 播客订阅源链接
- 本地音频文件

## 9. 最终备用命令

只有 Codex 自动执行和双击入口都失败时，才由 Codex 在正确项目目录中执行或
提供以下故障排查命令：

```bash
python3 -m venv .venv
./.venv/bin/python scripts/bootstrap_environment.py --skip-tests
./.venv/bin/python scripts/first_time_setup.py
```

不得把访问密钥拼接到任何命令中。
