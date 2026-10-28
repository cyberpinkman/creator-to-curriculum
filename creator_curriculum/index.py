"""Knowledge maps that send learners to the original videos, without a new course."""
import csv
import html
import io
import json
import re
from pathlib import Path

from .core import (atomic_text, digest, index_package_id, index_learning_design, index_learning_feedback, index_task,
                   require, validate_index_plan, write_json)
from .feedback import feedback_context_for_workspace, read_feedback_state, write_feedback_report
from .index_workflow import resolve_index_plan_identity, write_index_identity
from .render import link, text, timecode


def evidence_markdown(evidence):
    kind = '画面 OCR' if evidence['evidence_kind'] == 'screen_ocr' else '转写'
    return (f'  - {text(evidence.get("label", "内容依据"))} · '
            f'{timecode(evidence["start"])}–{timecode(evidence["end"])} · '
            f'{kind} / {evidence["transcript_source"]} · 段 {evidence["segment_id"]}：{text(evidence["quote"])}')


def topic_source_signature(entries, videos):
    """Fingerprint original sources and displayed quotes, not Agent interpretation."""
    def quotes(evidence):
        fields = ('segment_id', 'quote', 'start', 'end', 'evidence_kind', 'transcript_source')
        return sorted(({key: item[key] for key in fields} for item in evidence),
                      key=lambda item: (item['segment_id'], item['quote']))

    sources = []
    for entry in sorted(entries, key=lambda item: item['id']):
        video = videos[entry['id']]
        sources.append({**{key: entry[key] for key in ('id', 'title', 'url', 'duration_seconds')},
                        'transcript_source': video['transcript_source'],
                        'segments': sorted(video['segments'], key=lambda item: item['id']),
                        'review_evidence': quotes((entry['review'] or {}).get('evidence', [])),
                        'topic_evidence': quotes(entry['topic_evidence'])})
    return digest(sources)


ACTIVITY_LABELS = {'understand': '理解概念', 'practice': '操作练习', 'create': '制作产物',
                   'compare': '比较判断', 'lookup': '查找使用'}
COVERAGE_LABELS = {'supported': '已有内容支持', 'candidate': '待核对的候选内容',
                   'missing': '缺少内容', 'conflicting': '存在分歧或条件差异'}
READINESS_LABELS = {'ready': '准备条件齐全', 'needs_review': '需要核对', 'partial': '部分可开始',
                    'blocked': '需要先处理缺口', 'legacy': '旧版索引，学习设计尚未评估'}
_LOAD_FEEDBACK_STATE = object()
_GENERATED_FILES = {'corpus.json', 'learner.json', 'index-plan.json', 'index-workspace.json',
                    'feedback-state.json', 'feedback-input.json', 'learning-feedback.json', 'learning-feedback.md',
                    'README.md', 'materials.md', 'knowledge-map.svg', 'video-index.csv',
                    'learning-design.json', 'learning-design.md', 'index.json', 'index.html'}


def material_documents(resources, output):
    """Resolve resources against the output workspace, never an external plan's directory."""
    documents = []
    generated_paths = {(output / name).resolve() for name in _GENERATED_FILES}
    text_suffixes = {'.md', '.txt', '.csv', '.json', '.srt', '.vtt'}
    limit = 256 * 1024
    for resource in resources:
        document = {key: value for key, value in resource.items()
                    if key not in {'preview_text', 'preview_unavailable'}}
        if resource.get('local_path'):
            path = output / resource['local_path']
            require(path.resolve().is_relative_to(output.resolve()), 'Material resolves outside index folder')
            require(path.resolve() not in generated_paths, 'Material path conflicts with a generated workspace file')
            require(path.is_file(), f'Material file missing: {resource["local_path"]}')
            if path.suffix.lower() in text_suffixes:
                with path.open('rb') as handle:
                    content = handle.read(limit + 1)
                if len(content) > limit:
                    document['preview_unavailable'] = '文件超过 256 KiB，请下载原文件查看。'
                else:
                    try:
                        document['preview_text'] = content.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        document['preview_unavailable'] = '文件不是 UTF-8 文本，请下载后用原编码打开。'
        documents.append(document)
    return documents


def learning_markdown(plan, learner, design, activities, videos):
    """Project the shared planning result; do not infer a new route in exporters."""
    lines = ['## 学习需求与覆盖', f'当前状态：{READINESS_LABELS[design["status"]]}。这不代表教学效果或掌握认证。']
    if learner is not None:
        modes = {'systematic': '系统学习', 'problem': '解决具体问题', 'explore': '浏览探索'}
        minutes = learner['minutes_per_session']
        lines += [f'目标：{text(learner["goal"])}',
                  f'起点：{text(learner["level"] or "未知，待确认")}；方式：{modes[learner["mode"]]}；'
                  f'每次可用时间：{str(minutes) + " 分钟" if minutes is not None else "未知"}。']
        for key, label in [('prior_knowledge', '已有基础（用户描述）'), ('constraints', '约束'), ('assumptions', '规划假设')]:
            lines.extend(f'- {label}：{text(item)}' for item in learner[key])
    lines.extend(f'- {text(issue)}' for issue in design['issues'])
    for capability in plan.get('capabilities', []):
        coverage = capability['coverage']
        lines += [f'### {text(capability["title"])}', f'期望能力：{text(capability["outcome"])}',
                  f'{"目标必需" if capability["required"] else "可选拓展"} · {COVERAGE_LABELS[coverage["status"]]}：{text(coverage["reason"])}']
        if coverage.get('next_action'):
            lines.append('下一步处理：' + text(coverage['next_action']))
        for source in coverage['sources']:
            video = videos[source['video_id']]
            lines.append(f'- 来源：{link(video["title"], video["url"]) if video["url"] else text(video["title"])}；'
                         f'证据段：{text("、".join(source["segment_ids"]) or "尚无，只有候选入口")}')
    if activities:
        lines.append('## 按路径学习')
        for path in design['paths']:
            lines += [f'### {text(path["title"])}', '阶段结果：' + text(path['outcome']),
                      '安排理由：' + text(path['reason']),
                      '路径状态：' + READINESS_LABELS[path['readiness']['status']]]
            lines.extend('- ' + text(issue) for issue in path['readiness']['issues'])
            for number, step in enumerate(path['steps'], 1):
                activity = activities[step['activity_id']]
                lines += [f'<a id="study-{path["id"]}-{step["id"]}"></a>',
                          f'#### {number}. {text(activity["title"])} · {ACTIVITY_LABELS[activity["kind"]]}',
                          '这一步的安排理由：' + text(step['reason']),
                          f'知识点：[查看对应来源](#{activity["topic_id"]})',
                          '本次目标：' + text(activity['objective'])]
                lines.extend(f'{i}. {text(instruction)}' for i, instruction in enumerate(activity['instructions'], 1))
                lines += ['留下的产物：' + text(activity['output']), '停止点：' + text(activity['stop_when'])]
                lines.extend('- 自查：' + text(criterion) for criterion in activity['success_criteria'])
                lines.append('准备状态：' + READINESS_LABELS[step['readiness']['status']])
                lines.extend('- ' + text(issue) for issue in step['readiness']['issues'])
                minutes = activity.get('practice_minutes')
                lines.append('练习估算：' + (f'{minutes} 分钟' if minutes is not None else '未知') + '；不含完整原视频观看时间。')
                for source in activity['sources']:
                    lines.append('- 本次来源：' + (link(source['title'], source['url']) if source['url'] else text(source['title'])))
                    lines.extend(evidence_markdown(e) for e in source['evidence'])
                for material in activity['required_materials']:
                    target = material.get('local_path') or material.get('url')
                    title = link(material['title'], target) if target else text(material['title'])
                    lines.append(f'- 本次必需资料：{title} · {text(material["status"])}')
    return lines


def build_index(corpus, plan, output, *, learner=None, feedback_state=_LOAD_FEEDBACK_STATE):
    used = validate_index_plan(plan, corpus, learner)
    out = Path(output)
    plan = resolve_index_plan_identity(out, plan, corpus)
    videos = {v["id"]: v for v in corpus["videos"]}
    topics = {t["id"]: t for t in plan["topics"]}
    reviews = plan.get("reviews", {})
    material_data = material_documents(plan.get('materials', []), out)
    design = index_learning_design(plan, corpus, learner)
    feedback_context = feedback_context_for_workspace(out, corpus, plan, learner)
    save_feedback_state = feedback_state is not _LOAD_FEEDBACK_STATE or (out / 'feedback-state.json').exists()
    if feedback_state is _LOAD_FEEDBACK_STATE:
        feedback_state = read_feedback_state(out, feedback_context)
    if feedback_state is None:
        feedback_state = {'schema_version': 1, 'package_id': index_package_id(plan, corpus), 'attempts': [], 'feedback': []}
    learning_feedback = index_learning_feedback(feedback_context, feedback_state)
    paths = design['paths']
    is_design = plan['schema_version'] == 2
    materials = {m['id']: {**m, 'material_index': i} for i, m in enumerate(material_data) if 'id' in m}
    activities = {}
    for activity in plan.get('activities', []) if is_design else []:
        sources = []
        for source in activity['sources']:
            video = videos[source['video_id']]
            segments = {s['id']: s for s in video['segments']}
            evidence = [{**e, 'start': segments[e['segment_id']]['start'], 'end': segments[e['segment_id']]['end'],
                         'evidence_kind': segments[e['segment_id']].get('evidence_kind', 'speech_transcript'),
                         'transcript_source': video['transcript_source']}
                        for e in reviews.get(video['id'], {}).get('evidence', []) if e['segment_id'] in source['segment_ids']]
            sources.append({**source, **{key: video[key] for key in ('title', 'url', 'duration_seconds')}, 'evidence': evidence})
        activities[activity['id']] = {**activity, 'sources': sources,
                                     'required_materials': [materials[mid] for mid in activity['required_material_ids']]}
    rows, documents = [], []
    markdown = [f'# {plan["title"]}', plan["overview"], f'学习目标：{plan["goal"]}',
                f'索引覆盖 {len(used)} 条作品；{len(reviews)} 条有转写/OCR辅助归类，其余依据标题。目录不代表所有原视频已观看。',
                *learning_markdown(plan, learner if is_design else None, design, activities, videos),
                '## 知识点路径索引']
    for path in paths:
        markdown.append(f'### {path["title"]}')
        for exemption in path.get('prerequisite_exemptions', []):
            label = '假定已具备（非掌握认证）' if exemption['status'] == 'assumed_known' else '显式跳过的先修缺口'
            markdown.append(f'- {label}：[{topics[exemption["topic_id"]]["title"]}](#{exemption["topic_id"]})；{exemption["reason"]}')
        for i, tid in enumerate(path['topic_ids'], 1):
            topic = topics[tid]
            markdown.append(f'{i}. [{topic["title"]}](#{tid})：{topic["question"]}')
    for topic in plan["topics"]:
        markdown += [f'<a id="{topic["id"]}"></a>', f'## {topic["title"]}',
                     topic["question"], topic["guidance"]]
        task = None if is_design else index_task(topic)
        if task:
            primary = videos[task['primary_video_id']]
            practice = f'{task["practice_minutes"]} 分钟（估算）' if task.get('practice_minutes') is not None else '未估算'
            full_duration = timecode(primary['duration_seconds']) if primary['duration_seconds'] is not None else '未知'
            markdown += [f'本次小目标：{task["objective"]}',
                         f'主要观看入口：{link(primary["title"], primary["url"]) if primary["url"] else text(primary["title"])}；整条视频时长：{full_duration}（不是本次任务预算）。练习时间：{practice}。',
                         f'停止点：{task["stop_when"]}']
        else:
            for path in paths:
                for step in path['steps']:
                    if step['topic_id'] == topic['id']:
                        markdown.append(f'学习活动：[{text(activities[step["activity_id"]]["title"])}](#study-{path["id"]}-{step["id"]}) · {text(path["title"])}')
        if topic.get('prerequisites'):
            markdown.append('先修：'+'、'.join(topics[x]['title'] for x in topic['prerequisites']))
        if topic.get('watch_for'): markdown.append('观看重点：'+topic['watch_for'])
        if topic.get('self_check'): markdown.append('看完自查：'+topic['self_check'])
        entries = []
        for vid in topic["video_ids"]:
            video = videos[vid]
            duration = timecode(video['duration_seconds']) if video['duration_seconds'] is not None else '时长未知'
            entry = {k: video.get(k) for k in ('id', 'title', 'url', 'duration_seconds')}
            review = None
            if vid in reviews:
                segments = {s['id']: s for s in video['segments']}
                review = {**reviews[vid], 'evidence': [{**e, 'start': segments[e['segment_id']]['start'],
                           'end': segments[e['segment_id']]['end'], 'evidence_kind': segments[e['segment_id']].get('evidence_kind','speech_transcript'),
                           'transcript_source': video['transcript_source']}
                          for e in reviews[vid]['evidence']]}
            selected_segments = topic.get('video_evidence', {}).get(vid, [])
            topic_evidence = [e for e in review['evidence'] if e['segment_id'] in selected_segments] if review else []
            basis = '主题有转写/OCR证据定位' if topic_evidence else ('标题归类；视频证据未关联此主题' if review else '标题归类')
            entry.update(basis=basis, recommended=vid in topic.get('recommended_ids', []),
                         review=review, topic_evidence=topic_evidence, group=topic['group'], topic=topic['title'])
            entries.append(entry)
            rows.append([topic['group'],topic['title'],vid,video['title'],video['url'],video['duration_seconds'],basis,'先看' if entry['recommended'] else '补充'])
            markdown.append(f'- {"**先看** · " if entry["recommended"] else ""}{link(video["title"],video["url"]) if video["url"] else text(video["title"])} · {duration} · {basis}')
            if topic_evidence:
                markdown.append('  本主题证据位置（不是完整教学区间；请打开原视频手动定位）：')
                markdown.extend(evidence_markdown(e) for e in topic_evidence)
            elif review:
                markdown.append('  尚未把视频证据关联到本主题；下列完整证据不能视为本主题已核准。')
            if review:
                markdown += ['<details><summary>完整视频证据（供核对）</summary>', review['note'],
                             '引文时间不是完整教学区间；机器证据可能有误，请核对原作。']
                markdown.extend(evidence_markdown(e) for e in review['evidence'])
                markdown.append('</details>')
        for path in paths if not is_design else []:
            if topic['id'] not in path['topic_ids']:
                continue
            position = path['topic_ids'].index(topic['id'])
            if position + 1 < len(path['topic_ids']):
                following = topics[path['topic_ids'][position + 1]]
                markdown.append(f'{path["title"]} · 下一步：[{following["title"]}](#{following["id"]})')
            else:
                markdown.append(f'{path["title"]} · 路径已结束。可停下记录，也可自由查阅。')
        source_signature = topic_source_signature(entries, videos)
        documents.append({**topic, 'task':task, 'source_signature':source_signature, 'entries':entries})
    markdown += ['## 学习建议', *[f'- {x}' for x in plan.get('learning_advice', [])], '## 学习素材', '[查看资料与下载状态](materials.md)', '## 范围与使用说明', *[f'- {x}' for x in plan.get('limitations', [])],
                 f'- 来源发现状态：{corpus["discovery"]["status"]}；范围：{corpus["discovery"]["scope"]}。']
    readme = '\n\n'.join(markdown) + '\n'
    materials = ['# 学习素材与课件索引', '博主原作、外部补充和 Agent 学习提示分别标识。下载状态由实际文件决定。']
    for m in plan.get('materials', []):
        materials += [f'## {m["title"]}', f'来源：{m["origin"]} · 状态：{m["status"]}', m['description']]
        if m.get('url'): materials.append(link('来源入口',m['url']))
        if m.get('local_path'): materials.append(link('本地文件',m['local_path']))
    svg=knowledge_map(plan)
    stream=io.StringIO();writer=csv.writer(stream)
    writer.writerow(['分组','知识点','视频ID','原视频标题','原视频链接','秒数','依据','顺序']);writer.writerows([["'"+x if isinstance(x,str) and x.lstrip().startswith(('=','+','-','@')) else x for x in row] for row in rows])
    payload={**plan,'package_id':index_package_id(plan, corpus),'learning_paths':paths,'topics':documents,'inventory_count':len(corpus['videos']),'indexed_count':len(used),'review_count':len(reviews),'creator':corpus['creator'],
             'learning_design': design, 'materials': material_data,
             'feedback_context': feedback_context, 'learning_feedback': learning_feedback}
    if is_design:
        payload.update(learner=learner, activities=list(activities.values()))
    design_markdown = '\n\n'.join(learning_markdown(plan, learner if is_design else None, design, activities, videos)) + '\n'
    # Embedded JSON is non-executable and cannot terminate the script element.
    encoded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    assets = Path(__file__).with_name('web')
    page = (assets/'reader.html').read_text(encoding='utf-8')
    parts = {'TITLE': html.escape(plan['title']), 'DATA': encoded,
             'STYLE': (assets/'reader.css').read_text(encoding='utf-8'),
             'SCRIPT': '\n'.join((assets/name).read_text(encoding='utf-8')
                                 for name in ('feedback.js', 'progress.js', 'routes.js', 'reader.js'))}
    # One pass: source text resembling a template marker must remain literal.
    page = re.sub(r'__(TITLE|DATA|STYLE|SCRIPT)__', lambda match: parts[match[1]], page)
    # All input, identity, material, history and bundled-template checks precede
    # writes. Persist the exact inputs projected above so feedback cannot read a
    # different plan from the one delivered to the learner.
    write_json(out/'corpus.json', corpus)
    write_json(out/'index-plan.json', plan)
    if is_design:
        write_json(out/'learner.json', learner)
    write_index_identity(out, plan)
    atomic_text(out/'README.md', readme)
    atomic_text(out/'materials.md', '\n\n'.join(materials) + '\n')
    atomic_text(out/'knowledge-map.svg', svg)
    atomic_text(out/'video-index.csv', '\ufeff' + stream.getvalue())
    write_json(out/'learning-design.json', design)
    atomic_text(out/'learning-design.md', design_markdown)
    write_feedback_report(out, feedback_context, feedback_state)
    write_json(out/'index.json', payload)
    if save_feedback_state:
        write_json(out/'feedback-state.json', feedback_state)
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
                svg.append(f'<a href="index.html#topic/{topic["id"]}"><title>{title}</title><text x="{x+28}" y="{ty}" font-size="14" fill="#2457ae">{short}</text></a>')
        y += row_height
    svg.append('</g></svg>')
    return ''.join(svg)
