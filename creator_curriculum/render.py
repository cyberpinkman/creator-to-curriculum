"""Portable Markdown courseware. Source citations and generated pedagogy stay distinct."""

import html
from pathlib import Path
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .core import atomic_text, digest, read_json, validate_plan, write_json
from .pipeline import synthesize


def text(value):
    value = html.escape(str(value), quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+!|>~])", r"\\\1", value).replace("\n", "  \n")


def timecode(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def link(label, target):
    return f"[{text(label)}](<{target.replace('<', '%3C').replace('>', '%3E')}>)"


def timestamp_url(target, start):
    if not target:
        return None
    parsed = urlsplit(target)
    host = (parsed.hostname or "").lower()
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "bilibili.com", "www.bilibili.com"}:
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "t"]
        query.append(("t", str(int(start))))
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))
    return target  # Douyin has no supported timestamp deep-link here; always show the time range.


def citation(evidence):
    label = f'{evidence["video_title"]} · {timecode(evidence["start"])}–{timecode(evidence["end"])}'
    target = timestamp_url(evidence["url"], evidence["start"])
    rendered = link(label, target) if target else text(label)
    return f'- {rendered} · {text(evidence["transcript_source"])}\n  > {text(evidence["quote"])}'


def bullets(items):
    return "\n".join(f"- {text(item)}" for item in items)


def render(workspace, *, allow_partial=False):
    root = Path(workspace)
    synthesis = synthesize(root, allow_partial=allow_partial, save=False)
    plan = read_json(root / "plan.json")
    order = validate_plan(plan, synthesis)
    revision = digest({"synthesis": synthesis, "plan": plan})[:16]
    out = root / "packs" / revision
    out.mkdir(parents=True, exist_ok=True)
    coverage = synthesis["coverage"]
    scope_label = "声明清单内的已导入转写均已提取" if coverage["complete_for_declared_scope"] else "部分覆盖草稿"
    banner = (f'> {scope_label}。知识内容来自转写证据；课程排序、解释组织、练习和时长估算由 Agent 生成。\n'
              '> 引用校验仅确认片段存在，不证明解释正确、原视频观点正确或学习者已经掌握。画面、课件与演示尚未核验。\n')
    claims = {c["ref"]: c for c in synthesis["claims"]}
    modules = {m["id"]: m for m in plan["modules"]}
    overview = [f'# {text(plan["title"])}', banner, text(plan["overview"]),
                f'学习目标：{text(synthesis["learner"]["goal"])}  \n'
                f'起点：{text(synthesis["learner"]["level"])} · 每次 {synthesis["learner"]["minutes_per_session"]} 分钟',
                f'清单 {coverage["inventory_count"]} 条 → 有转写 {coverage["transcript_ready_count"]} 条 → '
                f'转写提取完成 {coverage["analyzed_video_count"]} 条。详见 [覆盖记录](coverage.md)。',
                '## 学习路径', '按下列先修顺序学习；每课先理解材料，再完成练习并对照验收标准自评。']
    courseware = [f'# {text(plan["title"])} · 课件讲义', banner]
    map_lines = ['# 知识结构', '先修关系是 Agent 对当前学习目标的教学组织建议。', '```mermaid', 'graph TD']
    for index, mid in enumerate(order, 1):
        module = modules[mid]
        # Use synthetic labels rather than interpolating untrusted text into Mermaid syntax.
        map_lines.append(f'  m{index}["{index}"]')
        for dep in module["prerequisites"]:
            map_lines.append(f'  m{order.index(dep) + 1} --> m{index}')
    map_lines.append('```')
    for index, mid in enumerate(order, 1):
        module = modules[mid]
        overview.append(f'{index}. [{text(module["title"])}](lessons/{mid}.md)')
        map_lines.append(f'{index}. {text(module["title"])}\n\n{bullets(module["objectives"])}')
        lesson_lines = [f'# {index}. {text(module["title"])}', banner,
                        '## 学习目标', bullets(module["objectives"]),
                        '先修：' + ('、'.join(text(modules[d]["title"]) for d in module["prerequisites"]) or '无')]
        courseware.extend([f'## {index}. {text(module["title"])}', bullets(module["objectives"])])
        for lesson in module["lessons"]:
            lesson_lines.extend([f'## {text(lesson["title"])}', f'预计 {lesson["estimated_minutes"]} 分钟（Agent 估算）',
                                 text(lesson["explanation"]), '### 依据与原视频'])
            courseware.extend([f'### {text(lesson["title"])}', text(lesson["explanation"]),
                               f'练习（Agent 设计）：{text(lesson["practice"]["task"])}',
                               bullets(lesson["practice"]["success_criteria"]),
                               f'[阅读原始依据](lessons/{mid}.md)'])
            for ref in lesson["claim_refs"]:
                claim = claims[ref]
                lesson_lines.extend([f'**{text(claim["title"])}**', text(claim["explanation"]),
                                     *[citation(e) for e in claim["evidence"]]])
            lesson_lines.extend(['### 练习（Agent 设计）', text(lesson["practice"]["task"]),
                                 '验收标准：', bullets(lesson["practice"]["success_criteria"])])
        atomic_text(out / "lessons" / f"{mid}.md", "\n\n".join(lesson_lines) + "\n")
    overview.extend(['## 学习材料',
                     '- [知识结构](knowledge-map.md)\n- [方法手册](methods.md)\n- [课件讲义](courseware.md)\n'
                     '- [参考资料](references.md)\n- [缺口与分歧](gaps.md)\n- [覆盖记录](coverage.md)',
                     '学习记录请写在工作区根目录的 progress.md；重新构建不会覆盖你的记录。'])
    methods = ['# 方法手册', banner]
    for claim in synthesis["claims"]:
        if claim["kind"] == "method":
            methods.extend([f'## {text(claim["title"])}', text(claim["explanation"]),
                            '\n'.join(f'{i}. {text(s)}' for i, s in enumerate(claim["steps"], 1)),
                            *[citation(e) for e in claim["evidence"]]])
    if len(methods) == 2:
        methods.append('现有证据未提取到可核对的分步方法。')
    references = ['# 参考资料', '此处仅列出创作者在转写中提及的资料。标题已知但网址未出现在证据中时，不生成猜测链接。']
    for resource in synthesis["resources"]:
        title = link(resource["title"], resource["url"]) if resource["url"] else text(resource["title"]) + '（网址待核实）'
        references.extend([f'## {title}', *[citation(e) for e in resource["evidence"]]])
    if not synthesis["resources"]:
        references.append('尚未找到带有来源证据的参考资料。')
    gap_lines = ['# 缺口与分歧', '## 学习缺口', bullets(plan["gaps"]) or 'Agent 未报告学习缺口；这不等于内容已覆盖整个领域。',
                 '## 转写与视觉不确定性', bullets([u["text"] for u in synthesis["uncertainties"]]) or '提取阶段未记录额外不确定性。',
                 '当前版本没有导入画面证据；画面中的操作、公式和原始课件仍需核对。', '## 观点分歧']
    for conflict in plan["conflicts"]:
        gap_lines.append(text(conflict["description"]))
        for ref in conflict["claim_refs"]:
            gap_lines.extend(citation(e) for e in claims[ref]["evidence"])
    if not plan["conflicts"]:
        gap_lines.append('Agent 未标注分歧；未做外部事实核查。')
    gap_lines.append('## 未纳入当前学习路径的知识')
    gap_lines.extend(f'- {text(claims[o["ref"]]["title"])}：{text(o["reason"])}' for o in plan["omitted_claims"])
    coverage_lines = ['# 覆盖记录', banner,
                      f'范围：{text(coverage["discovery"]["scope"])}',
                      f'发现状态：{coverage["discovery"]["status"]} · 观察时间：{text(coverage["discovery"]["observed_at"])}',
                      f'声明数量：{coverage["discovery"]["expected_count"] if coverage["discovery"]["expected_count"] is not None else "未知"} · '
                      f'实际清单：{coverage["inventory_count"]} · 转写可用：{coverage["transcript_ready_count"]} · '
                      f'转写提取完成：{coverage["analyzed_video_count"]}',
                      bullets(coverage["discovery"]["notes"]), '## 未完成内容']
    coverage_lines.extend(f'- {text(v["title"])}：{text(v["status"])}；{text(v["reason"])}' for v in coverage["blocked_videos"])
    coverage_lines.extend(f'- 待提取：{jid}' for jid in coverage["pending_jobs"])
    coverage_lines.append('## 已处理批次')
    coverage_lines.extend(f'- {r["job_id"]} · {r["disposition"]} · {text(r["reason"])}' for r in synthesis["reviewed_chunks"])
    documents = {"index.md": overview, "knowledge-map.md": map_lines, "methods.md": methods,
                 "courseware.md": courseware, "references.md": references,
                 "coverage.md": coverage_lines, "gaps.md": gap_lines}
    for filename, lines in documents.items():
        atomic_text(out / filename, '\n\n'.join(lines) + '\n')
    write_json(out / "evidence.json", synthesis)
    write_json(out / "curriculum.json", plan)
    atomic_text(root / "LATEST.md", f'# 最新构建\n\n[打开学习包](packs/{revision}/index.md)\n\n版本：{revision}\n')
    if not (root / "progress.md").exists():
        atomic_text(root / "progress.md", '# 我的学习记录\n\n记录日期、课节、练习产物、自评证据和下次复习时间。空白表示尚未记录。\n')
    return out
