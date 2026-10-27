# -*- coding: utf-8 -*-
"""阶段 5：审核通过后上传 Markdown 到阿里云 OSS。

用法：
    python upload_oss.py --file output/blog.md --slug my-skill [--db /path/to.db]

凭证从 sqlite3 account_config 表 env_key='OSS_VALUE' 读取，不硬编码。
Object 路径固定：blog/skillhub/{slug}/{YYYYMMDD-HHMMSS}.md
"""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import get_oss_credentials


def upload(file_path, slug, db_path=None):
    if not os.path.exists(file_path):
        raise RuntimeError(f"待上传文件不存在: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    import oss2
    creds = get_oss_credentials(db_path)
    auth = oss2.Auth(creds["access_key_id"], creds["access_key_secret_encrypted"])
    bucket = oss2.Bucket(auth, creds["endpoint"], creds["bucket"])

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    key = f"blog/skillhub/{slug}/{timestamp}-{uuid.uuid4().hex[:8]}.md"

    bucket.put_object(key, content.encode("utf-8"))

    # 生成 7 天有效签名 URL（Bucket 为私有时需要）
    try:
        url = bucket.sign_url("GET", key, 7 * 24 * 3600)
    except Exception:
        url = f"oss://{creds['bucket']}/{key}"

    return key, url


def main():
    p = argparse.ArgumentParser(description="上传 Markdown 到阿里云 OSS")
    p.add_argument("--file", required=True, help="本地 md 文件路径")
    p.add_argument("--slug", required=True, help="技能 slug（用于 OSS 路径）")
    p.add_argument("--db", help="sqlite3 数据库路径")
    args = p.parse_args()

    key, url = upload(args.file, args.slug, args.db)
    print(json.dumps({
        "ok": True,
        "oss_key": key,
        "oss_url": url,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
