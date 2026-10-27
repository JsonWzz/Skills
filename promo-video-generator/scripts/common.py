# -*- coding: utf-8 -*-
"""promo-video-generator 独立公共模块。

功能：sqlite3 配置读取、企业微信 webhook 推送、审批记录、阿里云 OSS 上传/下载、
阿里云百炼（DashScope）LLM / 文生图 / 视频生成调用。
本模块独立于其他 skill，不共用任何文件。
"""
import json
import os
import sqlite3
import time
import uuid

import requests

SKILL_NAME = "promo-video-generator"

# 数据库路径：环境变量 SQLITE_DB_PATH，或运行时 --db。两者都未提供时报错，避免连到错误库。
DEFAULT_DB = os.environ.get("SQLITE_DB_PATH")

DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/api/v1"


# ---------------------------------------------------------------- 数据库与配置

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
    conn = get_db_conn(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM account_config WHERE env_key = ? AND enabled = 1 "
            "ORDER BY id DESC LIMIT 1",
            (env_key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise RuntimeError(f"account_config 表中未找到 env_key={env_key} 的启用配置")
    return dict(row)


def get_api_key(env_key, db_path=None):
    """从 account_config 取百炼 APIKey（secret 字段）。"""
    cfg = get_config(env_key, db_path)
    key = cfg.get("secret")
    if not key:
        raise RuntimeError(f"env_key={env_key} 的配置中 secret（APIKey）为空")
    return key


# ---------------------------------------------------------------- 企业微信

def send_wecom(markdown_content, db_path=None):
    """通过企业微信机器人 webhook 发送 markdown 消息（4000 字符上限内截断）。"""
    cfg = get_config("WEIXIN_WEBHOOK", db_path)
    webhook = cfg.get("webhook_url")
    if not webhook:
        raise RuntimeError("WEIXIN_WEBHOOK 配置中 webhook_url 为空")
    payload = {"msgtype": "markdown", "markdown": {"content": markdown_content[:3800]}}
    resp = requests.post(webhook, json=payload, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode") != 0:
        raise RuntimeError(f"企业微信推送失败: {data}")
    return data


# ---------------------------------------------------------------- 审批记录

def insert_approval(conn, approval_id, message_type, message_summary,
                    requester="agent", channel="weixin"):
    conn.execute(
        "INSERT INTO approval_log "
        "(approval_id, skill_name, message_type, message_summary, requester, channel, approval_status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
        (approval_id, SKILL_NAME, message_type, message_summary, requester, channel),
    )
    conn.commit()


def finish_approval(conn, approval_id, approval_data, approval_result="", approver="user"):
    row = conn.execute(
        "SELECT id FROM approval_log WHERE approval_id = ? AND skill_name = ? "
        "ORDER BY id DESC LIMIT 1",
        (approval_id, SKILL_NAME),
    ).fetchone()
    if not row:
        raise RuntimeError(f"未找到 approval_id={approval_id} 的本技能审批记录")
    conn.execute(
        "UPDATE approval_log SET approval_status='approved', approver=?, approval_data=?, "
        "approval_result=?, updated_at=datetime('now','localtime') WHERE id=?",
        (approver, approval_data, approval_result, row["id"]),
    )
    conn.commit()


def new_approval_id():
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------- 阿里云 OSS

def make_bucket(env_key, db_path=None):
    """按 account_config 的 env_key 构造 oss2.Bucket。"""
    import oss2
    cfg = get_config(env_key, db_path)
    auth = oss2.Auth(cfg["access_key_id"], cfg["access_key_secret_encrypted"])
    return oss2.Bucket(auth, cfg["endpoint"], cfg["bucket"])


def oss_upload_file(env_key, local_path, oss_key, db_path=None, sign_days=7):
    """上传本地文件到指定 OSS 配置，返回可访问 URL。
    公开读桶直接返回无签名 URL，私有桶返回签名 URL。"""
    bucket = make_bucket(env_key, db_path)
    bucket.put_object_from_file(oss_key, local_path)
    # 构造公开访问 URL（virtual-hosted style: https://{bucket}.{endpoint}/{key}）
    endpoint = bucket.endpoint
    if not endpoint.startswith('http'):
        endpoint = 'https://' + endpoint
    scheme = 'https' if endpoint.startswith('https') else 'http'
    host = endpoint.split('://', 1)[1]
    public_url = f"https://{bucket.bucket_name}.{host}/{oss_key}"
    # 探测是否公开可读
    import requests as _req
    try:
        r = _req.head(public_url, timeout=10)
        if r.status_code < 400:
            return public_url
    except Exception:
        pass
    # 回退到签名 URL
    url = bucket.sign_url("GET", oss_key, sign_days * 24 * 3600)
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    return url


def oss_download_file(env_key, oss_key, local_path, db_path=None):
    bucket = make_bucket(env_key, db_path)
    bucket.get_object_to_file(oss_key, local_path)
    return local_path


def oss_latest_object(env_key, prefix="", suffix="", db_path=None):
    """列出桶内对象，按 last_modified 倒序返回最新一个 {key, size, last_modified}。"""
    import oss2
    bucket = make_bucket(env_key, db_path)
    latest = None
    for obj in oss2.ObjectIterator(bucket, prefix=prefix):
        if suffix and not obj.key.lower().endswith(suffix.lower()):
            continue
        if latest is None or obj.last_modified > latest["last_modified"]:
            latest = {"key": obj.key, "size": obj.size, "last_modified": obj.last_modified}
    if not latest:
        raise RuntimeError(
            f"OSS 桶（env_key={env_key}）中未找到 prefix={prefix!r} suffix={suffix!r} 的对象")
    return latest


# ---------------------------------------------------------------- 百炼 DashScope

def _dashscope_headers(api_key, async_task=False):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if async_task:
        headers["X-DashScope-Async"] = "enable"
    return headers


def llm_chat(system_prompt, user_content, db_path=None, model_env_key="QWEN_PLUS",
             temperature=0.6, max_retries=3):
    """调用百炼文本模型（默认 env_key=QWEN_PLUS 即 qwen-plus），返回文本。"""
    cfg = get_config(model_env_key, db_path)
    model = cfg.get("account_name") or "qwen-plus"
    api_key = cfg["secret"]
    payload = {
        "model": model,
        "input": {"messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]},
        "parameters": {"result_format": "message", "temperature": temperature},
    }
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(
                f"{DASHSCOPE_BASE}/services/aigc/text-generation/generation",
                headers=_dashscope_headers(api_key), json=payload, timeout=120)
            data = resp.json()
            if resp.status_code == 200 and "output" in data:
                return data["output"]["choices"][0]["message"]["content"]
            last_err = f"HTTP {resp.status_code}: {data}"
        except requests.RequestException as e:
            last_err = str(e)
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"百炼 LLM 调用失败: {last_err}")


def llm_json(system_prompt, user_content, db_path=None, model_env_key="QWEN_PLUS"):
    """调用 LLM 并把返回文本解析为 JSON（自动剥离 markdown 代码围栏）。"""
    text = llm_chat(system_prompt, user_content, db_path, model_env_key)
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return json.loads(t.strip())


def text_to_image(prompt, db_path=None, size="1024*1536", model_env_key="QWEN_PLUS",
                  timeout=180):
    """文生图（同步 multimodal-generation），返回图片 URL。"""
    cfg = get_config(model_env_key, db_path)
    api_key = cfg["secret"]
    payload = {
        "model": "qwen-image-2.0-pro",
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": size, "watermark": False, "prompt_extend": True},
    }
    resp = requests.post(
        f"{DASHSCOPE_BASE}/services/aigc/multimodal-generation/generation",
        headers=_dashscope_headers(api_key), json=payload, timeout=timeout)
    data = resp.json()
    if resp.status_code != 200 or "output" not in data:
        raise RuntimeError(f"文生图失败: HTTP {resp.status_code} {data}")
    content = data["output"]["choices"][0]["message"]["content"]
    for item in content:
        if item.get("image"):
            return item["image"]
    raise RuntimeError(f"文生图返回中无图片: {data}")


def submit_video_task(prompt, image_url=None, db_path=None,
                      model_env_key="WAN_VIDEO", duration=10, resolution="720P",
                      ratio="9:16"):
    """提交百炼视频生成异步任务，返回 task_id。

    image_url 提供时走图生视频（画面更可控），否则走文生视频。
    """
    cfg = get_config(model_env_key, db_path)
    model = cfg.get("account_name") or "wan2.7-i2v-2026-04-25"
    api_key = cfg["secret"]
    
    # 新版 wan2.7 API endpoint
    endpoint = f"{DASHSCOPE_BASE}/services/aigc/video-generation/video-synthesis"
    
    if image_url:
        # 图生视频：使用 media 数组格式
        input_payload = {
            "prompt": prompt,
            "media": [{"type": "first_frame", "url": image_url}]
        }
    else:
        # 文生视频：暂时保持旧格式（如果需要的话）
        endpoint = f"{DASHSCOPE_BASE}/services/aigc/text2video/video-synthesis"
        input_payload = {"prompt": prompt}
    
    parameters = {"resolution": resolution, "duration": duration, "prompt_extend": True}
    payload = {"model": model, "input": input_payload, "parameters": parameters}
    resp = requests.post(endpoint, headers=_dashscope_headers(api_key, async_task=True),
                         json=payload, timeout=60)
    data = resp.json()
    task_id = (data.get("output") or {}).get("task_id")
    if resp.status_code != 200 or not task_id:
        raise RuntimeError(f"视频任务提交失败: HTTP {resp.status_code} {data}")
    return task_id, api_key


def _t2v_size(resolution, ratio):
    """文生视频 size 参数：如 720P + 9:16 -> 1280*720 竖版写法按官方支持。"""
    base = {"480P": "832*480", "720P": "1280*720", "1080P": "1920*1080"}.get(resolution, "1280*720")
    if ratio == "9:16":
        w, h = base.split("*")
        return f"{h}*{w}"
    return base


def poll_video_task(task_id, api_key, timeout=900, interval=15):
    """轮询异步任务直到 SUCCEEDED，返回 video_url。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = requests.get(f"{DASHSCOPE_BASE}/tasks/{task_id}",
                            headers=_dashscope_headers(api_key), timeout=30)
        data = resp.json()
        status = (data.get("output") or {}).get("task_status")
        if status == "SUCCEEDED":
            url = (data["output"].get("video_url")
                   or (data["output"].get("results") or [{}])[0].get("url"))
            if not url:
                raise RuntimeError(f"任务成功但无视频地址: {data}")
            return url
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"视频任务失败: {data.get('output')}")
        time.sleep(interval)
    raise RuntimeError(f"视频任务轮询超时（{timeout}s）: task_id={task_id}")


def download_file(url, local_path, timeout=300):
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 256):
            f.write(chunk)
    return local_path


def text_to_speech(text, output_path, db_path=None, model_env_key="COSYVOICE",
                   voice="longanyang", format="mp3", sample_rate=24000):
    """调用百炼语音合成 API（CosyVoice），将文本转为音频文件。
    
    使用非实时 HTTP API：
    POST https://dashscope.aliyuncs.com/api/v1/services/audio/tts/SpeechSynthesizer
    
    Args:
        text: 要转换的文本
        output_path: 输出音频文件路径
        db_path: 数据库路径
        model_env_key: 环境配置键，默认 COSYVOICE，若不存在则回退到 QWEN_PLUS
        voice: 音色名称，默认 longanyang
        format: 输出格式，mp3/wav/pcm
        sample_rate: 采样率
    
    Returns:
        output_path: 生成的音频文件路径
    """
    # 尝试获取配置，若 COSYVOICE 不存在则回退到 QWEN_PLUS（共用百炼 APIKey）
    try:
        cfg = get_config(model_env_key, db_path)
        model = cfg.get("account_name") or "cosyvoice-v3-flash"
    except RuntimeError:
        print(f"[TTS] {model_env_key} 未配置，回退使用 QWEN_PLUS")
        cfg = get_config("QWEN_PLUS", db_path)
        # 回退到 QWEN_PLUS 时，强制使用 cosyvoice-v3-flash 模型
        model = "cosyvoice-v3-flash"
    
    api_key = cfg.get("secret")
    if not api_key:
        raise RuntimeError(f"{model_env_key} 配置中 secret（APIKey）为空")
    
    # CosyVoice 非实时 HTTP API endpoint
    endpoint = f"{DASHSCOPE_BASE}/services/audio/tts/SpeechSynthesizer"
    
    payload = {
        "model": model,
        "input": {
            "text": text,
            "voice": voice,
            "format": format,
            "sample_rate": sample_rate
        }
    }
    
    headers = _dashscope_headers(api_key)
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
    
    if resp.status_code != 200:
        raise RuntimeError(f"语音合成失败: HTTP {resp.status_code} {resp.text}")
    
    data = resp.json()
    
    # 非实时模式直接返回 audio.url
    audio_url = (data.get("output") or {}).get("audio", {}).get("url")
    if not audio_url:
        raise RuntimeError(f"语音合成返回中无音频URL: {data}")
    
    download_file(audio_url, output_path)
    return output_path
