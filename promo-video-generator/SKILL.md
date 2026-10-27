---
name: promo-video-generator
description: 根据文字或图文信息生成竖版宣传短视频。技能启动时先通过企业微信征求数据来源意见，用户回复序号1跑脚本1（approval_log最近审批通过的GitHub项目+图文），回复2跑脚本2（OSS桶json-files-bucket最近技术文档）；再用百炼qwen-plus生成分镜、企业微信审核、wan图生视频、ffmpeg拼接，成片上传OSS桶json-video-bucket返回下载地址。当用户要求生成宣传视频、技术分享视频、trending视频时使用。不用于普通视频剪辑或图片生成。
---

# 宣传视频生成器

四阶段流水线：**询问数据来源 → 取材 → 分镜审核 → 生成视频并上传 OSS**。
所有配置从 sqlite3 数据库（环境变量 `SQLITE_DB_PATH`）的 `account_config` 表按 `env_key` 读取，
审批与询问记录写入 `approval_log` 表（本技能 skill_name=`promo-video-generator`）。

## 前置条件

- 环境变量 `SQLITE_DB_PATH` 指向数据库，或运行时所有命令追加 `--db /path/to.db`。
- `account_config` 已配置启用的记录：
  - `WEIXIN_WEBHOOK` — 取 `webhook_url` 发送企业微信消息
  - `OSS_VALUE` — 源文档桶（json-files-bucket）：`endpoint`/`access_key_id`/`access_key_secret_encrypted`/`bucket`
  - `OSS_VIDEO` — 成片桶（json-video-bucket）：同上四个字段
  - `QWEN_PLUS` — 模型 qwen-plus，`secret` 为百炼 APIKey
  - `WAN_VIDEO` — 模型 wan 视频生成，`secret` 为百炼 APIKey
- Python 依赖：`pip install requests oss2`。
- ffmpeg：本机已安装，或用 docker 镜像 `jrottenberg/ffmpeg`（脚本自动检测，优先本机）。

## 工作流

所有脚本在 `scripts/` 目录下执行；先建一个工作目录（如 `workdir/`）存放素材与产物。

### 阶段0：企业微信询问数据来源

```bash
python scripts/ask_source.py --ask
```

推送"请选择数据来源：1=审批库GitHub项目 2=OSS技术文档"，输出 `approval_id`。

**必须等用户在企业微信回复序号**（agent 转述给用户确认）。拿到 1 或 2 后：

```bash
python scripts/ask_source.py --confirm <序号> --approval-id <id>
```

### 阶段1：取材（二选一）

用户回复 **1** → 脚本1（取 approval_log 中 github-trending-share 最近审批通过的候选，
拉取 GitHub API 元数据与 README 图文）：

```bash
python scripts/source_approval.py --out workdir/source.json
```

用户回复 **2** → 脚本2（取 OSS 桶 json-files-bucket 最近一篇 .md 技术文档）：

```bash
python scripts/source_oss_doc.py --prefix github-trending/ --out workdir/source.json
```

两个脚本都产出统一格式的 `workdir/source.json`（含 title、正文/摘要、图片列表）。

### 阶段2：生成分镜并推送审核

```bash
python scripts/video_build.py --plan --source workdir/source.json --workdir workdir
```

调用百炼 qwen-plus 按分镜规则生成 3-6 个镜头（旁白/字幕/插图提示词/视频提示词），
推送企业微信审核，输出新的 `approval_id`。把分镜内容展示给用户。

**语音讲解选择**：分镜审核消息中会询问是否添加语音讲解：
- 回复 **1** = 添加语音讲解（生成旁白配音）
- 回复 **2** = 不添加语音讲解（仅视频画面）

### 阶段3：审核通过后生成视频并上传

用户确认分镜通过并选择语音讲解选项后：

```bash
# 添加语音讲解
python scripts/video_build.py --generate --approval-id <阶段2的id> \
  --source workdir/source.json --workdir workdir --with-voice

# 或不添加语音讲解
python scripts/video_build.py --generate --approval-id <阶段2的id> \
  --source workdir/source.json --workdir workdir
```

内部依次：文生图（qwen-image）→ 逐镜头图生视频（wan 异步任务轮询，耗时较长）→
（可选）TTS语音合成（cosyvoice）→ ffmpeg 拼接 → 上传 OSS（env_key=OSS_VIDEO）→ 
回写 approval_log → 企业微信推送下载地址 → 清理本地临时文件。
命令中断重跑会跳过已完成镜头（进度存 `workdir/state.json`）。把最终下载地址告知用户。

## 注意

- 各阶段 `approval_id` 必须原样传递；用户未回复序号前不得进入下一阶段。
- 视频生成是异步任务，单镜头约数分钟，`--generate` 整体可能超过 15 分钟，耐心等待不要重复执行。
- 百炼返回的图片/视频 URL 有效期短，脚本已即时下载到本地再拼接上传。
- 数据中的 URL 可能混入反引号，脚本已做清洗；解析失败时报错退出，不要伪造分镜或视频数据。

## 已知问题与修复记录

### 问题6：视频没有解说声音
**现象**：生成的视频只有画面，没有旁白解说
**原因**：脚本只调用了视频生成 API，没有调用 TTS 语音合成 API 生成旁白音频
**修复**：
1. 在 `common.py` 中添加 `text_to_speech()` 函数，调用百炼 cosyvoice API
2. 在 `video_build.py` 的 `do_generate()` 中增加 TTS 步骤，为每个场景的 `narration` 生成音频
3. 重写 `_ffmpeg_merge()` 函数，支持视频+音频混合拼接
4. 需要配置 `COSYVOICE` env_key（百炼语音合成 APIKey）
**脚本修改**：
- `scripts/common.py`：新增 `text_to_speech()` 和 `poll_audio_task()` 函数
- `scripts/video_build.py`：修改 `_ffmpeg_merge()` 支持音频，`do_generate()` 增加 TTS 步骤

### 问题1：OSS 图片桶配置缺失
**现象**：分镜图片生成后无法上传到公开可读的 OSS 桶
**修复**：新增 `json-picture-bucket` OSS 桶配置（env_key=`OSS_IMAGE`），用于存放分镜图片，设置为公开可读
**脚本修改**：`common.py` 中 `oss_upload_file` 函数支持 `OSS_IMAGE` env_key

### 问题2：OSS URL 格式问题
**现象**：`oss_upload_file` 返回的 URL 包含签名参数，不适合直接用于 wan API
**修复**：修改 `oss_upload_file` 返回干净的 HTTPS URL（不带签名参数），通过设置 `headers={'Content-Type': 'public-read'}` 实现公开访问
**脚本修改**：`common.py` 中 `oss_upload_file` 函数

### 问题3：wan 视频 API 版本过旧
**现象**：调用 wan 图生视频 API 返回 `url error` 或空响应
**修复**：升级到 wan2.7 新版 API 协议
- 旧 endpoint：`/services/aigc/image2video/video-synthesis`
- 新 endpoint：`/services/aigc/video-generation/video-synthesis`
- 旧参数：`img_url` 字段
- 新参数：`media` 数组格式 `[{"type": "first_frame", "url": image_url}]`
- 模型名：`wan2.7-i2v-2026-04-25`（或从 `account_config` 读取）
**脚本修改**：`common.py` 中 `submit_video_task` 函数

### 问题4：ffmpeg 拼接路径错误
**现象**：docker 容器内执行 ffmpeg 拼接时报错找不到文件
**修复**：`concat.txt` 中使用相对路径（如 `clip_1.mp4`）而不是宿主机绝对路径，docker 运行时用 `-w /work` 设置工作目录
**脚本修改**：`video_build.py` 中生成 `concat.txt` 的逻辑

### 问题5：endpoint URL 重复
**现象**：API 调用返回 404，URL 变成 `/api/v1/api/v1/...`
**修复**：`DASHSCOPE_BASE` 已包含 `/api/v1`，拼接 endpoint 时不要再加 `/api/v1`
**脚本修改**：`common.py` 中 `submit_video_task` 函数

## 参考资料

- 修复报告：[fix-report-2026-10-26.pdf](./fix-report-2026-10-26.pdf)
