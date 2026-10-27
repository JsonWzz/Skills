# -*- coding: utf-8 -*-
"""企业微信 SkillHub 分享流程常驻 Bot 进程（单一 daemon 模式）。

职责：
  1. 周期性扫描 state/ 目录下 stage="awaiting_selection" 的 session → 推送「选择卡片」
  2. 监听 event.template_card_event，按按钮 key 前缀分发：
       select_skill:<slug>     → 拉详情 → 生成博客 → 推送「审核卡片」
       review:approve:<sid>    → 上传 OSS → 回复结果
       review:reject:<sid>     → 标记 rejected → 回复取消
  3. 全程状态由 state/session_{session_id}.json 驱动，不依赖 sqlite3 审批表

启动：
    python wecom_bot.py --db /path/to.db

SDK pin：wecom-aibot-sdk-python==0.1.7 （导入路径 wecom_aibot_sdk）
         或 wecom-aibot-python-sdk==1.0.x （导入路径 aibot）
"""
import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (
    SKILL_ROOT,
    STATE_DIR,
    OUTPUT_DIR,
    TEMPLATE_DIR,
    ensure_dirs,
    make_ws_client,
    load_session,
    save_session,
    get_wecom_credentials,
)

# 同步子步骤：直接 import 其函数，用 asyncio.to_thread 避免阻塞事件循环
from fetch_detail import fetch_detail as skillhub_fetch_detail
from generate_blog import build_sections, assemble, validate_template as blog_validate_template
from upload_oss import upload as oss_upload

LOG = logging.getLogger("skillhub-blog-share")

POLL_INTERVAL = 5   # 秒，扫描 state/ 目录的轮询间隔
POLL_PROCESSED_KEY = "_polled"   # session 内标记，避免重复发送


# ---------- 模板卡片构造 ----------

def build_selection_template_card(skills, session_id):
    """构造企业微信模板卡片：10 个技能名 + 按钮，按钮 key = select_skill:<slug>。"""
    button_list = []
    for s in skills[:10]:
        slug = s.get("slug", "")
        name = s.get("name", "未命名")
        desc = s.get("description_zh", "")
        dl = s.get("downloads", 0)
        btn_text = f"{name}（下载 {dl}）"[:18]
        button_list.append({
            "key": f"select_skill:{slug}",
            "text": btn_text,
            "data": {
                "session_id": session_id,
                "slug": slug,
                "name": name,
                "desc": desc,
                "downloads": dl,
            },
        })

    # 企业微信模板卡片结构（按 1.0.x WSClientOptions.reply_template_card 约定）
    template_card = {
        "card_type": "button_interaction",
        "main_title": {
            "title": "🦞 SkillHub 热门技能 Top 10",
            "desc": "请点击下方任一技能，我会拉取详情、按博客模板生成文档并发你审核",
        },
        "detail_list": [
            {"label": f"{i+1}. {s['name']}", "value": (s.get("description_zh") or "")[:80]}
            for i, s in enumerate(skills[:10])
        ],
        "button_list": button_list,
        "footer": {
            "text": f"session_id: {session_id[:12]}",
        },
    }
    return template_card


def build_review_template_card(session_id, slug, title, preview_300):
    """构造审核卡片：approve / reject 两个按钮。"""
    return {
        "card_type": "button_interaction",
        "main_title": {
            "title": f"📝 博客生成完毕：{title}",
            "desc": "请审核，满意就通过上传 OSS，不满意可以驳回",
        },
        "detail_list": [
            {"label": "技能 slug", "value": slug},
            {"label": "文档预览（前 300 字）", "value": preview_300[:200]},
        ],
        "button_list": [
            {"key": f"review:approve:{session_id}", "text": "✅ 审核通过，上传 OSS"},
            {"key": f"review:reject:{session_id}", "text": "❌ 驳回，不做上传"},
        ],
        "footer": {"text": f"session_id: {session_id[:12]}"},
    }


# ---------- 业务逻辑 ----------

async def push_selection_cards_for_pending_sessions(client):
    """轮询 state/ 目录，给所有 stage=awaiting_selection 且未推送过的 session 发选择卡片。"""
    ensure_dirs()
    for fname in sorted(os.listdir(STATE_DIR)):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        fpath = os.path.join(STATE_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                sess = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            LOG.warning("session %s 读取失败: %s", fname, e)
            continue

        if sess.get("stage") != "awaiting_selection":
            continue
        if sess.get("_polled"):
            continue
        chat_id = sess.get("chat_id") or sess.get("userid")
        if not chat_id:
            LOG.info("session %s 缺少 chat_id，暂不推送", sess.get("session_id"))
            continue

        template_card = build_selection_template_card(sess.get("skills", []), sess["session_id"])
        try:
            # 主动推送：不依赖 reply 回调帧
            await client.send_message(chat_id, {
                "msgtype": "template_card",
                "template_card": template_card,
            })
            sess["_polled"] = True
            sess["_card_sent_at"] = datetime.now().isoformat()
            save_session(sess["session_id"], sess)
            LOG.info("选择卡片已推送给 %s（session=%s）", chat_id, sess["session_id"])
        except Exception as e:
            LOG.error("推送选择卡片失败 session=%s err=%s", sess.get("session_id"), e)


async def handle_select_skill(client, session_id, slug):
    """收到 select_skill:<slug> 按钮点击 → 拉详情 → 生成博客 → 推送审核卡片。"""
    try:
        sess = load_session(session_id)
    except RuntimeError as e:
        await _send_text_or_card(client, sess=None, text=f"❌ session 不存在：{e}")
        return
    sess["selected_slug"] = slug
    save_session(session_id, sess)

    # 拉详情（同步 I/O 丢到线程池）
    try:
        detail = await asyncio.to_thread(skillhub_fetch_detail, slug)
    except Exception as e:
        LOG.error("fetch_detail 失败 slug=%s err=%s", slug, e)
        await _send_text_or_card(client, sess, text=f"❌ 拉取技能详情失败：{e}")
        return
    sess["detail_json"] = detail
    save_session(session_id, sess)

    # 生成博客
    try:
        await asyncio.to_thread(blog_validate_template)   # 校验模板章节锚点
        sections = build_sections(detail, slug)
        md_text = assemble(sections)
        ensure_dirs()
        out_path = os.path.join(OUTPUT_DIR, f"{slug}-{session_id[:8]}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md_text)
        sess["markdown_path"] = out_path
    except Exception as e:
        LOG.error("generate_blog 失败 slug=%s err=%s", slug, e, exc_info=True)
        await _send_text_or_card(client, sess, text=f"❌ 生成博客失败：{e}")
        return
    save_session(session_id, sess)

    # 推审核卡片
    title = detail.get("name") or detail.get("title") or slug
    preview = md_text[:300].replace("\n", " ")
    review_card = build_review_template_card(session_id, slug, title, preview)
    chat_id = sess.get("chat_id") or sess.get("userid")
    try:
        await client.send_message(chat_id, {
            "msgtype": "template_card",
            "template_card": review_card,
        })
        sess["stage"] = "awaiting_review"
        sess["review_card_sent"] = True
        save_session(session_id, sess)
        LOG.info("审核卡片已推送 session=%s slug=%s", session_id, slug)
    except Exception as e:
        LOG.error("推送审核卡片失败 session=%s err=%s", session_id, e)


async def handle_review(client, session_id, approve):
    sess = None   # 兜底，防止 except 块引用未定义变量
    if approve:
        try:
            sess = load_session(session_id)
            slug = sess.get("selected_slug")
            md_path = sess.get("markdown_path")
            if not slug or not md_path:
                raise RuntimeError("session 缺少 slug 或 markdown_path")
            oss_key, oss_url = await asyncio.to_thread(oss_upload, md_path, slug)
            sess["oss_key"] = oss_key
            sess["oss_url"] = oss_url
            sess["stage"] = "done"
            save_session(session_id, sess)
            await _send_text_or_card(client, sess, text=(
                f"✅ 审核通过，已上传 OSS\n"
                f"OSS 路径：`{oss_key}`\n"
                f"下载地址：{oss_url}"
            ))
            LOG.info("上传成功 session=%s oss_key=%s", session_id, oss_key)
        except Exception as e:
            LOG.error("上传 OSS 失败 session=%s err=%s", session_id, e, exc_info=True)
            await _send_text_or_card(client, sess or {}, text=f"❌ 上传 OSS 失败：{e}")
    else:
        try:
            sess = load_session(session_id)
            sess["stage"] = "rejected"
            save_session(session_id, sess)
            await _send_text_or_card(client, sess, text="❌ 已驳回，文档未上传。需要重做可再触发。")
        except RuntimeError as e:
            LOG.warning("驳回时 session 不存在：%s", e)
            await _send_text_or_card(client, {}, text="❌ session 不存在，无法标记驳回。")


async def _send_text_or_card(client, sess, text):
    """兜底：优先用 send_message 发纯文本（消息类型 text）。"""
    chat_id = (sess or {}).get("chat_id") or (sess or {}).get("userid")
    if not chat_id:
        LOG.warning("没有 chat_id，跳过回复: %s", text)
        return
    try:
        await client.send_message(chat_id, {
            "msgtype": "text",
            "text": {"content": text[:2000]},
        })
    except Exception as e:
        LOG.error("回复失败: %s", e)


async def on_template_card_event(client, frame):
    """模板卡片按钮点击事件处理。"""
    try:
        body = frame.get("body", {})
        # 兼容 SDK 0.1.x / 1.0.x 的不同字段名
        button_key = (body.get("button_key") or body.get("event_key")
                      or (body.get("template_card_event") or {}).get("button_key") or "")
        chat_id = body.get("chat_id") or body.get("chatid") or (body.get("chat_info") or {}).get("chat_id") or ""
        userid = body.get("userid") or body.get("user_id") or (body.get("from") or {}).get("userid") or ""
    except Exception as e:
        LOG.error("解析 template_card_event 帧失败: %s", e)
        return

    LOG.info("收到卡片点击 key=%s chat_id=%s userid=%s", button_key, chat_id, userid)

    if button_key.startswith("select_skill:"):
        slug = button_key[len("select_skill:"):]
        # 找到最匹配的 awaiting_selection session（先按 slug 匹配，再按最新）
        session_id = await _find_session_for_action(slug, chat_id, userid)
        if not session_id:
            await _send_text_or_card(client, None, text=f"❌ 找不到对应 session，请先触发抓取流程")
            return
        # 把 chat_id / userid 回写到 session（之前可能没采到）
        try:
            sess = load_session(session_id)
            if chat_id and not sess.get("chat_id"):
                sess["chat_id"] = chat_id
            if userid and not sess.get("userid"):
                sess["userid"] = userid
            save_session(session_id, sess)
        except RuntimeError:
            pass
        await handle_select_skill(client, session_id, slug)

    elif button_key.startswith("review:approve:"):
        sid = button_key[len("review:approve:"):]
        await handle_review(client, sid, approve=True)

    elif button_key.startswith("review:reject:"):
        sid = button_key[len("review:reject:"):]
        await handle_review(client, sid, approve=False)

    else:
        LOG.info("未识别的按钮 key=%s", button_key)


async def _find_session_for_action(slug, chat_id, userid):
    """扫描 state/，找一个匹配 slug 或 chat_id 的最新 session。"""
    ensure_dirs()
    best = None
    for fname in sorted(os.listdir(STATE_DIR)):
        if not fname.startswith("session_") or not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(STATE_DIR, fname), "r", encoding="utf-8") as f:
                sess = json.load(f)
        except Exception:
            continue
        # 按 slug 精确匹配优先
        skills = sess.get("skills") or []
        slugs = [s.get("slug") for s in skills if s.get("slug")]
        if slug in slugs and sess.get("stage") in ("awaiting_selection",):
            return sess["session_id"]
        # 其次按 chat_id / userid 匹配
        if (chat_id and chat_id == sess.get("chat_id")) or (userid and userid == sess.get("userid")):
            best = sess["session_id"]
    return best


# ---------- 主循环 ----------

async def poll_loop(client, stop_event):
    """每隔 POLL_INTERVAL 秒扫描一次 state/ 目录。"""
    while not stop_event.is_set():
        try:
            await push_selection_cards_for_pending_sessions(client)
        except Exception as e:
            LOG.exception("scan state/ 时出错: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def run_daemon(db_path):
    ensure_dirs()
    client = make_ws_client(db_path, logger=LOG)
    stop_event = asyncio.Event()

    # 注册事件：SDK 的 client.on() 会自动 await 异步回调。
    # 用闭包捕获 client，避免修改 on_template_card_event 函数签名。
    async def _on_card_event(frame):
        await on_template_card_event(client, frame)

    client.on("event.template_card_event", _on_card_event)
    LOG.info("已注册 event.template_card_event 回调")

    # 连接
    try:
        connect_coro = client.connect_async if hasattr(client, "connect_async") else client.connect
        await connect_coro()
    except Exception as e:
        LOG.error("WebSocket 连接失败: %s", e)
        return
    LOG.info("WebSocket 已连接，开始轮询 state/ 目录…")

    poll_task = asyncio.create_task(poll_loop(client, stop_event))
    try:
        await asyncio.Event().wait()   # 挂起直到键盘中断
    except KeyboardInterrupt:
        LOG.info("收到中断，正在退出…")
    finally:
        stop_event.set()
        poll_task.cancel()
        try:
            if hasattr(client, "disconnect"):
                client.disconnect()
        except Exception:
            pass


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser(description="SkillHub 分享流程 Bot 常驻进程")
    p.add_argument("--db", help="sqlite3 数据库路径（也可用 SQLITE_DB_PATH 环境变量）")
    p.add_argument("--once", action="store_true",
                   help="单次扫描 state/ 目录并推送，然后退出（调试用，一般不用）")
    args = p.parse_args()

    if args.once:
        # 一次性推送模式，方便本地调试
        client = make_ws_client(args.db, logger=LOG)
        async def _once():
            connect_coro = client.connect_async if hasattr(client, "connect_async") else client.connect
            await connect_coro()
            await push_selection_cards_for_pending_sessions(client)
            client.disconnect()
        asyncio.run(_once())
        return

    try:
        asyncio.run(run_daemon(args.db))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
