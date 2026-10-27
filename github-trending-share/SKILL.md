---
name: github-trending-share
description: 抓取 GitHub Trending 前5热门项目，获取 README 与 GitHub API 元数据，生成中文素材（概述、热点、技术栈、场景、上手）经企业微信审核后入库，再按《技术分享博客模板》九大章节生成技术分析博客，审核后上传阿里云 OSS 返回下载地址。当用户要求分享今日 GitHub 热点、trending 摘要、开源项目推送时使用。不用于普通 GitHub 搜索。
---

# GitHub Trending 热点分享

通过两个脚本完成"抓取→摘要→审核入库→分享文档→审核发布 OSS"的闭环。所有敏感配置从服务器 sqlite3 数据库 `account_config` 表按 `env_key` 读取，审核记录写入 `approval_log` 表。

## 前置条件

- 数据库路径：环境变量 `SQLITE_DB_PATH`，或运行时用 `--db` 传入。
- `account_config` 表已有 `env_key='WEIXIN_WEBHOOK'`（取 `webhook_url`）和 `env_key='OSS_VALUE'`（取 `endpoint`/`access_key_id`/`access_key_secret_encrypted`/`bucket`）的启用记录。
- Python 依赖：`requests`、`oss2`（缺失时先 `pip install requests oss2`）。
- 博客模板：`templates/blog_template.md`（《技术分享博客模板》，九大章节），脚本生成前会校验章节锚点。

## 工作流

### 阶段1：抓取 trending 并推送候选

```bash
python scripts/trending_fetch.py --fetch --details
```

输出前5项目的 JSON（含 repo、stars、forks、language、license、topics、homepage、description、readme 正文）与 `approval_id`，同时企业微信已收到候选列表。

### 阶段2：生成结构化中文素材（由你完成，不调脚本）

阅读阶段1输出中每个项目的 description、topics 与 readme，为每个项目产出一组 JSON 字段（阶段4博客按《技术分享博客模板》填充各章节所需素材）：

```json
{
  "summary_zh": "项目是什么+解决什么问题+技术栈+Star数（150-300字）",
  "hotspots": "核心热点：为什么现在火、近期亮点（Markdown 列表）",
  "tech_analysis": "技术栈解析：语言/框架/架构特点（Markdown 段落）",
  "scenarios": "应用场景：适合谁用、典型用例（Markdown 列表）",
  "getting_started": "快速上手命令（如 pip install xxx / git clone ...）"
}
```

### 阶段3：用户选定项目并入库

向用户展示5个摘要，请用户回复序号（1-5）。拿到序号后，把阶段1该项目输出的元数据字段与阶段2的素材字段合并为一个 JSON，通过 `--meta` 传入：

```bash
python scripts/trending_fetch.py --approve <序号> --approval-id <阶段1的approval_id> \
  --summary "<summary_zh 内容>" --meta '<合并后的完整JSON>'
```

该项目连同素材以 `approval_status='approved'` 写入 `approval_log.approval_data`。

### 阶段4：生成技术分析博客并推送审核

```bash
python scripts/share_publish.py --generate
```

读取 `approval_log` 中最近一条审批通过记录的素材，按 `templates/blog_template.md`《技术分享博客模板》的九大章节结构（前言/技术原理/准备工作/分步实操/功能测试/常见报错/性能优化/总结/文末福利）生成含 frontmatter 的技术分析博客 markdown，推送企业微信审核，输出新的 `approval_id` 与文档内容。把文档内容展示给用户。素材字段缺失时对应位置显示「待补充」，不要伪造数据。

### 阶段5：审核通过后上传 OSS

用户确认通过后：

```bash
python scripts/share_publish.py --approve --approval-id <阶段4的approval_id>
```

上传阿里云 OSS，返回签名下载地址（7天有效），并把 URL 回写 `approval_log`。把下载地址告知用户。

## 注意

- 阶段1/4 的 `approval_id` 必须原样传递给对应 `--approve` 调用。
- 企业微信 markdown 消息有 4000 字符上限，脚本已截断。
- 解析失败（页面结构变化）时脚本会报错退出，不要伪造数据。
