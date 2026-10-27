#!/usr/bin/env python3
"""生成修复报告PDF"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import os

# 尝试注册中文字体
font_paths = [
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJKsc-Regular.otf',
    '/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf',
]

chinese_font = None
for fp in font_paths:
    if os.path.exists(fp):
        try:
            pdfmetrics.registerFont(TTFont('ChineseFont', fp))
            chinese_font = 'ChineseFont'
            print(f"已注册字体: {fp}")
            break
        except Exception as e:
            print(f"字体注册失败 {fp}: {e}")
            continue

if not chinese_font:
    print("警告: 未找到中文字体，将使用默认字体（可能无法正确显示中文）")
    chinese_font = 'Helvetica'

# 创建PDF文档
pdf_filename = 'fix-report-2026-10-26.pdf'
doc = SimpleDocTemplate(
    pdf_filename,
    pagesize=A4,
    rightMargin=2*cm,
    leftMargin=2*cm,
    topMargin=2*cm,
    bottomMargin=2*cm
)

# 定义样式
styles = getSampleStyleSheet()

# 标题样式
title_style = ParagraphStyle(
    'ChineseTitle',
    parent=styles['Heading1'],
    fontName=chinese_font,
    fontSize=18,
    spaceAfter=20,
    alignment=TA_CENTER,
    textColor=colors.HexColor('#333333')
)

# 二级标题样式
heading2_style = ParagraphStyle(
    'ChineseHeading2',
    parent=styles['Heading2'],
    fontName=chinese_font,
    fontSize=14,
    spaceAfter=12,
    spaceBefore=16,
    textColor=colors.HexColor('#555555'),
    leftIndent=10,
    borderPadding=(0, 0, 0, 10),
    borderColor=colors.HexColor('#007bff'),
    borderWidth=2
)

# 三级标题样式
heading3_style = ParagraphStyle(
    'ChineseHeading3',
    parent=styles['Heading3'],
    fontName=chinese_font,
    fontSize=12,
    spaceAfter=10,
    spaceBefore=12,
    textColor=colors.HexColor('#666666')
)

# 正文样式
body_style = ParagraphStyle(
    'ChineseBody',
    parent=styles['Normal'],
    fontName=chinese_font,
    fontSize=10,
    leading=16,
    spaceAfter=8,
    alignment=TA_JUSTIFY
)

# 代码样式
code_style = ParagraphStyle(
    'Code',
    parent=styles['Code'],
    fontName='Courier',
    fontSize=9,
    leading=12,
    leftIndent=20,
    rightIndent=20,
    spaceAfter=10,
    backColor=colors.HexColor('#f8f8f8'),
    borderPadding=(8, 8, 8, 8),
    borderColor=colors.HexColor('#007bff'),
    borderWidth=1
)

# 列表项样式
list_style = ParagraphStyle(
    'ChineseList',
    parent=body_style,
    leftIndent=30,
    bulletIndent=20,
    spaceAfter=6
)

# 构建内容
story = []

# 标题
story.append(Paragraph("promo-video-generator 技能修复报告", title_style))
story.append(Spacer(1, 0.3*cm))

# 基本信息
info_data = [
    ['日期', '2026-10-26'],
    ['测试人员', 'AI Assistant'],
    ['技能版本', 'promo-video-generator v1.0']
]
info_table = Table(info_data, colWidths=[3*cm, 10*cm])
info_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, -1), chinese_font),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#666666')),
    ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
    ('ALIGN', (1, 0), (1, -1), 'LEFT'),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
]))
story.append(info_table)
story.append(Spacer(1, 0.5*cm))

# 概述
story.append(Paragraph("概述", heading2_style))
story.append(Paragraph(
    "在2026年10月26日对 <b>promo-video-generator</b> 技能进行完整测试过程中，发现并修复了5个关键问题。"
    "这些问题涉及OSS配置、API版本、路径处理等方面。本报告详细记录了每个问题的现象、原因分析和修复方案。",
    body_style
))

# 问题1
story.append(Paragraph("问题1：OSS 图片桶配置缺失", heading2_style))
story.append(Paragraph("<b>现象</b>：分镜图片生成后无法上传到公开可读的OSS桶，导致后续wan视频生成API无法访问图片。", body_style))
story.append(Paragraph("<b>原因分析</b>：", body_style))
story.append(Paragraph("• 系统只配置了 <font face='Courier'>OSS_VALUE</font>（源文档桶）和 <font face='Courier'>OSS_VIDEO</font>（成片桶）", list_style))
story.append(Paragraph("• 缺少专门用于存放分镜图片的公开可读桶", list_style))
story.append(Paragraph("• 分镜图片需要公开访问权限，wan API才能通过URL读取", list_style))
story.append(Paragraph("<b>修复方案</b>：", body_style))
story.append(Paragraph("1. 新增OSS桶 <font face='Courier'>json-picture-bucket</font>，用于存放分镜图片", list_style))
story.append(Paragraph("2. 在 <font face='Courier'>account_config</font> 表中新增配置项，env_key为 <font face='Courier'>OSS_IMAGE</font>", list_style))
story.append(Paragraph("3. 设置该桶为公开可读（public-read）", list_style))
story.append(Paragraph("4. 修改 <font face='Courier'>common.py</font> 中的 <font face='Courier'>oss_upload_file</font> 函数，支持 <font face='Courier'>OSS_IMAGE</font> env_key", list_style))
story.append(Paragraph("<b>修改文件</b>：<font face='Courier'>scripts/common.py</font>", body_style))

# 问题2
story.append(Paragraph("问题2：OSS URL 格式问题", heading2_style))
story.append(Paragraph("<b>现象</b>：<font face='Courier'>oss_upload_file</font> 返回的URL包含签名参数（如 <font face='Courier'>OSSAccessKeyId</font>、<font face='Courier'>Signature</font> 等），不适合直接用于wan API调用。", body_style))
story.append(Paragraph("<b>原因分析</b>：", body_style))
story.append(Paragraph("• 默认情况下，OSS生成的URL带有签名参数，用于临时授权访问", list_style))
story.append(Paragraph("• wan API需要的是公开可读的URL，不需要签名参数", list_style))
story.append(Paragraph("• 带签名的URL可能导致API解析失败", list_style))
story.append(Paragraph("<b>修复方案</b>：修改 <font face='Courier'>oss_upload_file</font> 函数，在上传时设置 <font face='Courier'>headers={'Content-Type': 'public-read'}</font>，使上传的文件默认可公开访问，返回干净的HTTPS URL（不带签名参数）。", body_style))
story.append(Paragraph("<b>修改文件</b>：<font face='Courier'>scripts/common.py</font>", body_style))

# 问题3
story.append(Paragraph("问题3：wan 视频 API 版本过旧", heading2_style))
story.append(Paragraph("<b>现象</b>：调用wan图生视频API时返回 <font face='Courier'>url error</font> 或空响应，视频生成任务无法提交。", body_style))
story.append(Paragraph("<b>原因分析</b>：", body_style))
story.append(Paragraph("• 脚本使用的是旧版API endpoint：<font face='Courier'>/services/aigc/image2video/video-synthesis</font>", list_style))
story.append(Paragraph("• 旧版API使用 <font face='Courier'>img_url</font> 字段传递图片URL", list_style))
story.append(Paragraph("• 阿里云百炼已升级到wan2.7版本，旧版API已废弃或行为变更", list_style))
story.append(Paragraph("<b>修复方案</b>：升级到wan2.7新版API协议", body_style))
story.append(Paragraph("<b>Endpoint变更</b>：", body_style))
story.append(Paragraph("• 旧：<font face='Courier'>/services/aigc/image2video/video-synthesis</font>", list_style))
story.append(Paragraph("• 新：<font face='Courier'>/services/aigc/video-generation/video-synthesis</font>", list_style))
story.append(Paragraph("<b>参数格式变更</b>：", body_style))
story.append(Paragraph("• 旧：<font face='Courier'>{\"img_url\": image_url}</font>", list_style))
story.append(Paragraph("• 新：<font face='Courier'>{\"media\": [{\"type\": \"first_frame\", \"url\": image_url}]}</font>", list_style))
story.append(Paragraph("<b>模型名称</b>：<font face='Courier'>wan2.7-i2v-2026-04-25</font>（或从 <font face='Courier'>account_config</font> 读取）", body_style))
story.append(Paragraph("<b>修改文件</b>：<font face='Courier'>scripts/common.py</font> 中的 <font face='Courier'>submit_video_task</font> 函数", body_style))

# 问题4
story.append(Paragraph("问题4：ffmpeg 拼接路径错误", heading2_style))
story.append(Paragraph("<b>现象</b>：使用docker容器执行ffmpeg拼接时，报错找不到视频文件，拼接失败。", body_style))
story.append(Paragraph("<b>原因分析</b>：", body_style))
story.append(Paragraph("• <font face='Courier'>concat.txt</font> 中使用了宿主机的绝对路径", list_style))
story.append(Paragraph("• docker容器内挂载点为 <font face='Courier'>/work</font>，容器内无法访问宿主机路径", list_style))
story.append(Paragraph("• 导致ffmpeg读取文件时路径不存在", list_style))
story.append(Paragraph("<b>修复方案</b>：修改 <font face='Courier'>video_build.py</font> 中生成 <font face='Courier'>concat.txt</font> 的逻辑，使用相对路径（如 <font face='Courier'>clip_1.mp4</font>）而不是绝对路径，docker运行时使用 <font face='Courier'>-w /work</font> 参数设置工作目录。", body_style))
story.append(Paragraph("<b>修改文件</b>：<font face='Courier'>scripts/video_build.py</font>", body_style))

# 问题5
story.append(Paragraph("问题5：endpoint URL 重复", heading2_style))
story.append(Paragraph("<b>现象</b>：API调用返回404错误，日志显示URL变成 <font face='Courier'>/api/v1/api/v1/services/aigc/...</font>，路径重复。", body_style))
story.append(Paragraph("<b>原因分析</b>：", body_style))
story.append(Paragraph("• <font face='Courier'>DASHSCOPE_BASE</font> 常量的值已经包含 <font face='Courier'>/api/v1</font> 前缀", list_style))
story.append(Paragraph("• 在拼接endpoint时又手动添加了 <font face='Courier'>/api/v1</font>，导致路径重复", list_style))
story.append(Paragraph("<b>修复方案</b>：在 <font face='Courier'>submit_video_task</font> 函数中，拼接endpoint时不再添加 <font face='Courier'>/api/v1</font> 前缀，直接使用 <font face='Courier'>DASHSCOPE_BASE</font> + 相对路径。", body_style))
story.append(Paragraph("<b>修改文件</b>：<font face='Courier'>scripts/common.py</font> 中的 <font face='Courier'>submit_video_task</font> 函数", body_style))

# 修复总结
story.append(PageBreak())
story.append(Paragraph("修复总结", heading2_style))

summary_data = [
    ['问题编号', '问题类型', '影响范围', '修复状态'],
    ['1', '配置缺失', 'OSS图片上传', '✅ 已修复'],
    ['2', 'URL格式', 'wan API调用', '✅ 已修复'],
    ['3', 'API版本', '视频生成', '✅ 已修复'],
    ['4', '路径处理', 'ffmpeg拼接', '✅ 已修复'],
    ['5', 'URL拼接', 'API调用', '✅ 已修复'],
]

summary_table = Table(summary_data, colWidths=[2.5*cm, 3*cm, 4*cm, 3*cm])
summary_table.setStyle(TableStyle([
    ('FONTNAME', (0, 0), (-1, -1), chinese_font),
    ('FONTSIZE', (0, 0), (-1, -1), 10),
    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f2f2')]),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ('TOPPADDING', (0, 0), (-1, -1), 8),
]))
story.append(summary_table)
story.append(Spacer(1, 0.5*cm))

# 测试验证
story.append(Paragraph("测试验证", heading2_style))
story.append(Paragraph("修复完成后，成功完成了完整的视频生成流程：", body_style))
story.append(Paragraph("✅ 阶段0：企业微信询问数据来源", list_style))
story.append(Paragraph("✅ 阶段1：从GitHub项目取材（luongnv89/claude-howto）", list_style))
story.append(Paragraph("✅ 阶段2：生成4个分镜并通过企业微信审核", list_style))
story.append(Paragraph("✅ 阶段3：视频生成", list_style))
story.append(Paragraph("  • 4个镜头图片生成成功", list_style))
story.append(Paragraph("  • 4个镜头视频生成成功（每个约1-5分钟）", list_style))
story.append(Paragraph("  • ffmpeg拼接成功", list_style))
story.append(Paragraph("  • 上传OSS成功", list_style))
story.append(Paragraph("  • 企业微信通知发送成功", list_style))

story.append(Spacer(1, 0.3*cm))
story.append(Paragraph("<b>最终产物</b>：", body_style))
story.append(Paragraph("• 视频文件：<font face='Courier'>workdir/final_video.mp4</font>", list_style))
story.append(Paragraph("• 文件大小：4.4MB", list_style))
story.append(Paragraph("• 时长：20秒", list_style))
story.append(Paragraph("• 分辨率：782x1174（竖版）", list_style))
story.append(Paragraph("• OSS下载地址：已生成并发送到企业微信", list_style))

# 建议与注意事项
story.append(Paragraph("建议与注意事项", heading2_style))
story.append(Paragraph("1. <b>API版本监控</b>：定期检查阿里云百炼API文档，关注版本变更和废弃通知", list_style))
story.append(Paragraph("2. <b>OSS桶配置</b>：确保所有必需的OSS桶已正确配置并设置合适的访问权限", list_style))
story.append(Paragraph("3. <b>路径处理</b>：使用docker时注意路径映射，优先使用相对路径", list_style))
story.append(Paragraph("4. <b>错误处理</b>：建议在各脚本中增加更详细的错误日志，便于快速定位问题", list_style))
story.append(Paragraph("5. <b>测试覆盖</b>：建议增加单元测试，覆盖各种边界情况", list_style))

# 附录
story.append(Paragraph("附录：修改文件清单", heading2_style))
story.append(Paragraph("1. <font face='Courier'>scripts/common.py</font>", list_style))
story.append(Paragraph("  • <font face='Courier'>oss_upload_file</font> 函数：支持 <font face='Courier'>OSS_IMAGE</font> env_key，返回干净URL", list_style))
story.append(Paragraph("  • <font face='Courier'>submit_video_task</font> 函数：升级到wan2.7 API，修复endpoint拼接", list_style))
story.append(Paragraph("2. <font face='Courier'>scripts/video_build.py</font>", list_style))
story.append(Paragraph("  • 生成 <font face='Courier'>concat.txt</font> 的逻辑：使用相对路径", list_style))

# 页脚信息
story.append(Spacer(1, 1*cm))
story.append(Paragraph("报告生成时间：2026-10-26 22:22", body_style))
story.append(Paragraph("下次测试建议：2026-11-26", body_style))

# 生成PDF
doc.build(story)

print(f"PDF生成成功: {pdf_filename}")
print(f"文件大小: {os.path.getsize(pdf_filename)} bytes")
