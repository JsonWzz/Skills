#!/usr/bin/env python3
"""生成修复报告PDF"""

from weasyprint import HTML, CSS
import os

# 读取markdown文件
with open('fix-report-2026-10-26.md', 'r', encoding='utf-8') as f:
    md_content = f.read()

# 简单的markdown转HTML（使用标准库）
def simple_markdown_to_html(md_text):
    """简单的markdown转HTML"""
    lines = md_text.split('\n')
    html_lines = []
    in_code_block = False
    in_list = False
    
    for line in lines:
        # 代码块
        if line.startswith('```'):
            if in_code_block:
                html_lines.append('</code></pre>')
                in_code_block = False
            else:
                html_lines.append('<pre><code>')
                in_code_block = True
            continue
        
        if in_code_block:
            html_lines.append(line)
            continue
        
        # 标题
        if line.startswith('# '):
            html_lines.append(f'<h1>{line[2:]}</h1>')
        elif line.startswith('## '):
            html_lines.append(f'<h2>{line[3:]}</h2>')
        elif line.startswith('### '):
            html_lines.append(f'<h3>{line[4:]}</h3>')
        # 列表
        elif line.startswith('- '):
            if not in_list:
                html_lines.append('<ul>')
                in_list = True
            html_lines.append(f'<li>{line[2:]}</li>')
        else:
            if in_list:
                html_lines.append('</ul>')
                in_list = False
            # 普通段落
            if line.strip():
                html_lines.append(f'<p>{line}</p>')
    
    if in_list:
        html_lines.append('</ul>')
    
    return '\n'.join(html_lines)

html_content = simple_markdown_to_html(md_content)

# 添加CSS样式
full_html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
@page {{
    size: A4;
    margin: 2cm;
}}
body {{
    font-family: "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", sans-serif;
    font-size: 11pt;
    line-height: 1.6;
}}
h1 {{
    font-size: 18pt;
    color: #333;
    border-bottom: 2px solid #333;
    padding-bottom: 10px;
    margin-top: 20px;
}}
h2 {{
    font-size: 14pt;
    color: #555;
    margin-top: 20px;
    border-left: 4px solid #007bff;
    padding-left: 10px;
}}
h3 {{
    font-size: 12pt;
    color: #666;
    margin-top: 15px;
}}
ul {{
    margin: 10px 0;
    padding-left: 20px;
}}
li {{
    margin: 5px 0;
}}
p {{
    margin: 10px 0;
    text-align: justify;
}}
code {{
    background-color: #f4f4f4;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: "Courier New", monospace;
    font-size: 10pt;
}}
pre {{
    background-color: #f8f8f8;
    padding: 10px;
    border-left: 3px solid #007bff;
    overflow-x: auto;
    font-size: 9pt;
    margin: 10px 0;
}}
strong {{
    color: #d9534f;
    font-weight: bold;
}}
</style>
</head>
<body>
{html_content}
</body>
</html>
"""

# 生成PDF
output_file = 'fix-report-2026-10-26.pdf'
HTML(string=full_html).write_pdf(output_file)

print(f"PDF生成成功: {output_file}")
print(f"文件大小: {os.path.getsize(output_file)} bytes")
