---
name: skillhub-blog-share
description: 抓取 SkillHub 热门技能，通过企业微信卡片让用户选择并审核，按技术分享博客模板生成 Markdown 文档，审核通过后上传阿里云 OSS。当用户说「从 SkillHub 挑热门技能写博客」「推送 SkillHub 技能给我选」「生成技能分享文档并发我审核」时使用。
---

# SkillHub 热门技能 → 博客分享技能

## 准备工作（必须先做）

```bash
# Python 依赖（含 wecom-aibot-sdk-python 0.1.7 pin）
pip install wecom-aibot-sdk-python==0.1.7 oss2 requests
```

sqlite3 `account_config` 表需有以下启用记录（`env_key` + 字段）：

| env_key | 必填字段 | 用途 |
| --- | --- | --- |
| `WECOM_BOT_ID` | `config_value` | 企业微信 AI Bot ID |
| `WECOM_BOT_SECRET` | `config_value` | 企业微信 AI Bot Secret |
| `OSS_VALUE` | `endpoint` / `access_key_id` / `access_key_secret_encrypted` / `bucket` | 阿里云 OSS |

环境变量（运行脚本前设置）：

| 变量 | 用途 |
| --- | --- |
| `SQLITE_DB_PATH` | sqlite3 数据库绝对路径（所有凭证从这里读） |

**启动顺序要求**：运行此技能的任何阶段前，**必须先在独立终端启动企业微信 Bot 常驻进程**，然后再触发抓取。

```bash
# 终端 A：启动常驻进程（不要关，直到整个分享流程结束）
cd .trae/skills/skillhub-blog-share
python scripts/wecom_bot.py --db /path/to/your.db
```

目录约定：

```
.trae/skills/skillhub-blog-share/
├── SKILL.md
├── scripts/
│   ├── common.py           # sqlite3 凭证 + session JSON + SDK 工厂
│   ├── fetch_skills.py     # 阶段 1：调 SkillHub 列表 API
│   ├── fetch_detail.py     # 阶段 3 子步骤：拉详情
│   ├── generate_blog.py    # 阶段 3 子步骤：按模板生成 md
│   ├── upload_oss.py       # 阶段 5：上传 OSS
│   └── wecom_bot.py        # 常驻 WebSocket 进程 + 状态机
├── templates/
│   └── blog_template.md    # 技术分享博客模板
├── state/                  # 运行时 session JSON（.gitkeep 占位，不提交实际内容）
└── output/                 # 生成的 md 临时目录
```

---

## 工作流（按此顺序执行）

### 阶段 1：抓取热门列表

```bash
python scripts/fetch_skills.py --output state/latest_skills.json
```

调用 `GET https://api.skillhub.cn/api/skills?sortBy=downloads&pageSize=10`，
提取每条技能的 `slug`、`name`、`description_zh`（缺失回退 `description`）、`downloads`、`category`。
**不要在这一步调详情接口**，列表字段足够做选择卡片。

拿到 JSON 后，让 Agent 构造 `state/session_{session_id}.json`：

```json
{
  "session_id": "<uuid4 前 16 位>",
  "stage": "awaiting_selection",
  "chat_id": "<从企业微信上下文拿，或先空着由 Bot 回调时补齐>",
  "userid": "<从企业微信上下文拿，或先空着>",
  "skills": "<list 中 10 条>",
  "created_at": "<当前 ISO 时间>"
}
```

写入 `state/session_{session_id}.json`，标记 `stage="awaiting_selection"`。

### 阶段 2：企业微信「选择卡片」

**不需要 Agent 手动推送**。`wecom_bot.py` 常驻进程每 5 秒扫描 `state/` 目录，
遇到 `stage="awaiting_selection"` 且未标记 `_polled` 的 session，会自动构造
`button_interaction` 模板卡片并调用 `client.send_message(chat_id, {...})` 推送。

卡片正文列出 10 条技能的 `name + 一句话描述 + 下载量`，每条对应一个按钮，
按钮 `key` 为 `select_skill:<slug>`。

### 阶段 3：监听选择回调，生成文档

`wecom_bot.py` 已注册 `event.template_card_event` 回调。收到 `select_skill:<slug>` 后，
进程内部串行执行：

1. 调 `GET https://api.skillhub.cn/api/v1/skills/<slug>` 获取完整详情（含 README / content）。
2. 读取 `templates/blog_template.md`，将详情中的名称、描述、核心能力、使用场景等填入对应章节。
3. 模板中无法从详情直接映射的章节（如「常见报错 & 踩坑汇总」「性能优化」等），
   按 SkillHub / 通用 AI Agent 部署常识做**合理占位**，不编造不存在的接口或数据。
4. 生成 `.md` 文件，保存到 `output/{slug}-{session_id[:8]}.md`。
5. 把 `selected_slug`、`detail_json`、`markdown_path` 写回 session JSON，标记 `stage="awaiting_review"`。

### 阶段 4：企业微信「审核卡片」

同样由 `wecom_bot.py` 自动推送第二张 `button_interaction` 卡片。
正文展示文档标题和前 300 字摘要，按钮为：

- `review:approve:<session_id>` — 审核通过，上传 OSS
- `review:reject:<session_id>` — 驳回，中止流程

### 阶段 5：审核回调，上传 OSS

`wecom_bot.py` 收到 `review:approve`：

1. 用 `oss2.Auth + Bucket.put_object` 上传 Markdown。
2. 凭证从 sqlite3 读 `OSS_VALUE`，不硬编码。
3. Object 路径固定为 `blog/skillhub/{slug}/{YYYYMMDD-HHMMSS}-{uuid8}.md`。
4. 生成 7 天签名 URL（Bucket 私有时）。
5. 通过 `client.send_message(chat_id, text)` 把 OSS key 和下载地址回复给用户。
6. session 标记 `stage="done"`。

收到 `review:reject`：session 标记 `stage="rejected"`，回复「已取消，文档未上传」。

---

## 关键约束（必须遵守）

1. **两处企业微信交互都是异步回调**，不能写成同步阻塞等待。
   `wecom_bot.py` 必须作为常驻进程运行；SKILL 指令要求 TRAE 先在独立终端启动它，再触发抓取。

2. **状态文件是会话串联的唯一依据**。每一步先读 `state/session_{session_id}.json`，
   确认当前 `stage` 再执行下一阶段，防止重复推送或跳过步骤。
   `awaiting_selection → awaiting_review → done / rejected` 是严格单向状态机。

3. **SkillHub 公开接口无需鉴权，但不得滥用**：列表只调一次，详情仅在用户选定后调一次。

4. **阿里云凭证和企微 bot_id / secret 全部从 sqlite3 读取**，
   与 github-trending-share 技能共享同一 `account_config` 表。
   绝对不在脚本中硬编码 AK/SK / bot_id / secret / webhook。

5. **生成的 Markdown 必须保留 `templates/blog_template.md` 的章节结构**，
   不得增删一级标题（一、二、三 … 八、九）。

6. **Session 文件留在 `state/` 目录**，用于追溯。
   `.gitkeep` 占位，实际 session JSON 不应提交到版本库。

7. **不编造 SkillHub 不存在的字段或接口**。API 字段名以实际返回为准；
   拿不到的字段在模板里显示 `待补充`，不凭空造内容。

---

## 验收标准（自检）

- [ ] `python scripts/fetch_skills.py` 能独立运行并打印 10 条技能的 slug 和 name。
- [ ] `wecom_bot.py` 作为常驻进程启动后，向 `state/` 目录写入 `stage="awaiting_selection"` 的 session，
      企微能收到选择卡片；点击任一技能，`output/` 下出现对应 Markdown 文件。
- [ ] 审核卡片能收到；点击「通过」后 OSS 对应路径可访问，点击「驳回」后不执行上传。
- [ ] 全程无硬编码凭证；`state/session_*.json` 记录了完整流程状态，可追溯。
