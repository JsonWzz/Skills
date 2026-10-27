# -*- coding: utf-8 -*-
"""
脚本2：读取 approval_log 中最近一条审批通过的中文摘要，生成热点开源项目分享 markdown，
企业微信推送审核，审核通过后上传阿里云 OSS 并返回下载地址。

用法：
  阶段A 生成分享文档并推送审核：
      python share_publish.py --generate [--db /path/to.db]
  阶段B 审核通过后上传 OSS：
      python share_publish.py --approve --approval-id <id> [--db ...]

依赖：oss2（pip install oss2）、requests
"""
import argparse
import json
import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import send_wecom, get_db_conn, get_config, insert_approval, finish_approval


def get_latest_approved(db):
    """取最近一条 approval_status='approved' 且含 approval_data 的记录。"""
    with get_db_conn(db) as conn:
        row = conn.execute(
            "SELECT * FROM approval_log WHERE approval_status='approved' "
            "AND approval_data IS NOT NULL AND approval_data != '' "
            "ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise RuntimeError("approval_log 中没有已审批通过的项目记录，请先运行脚本1完成审核")
    return json.loads(row["approval_data"])


def _fmt_num(n):
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(n) if n else "N/A"


# 模板：templates/blog_template.md（《技术分享博客模板》），九大章节锚点必须齐全
TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "blog_template.md")

REQUIRED_SECTIONS = [
    "## 一、前言", "## 二、技术原理", "## 三、准备工作", "## 四、分步实操",
    "## 五、功能测试", "## 六、常见报错", "## 七、性能优化", "## 八、总结",
    "## 九、文末福利",
]

RUNTIME_MAP = {
    "Python": "Python 3.10+ / pip",
    "JavaScript": "Node.js 22 LTS+ / npm",
    "TypeScript": "Node.js 22 LTS+ / pnpm",
    "Go": "Go 1.22+ / go modules",
    "Rust": "Rust stable / cargo",
    "Java": "JDK 17+ / Maven 或 Gradle",
    "C++": "GCC 12+ / CMake",
    "C": "GCC 12+ / Make",
}


def validate_template():
    """校验模板文件存在且包含全部 9 个章节锚点，保证生成结构不跑偏。"""
    if not os.path.exists(TEMPLATE_PATH):
        raise RuntimeError(f"模板文件不存在: {TEMPLATE_PATH}")
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        text = f.read()
    missing = [a for a in REQUIRED_SECTIONS if a not in text]
    if missing:
        raise RuntimeError(f"模板缺少章节锚点: {missing}")


def build_markdown(data):
    """按《技术分享博客模板》九大章节结构生成技术分析博客。

    data 来自 approval_log.approval_data；字段缺失时显示「待补充」，不编造数据。
    """
    validate_template()
    today = datetime.now().strftime("%Y-%m-%d")
    repo = data.get("repo", "unknown/repo")
    name = repo.split("/")[-1]
    stars = _fmt_num(data.get("stars"))
    forks = _fmt_num(data.get("forks"))
    issues = _fmt_num(data.get("open_issues"))
    language = data.get("language") or "N/A"
    license_ = data.get("license") or "Unknown"
    homepage = data.get("homepage") or ""
    topics = data.get("topics") or []
    created = data.get("created_at") or ""
    pushed = data.get("pushed_at") or ""
    url = data.get("url") or f"https://github.com/{repo}"
    branch = data.get("default_branch") or "main"
    description = data.get("description") or ""
    overview = data.get("summary_zh") or "（待补充）"
    hotspots = data.get("hotspots") or "（待补充：请结合 README 与提交活跃度补充）"
    tech_analysis = data.get("tech_analysis") or f"该项目以 {language} 为主，采用 {license_} 开源协议。"
    scenarios = data.get("scenarios") or "（待补充：请结合项目定位补充适用场景）"
    getting_started = data.get("getting_started") or f"git clone {url}.git"
    runtime = RUNTIME_MAP.get(language, f"{language} 对应官方最新稳定版运行时")
    readme_url = f"{url}/blob/{branch}/README.md"
    tags_str = ", ".join(topics[:5]) if topics else "开源, GitHub, Trending"

    parts = [
        "---",
        f'title: "热点开源项目技术分析 | {name}"',
        f"date: {today}",
        f"tags: [{tags_str}]",
        f'categories: ["开源项目", "技术分享"]',
        f"keywords: [{name}, {language}, GitHub Trending]",
        "---",
        "",
        f"# 《{name} 技术指南 / 实战入门》",
        "",
        f"> 作者：GitHub Trending 热点分享",
        f"> 日期：{today}",
        f"> 关键词：{name} / {language} / {tags_str}",
        "",
        "---",
        "",
        # ---- 一、前言 ----
        "## 一、前言（开篇必写，30 秒留住读者）",
        "",
        "### 1.1 写作背景",
        f"`{repo}` 是今日 GitHub Trending 热门项目（⭐ {stars} / 🍴 {forks} / {language} / {license_}）。",
        "",
        overview,
        "",
        "### 1.2 核心热点",
        "",
        hotspots,
        "",
        "### 1.3 适用人群",
        "",
        scenarios,
        "",
        "### 1.4 阅读收获",
        f"读完这篇，你能：",
        f"1. 快速理解 {name} 是什么、解决什么问题",
        "2. 掌握其技术栈与架构特点",
        "3. 独立完成本地跑通与最小功能验证",
        "",
        "### 1.5 环境前置",
        "",
        "| 类别 | 推荐 | 备注 |",
        "| --- | --- | --- |",
        f"| 运行时 | {runtime} | 以项目 README 为准 |",
        f"| 操作系统 | Linux / macOS / Windows | 跨平台项目以 README 说明为准 |",
        "| 网络 | 可访问 GitHub | 国内网络受限时用镜像或代理 |",
        "",
        # ---- 二、技术原理 ----
        "## 二、技术原理 / 核心概念（通俗讲解，不堆公式）",
        "",
        "### 2.1 项目一句话介绍",
        f"**{name}**：{description or overview}",
        "",
        "### 2.2 技术栈解析",
        "",
        tech_analysis,
        "",
        "### 2.3 项目档案",
        "",
        "| 维度 | 信息 |",
        "| --- | --- |",
        f"| 仓库 | [{repo}]({url}) |",
        f"| 主要语言 | {language} |",
        f"| 开源协议 | {license_} |",
        f"| Star 数量 | ⭐ {stars} |",
        f"| Fork 数量 | 🍴 {forks} |",
        f"| 未解决 Issue | {issues} |",
        f"| 创建时间 | {created or 'N/A'} |",
        f"| 最近推送 | {pushed or 'N/A'} |",
    ]
    if homepage:
        parts.append(f"| 官网 | [{homepage}]({homepage}) |")
    if topics:
        parts.append(f"| 主题标签 | {', '.join(topics)} |")
    parts += [
        "",
        "### 2.4 新手最容易误解的点",
        "",
        "1. ❌ 只看 Star 数就上手 → ✅ 先读 README 与 issue，确认与自己的场景匹配",
        "2. ❌ 直接用于生产 → ✅ 先在本地 / 测试环境跑通最小示例",
        "3. ❌ 遇到报错就换项目 → ✅ 先看「常见报错」章节与项目 issue 搜索",
        "",
        # ---- 三、准备工作 ----
        "## 三、准备工作（前置依赖）",
        "",
        "### 3.1 获取源码",
        "",
        "```bash",
        f"git clone {url}.git",
        f"cd {name}",
        "```",
        "",
        "### 3.2 环境与依赖",
        f"- 运行时：{runtime}",
        "- 其余依赖以项目 README 的 requirements / package.json / go.mod 等为准",
        "- 国内网络拉取依赖慢时，配置对应包管理器镜像加速",
        "",
        # ---- 四、分步实操 ----
        "## 四、分步实操教程（博客核心主体）",
        "",
        "### 步骤 1：快速上手",
        "",
        "```bash",
        getting_started,
        "```",
        "",
        "### 步骤 2：按 README 示例逐个跑通",
        f"项目提供了系统的使用示例，参阅 [README]({readme_url}) 的 Quick Start / 示例目录。",
        "",
        "### 步骤 3：结合自己的场景改造",
        "把示例中的输入替换为真实业务数据，从小规模验证开始。",
        "",
        # ---- 五、功能测试 ----
        "## 五、功能测试与验证",
        "",
        "| 检查项 | 方式 | 期望结果 |",
        "| --- | --- | --- |",
        "| 项目可克隆 | `git clone` 成功 | 无网络 / 权限报错 |",
        "| 依赖可安装 | 按 README 安装依赖 | 无版本冲突 |",
        "| 最小示例可运行 | 执行 README 示例命令 | 输出与文档描述一致 |",
        "",
        # ---- 六、常见报错 ----
        "## 六、常见报错 & 踩坑汇总（博客高价值点）",
        "",
        "1. **clone / 依赖下载超时**：网络受限，改用镜像源或代理后重试",
        "2. **运行时版本不匹配**：先核对 README 声明的最低版本，别用太旧或太新的运行时",
        "3. **权限 / 路径问题**：避免用 sudo 装包；虚拟环境（venv / nvm）隔离依赖",
        "4. **示例能跑、自己改完就报错**：对照官方示例逐项 diff 参数与配置",
        "5. **疑难问题**：优先在项目 Issues 中搜索，多数坑已被社区踩过",
        "",
        # ---- 七、进阶玩法 ----
        "## 七、性能优化 / 进阶玩法",
        "",
        "- 关注项目的 releases 与 changelog，及时跟进 breaking change",
        "- fork 后按需裁剪功能，避免全量依赖",
        "- 结合团队规范二次封装（统一配置、日志、CI），沉淀为内部工具",
        "",
        # ---- 八、总结 ----
        "## 八、总结（收尾）",
        "",
        f"1. ✅ **{name}** 定位清晰：{description or '见 2.1 一句话介绍'}",
        f"2. ✅ 热度验证：⭐ {stars}、最近推送 {pushed or 'N/A'}，社区持续活跃",
        "3. ✅ 上手路径：clone → 依赖 → README 示例 → 场景化改造",
        "4. ✅ 风险提示：生产使用前先读 license 与 issue 区",
        "",
        # ---- 九、文末福利 ----
        "## 九、文末福利（可选）",
        "",
        f"- 📦 项目地址：[{url}]({url})",
        f"- 📦 在线文档：[README]({readme_url})",
    ]
    if homepage:
        parts.append(f"- 📦 官网 / 在线演示：[{homepage}]({homepage})")
    parts += [
        "",
        "---",
        "",
        f"*本文基于 GitHub Trending（{today}）自动生成，按《技术分享博客模板》组织，数据来自 GitHub API 与审批入库素材。*",
        "",
    ]
    return "\n".join(parts)


def upload_to_oss(key, content, db):
    import oss2
    cfg = get_config("OSS_VALUE", db)
    auth = oss2.Auth(cfg["access_key_id"], cfg["access_key_secret_encrypted"])
    bucket = oss2.Bucket(auth, cfg["endpoint"], cfg["bucket"])
    bucket.put_object(key, content.encode("utf-8"))
    # 生成 7 天有效的签名下载地址
    url = bucket.sign_url("GET", key, 7 * 24 * 3600)
    return url


def do_generate(db):
    data = get_latest_approved(db)
    md = build_markdown(data)
    approval_id = uuid.uuid4().hex[:16]
    with get_db_conn(db) as conn:
        insert_approval(conn, approval_id, "share_doc",
                        f"分享文档待审核: {data['repo']}")
    msg = (f"## 博客文档审核\n\n**项目**：{data['repo']}\n\n"
           f"文档预览：\n\n{md[:1500]}\n\n"
           f"approval_id: `{approval_id}`")
    send_wecom(msg, db)
    # 本地暂存文档内容，供阶段B上传
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pending_share.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"approval_id": approval_id, "repo": data["repo"], "markdown": md},
                  f, ensure_ascii=False)
    print(json.dumps({"approval_id": approval_id, "markdown": md}, ensure_ascii=False))


def do_approve(db, approval_id):
    tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pending_share.json")
    if not os.path.exists(tmp):
        raise RuntimeError("未找到待审核文档，请先运行 --generate")
    with open(tmp, encoding="utf-8") as f:
        pending = json.load(f)
    if pending["approval_id"] != approval_id:
        raise RuntimeError("approval_id 与待审核文档不匹配")
    key = f"github-trending/{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}.md"
    url = upload_to_oss(key, pending["markdown"], db)
    with get_db_conn(db) as conn:
        finish_approval(conn, approval_id,
                        json.dumps({"oss_key": key, "oss_url": url}, ensure_ascii=False),
                        approval_result=url)
    os.remove(tmp)
    print(json.dumps({"ok": True, "oss_url": url, "oss_key": key}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="分享文档生成与OSS发布")
    p.add_argument("--db", help="sqlite3 数据库路径")
    p.add_argument("--generate", action="store_true", help="生成分享md并推送企业微信审核")
    p.add_argument("--approve", action="store_true", help="审核通过后上传OSS")
    p.add_argument("--approval-id", help="阶段A返回的 approval_id")
    args = p.parse_args()

    if args.generate:
        do_generate(args.db)
    elif args.approve:
        if not args.approval_id:
            p.error("--approve 需要 --approval-id")
        do_approve(args.db, args.approval_id)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
