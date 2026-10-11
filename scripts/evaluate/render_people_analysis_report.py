#!/usr/bin/env python3
"""Render the local CSI Markdown report as a standalone HTML file.

Small renderer for the report's paragraphs, lists, tables, links and code blocks;
not a general Markdown parser. Plot images are embedded for offline sharing.
"""
import base64
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/csi_people_analysis_20260914.md'


def inline(text):
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    return text


def main():
    lines = SOURCE.read_text().splitlines()
    content, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        if line.startswith('```'):
            code = []; i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            content.append('<pre><code>{}</code></pre>'.format(html.escape('\n'.join(code))))
        elif line.startswith('#'):
            level = len(line) - len(line.lstrip('#'))
            content.append('<h{0}>{1}</h{0}>'.format(level, inline(line[level:].strip())))
        elif line.startswith('|'):
            table = []
            while i < len(lines) and lines[i].startswith('|'):
                cells = [s.strip() for s in lines[i].strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', s) for s in cells):
                    tag = 'th' if not table else 'td'
                    table.append('<tr>' + ''.join('<{0}>{1}</{0}>'.format(tag, inline(s)) for s in cells) + '</tr>')
                i += 1
            content.append('<div class="table-wrap"><table>' + ''.join(table) + '</table></div>')
            continue
        elif line.startswith('- '):
            items = []
            while i < len(lines) and lines[i].startswith('- '):
                items.append('<li>' + inline(lines[i][2:]) + '</li>'); i += 1
            content.append('<ul>' + ''.join(items) + '</ul>'); continue
        elif line.startswith('!['):
            match = re.fullmatch(r'!\[([^]]*)\]\(([^)]*)\)', line)
            alt, rel = match.groups()
            img = SOURCE.parent / rel
            encoded = base64.b64encode(img.read_bytes()).decode('ascii')
            content.append('<figure><img alt="{}" src="data:image/png;base64,{}"><figcaption>{}</figcaption></figure>'.format(
                html.escape(alt), encoded, html.escape(alt)))
        else:
            paragraph = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].startswith(('#', '|', '- ', '```', '![')):
                i += 1; paragraph.append(lines[i])
            content.append('<p>' + inline(' '.join(paragraph)) + '</p>')
        i += 1
    css = '''body{margin:0;background:#f4f6fa;color:#172235;font-family:"Noto Sans CJK KR","Malgun Gothic",sans-serif;line-height:1.85}
    main{max-width:1000px;margin:32px auto;padding:42px;background:white;border-radius:16px}
    h1{font-size:29px;line-height:1.5}h2{margin-top:48px;font-size:23px;border-bottom:2px solid #dce5f4;padding-bottom:10px}
    strong{color:#164aa1}p,li{font-size:15px}li{margin-bottom:10px}a{color:#185abc;text-underline-offset:3px}
    table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.6}th,td{padding:11px 13px;border:1px solid #dbe2ec;text-align:left}
    th{background:#eaf0fb}tr:nth-child(even){background:#f8fafc}.table-wrap{overflow:auto;margin:22px 0}
    code{font-family:monospace;background:#edf1f7;padding:2px 4px;border-radius:4px}pre{padding:18px;background:#edf1f7;overflow:auto}
    figure{margin:24px 0}img{max-width:100%;height:auto}figcaption{font-size:13px;color:#64748b;text-align:center}
    @media(max-width:700px){main{padding:20px;margin:0;border-radius:0}h1{font-size:24px}}
    @media print{body{background:white}main{margin:0;padding:0;max-width:none}h2{break-after:avoid}table,figure{break-inside:avoid}}
    '''
    doc = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
    doc += '<title>CSI 0~3명 구분 및 날짜별 혼합 학습 분석</title><style>' + css + '</style><main>'
    doc += '\n'.join(content) + '</main></html>'
    target = SOURCE.with_suffix('.html'); target.write_text(doc)
    print(target)


if __name__ == '__main__':
    main()
