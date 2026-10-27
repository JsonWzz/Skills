# -*- coding: utf-8 -*-
"""公共工具：sqlite3 凭证读取 + session JSON 读写 + SDK 客户端工厂。

所有凭证从 sqlite3 的 account_config 表按 env_key 读取，不在代码中硬编码。
SDK 版本 pin 到 0.1.7（PyPI: wecom-aibot-sdk-python），导入路径 wecom_aibot_sdk。
"""
import json
import os
import sqlite3
import sys

SKILL_NAME = "skillhub-blog-share"

# 数据库路径：环境变量 SQLITE_DB_PATH，或命令行 --db。两者都未提供时报错。
DEFAULT_DB = os.environ.get("SQLITE_DB_PATH")

# 本脚本所在目录，用于定位 state/ 模板/ output 目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
STATE_DIR = os.path.join(SKILL_ROOT, "state")
TEMPLATE_DIR = os.path.join(SKILL_ROOT, "templates")
OUTPUT_DIR = os.path.join(SKILL_ROOT, "output")


def ensure_dirs():
    """确保 state / output 目录存在。"""
    for d in (STATE_DIR, OUTPUT_DIR):
        os.makedirs(d, exist_ok=True)


# ---------- sqlite3 ----------

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


def get_wecom_credentials(db_path=None):
    """读取 WECOM_BOT_ID + WECOM_BOT_SECRET。"""
    bot_cfg = get_config("WECOM_BOT_ID", db_path)
    secret_cfg = get_config("WECOM_BOT_SECRET", db_path)
    bot_id = bot_cfg.get("config_value") or bot_cfg.get("webhook_url") or bot_cfg.get("bot_id")
    secret = secret_cfg.get("config_value") or secret_cfg.get("secret") or secret_cfg.get("webhook_url")
    if not bot_id or not secret:
        raise RuntimeError(
            "WECOM_BOT_ID 或 WECOM_BOT_SECRET 配置值为空，请检查 account_config 表字段"
        )
    return bot_id, secret


def get_oss_credentials(db_path=None):
    """读取 OSS_VALUE：endpoint / access_key_id / access_key_secret_encrypted / bucket。"""
    cfg = get_config("OSS_VALUE", db_path)
    required = ("endpoint", "access_key_id", "access_key_secret_encrypted", "bucket")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"OSS_VALUE 配置缺少字段: {missing}")
    return {k: cfg[k] for k in required}


# ---------- session JSON ----------

def session_path(session_id):
    ensure_dirs()
    return os.path.join(STATE_DIR, f"session_{session_id}.json")


def load_session(session_id):
    path = session_path(session_id)
    if not os.path.exists(path):
        raise RuntimeError(f"session 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_session(session_id, data):
    ensure_dirs()
    path = session_path(session_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def new_session(session_id, **kwargs):
    """创建全新 session，初始 stage=awaiting_selection。"""
    ensure_dirs()
    data = {
        "session_id": session_id,
        "stage": "awaiting_selection",          # awaiting_selection → awaiting_review → done / rejected
        "chat_id": kwargs.get("chat_id", ""),
        "userid": kwargs.get("userid", ""),
        "skills": kwargs.get("skills", []),      # [{slug, name, description_zh, downloads, category}]
        "selected_slug": "",
        "detail_json": {},
        "markdown_path": "",
        "oss_key": "",
        "oss_url": "",
        "review_card_sent": False,
        "created_at": kwargs.get("created_at", ""),
    }
    save_session(session_id, data)
    return data


# ---------- SDK 客户端工厂 ----------

def make_ws_client(db_path=None, logger=None):
    """创建 wecom-aibot-sdk-python WSClient 实例（同步上下文返回；内部 async）。

    SDK 版本 pin 到 0.1.7（PyPI: wecom-aibot-sdk-python）。
    若用户装的是 1.0.x（PyPI: wecom-aibot-python-sdk），导入路径为 aibot，
    代码里同时做两种导入尝试。
    """
    try:
        from wecom_aibot_sdk import WSClient  # 0.1.x
    except ImportError:
        try:
            from aibot import WSClient         # 1.0.x
        except ImportError:
            raise RuntimeError(
                "未找到 wecom-aibot-sdk-python。请先 pip install wecom-aibot-sdk-python==0.1.7"
            )
    bot_id, secret = get_wecom_credentials(db_path)
    opts = {"bot_id": bot_id, "secret": secret}
    if logger is not None:
        opts["logger"] = logger
    return WSClient(opts)
