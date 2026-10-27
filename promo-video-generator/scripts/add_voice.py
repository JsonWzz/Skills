#!/usr/bin/env python3
"""为已有视频片段添加语音解说并重新拼接。

用法：
    python add_voice.py --workdir workdir --source source.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import text_to_speech
from video_build import _ffmpeg_merge, load_json


def main():
    p = argparse.ArgumentParser(description="为已有视频添加语音")
    p.add_argument("--workdir", default="workdir", help="工作目录")
    p.add_argument("--source", default="source.json", help="素材文件路径")
    p.add_argument("--db", help="sqlite3 数据库路径")
    args = p.parse_args()

    workdir = args.workdir
    plan_path = os.path.join(workdir, "plan.json")
    if not os.path.exists(plan_path):
        raise RuntimeError("未找到 plan.json")
    
    plan = load_json(plan_path)
    state_path = os.path.join(workdir, "state.json")
    state = load_json(state_path) if os.path.exists(state_path) else {"scenes": {}}

    # 生成语音
    audio_clips = []
    for sc in plan["scenes"]:
        idx = str(sc["index"])
        st = state["scenes"].setdefault(idx, {})
        narration = sc.get("narration", "").strip()
        
        if not narration:
            print(f"[scene {idx}] 无旁白文案，跳过")
            audio_clips.append(None)
            continue
        
        audio_path = os.path.join(workdir, f"audio_{idx}.mp3")
        
        if not os.path.exists(audio_path):
            print(f"[scene {idx}] 生成语音: {narration[:30]}...")
            try:
                text_to_speech(narration, audio_path, db_path=args.db)
                st["audio"] = audio_path
                # 保存状态
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                print(f"[scene {idx}] ✅ 语音已生成: {audio_path}")
            except Exception as e:
                print(f"[scene {idx}] ❌ 语音合成失败: {e}")
                audio_clips.append(None)
                continue
        else:
            print(f"[scene {idx}] 语音已存在: {audio_path}")
        
        audio_clips.append(audio_path)

    # 拼接视频+音频
    clips = [state["scenes"][str(sc["index"])]["clip"] for sc in plan["scenes"]]
    final = os.path.join(workdir, "final_video_with_voice.mp4")
    
    print("\n拼接视频和音频...")
    _ffmpeg_merge(clips, audio_clips, final, workdir)
    print(f"✅ 成片已生成: {final}")
    
    # 显示文件信息
    import subprocess
    result = subprocess.run(["ls", "-lh", final], capture_output=True, text=True)
    print(result.stdout)


if __name__ == "__main__":
    main()
