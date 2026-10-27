# -*- coding: utf-8 -*-
"""公共工具：sqlite3 配置读取 + 企业微信 webhook 推送。"""
import os
import sqlite3
import requests

SKILL_NAME = "github-trending-share"

# 数据库路径：环境变量 SQLITE_DB_PATH，或命令行 --db。两者都未提供时报错，避免连到错误库。
DEFAULT_DB = os.environ.get("SQLITE_DB_PATH")


def get_db_conn(db_path=None):
    path = db_path or DEFAULT_DB
    if not path:
        raise RuntimeError(
            "未指定 sqlite3 数据库路径：请设置环境变量 SQLITE_DB_PATH 或使用 --db 参数")
    if not os.path.exists(path):
        raise RuntimeError(f"数据库文件不存在: {path}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_config(env_key, db_path=None):
    """按 env_key 从 account_config 表查询一条启用的配置。"""
    with get_db_conn(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM account_config WHERE env_key = ? AND enabled = 1 "
            "ORDER BY id DESC LIMIT 1",
            (env_key,),
        ).fetchone()
    if not row:
        raise RuntimeError(f"account_config 表中未找到 env_key={env_key} 的启用配置")
    return dict(row)


def send_wecom(markdown_content, db_path=None):
    """通过企业微信机器人 webhook 发送 markdown 消息。"""
    cfg = get_config("WEIXIN_WEBHOOK", db_path)
    webhook = cfg.get("webhook_url")
    if not webhook:
        raise RuntimeError("WEIXIN_WEBHOOK 配置中 webhook_url 为空")
    payload = {"msgtype": "markdown", "markdown": {"content": markdown_content[:4000]}}
    resp = requests.post(webhook, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"企业微信推送失败: {data}")
    return data


def insert_approval(conn, approval_id, message_type, message_summary, requester="agent", channel="weixin"):
    conn.execute(
        "INSERT INTO approval_log "
        "(approval_id, skill_name, message_type, message_summary, requester, channel, approval_status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (approval_id, SKILL_NAME, message_type, message_summary, requester, channel),
    )
    conn.commit()


def finish_approval(conn, approval_id, approval_data, approval_result="", approver="user"):
    row = conn.execute(
        "SELECT id FROM approval_log WHERE approval_id = ? ORDER BY id DESC LIMIT 1",
        (approval_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"未找到 approval_id={approval_id} 的审批记录")
    conn.execute(
        "UPDATE approval_log SET approval_status='approved', approver=?, approval_data=?, "
        "approval_result=?, updated_at=datetime('now','localtime') WHERE id=?",
        (approver, approval_data, approval_result, row["id"]),
    )
    conn.commit()
