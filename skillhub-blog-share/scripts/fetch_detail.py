# -*- coding: utf-8 -*-
"""阶段 3 子步骤：按 slug 拉取 SkillHub 单个技能的完整详情。

用法：
    python fetch_detail.py <slug> [--output detail.json]
"""
import argparse
import json
import sys

import requests

SKILLHUB_DETAIL_URL = "https://api.skillhub.cn/api/v1/skills/{slug}"
HEADERS = {"User-Agent": "skillhub-blog-share/1.0"}


def fetch_detail(slug):
    url = SKILLHUB_DETAIL_URL.format(slug=slug)
    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code == 404:
        raise RuntimeError(f"SkillHub 未找到 slug={slug} 的技能")
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def main():
    p = argparse.ArgumentParser(description="拉取 SkillHub 单个技能详情")
    p.add_argument("slug", help="技能 slug")
    p.add_argument("--output", default="", help="写入指定 JSON 文件")
    args = p.parse_args()

    detail = fetch_detail(args.slug)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(detail, f, ensure_ascii=False, indent=2)
        print(f"已写入 {args.output}")
    else:
        print(json.dumps(detail, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
