"""Knowledge maps that send learners to the original videos, without a new course."""
import csv
import html
import io
import json
import re
from pathlib import Path

from .core import atomic_text, require, validate_index_plan, write_json
from .render import link, text, timecode


def build_index(corpus, plan, output):
    used = validate_index_plan(plan, corpus)
    out = Path(output)
    videos = {v["id"]: v for v in corpus["videos"]}
    topics = {t["id"]: t for t in plan["topics"]}
    reviews = plan.get("reviews", {})
    for resource in plan.get("materials", []):
        if resource.get("local_path"):
            require((out/resource["local_path"]).resolve().is_relative_to(out.resolve()), "Material resolves outside index folder")
            require((out/resource["local_path"]).is_file(), f'Material file missing: {resource["local_path"]}')
    rows, documents = [], []
    markdown = [f'# {plan["title"]}', plan["overview"], f'学习目标：{plan["goal"]}',
                f'索引覆盖 {len(used)} 条作品；{len(reviews)} 条有转写/OCR辅助归类，其余依据标题。目录不代表所有原视频已观看。',
                '## 建议起步顺序']
    for i, tid in enumerate(plan["start_path"], 1):
        topic = topics[tid]
        markdown.append(f'{i}. [{topic["title"]}](#{tid})：{topic["question"]}')
    for topic in plan["topics"]:
        markdown += [f'<a id="{topic["id"]}"></a>', f'## {topic["title"]}',
                     topic["question"], topic["guidance"]]
        if topic.get('prerequisites'):
            markdown.append('先修：'+'、'.join(topics[x]['title'] for x in topic['prerequisites']))
        if topic.get('watch_for'): markdown.append('观看重点：'+topic['watch_for'])
        if topic.get('self_check'): markdown.append('看完自查：'+topic['self_check'])
        entries = []
        for vid in topic["video_ids"]:
            video = videos[vid]
            basis = '转写/OCR辅助归类' if vid in reviews else '标题归类'
            duration = timecode(video['duration_seconds']) if video['duration_seconds'] is not None else '时长未知'
            entry = {k: video.get(k) for k in ('id', 'title', 'url', 'duration_seconds')}
            review = None
            if vid in reviews:
                segments = {s['id']: s for s in video['segments']}
                review = {**reviews[vid], 'evidence': [{**e, 'start': segments[e['segment_id']]['start'],
                           'end': segments[e['segment_id']]['end'], 'evidence_kind': segments[e['segment_id']].get('evidence_kind','speech_transcript')}
                          for e in reviews[vid]['evidence']]}
            entry.update(basis=basis, recommended=vid in topic.get('recommended_ids', []),
                         review=review, group=topic['group'], topic=topic['title'])
            entries.append(entry)
            rows.append([topic['group'],topic['title'],vid,video['title'],video['url'],video['duration_seconds'],basis,'先看' if entry['recommended'] else '补充'])
            markdown.append(f'- {"**先看** · " if entry["recommended"] else ""}{link(video["title"],video["url"]) if video["url"] else text(video["title"])} · {duration} · {basis}')
            if review:
                markdown.append('  定位说明：'+review['note'])
                for e in review['evidence']:
                    markdown.append(f'  - {text(e.get("label", "内容依据"))} · {timecode(e["start"])}–{timecode(e["end"])} · {"画面 OCR" if e["evidence_kind"] == "screen_ocr" else "机器转写"}：{text(e["quote"])}')
        documents.append({**topic,'entries':entries})
    markdown += ['## 学习建议', *[f'- {x}' for x in plan.get('learning_advice', [])], '## 学习素材', '[查看资料与下载状态](materials.md)', '## 范围与使用说明', *[f'- {x}' for x in plan.get('limitations', [])],
                 f'- 来源发现状态：{corpus["discovery"]["status"]}；范围：{corpus["discovery"]["scope"]}。']
    atomic_text(out/'README.md','\n\n'.join(markdown)+'\n')
    materials = ['# 学习素材与课件索引', '博主原作、外部补充和 Agent 学习提示分别标识。下载状态由实际文件决定。']
    for m in plan.get('materials', []):
        materials += [f'## {m["title"]}', f'来源：{m["origin"]} · 状态：{m["status"]}', m['description']]
        if m.get('url'): materials.append(link('来源入口',m['url']))
        if m.get('local_path'): materials.append(link('本地文件',m['local_path']))
    atomic_text(out/'materials.md','\n\n'.join(materials)+'\n')
    svg=knowledge_map(plan)
    atomic_text(out/'knowledge-map.svg',svg)
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['分组','知识点','视频ID','原视频标题','原视频链接','秒数','依据','顺序']);writer.writerows([["'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x for x in row] for row in rows])
    atomic_text(out/'video-index.csv','\ufeff'+stream.getvalue())
    payload={**plan,'topics':documents,'inventory_count':len(corpus['videos']),'indexed_count':len(used),'review_count':len(reviews),'creator':corpus['creator']}
    write_json(out/'index.json',payload)
    # Embedded JSON is non-executable and cannot terminate the script element.
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    assets = Path(__file__).with_name('web')
    page = (assets/'reader.html').read_text(encoding='utf-8')
    parts = {'TITLE': html.escape(plan['title']), 'DATA': encoded,
             'STYLE': (assets/'reader.css').read_text(encoding='utf-8'),
             'SCRIPT': (assets/'reader.js').read_text(encoding='utf-8')}
    # One pass: source text resembling a template marker must remain literal.
    page = re.sub(r'__(TITLE|DATA|STYLE|SCRIPT)__', lambda match: parts[match[1]], page)
    atomic_text(out/'index.html',page)
    return out.resolve()


def knowledge_map(plan):
    """Printable topic tree; the HTML reader reflows the same groups on mobile."""
    groups = list(dict.fromkeys(topic['group'] for topic in plan['topics']))
    columns = min(3, len(groups))
    cell_width = 420
    width = columns * cell_width + 48
    rows = [groups[i:i+columns] for i in range(0, len(groups), columns)]
    heights = [90 + max(sum(t['group'] == g for t in plan['topics']) for g in row) * 42 for row in rows]
    height = 100 + sum(heights)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="知识地图：按主题分组，点击知识点打开原视频索引。">',
           f'<rect width="{width}" height="{height}" fill="#fcfcfb"/>',
           '<g font-family="system-ui,sans-serif" fill="#24262b">',
           f'<text x="30" y="44" font-size="22" font-weight="600">{html.escape(plan["title"])}</text>',
           '<text x="30" y="72" font-size="13" fill="#61646d">主题分组 · 点击知识点查看原视频与先修关系</text>']
    y = 112
    for row, row_height in zip(rows, heights):
        for col, group in enumerate(row):
            x = 30 + col * cell_width
            items = [t for t in plan['topics'] if t['group'] == group]
            svg.append(f'<text x="{x}" y="{y}" font-size="16" font-weight="600">{html.escape(group)}</text>')
            svg.append(f'<path d="M {x+5} {y+18} V {y+len(items)*42}" fill="none" stroke="#dedfdf"/>')
            for i, topic in enumerate(items):
                ty = y + 40 + i * 42
                title = html.escape(topic['title'])
                short = html.escape(topic['title'][:23] + ('…' if len(topic['title']) > 23 else ''))
                svg.append(f'<path d="M {x+5} {ty-5} H {x+19}" stroke="#dedfdf"/>')
                svg.append(f'<a href="index.html#{topic["id"]}"><title>{title}</title><text x="{x+28}" y="{ty}" font-size="14" fill="#2457ae">{short}</text></a>')
        y += row_height
    svg.append('</g></svg>')
    return ''.join(svg)
