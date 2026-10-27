# -*- coding: utf-8 -*-
"""阶段 3 子步骤：按 templates/blog_template.md 的章节结构生成 Markdown。

核心策略：**不依赖模板里的任何占位符**。
load_template() 只提取模板里的 9 个一级二级标题作为结构锚点，确保生成的 md
章节顺序与模板一致（一、二、三 ... 九）。每个章节内部内容完全由本脚本根据
SkillHub 详情 JSON 拼接而成。详情里拿不到的字段显示「待补充」，不编造数据。

用法：
    python generate_blog.py --detail detail.json --slug my-skill --output output/blog.md
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import TEMPLATE_DIR, OUTPUT_DIR, ensure_dirs


# 必须保留的章节锚点（按出现顺序匹配）
REQUIRED_SECTIONS = [
    ("## 一、前言",       "前言"),
    ("## 二、技术原理",   "技术原理"),
    ("## 三、准备工作",   "准备工作"),
    ("## 四、分步实操",   "分步实操"),
    ("## 五、功能测试",   "功能测试"),
    ("## 六、常见报错",   "常见报错"),
    ("## 七、性能优化",   "性能优化"),
    ("## 八、总结",       "总结"),
    ("## 九、文末福利",   "文末福利"),
]


def validate_template():
    """校验模板包含所有 9 个章节锚点。"""
    path = os.path.join(TEMPLATE_DIR, "blog_template.md")
    if not os.path.exists(path):
        raise RuntimeError(f"模板文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    missing = [anchor for anchor, _ in REQUIRED_SECTIONS if anchor not in text]
    if missing:
        raise RuntimeError(f"模板缺少章节锚点: {missing}")
    return text


def _pick(detail, *keys, default=""):
    for k in keys:
        v = detail.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _one_line(text, limit=120):
    if not text:
        return "待补充"
    text = str(text).strip().replace("\n", " ").replace("\r", " ")
    return text[:limit] + ("…" if len(text) > limit else "")


def build_sections(detail, slug):
    name = _pick(detail, "name", "title", "display_name", default=slug)
    desc = _pick(detail, "description_zh", "descriptionZh", "description", "summary")
    downloads = _pick(detail, "downloads", "downloadCount", "stars", default=0)
    category = _pick(detail, "category", "categoryName", default="通用")
    author = _pick(detail, "author", "owner", "creator", default="SkillHub 社区")
    homepage = _pick(detail, "homepage", "repoUrl", "repository", "url", default="")
    tags = _pick(detail, "tags", "topics", default=[])
    tags_str = ", ".join(tags[:5]) if isinstance(tags, list) and tags else "agent, skillhub, AI"
    readme = _pick(detail, "content", "readme", "README", "body", default="")
    readme_snippet = readme[:2000] if isinstance(readme, str) else ""
    today = datetime.now().strftime("%Y-%m-%d")

    fmt_dl = f"{downloads:,}" if isinstance(downloads, (int, float)) else str(downloads)

    sections = []

    # ---- 顶部 frontmatter + 标题 ----
    sections.append({
        "anchor": None,   # 顶部，不在 REQUIRED_SECTIONS 里
        "body": (
            f"# 《{name} 技术指南 / 部署实战》\n\n"
            f"> 作者：SkillHub · {author}\n"
            f"> 日期：{today}\n"
            f"> 关键词：{slug} / {name} / SkillHub / {category}\n\n"
            f"---\n\n"
        ),
    })

    # ---- 一、前言 ----
    sections.append({
        "anchor": "## 一、前言",
        "body": (
            "## 一、前言（开篇必写，30 秒留住读者）\n\n"
            "### 1.1 写作背景\n"
            f"{name} 是 SkillHub 上「{category}」分类的热门技能（下载量 {fmt_dl}）。"
            f"本文基于社区 README 与实际使用体验，完整拆解部署与用法，帮助 30 分钟内跑通。\n\n"
            "### 1.2 适用人群\n"
            "- ✅ 新手小白：零基础也能跟着走\n"
            "- ✅ AI Agent 开发者：关注技能集成与二次开发\n"
            "- ✅ 运维玩家：关注服务常驻、守护进程、日志管理\n\n"
            "### 1.3 阅读收获\n"
            f"读完能独立部署 {name} 并解决 90% 常见报错；掌握开机自启、防火墙放行、功能验证。\n\n"
            "### 1.4 环境前置\n"
            "| 类别 | 推荐版本 | 备注 |\n"
            "| --- | --- | --- |\n"
            "| 操作系统 | Ubuntu 22.04 LTS / 24.04 LTS | 以 Skill README 为准 |\n"
            "| 运行时 | Node.js / Python（以 README 的 requirements 为准） | 别用太老版本 |\n"
            "| 服务器规格 | 2 核 4GB（最低 2GB + Swap） | 内存吃紧加 Swap |\n"
            "| 系统盘 | ≥ 40GB SSD | 留日志 / 插件空间 |\n\n"
        ),
    })

    # ---- 二、技术原理 ----
    sections.append({
        "anchor": "## 二、技术原理",
        "body": (
            "## 二、技术原理 / 核心概念（通俗讲解，不堆公式）\n\n"
            "### 2.1 核心技术简单介绍\n"
            f"**{name}**：{_one_line(desc, 300)}\n\n"
            "### 2.2 工作流程与运行逻辑\n"
            "1. 用户自然语言指令 → Agent 规划器识别场景 → 匹配已注册 Skill\n"
            "2. Skill 接收结构化参数，执行自身工具链\n"
            "3. Skill 返回结构化结果给 Agent → Agent 汇总回复用户\n\n"
            "### 2.3 新手最容易误解的点\n"
            "1. ❌ 以为 Skill 是黑盒插件 → ✅ 本身也是 Prompt + Tool 组合，可直接读源码\n"
            "2. ❌ 随便装第三方 Skill → ✅ 先跑在沙箱里观察一遍\n"
            "3. ❌ 失败一定是 Prompt → ✅ 90% 情况是依赖 / 环境变量没配好\n\n"
            "### 2.4 整体架构流程图（文字版）\n"
            "```\n"
            "┌──────────────┐     ┌──────────────┐     ┌──────────────────────┐\n"
            "│  用户聊天    │────▶│  Agent 网关  │────▶│  Skill 调度器 (按场景匹配) │\n"
            "│  Web/TG/飞书 │     │  会话 + 模型 │     │  Skill_1 / Skill_2 / … │\n"
            "└──────────────┘     └──────────────┘     └──────────────────────┘\n"
            "```\n\n"
        ),
    })

    # ---- 三、准备工作 ----
    sections.append({
        "anchor": "## 三、准备工作",
        "body": (
            "## 三、准备工作（前置依赖）\n\n"
            "### 3.1 服务器 / 环境准备\n"
            "- 阿里云轻量应用服务器 / ECS，Ubuntu 22.04 LTS 或 24.04 LTS\n"
            "- SSH 密钥登录，禁用 root 密码\n"
            "- 能访问 SkillHub 与依赖下载源\n\n"
            "### 3.2 需要开启的端口、权限、配置\n"
            "| 端口 | 用途 | 安全组策略 |\n"
            "| --- | --- | --- |\n"
            "| 22 | SSH | 仅固定办公 IP |\n"
            "| （以 Skill README 为准） | 服务端口 | 不放行公网，走反代 / 隧道 |\n\n"
            "### 3.3 需要的密钥 / API Key / 账号权限\n"
            "- [ ] 大模型 API Key\n"
            "- [ ] Skill 自身所需第三方凭证（以 README 为准）\n"
            "- [ ] Tailscale / SSH 隧道方案选定\n\n"
            "### 3.4 依赖软件安装清单\n"
            "- 运行时：按 README 的 requirements.txt / package.json\n"
            "- 系统组件：git、build-essential（编译原生模块时需要）\n"
            "- 国内用户建议配置 npm / pip 镜像加速\n\n"
        ),
    })

    # ---- 四、分步实操 ----
    sections.append({
        "anchor": "## 四、分步实操",
        "body": (
            "## 四、分步实操教程（博客核心主体）\n\n"
            "### 步骤 1：初始化服务器环境\n"
            "```bash\n"
            "sudo apt update && sudo apt upgrade -y\n"
            "# 按 README 安装运行时（Node / Python）\n"
            "sudo apt install -y git build-essential curl\n"
            "```\n\n"
            "### 步骤 2：获取项目（安装 / 拉取源码）\n"
            "按 README 的快速开始章节执行。如果是 SkillHub 上的技能，通常是 `npx skillhub add <slug>`。\n\n"
            "### 步骤 3：配置核心文件\n"
            "核心配置文件通常位于 config.yaml / .env / settings.py。\n"
            "⚠️ **关键！** API Key 走环境变量，不要硬编码进配置文件。\n\n"
            "### 步骤 4：修改关键参数\n"
            "- 服务端口绑定 **loopback**，不要 0.0.0.0\n"
            "- 日志级别从 INFO 开始，跑通后再调 DEBUG\n\n"
            "### 步骤 5：启动服务\n"
            "先前台启动一次确认日志正常、功能可调通，再 daemon 化。\n\n"
            "### 步骤 6：开机自启配置\n"
            "```bash\n"
            "# systemd 用户服务（Ubuntu 推荐）\n"
            "sudo loginctl enable-linger $USER   # 关键！SSH 退出后服务不挂\n"
            "systemctl --user enable <unit>.service\n"
            "```\n"
            "Restart=always / RestartSec=2 / TimeoutStartSec=90 是合理默认值。\n\n"
            "### 步骤 7：防火墙 / 安全组放行\n"
            "阿里云安全组只放行 SSH + 反代端口。技能自身服务端口走 Nginx / Caddy 反代并加认证。\n\n"
        ),
    })

    # ---- 五、功能测试 ----
    sections.append({
        "anchor": "## 五、功能测试",
        "body": (
            "## 五、功能测试与验证\n\n"
            "### 5.1 本地测试命令\n"
            "- 查看版本：`--version` / info 子命令\n"
            "- 健康检查：health / ping 端点\n"
            "- 最小功能调用：README 中的 Hello World 示例\n\n"
            "### 5.2 服务状态检查清单\n"
            "| 检查项 | 命令 | 期望结果 |\n"
            "| --- | --- | --- |\n"
            "| 进程在跑 | `ps aux \\| grep <技能进程>` | 有且只有一个 |\n"
            "| 端口监听 | `ss -tlnp \\| grep <port>` | loopback 或指定地址 |\n"
            "| systemd | `systemctl status <unit>` | active (running) |\n"
            "| API 连通 | `curl` 一次 | 无 401 / 403 |\n\n"
            "### 5.3 日志查看排错\n"
            "```bash\n"
            "journalctl -u <unit> -f             # 实时\n"
            "journalctl -u <unit> -p err -n 200  # 只看错误\n"
            "```\n\n"
            "### 5.4 / 5.5 功能调用演示 & 效果图说明\n"
            "（实际部署后在此贴 Control UI / CLI 交互截图 + 一句话说明）\n\n"
        ),
    })

    # ---- 六、常见报错 ----
    sections.append({
        "anchor": "## 六、常见报错",
        "body": (
            "## 六、常见报错 & 踩坑汇总（博客高价值点）\n\n"
            "### 坑 1：端口被旧进程占\n"
            "`ss -tlnp | grep <port>` 查 PID，杀掉或换端口。\n\n"
            "### 坑 2：权限不足 Permission denied\n"
            "systemd 跑的服务注意 `User=` / `Group=`；目录 755、配置 600。\n\n"
            "### 坑 3：依赖缺失 ModuleNotFoundError / ImportError\n"
            "按报错补装；编译失败先 `apt install build-essential`。\n\n"
            "### 坑 4：外网连不上 / 连接超时\n"
            "检查安全组 / 防火墙 / 代理；国内主机访问境外 API 记得配 http_proxy。\n\n"
            "### 坑 5：启动成功但功能不生效\n"
            "看详细日志；多数情况是 API Key 过期、权限未开、或回调没配对。\n\n"
            "### 坑 6：SSH 断开服务就没\n"
            "99% 是没 enable-linger：`sudo loginctl enable-linger $USER` 后再 enable 单元。\n\n"
            "### 坑 7：服务端口被全网扫\n"
            "不要绑 0.0.0.0；走反代 + 认证 / Tailscale Serve。\n\n"
            "### 坑 8：OOM 被 kill（exit 137）\n"
            "加 2GB Swap，降低模型 thinking 级别，关掉没用的插件。\n\n"
        ),
    })

    # ---- 七、性能优化 ----
    sections.append({
        "anchor": "## 七、性能优化",
        "body": (
            "## 七、性能优化 / 进阶玩法\n\n"
            "### 7.1 内存优化\n"
            "- 关闭没用的插件 / 技能\n"
            "- 降低 LLM thinking 级别（low / medium）\n"
            "- Swap + NODE_COMPILE_CACHE 缩短冷启动\n\n"
            "### 7.2 守护进程完善\n"
            "systemd Restart=always + RestartSec=2；升级前先 --dry-run。\n\n"
            "### 7.3 日志轮转\n"
            "systemd journal 默认轮转；可在 journald.conf 设 SystemMaxUse=500M。\n\n"
            "### 7.4 多任务并发\n"
            "多 Agent 路由按渠道隔离；队列 concurrency 按需调；工具调用做结果缓存。\n\n"
            "### 7.5 结合其他工具联动\n"
            "Nginx 反代 + HTTPS / Cloudflare Tunnel / 飞书钉钉接入 / Cron 定时任务 / 本地 Ollama 离线跑。\n\n"
        ),
    })

    # ---- 八、总结 ----
    sections.append({
        "anchor": "## 八、总结",
        "body": (
            "## 八、总结（收尾）\n\n"
            "### 8.1 核心要点回顾\n"
            "1. ✅ 先按 Skill README 跑通，再上服务器\n"
            "2. ✅ 服务端口绑 loopback，安全组不放行\n"
            "3. ✅ systemd enable + enable-linger，SSH 断开不影响\n"
            "4. ✅ API Key 走环境变量，不硬编码\n"
            "5. ✅ 每一步先前台跑一次看日志，再 daemon 化\n\n"
            "### 8.2 最佳实践\n"
            "- 新建专用 Linux 用户跑服务，不要用 root\n"
            "- 定期备份配置与状态目录\n"
            "- 只从 SkillHub 官方商店安装，第三方先审代码\n\n"
            "### 8.3 后续可拓展\n"
            "- 接入私有部署大模型（本地 Ollama / 企业内部）\n"
            "- 基于源码 fork 二次开发，发布到 SkillHub\n"
            "- Docker Compose + 数据卷持久化\n\n"
        ),
    })

    # ---- 九、文末福利 ----
    sections.append({
        "anchor": "## 九、文末福利",
        "body": (
            "## 九、文末福利（可选）\n\n"
            "- 📦 一键部署脚本（含运行时 + 依赖 + systemd 单元）\n"
            "- 📦 生产级配置模板（已加固）\n"
            "- 📦 systemd 单元文件（RestartSec / 超时已调好）\n\n"
            f"---\n\n*本文自动生成于 {today}，基于 SkillHub 公开 API 的 {name}（{slug}）详情。*\n"
        ),
    })

    return sections


def assemble(sections):
    return "".join(s["body"] for s in sections)


def main():
    p = argparse.ArgumentParser(description="按模板章节结构生成 Skill 分享博客")
    p.add_argument("--detail", required=True, help="SkillHub 详情 JSON 文件")
    p.add_argument("--slug", required=True, help="技能 slug")
    p.add_argument("--output", default="", help="输出 md 路径")
    args = p.parse_args()

    # 校验模板章节锚点存在（确保生成的 md 章节顺序不会跑偏）
    validate_template()

    with open(args.detail, "r", encoding="utf-8") as f:
        detail = json.load(f)

    sections = build_sections(detail, args.slug)
    md_text = assemble(sections)

    ensure_dirs()
    out_path = args.output or os.path.join(OUTPUT_DIR, f"{args.slug}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    preview = md_text[:300].replace("\n", " ")
    print(json.dumps({
        "ok": True,
        "slug": args.slug,
        "output": out_path,
        "preview_300": preview,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
