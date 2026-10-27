# promo-video-generator 技能修复报告

**日期**：2026-10-26  
**测试人员**：AI Assistant  
**技能版本**：promo-video-generator v1.0

---

## 概述

在2026年10月26日对 `promo-video-generator` 技能进行完整测试过程中，发现并修复了5个关键问题。这些问题涉及OSS配置、API版本、路径处理等方面。本报告详细记录了每个问题的现象、原因分析和修复方案。

---

## 问题1：OSS 图片桶配置缺失

### 现象
分镜图片生成后无法上传到公开可读的OSS桶，导致后续wan视频生成API无法访问图片。

### 原因分析
- 系统只配置了 `OSS_VALUE`（源文档桶）和 `OSS_VIDEO`（成片桶）
- 缺少专门用于存放分镜图片的公开可读桶
- 分镜图片需要公开访问权限，wan API才能通过URL读取

### 修复方案
1. 新增OSS桶 `json-picture-bucket`，用于存放分镜图片
2. 在 `account_config` 表中新增配置项，env_key为 `OSS_IMAGE`
3. 设置该桶为公开可读（public-read）
4. 修改 `common.py` 中的 `oss_upload_file` 函数，支持 `OSS_IMAGE` env_key

### 修改文件
- `scripts/common.py`：`oss_upload_file` 函数增加对 `OSS_IMAGE` 的支持

---

## 问题2：OSS URL 格式问题

### 现象
`oss_upload_file` 返回的URL包含签名参数（如 `OSSAccessKeyId`、`Signature` 等），不适合直接用于wan API调用。

### 原因分析
- 默认情况下，OSS生成的URL带有签名参数，用于临时授权访问
- wan API需要的是公开可读的URL，不需要签名参数
- 带签名的URL可能导致API解析失败

### 修复方案
修改 `oss_upload_file` 函数，在上传时设置 `headers={'Content-Type': 'public-read'}`，使上传的文件默认可公开访问，返回干净的HTTPS URL（不带签名参数）。

### 修改文件
- `scripts/common.py`：`oss_upload_file` 函数

### 修复前
```python
url = f"https://{bucket}.{endpoint}/{key}?{sign_params}"
```

### 修复后
```python
url = f"https://{bucket}.{endpoint}/{key}"
```

---

## 问题3：wan 视频 API 版本过旧

### 现象
调用wan图生视频API时返回 `url error` 或空响应，视频生成任务无法提交。

### 原因分析
- 脚本使用的是旧版API endpoint：`/services/aigc/image2video/video-synthesis`
- 旧版API使用 `img_url` 字段传递图片URL
- 阿里云百炼已升级到wan2.7版本，旧版API已废弃或行为变更

### 修复方案
升级到wan2.7新版API协议：

**Endpoint变更**：
- 旧：`/services/aigc/image2video/video-synthesis`
- 新：`/services/aigc/video-generation/video-synthesis`

**参数格式变更**：
- 旧：`{"img_url": image_url}`
- 新：`{"media": [{"type": "first_frame", "url": image_url}]}`

**模型名称**：
- 推荐使用：`wan2.7-i2v-2026-04-25`
- 从 `account_config` 表的 `WAN_VIDEO` 配置中读取 `account_name` 字段

### 修改文件
- `scripts/common.py`：`submit_video_task` 函数

### 修复前
```python
endpoint = f"{DASHSCOPE_BASE}/services/aigc/image2video/video-synthesis"
input_payload = {"prompt": prompt, "img_url": image_url}
```

### 修复后
```python
endpoint = f"{DASHSCOPE_BASE}/services/aigc/video-generation/video-synthesis"
input_payload = {
    "prompt": prompt,
    "media": [{"type": "first_frame", "url": image_url}]
}
```

---

## 问题4：ffmpeg 拼接路径错误

### 现象
使用docker容器执行ffmpeg拼接时，报错找不到视频文件，拼接失败。

### 原因分析
- `concat.txt` 中使用了宿主机的绝对路径（如 `/home/admin/.openclaw/workspace/skills/promo-video-generator/workdir/clip_1.mp4`）
- docker容器内挂载点为 `/work`，容器内无法访问宿主机路径
- 导致ffmpeg读取文件时路径不存在

### 修复方案
修改 `video_build.py` 中生成 `concat.txt` 的逻辑：
1. 使用相对路径（如 `clip_1.mp4`）而不是绝对路径
2. docker运行时使用 `-w /work` 参数设置工作目录
3. 确保 `concat.txt` 和视频文件在同一目录下

### 修改文件
- `scripts/video_build.py`：生成 `concat.txt` 的逻辑

### 修复前
```python
concat_content = "\n".join([f"file '{os.path.abspath(clip)}'" for clip in clips])
```

### 修复后
```python
concat_content = "\n".join([f"file '{os.path.basename(clip)}'" for clip in clips])
```

### docker运行命令
```bash
docker run --rm -v "$(pwd):/work" -w /work jrottenberg/ffmpeg \
  -y -f concat -safe 0 -i concat.txt \
  -c:v libx264 -preset medium -crf 23 -pix_fmt yuv420p \
  final_video.mp4
```

---

## 问题5：endpoint URL 重复

### 现象
API调用返回404错误，日志显示URL变成 `/api/v1/api/v1/services/aigc/...`，路径重复。

### 原因分析
- `DASHSCOPE_BASE` 常量的值已经包含 `/api/v1` 前缀
- 在拼接endpoint时又手动添加了 `/api/v1`，导致路径重复
- 例如：`https://dashscope.aliyuncs.com/api/v1` + `/api/v1/services/...` = 错误URL

### 修复方案
在 `submit_video_task` 函数中，拼接endpoint时不再添加 `/api/v1` 前缀，直接使用 `DASHSCOPE_BASE` + 相对路径。

### 修改文件
- `scripts/common.py`：`submit_video_task` 函数

### 修复前
```python
endpoint = f"{DASHSCOPE_BASE}/api/v1/services/aigc/video-generation/video-synthesis"
```

### 修复后
```python
endpoint = f"{DASHSCOPE_BASE}/services/aigc/video-generation/video-synthesis"
```

---

## 修复总结

| 问题编号 | 问题类型 | 影响范围 | 修复状态 |
|---------|---------|---------|---------|
| 1 | 配置缺失 | OSS图片上传 | ✅ 已修复 |
| 2 | URL格式 | wan API调用 | ✅ 已修复 |
| 3 | API版本 | 视频生成 | ✅ 已修复 |
| 4 | 路径处理 | ffmpeg拼接 | ✅ 已修复 |
| 5 | URL拼接 | API调用 | ✅ 已修复 |

---

## 测试验证

修复完成后，成功完成了完整的视频生成流程：

1. ✅ 阶段0：企业微信询问数据来源
2. ✅ 阶段1：从GitHub项目取材（luongnv89/claude-howto）
3. ✅ 阶段2：生成4个分镜并通过企业微信审核
4. ✅ 阶段3：视频生成
   - 4个镜头图片生成成功
   - 4个镜头视频生成成功（每个约1-5分钟）
   - ffmpeg拼接成功
   - 上传OSS成功
   - 企业微信通知发送成功

**最终产物**：
- 视频文件：`workdir/final_video.mp4`
- 文件大小：4.4MB
- 时长：20秒
- 分辨率：782x1174（竖版）
- OSS下载地址：已生成并发送到企业微信

---

## 建议与注意事项

1. **API版本监控**：定期检查阿里云百炼API文档，关注版本变更和废弃通知
2. **OSS桶配置**：确保所有必需的OSS桶已正确配置并设置合适的访问权限
3. **路径处理**：使用docker时注意路径映射，优先使用相对路径
4. **错误处理**：建议在各脚本中增加更详细的错误日志，便于快速定位问题
5. **测试覆盖**：建议增加单元测试，覆盖各种边界情况

---

## 附录：修改文件清单

1. `scripts/common.py`
   - `oss_upload_file` 函数：支持 `OSS_IMAGE` env_key，返回干净URL
   - `submit_video_task` 函数：升级到wan2.7 API，修复endpoint拼接

2. `scripts/video_build.py`
   - 生成 `concat.txt` 的逻辑：使用相对路径

---

**报告生成时间**：2026-10-26 22:22  
**报告格式**：Markdown → PDF  
**下次测试建议**：2026-11-26
