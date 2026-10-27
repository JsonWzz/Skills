# -*- coding: utf-8 -*-
"""阶段 1：抓取 SkillHub 热门技能前 10 条（按下载量排序）。

用法：
    python fetch_skills.py [--output skills.json]

输出 JSON，每条包含 slug / name / description_zh（缺失回退 description）/ downloads / category。
不调详情接口，列表字段足够做选择卡片。
"""
import argparse
import json
import sys

import requests

SKILLHUB_LIST_URL = "https://api.skillhub.cn/api/skills"
HEADERS = {"User-Agent": "skillhub-blog-share/1.0"}


def fetch_top10():
    params = {"sortBy": "downloads", "pageSize": 10}
    resp = requests.get(SKILLHUB_LIST_URL, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    # 兼容常见 API 包装：{data: [...]} / {items: [...]} / 直接列表
    items = payload
    if isinstance(payload, dict):
        items = (payload.get("data") or payload.get("items")
                 or payload.get("list") or payload.get("results") or [])
    if not isinstance(items, list):
        raise RuntimeError(f"SkillHub API 返回结构异常，未找到列表字段: {payload.keys() if isinstance(payload, dict) else type(payload)}")

    normalized = []
    for raw in items[:10]:
        desc_zh = raw.get("description_zh") or raw.get("descriptionZh") or ""
        if not desc_zh:
            desc_zh = raw.get("description") or raw.get("summary") or ""
        normalized.append({
            "slug": raw.get("slug") or raw.get("id") or "",
            "name": raw.get("name") or raw.get("title") or "(未命名)",
            "description_zh": desc_zh[:200],   # 截断到 200 字做卡片
            "downloads": raw.get("downloads") or raw.get("downloadCount") or 0,
            "category": raw.get("category") or raw.get("categoryName") or "",
            "rating": raw.get("rating") or 0,
        })
    return normalized


def main():
    p = argparse.ArgumentParser(description="抓取 SkillHub 热门技能前 10 条")
    p.add_argument("--output", default="", help="写入指定 JSON 文件，否则打印到 stdout")
    args = p.parse_args()

    skills = fetch_top10()
    if not skills:
        print("未抓到任何技能，请检查网络或 API 可用性", file=sys.stderr)
        sys.exit(1)

    text = json.dumps({"count": len(skills), "skills": skills}, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"已写入 {args.output}（{len(skills)} 条）")
    else:
        print(text)


if __name__ == "__main__":
    main()
