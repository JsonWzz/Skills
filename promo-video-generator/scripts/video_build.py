# -*- coding: utf-8 -*-
"""宣传视频构建流水线：分镜 → 文生图 → 视频生成 → 拼接 → 上传 OSS。

用法（按顺序执行，工作目录 workdir 贯穿各阶段）：
    1) 生成分镜并推送企业微信审核：
        python video_build.py --plan --source source.json --workdir workdir [--db ...]
    2) 用户审核通过后一键生成并上传：
        python video_build.py --generate --approval-id <id> --source source.json
                              --workdir workdir [--db ...]

--generate 内部依次完成：
    a. 对 need_image 的镜头调用文生图（百炼 qwen-image），下载图片到本地
    b. 每个镜头以图生视频（百炼 wan，env_key=WAN_VIDEO，异步任务轮询）
    c. ffmpeg 拼接全部片段（本机无 ffmpeg 时自动改用 docker 镜像 jrottenberg/ffmpeg）
    d. 上传成片到 OSS（env_key=OSS_VIDEO，bucket=json-video-bucket），回写 approval_log

依赖：requests、oss2；ffmpeg（本机或 docker）。视频生成耗时较长，单镜头默认 5-10 秒。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (send_wecom, get_db_conn, get_config, insert_approval, finish_approval,
                    llm_json, text_to_image, submit_video_task, poll_video_task,
                    download_file, oss_upload_file, new_approval_id, text_to_speech)

SYSTEM_PROMPT = """你是一个"技术分享短视频脚本与素材生成器"。把用户提供的技术内容转换成适合微信视频号、小红书、抖音发布的竖版短视频分镜。

严格输出 JSON（不要任何解释、不要代码围栏外的文字）：
{
  "title": "视频标题",
  "cover_prompt": "封面图提示词",
  "scenes": [
    {"index": 1, "narration": "旁白文案", "on_screen_text": "屏幕字幕",
     "image_prompt": "插图提示词", "video_prompt": "视频提示词",
     "need_image": true, "image_size": "1024*1536", "video_duration": 5}
  ],
  "video_parameters": {"resolution": "720P", "ratio": "9:16", "audio": true,
                       "prompt_extend": true, "watermark": false}
}

规则：
1. 镜头 3-6 个；narration 不超过 35 字；on_screen_text 用结论型短句。
2. image_prompt 必须具体：主体+场景+风格+构图+色彩；统一极简科技风/扁平插画，
   竖版 9:16 主体居中、上方留字幕位，蓝白灰紫为主，干净现代、少文字、无水印。
3. video_prompt 包含镜头运动、画面变化、节奏，前 3 秒有视觉钩子。
4. 素材没有提供图片时 need_image=true。
5. video_duration 只能取 5 或 10（秒）。"""


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- 阶段1 分镜

def do_plan(db, source_path, workdir):
    source = load_json(source_path)
    plan = llm_json(SYSTEM_PROMPT,
                    "技术内容素材（JSON）：\n" + json.dumps(source, ensure_ascii=False),
                    db_path=db)
    scenes = plan.get("scenes") or []
    if not (3 <= len(scenes) <= 6):
        raise RuntimeError(f"分镜数量异常（{len(scenes)}），请重试 --plan")
    save_json(os.path.join(workdir, "plan.json"), plan)

    approval_id = new_approval_id()
    conn = get_db_conn(db)
    try:
        insert_approval(conn, approval_id, "video_plan",
                        f"视频分镜待审核: {plan.get('title', source.get('title', ''))}")
    finally:
        conn.close()
    lines = [f"## 宣传视频分镜审核\n\n**标题**：{plan.get('title', '')}\n"]
    for s in scenes:
        lines.append(f"**镜头{s['index']}**（{s.get('video_duration', 5)}s）\n"
                     f"> 旁白：{s.get('narration', '')}\n"
                     f"> 字幕：{s.get('on_screen_text', '')}\n")
    lines.append(f"approval_id: `{approval_id}`")
    lines.append("\n**请选择是否添加语音讲解：**")
    lines.append("1=添加语音讲解（生成旁白配音）")
    lines.append("2=不添加语音讲解（仅视频画面）")
    send_wecom("\n".join(lines), db)
    print(json.dumps({"ok": True, "approval_id": approval_id,
                      "title": plan.get("title"), "scenes": len(scenes)},
                     ensure_ascii=False))


# ---------------------------------------------------------------- 阶段2 生成

def _get_audio_duration(audio_path):
    """用 ffprobe 获取音频时长（秒）。"""
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    if shutil.which("ffprobe"):
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return float(result.stdout.strip())
        except ValueError:
            pass
    # ffprobe 不可用时用 docker
    if shutil.which("docker"):
        workdir = os.path.dirname(os.path.abspath(audio_path))
        fname = os.path.basename(audio_path)
        cmd = ["docker", "run", "--rm", "-v", f"{workdir}:/work",
               "jrottenberg/ffmpeg", "-i", f"/work/{fname}",
               "-f", "null", "-"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        # ffprobe 信息在 stderr
        import re
        m = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', result.stderr)
        if m:
            h, mi, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            return h * 3600 + mi * 60 + s
    return 0.0


def _ffmpeg_merge(clips, audio_clips, out_path, workdir):
    """拼接视频片段与对应音频，输出最终成片。

    clips:       视频片段路径列表
    audio_clips: 对应音频路径列表（与 clips 等长，缺失位置可为 None）
    out_path:    输出路径
    workdir:     工作目录（concat.txt 存放处）
    """
    use_docker = not shutil.which("ffmpeg")

    if not any(audio_clips):
        # 无音频，直接拼接视频
        list_file = os.path.join(workdir, "concat.txt")
        with open(list_file, "w") as f:
            for c in clips:
                if use_docker:
                    f.write(f"file '/work/{os.path.basename(c)}'\n")
                else:
                    f.write(f"file '{os.path.abspath(c)}'\n")
        if use_docker:
            cmd = ["docker", "run", "--rm",
                   "-v", f"{os.path.abspath(workdir)}:/work",
                   "jrottenberg/ffmpeg",
                   "-y", "-f", "concat", "-safe", "0", "-i", "/work/concat.txt",
                   "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                   "-pix_fmt", "yuv420p", "/work/" + os.path.basename(out_path)]
        else:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                   "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                   "-pix_fmt", "yuv420p", out_path]
        subprocess.run(cmd, check=True, capture_output=True)
        return

    # 有音频：逐片段 mux 视频+音频（音频不足时补静音，过长时截断），再 concat
    muxed_dir = os.path.join(workdir, "muxed")
    os.makedirs(muxed_dir, exist_ok=True)
    muxed_clips = []

    for i, (video, audio) in enumerate(zip(clips, audio_clips)):
        muxed = os.path.join(muxed_dir, f"muxed_{i+1}.mp4")
        v_path = f"/work/{os.path.basename(video)}" if use_docker else os.path.abspath(video)
        out_muxed = f"/work/muxed/muxed_{i+1}.mp4" if use_docker else muxed

        if audio:
            a_path = f"/work/{os.path.basename(audio)}" if use_docker else os.path.abspath(audio)
            # 用 -shortest 让输出与视频同长；音频不足时 ffmpeg 自动静音填充
            if use_docker:
                cmd = ["docker", "run", "--rm",
                       "-v", f"{os.path.abspath(workdir)}:/work",
                       "jrottenberg/ffmpeg",
                       "-y", "-i", v_path, "-i", a_path,
                       "-c:v", "copy", "-c:a", "aac",
                       "-map", "0:v:0", "-map", "1:a:0",
                       "-shortest", out_muxed]
            else:
                cmd = ["ffmpeg", "-y", "-i", video, "-i", audio,
                       "-c:v", "copy", "-c:a", "aac",
                       "-map", "0:v:0", "-map", "1:a:0",
                       "-shortest", muxed]
        else:
            # 无音频片段，直接复制视频
            if use_docker:
                cmd = ["docker", "run", "--rm",
                       "-v", f"{os.path.abspath(workdir)}:/work",
                       "jrottenberg/ffmpeg",
                       "-y", "-i", v_path, "-c:v", "copy", "-an", out_muxed]
            else:
                cmd = ["ffmpeg", "-y", "-i", video, "-c:v", "copy", "-an", muxed]
        subprocess.run(cmd, check=True, capture_output=True)
        muxed_clips.append(muxed)

    # 拼接所有 muxed 片段
    list_file = os.path.join(workdir, "concat.txt")
    with open(list_file, "w") as f:
        for c in muxed_clips:
            if use_docker:
                f.write(f"file '/work/muxed/{os.path.basename(c)}'\n")
            else:
                f.write(f"file '{os.path.abspath(c)}'\n")

    if use_docker:
        cmd = ["docker", "run", "--rm",
               "-v", f"{os.path.abspath(workdir)}:/work",
               "jrottenberg/ffmpeg",
               "-y", "-f", "concat", "-safe", "0", "-i", "/work/concat.txt",
               "-c:v", "libx264", "-preset", "medium", "-crf", "23",
               "-pix_fmt", "yuv420p", "/work/" + os.path.basename(out_path)]
    else:
        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
               "-c:v", "libx264", "-preset", "medium", "-crf", "23",
               "-pix_fmt", "yuv420p", out_path]
    subprocess.run(cmd, check=True, capture_output=True)


def do_generate(db, approval_id, source_path, workdir, with_voice=False):
    plan_path = os.path.join(workdir, "plan.json")
    if not os.path.exists(plan_path):
        raise RuntimeError("未找到 plan.json，请先运行 --plan")
    plan = load_json(plan_path)
    source = load_json(source_path)
    os.makedirs(workdir, exist_ok=True)
    state_path = os.path.join(workdir, "state.json")
    state = load_json(state_path) if os.path.exists(state_path) else {"scenes": {}}

    # a. 文生图 + 上传到 OSS 获取干净 URL（百炼临时签名含特殊字符，wan API 不认）
    for sc in plan["scenes"]:
        idx = str(sc["index"])
        st = state["scenes"].setdefault(idx, {})
        if not st.get("image") and sc.get("need_image", True):
            url = text_to_image(sc["image_prompt"], db_path=db,
                                size=sc.get("image_size", "1024*1536"))
            local = os.path.join(workdir, f"scene_{idx}.png")
            download_file(url, local)
            oss_key = f"promo-img-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}.png"
            oss_url = oss_upload_file("OSS_PICTURE", local, oss_key, db_path=db)
            st["image"] = local
            st["image_url"] = oss_url
            save_json(state_path, state)
            print(f"[scene {idx}] 图片已生成并上传: {local}")

    # b. 图生视频（逐镜头异步任务 + 轮询）
    for sc in plan["scenes"]:
        idx = str(sc["index"])
        st = state["scenes"].setdefault(idx, {})
        if st.get("clip"):
            continue
        img_url = st.get("image_url") or st.get("image")
        task_id, api_key = submit_video_task(
            sc["video_prompt"], image_url=img_url, db_path=db,
            duration=int(sc.get("video_duration", 5)))
        print(f"[scene {idx}] 视频任务已提交: {task_id}")
        video_url = poll_video_task(task_id, api_key)
        local = os.path.join(workdir, f"clip_{idx}.mp4")
        download_file(video_url, local)
        st["clip"] = local
        save_json(state_path, state)
        print(f"[scene {idx}] 片段已下载: {local}")

    # c. TTS 语音合成（仅当 with_voice=True 时执行）
    audio_clips = []
    if with_voice:
        print("[voice] 开始生成语音讲解...")
        for sc in plan["scenes"]:
            idx = str(sc["index"])
            st = state["scenes"].setdefault(idx, {})
            narration = sc.get("narration", "").strip()
            if not narration:
                audio_clips.append(None)
                continue
            audio_path = os.path.join(workdir, f"audio_{idx}.mp3")
            if not os.path.exists(audio_path):
                try:
                    text_to_speech(narration, audio_path, db_path=db)
                    st["audio"] = audio_path
                    save_json(state_path, state)
                    print(f"[scene {idx}] 语音已生成: {audio_path}")
                except Exception as e:
                    print(f"[scene {idx}] 语音合成失败，跳过: {e}")
                    audio_clips.append(None)
                    continue
            audio_clips.append(audio_path)
    else:
        print("[voice] 跳过语音讲解生成")

    # d. 拼接（视频 + 音频）
    clips = [state["scenes"][str(sc["index"])]["clip"] for sc in plan["scenes"]]
    final = os.path.join(workdir, "final_video.mp4")
    if not os.path.exists(final):
        _ffmpeg_merge(clips, audio_clips, final, workdir)
        print(f"成片已拼接: {final}")

    # e. 上传 OSS（视频桶 env_key=OSS_VIDEO）并回写审批
    key = (f"promo-video/{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}.mp4")
    url = oss_upload_file("OSS_VIDEO", final, key, db_path=db)
    conn = get_db_conn(db)
    try:
        finish_approval(conn, approval_id,
                        json.dumps({"source_type": source.get("source_type"),
                                    "title": plan.get("title"),
                                    "oss_key": key, "oss_url": url}, ensure_ascii=False),
                        approval_result=url)
    finally:
        conn.close()
    send_wecom(f"## 宣传视频已生成\n\n**标题**：{plan.get('title', '')}\n\n"
               f"下载地址（7天有效）：\n{url}", db)
    print(json.dumps({"ok": True, "oss_key": key, "oss_url": url}, ensure_ascii=False))
    
    # f. 清理本地临时文件
    print("[cleanup] 清理本地临时文件...")
    import glob
    # 删除音频文件
    for audio_file in glob.glob(os.path.join(workdir, "audio_*.mp3")):
        try:
            os.remove(audio_file)
            print(f"  已删除: {os.path.basename(audio_file)}")
        except Exception as e:
            print(f"  删除失败 {audio_file}: {e}")
    # 删除视频片段
    for clip_file in glob.glob(os.path.join(workdir, "clip_*.mp4")):
        try:
            os.remove(clip_file)
            print(f"  已删除: {os.path.basename(clip_file)}")
        except Exception as e:
            print(f"  删除失败 {clip_file}: {e}")
    # 删除 muxed 目录
    muxed_dir = os.path.join(workdir, "muxed")
    if os.path.exists(muxed_dir):
        try:
            import shutil
            shutil.rmtree(muxed_dir)
            print(f"  已删除目录: muxed/")
        except Exception as e:
            print(f"  删除失败 muxed/: {e}")
    print("[cleanup] 清理完成")


def main():
    p = argparse.ArgumentParser(description="宣传视频构建流水线")
    p.add_argument("--db", help="sqlite3 数据库路径")
    p.add_argument("--plan", action="store_true", help="生成分镜并推送企业微信审核")
    p.add_argument("--generate", action="store_true", help="审核通过后生成视频并上传OSS")
    p.add_argument("--approval-id", help="--plan 返回的 approval_id")
    p.add_argument("--source", default="source.json", help="素材文件路径")
    p.add_argument("--workdir", default="workdir", help="工作目录")
    p.add_argument("--with-voice", action="store_true",
                   help="添加语音讲解（生成旁白配音）")
    args = p.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    if args.plan:
        do_plan(args.db, args.source, args.workdir)
    elif args.generate:
        if not args.approval_id:
            p.error("--generate 需要 --approval-id")
        do_generate(args.db, args.approval_id, args.source, args.workdir, args.with_voice)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
