# -*- coding: utf-8 -*-
"""
脚本1：爬取 GitHub Trending 前5项目 + README，企业微信推送审核，选定后写入 approval_log。

用法：
  阶段A 抓取并推送候选（含 GitHub API 元数据；加 --details 同时抓 README 供生成中文摘要）：
      python trending_fetch.py --fetch [--details] [--db /path/to.db]
  阶段B 审核通过，把选定项目、中文摘要与元数据存入 approval_log：
      python trending_fetch.py --approve 2 --approval-id <id> --summary "中文摘要..." \
          --meta '<该项目JSON元数据>' [--db ...]

依赖：requests（标准库 sqlite3 已内置）
"""
import argparse
import json
import re
import sys
import uuid

import requests

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from common import send_wecom, get_db_conn, insert_approval, finish_approval

TRENDING_URL = "https://github.com/trending"
API_URL = "https://api.github.com/repos/{repo}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; trending-skill)"}


def fetch_repo_meta(repo):
    """通过 GitHub API 补全项目元数据（失败返回空字典，不中断流程）。"""
    try:
        r = requests.get(API_URL.format(repo=repo), headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "full_name": d.get("full_name", repo),
            "description": d.get("description") or "",
            "stars": d.get("stargazers_count", 0),
            "forks": d.get("forks_count", 0),
            "open_issues": d.get("open_issues_count", 0),
            "language": d.get("language") or "",
            "license": (d.get("license") or {}).get("spdx_id") or "Unknown",
            "homepage": d.get("homepage") or "",
            "topics": d.get("topics", []),
            "created_at": (d.get("created_at") or "")[:10],
            "pushed_at": (d.get("pushed_at") or "")[:10],
            "default_branch": d.get("default_branch", "main"),
            "url": d.get("html_url", "https://github.com/" + repo),
        }
    except requests.RequestException:
        return {}


def fetch_trending_top5():
    """解析 trending 页面，返回前5个项目 [{repo, url, stars, language, description}]。"""
    resp = requests.get(TRENDING_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    html = resp.text
    repos = []
    # 每个项目卡片：<article class="Box-row"> ... <h2 class="h3 lh-condensed"><a href="/owner/repo"
    articles = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.S)
    for art in articles[:5]:
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="(/[^"]+)"', art)
        if not m:
            continue
        path = m.group(1).strip("/")
        star_m = re.search(r'href="/%s/stargazers"[^>]*>.*?</svg>\s*([\d,]+)' % re.escape(path), art, re.S)
        lang_m = re.search(r'itemprop="programmingLanguage">([^<]+)</span>', art)
        desc_m = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', art, re.S)
        repos.append({
            "repo": path,
            "url": "https://github.com/" + path,
            "stars": star_m.group(1).replace(",", "") if star_m else "",
            "language": lang_m.group(1).strip() if lang_m else "",
            "description": re.sub(r"<[^>]+>", "", desc_m.group(1)).strip() if desc_m else "",
        })
    return repos


def fetch_readme(repo):
    """尽量获取 README 正文（截断到 6000 字符）。"""
    for branch in ("main", "master"):
        for name in ("README.md", "readme.md", "README.rst", "README"):
            url = f"https://raw.githubusercontent.com/{repo}/{branch}/{name}"
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code == 200:
                    return r.text[:6000]
            except requests.RequestException:
                continue
    return ""


def build_candidate_message(repos, approval_id):
    lines = ["## GitHub Trending 今日热点候选（请回复序号审核）", ""]
    for i, r in enumerate(repos, 1):
        lines.append(
            f"**{i}. {r['repo']}**  ⭐{r['stars']}  {r['language']}\n"
            f"> {r['description'][:80]}\n> {r['url']}"
        )
        lines.append("")
    lines.append(f"approval_id: `{approval_id}`")
    return "\n".join(lines)


def do_fetch(db, details=False):
    repos = fetch_trending_top5()
    if not repos:
        print(json.dumps({"error": "未解析到 trending 项目，请检查网络或页面结构"}, ensure_ascii=False))
        sys.exit(1)
    for r in repos:
        meta = fetch_repo_meta(r["repo"])
        if meta:
            r.update({k: v for k, v in meta.items() if k not in ("full_name",)})
        if details:
            r["readme"] = fetch_readme(r["repo"])
    approval_id = uuid.uuid4().hex[:16]
    summary = "Trending候选: " + ", ".join(r["repo"] for r in repos)
    with get_db_conn(db) as conn:
        insert_approval(conn, approval_id, "trending_candidates", summary)
    send_wecom(build_candidate_message(repos, approval_id), db)
    print(json.dumps({"approval_id": approval_id, "repos": repos}, ensure_ascii=False, indent=2))


def do_approve(db, index, approval_id, summary, meta_json):
    if not (1 <= index <= 5):
        print("序号必须是 1-5", file=sys.stderr)
        sys.exit(1)
    repos = fetch_trending_top5()
    if len(repos) < index:
        print("trending 项目数量不足", file=sys.stderr)
        sys.exit(1)
    chosen = repos[index - 1]
    payload = {"repo": chosen["repo"], "url": chosen["url"], "stars": chosen["stars"],
               "language": chosen["language"], "summary_zh": summary}
    # 合并阶段1已获取的 API 元数据（agent 从 --fetch 输出复制），避免重复请求
    if meta_json:
        try:
            payload.update(json.loads(meta_json))
        except json.JSONDecodeError:
            print("警告: --meta 不是合法 JSON，已忽略", file=sys.stderr)
    payload.setdefault("repo", chosen["repo"])
    payload.setdefault("url", chosen["url"])
    with get_db_conn(db) as conn:
        finish_approval(conn, approval_id, json.dumps(payload, ensure_ascii=False),
                        approval_result="已选定并入库")
    print(json.dumps({"ok": True, "selected": payload}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="GitHub Trending 抓取与审核入库")
    p.add_argument("--db", help="sqlite3 数据库路径")
    p.add_argument("--fetch", action="store_true", help="抓取前5并推送企业微信审核")
    p.add_argument("--details", action="store_true", help="同时抓取各项目 README（耗时较长）")
    p.add_argument("--approve", type=int, metavar="N", help="按序号(1-5)选定项目")
    p.add_argument("--approval-id", help="阶段A返回的 approval_id")
    p.add_argument("--summary", default="", help="该项目的中文摘要")
    p.add_argument("--meta", default="", help="阶段1输出中该项目的 JSON 元数据（可选，用于博客素材）")
    args = p.parse_args()

    if args.fetch:
        do_fetch(args.db, details=args.details)
    elif args.approve:
        if not args.approval_id:
            p.error("--approve 需要 --approval-id")
        do_approve(args.db, args.approve, args.approval_id, args.summary, args.meta)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
