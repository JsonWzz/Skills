# -*- coding: utf-8 -*-
"""脚本2（数据来源=2）：从阿里云 OSS（env_key=OSS_VALUE，bucket=json-files-bucket）
获取最近上传的一个技术文档（.md），产出视频素材 source.json。

用法：
    python source_oss_doc.py [--db /path/to/db] [--prefix github-trending/]
                             [--suffix .md] [--out workdir/source.json]
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_config, oss_latest_object, oss_download_file


def strip_frontmatter(md):
    m = re.match(r"^---\n.*?\n---\n", md, re.S)
    return md[m.end():] if m else md


def main():
    p = argparse.ArgumentParser(description="数据来源2：OSS 最近技术文档")
    p.add_argument("--db", help="sqlite3 数据库路径（默认取 SQLITE_DB_PATH）")
    p.add_argument("--env-key", default="OSS_VALUE", help="OSS 配置 env_key，默认 OSS_VALUE")
    p.add_argument("--prefix", default="", help="对象 key 前缀，如 github-trending/")
    p.add_argument("--suffix", default=".md", help="对象后缀过滤，默认 .md")
    p.add_argument("--out", default="source.json", help="输出素材文件路径")
    args = p.parse_args()

    obj = oss_latest_object(args.env_key, prefix=args.prefix, suffix=args.suffix,
                            db_path=args.db)
    cfg = get_config(args.env_key, args.db)
    work = os.path.dirname(os.path.abspath(args.out)) or "."
    os.makedirs(work, exist_ok=True)
    local = os.path.join(work, os.path.basename(obj["key"]))
    oss_download_file(args.env_key, obj["key"], local, db_path=args.db)

    with open(local, encoding="utf-8") as f:
        md = f.read()
    body = strip_frontmatter(md)
    title_m = re.search(r"^#\s+(.+)$", body, re.M)
    title = title_m.group(1).strip() if title_m else os.path.basename(obj["key"])

    source = {
        "source_type": "oss_doc",
        "title": title,
        "oss_key": obj["key"],
        "oss_bucket": cfg.get("bucket", ""),
        "content": body[:8000],
        "images": [],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": True, "out": args.out, "oss_key": obj["key"],
                      "title": title, "content_chars": len(body)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
