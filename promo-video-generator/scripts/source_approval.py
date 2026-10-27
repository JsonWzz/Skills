# -*- coding: utf-8 -*-
"""脚本1（数据来源=1）：从 approval_log 取最近一条审批通过的 trending 候选数据，
结合 GitHub API 元数据与 README 图文，产出视频素材 source.json。

用法：
    python source_approval.py [--db /path/to.db] [--out workdir/source.json]

SQL 依据：
    select approval_data from approval_log
    where skill_name='github-trending-share' and message_type='trending_candidates'
      and approval_status='approved'
    order by updated_at desc limit 1
"""
import argparse
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_db_conn

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; promo-video-skill)"}


def fetch_latest_approval(db):
    conn = get_db_conn(db)
    try:
        row = conn.execute(
            "SELECT approval_data FROM approval_log "
            "WHERE skill_name='github-trending-share' "
            "AND message_type='trending_candidates' AND approval_status='approved' "
            "AND approval_data IS NOT NULL AND approval_data != '' "
            "ORDER BY updated_at DESC, id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError("approval_log 中没有 github-trending-share 审批通过的候选数据")
    return json.loads(row["approval_data"])


def clean_url(s):
    """清洗数据中可能混入的反引号/空白。"""
    return (s or "").strip().strip("`").strip()


def fetch_github_meta(repo):
    url = clean_url(f"https://api.github.com/repos/{repo}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return {}
        d = r.json()
        return {
            "description": d.get("description") or "",
            "stars": d.get("stargazers_count", 0),
            "forks": d.get("forks_count", 0),
            "language": d.get("language") or "",
            "license": (d.get("license") or {}).get("spdx_id") or "Unknown",
            "topics": d.get("topics", []),
            "homepage": clean_url(d.get("homepage") or ""),
            "pushed_at": (d.get("pushed_at") or "")[:10],
            "default_branch": d.get("default_branch", "main"),
        }
    except requests.RequestException:
        return {}


def fetch_readme_text(repo, branch="main"):
    for name in ("README.md", "readme.md", "README.rst", "README"):
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{name}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r.text[:6000]
        except requests.RequestException:
            continue
    return ""


def extract_images(readme, repo, branch):
    """从 README 提取图片链接（相对路径转 raw 地址），最多 5 张。"""
    imgs = re.findall(r'!\[[^\]]*\]\(([^)\s]+)', readme)
    out = []
    for src in imgs:
        src = src.strip()
        if src.startswith("http"):
            out.append(src)
        elif src.startswith("/"):
            out.append(f"https://raw.githubusercontent.com/{repo}/{branch.lstrip('/')}{src}")
        else:
            out.append(f"https://raw.githubusercontent.com/{repo}/{branch}/{src}")
        if len(out) >= 5:
            break
    return out


def main():
    p = argparse.ArgumentParser(description="数据来源1：审批库最近通过数据 + GitHub 图文")
    p.add_argument("--db", help="sqlite3 数据库路径（默认取 SQLITE_DB_PATH）")
    p.add_argument("--out", default="source.json", help="输出素材文件路径")
    args = p.parse_args()

    data = fetch_latest_approval(args.db)
    repo = clean_url(data.get("repo", ""))
    if not repo:
        raise RuntimeError(f"approval_data 中无 repo 字段: {data}")
    branch = data.get("default_branch") or "main"

    meta = fetch_github_meta(repo)
    readme = fetch_readme_text(repo, branch)
    images = extract_images(readme, repo, branch) if readme else []

    source = {
        "source_type": "approval_github",
        "title": f"{repo}：GitHub 热门开源项目",
        "repo": repo,
        "url": clean_url(data.get("url") or f"https://github.com/{repo}"),
        "summary_zh": data.get("summary_zh", ""),
        "hotspots": data.get("hotspots", ""),
        "tech_analysis": data.get("tech_analysis", ""),
        "scenarios": data.get("scenarios", ""),
        "getting_started": data.get("getting_started", ""),
        "github_meta": meta,
        "readme_excerpt": readme[:3000],
        "images": images,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "out": args.out, "repo": repo,
                      "image_count": len(images),
                      "content_chars": len(json.dumps(source, ensure_ascii=False))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
