# Notion 首次设置

本文档说明 English Audio Learning Agent（英语音频学习助手）的唯一正式 Notion
首次设置流程和职责边界：

```text
普通用户完成一个可见操作并确认
↓
Codex 自动推进
↓
本地 Python 确定性执行
↓
四个数据库创建与验证
```

普通用户不需要寻找项目目录，不需要输入 `cd`，不需要手动编辑 `.env`，也不
需要手动提取 Notion 页面编号。

## Notion 插件说明

使用英语音频学习助手不需要安装 Codex 的 Notion 插件。数据库创建、验证和
学习内容写入，由本地 Python 程序通过用户自己的 Notion 内部连接完成。
Notion 插件只是可选的搜索、读取和辅助查看工具。

插件授权不会传递给本地 Python，不能代替 `NOTION_TOKEN`，也不能代替本页
描述的 `setup_workspace` 第一次设置流程。正式系统没有第二条插件写入路径；
不要让插件和本地设置分别创建数据库。

## 1. 普通用户看到的逐步流程

普通用户一次只看到一个操作。Codex 必须等待当前回复，才能显示下一步。

```text
开发者页面已打开
↓
连接列表已打开
↓
连接页面已打开
↓
权限已确认
↓
密钥已保存
↓
已打开 Notion
↓
页面已创建
↓
集成已添加
↓
链接已复制
↓
本地安全设置
```

首次设置不再要求用户预先判断是否已有连接。开发者后台左侧入口使用“连接”；
普通 Notion 页面右上角授权入口使用“集成”。已有连接可以直接打开，新用户在
同一步创建连接。

每个回复节点的完整用户可见文案以 `skill/SKILL.md` 的
`User-Visible Notion Conversation Contract` 为准。验收提示词不得覆盖它。

普通用户看到的页面名称始终是“英语音频学习助手”。用户不需要判断技术授权或
数据库验证是否成功。

## 2. Codex 负责

在用户回复“链接已复制”前，Codex 只负责显示当前一步和等待确认，不得启动
本地安全设置。

收到“链接已复制”后，Codex：

1. 获取或定位完整项目。
2. 自动准备项目内运行环境。
3. 自动启动 `scripts/first_time_setup.py`。
4. 如果当前环境不能安全读取隐藏输入，尝试打开 `start_setup.command`。
5. 如果仍无法自动打开，在访达中打开正确项目目录，只要求用户双击
   `start_setup.command`。
6. 解释错误并提供当前步骤的恢复动作。

用户只在本地安全界面输入访问密钥和完整页面链接。Codex 不在聊天中接收这两项
内容，也不要求用户提取页面编号或数据库编号。

本地窗口把访问密钥标记为“第 1/2 步”，把页面链接标记为“第 2/2 步”。两项
内容都通过隐藏输入读取；每次按回车后立即显示“已接收”确认，但不显示原文。
失败提示只包含非敏感摘要，并明确提示重新双击 `start_setup.command`。

## 3. 本地 Python 负责

安全设置程序负责：

1. 验证访问密钥。
2. 验证页面是否允许内部连接访问。
3. 原子更新本地私密配置并限制文件权限。
4. 检查数据库编号配置状态。
5. 开始创建前记录安全恢复状态。
6. 每成功创建一个数据库就立即保存该数据库编号。
7. 重试时要求继续使用首次创建数据库时的同一个页面。
8. 如果页面不一致或旧设置缺少页面编号，在任何数据库操作前安全停止。
9. 页面一致后验证已保存编号，仅继续创建缺失数据库。
10. 使用 data source 接口原地补齐缺失字段，不删除未知字段或已有记录。
11. 类型冲突时安全停止，不擅自删除或改写现有数据。
12. 为三个正式关系配置 `data_source_id` 和单向 `single_property`。
13. 来源不明且没有安全恢复标记的部分配置仍会停止，避免重复数据库。
14. 字段、关系和工作区验证全部成功后才标记设置完成。

系统会对父页面链接进行标准化，因此带标题、不带标题、带短横线或不带短横线
的同一页面编号会被视为同一父页面。系统不会把一套数据库拆到两个父页面。

创建的数据库：

- `Podcast Library`（播客资料库）
- `Expression Database`（表达资料库）
- `Vocabulary Database`（词汇资料库）
- `Weekly Review`（每周复盘资料库）

`Weekly Review` 存储 `Weekly Reflection`（每周复盘内容）。

规范环境变量：

- `NOTION_PODCAST_LIBRARY_DATABASE_ID`
- `NOTION_EXPRESSION_DATABASE_ID`
- `NOTION_WEEKLY_REFLECTION_DATABASE_ID`
- `NOTION_VOCABULARY_DATABASE_ID`

`NOTION_WEEKLY_REVIEW_DATABASE_ID` 仅作为旧配置兼容别名保留。

## 4. 正式写入路径

Codex 的 Notion 插件不是当前正式写入路径。正式路径仍是：

```text
Codex 生成结构化内容
↓
本地 Python 验证
↓
本地 Python 调用 Notion 接口
↓
Notion 数据库
```

## 5. 成功结果

设置成功后，Codex 应报告四个数据库均已通过验证，并主动提示用户发送：

- 苹果播客单集链接
- 播客订阅源链接
- 本地音频文件

## 6. 最终备用命令

只有 Codex 自动执行和双击入口都失败时，才由 Codex 在正确项目目录中执行或
提供以下故障排查命令：

```bash
python3 -m venv .venv
./.venv/bin/python scripts/bootstrap_environment.py --skip-tests
./.venv/bin/python scripts/first_time_setup.py
```

不得把访问密钥拼接到任何命令中。
