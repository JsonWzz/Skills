# -*- coding: utf-8 -*-
"""技能启动：通过企业微信征求"视频数据来源"意见，并写入 approval_log 待审批记录。

用法：
    阶段A 推送询问：
        python ask_source.py --ask [--db ...]
    阶段B 用户回复序号后确认：
        python ask_source.py --confirm 1 --approval-id <id> [--db ...]

确认结果写入 approval_log（skill_name=promo-video-generator, message_type=video_source_choice），
approval_data 形如 {"choice": 1, "source": "approval_github"}。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (send_wecom, get_db_conn, insert_approval, finish_approval,
                    new_approval_id)

CHOICE_SOURCE = {1: "approval_github", 2: "oss_doc"}


def do_ask(db):
    approval_id = new_approval_id()
    conn = get_db_conn(db)
    try:
        insert_approval(conn, approval_id, "video_source_choice",
                        "宣传视频数据来源选择: 1=审批库GitHub项目 2=OSS技术文档")
    finally:
        conn.close()
    msg = (
        "## 宣传视频生成 — 请选择数据来源\n\n"
        "请回复 **序号** 选择本次视频的数据来源：\n\n"
        "**1.** 审批库最近通过的 GitHub 热门项目（approval_log + GitHub 图文）\n\n"
        "**2.** OSS 桶最近一篇技术文档（json-files-bucket）\n\n"
        f"approval_id: `{approval_id}`"
    )
    send_wecom(msg, db)
    print(json.dumps({"ok": True, "approval_id": approval_id}, ensure_ascii=False))


def do_confirm(db, choice, approval_id):
    if choice not in CHOICE_SOURCE:
        raise RuntimeError("序号必须是 1 或 2")
    conn = get_db_conn(db)
    try:
        finish_approval(conn, approval_id,
                        json.dumps({"choice": choice, "source": CHOICE_SOURCE[choice]},
                                   ensure_ascii=False),
                        approval_result=f"用户选择数据来源{choice}")
    finally:
        conn.close()
    print(json.dumps({"ok": True, "choice": choice,
                      "source": CHOICE_SOURCE[choice]}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description="企业微信询问视频数据来源")
    p.add_argument("--db", help="sqlite3 数据库路径")
    p.add_argument("--ask", action="store_true", help="推送数据来源询问")
    p.add_argument("--confirm", type=int, metavar="N", help="确认用户选择的序号 1/2")
    p.add_argument("--approval-id", help="--ask 返回的 approval_id")
    args = p.parse_args()

    if args.ask:
        do_ask(args.db)
    elif args.confirm:
        if not args.approval_id:
            p.error("--confirm 需要 --approval-id")
        do_confirm(args.db, args.confirm, args.approval_id)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
