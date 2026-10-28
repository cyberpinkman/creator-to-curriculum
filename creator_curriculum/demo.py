"""Authored fictional fixture, deliberately out of pedagogical order. Never a model fallback."""

from .core import write_json
from .pipeline import initialize, load_workspace, synthesize
from .render import render


def demo_corpus():
    records = [
        ("v_questions", "别问用户会不会用你的产品", [
            (0, 35, "别问：如果我做了这个功能，你会不会用？这种问题容易收获礼貌的肯定。请对方讲最近一次遇到问题的具体经历。"),
            (35, 80, "我的访谈顺序是：先问最近一次发生在什么时候，再问当时怎么处理，最后追问花了多少时间、用了什么替代办法。每一项都先记录原话，再单独写自己的解释。"),
            (80, 105, "你可以准备一张访谈记录模板，分成具体场景、原话、实际行为和待核实问题四栏。"),
        ]),
        ("v_synthesis", "访谈做完以后怎么整理", [
            (0, 50, "不要按功能请求给访谈贴标签。先把同一任务下的场景和实际行为放在一起，再比较不同人的处理方式。相似表述不一定是同一个问题。"),
            (50, 100, "整理时先把原话和行为写在证据栏，再写你的问题假设，然后列一个反例和下一次要验证的问题。三个人提到同一件事，只能说明值得继续研究，不能直接推出所有用户都有这个需求。"),
        ]),
        ("v_foundation", "需求和方案要分开", [
            (0, 50, "用户说想要一个提醒按钮，这是方案。先追问他在什么场景想完成什么任务，又在哪里遇到了障碍，才有机会描述问题。"),
            (50, 95, "我会用一句话写问题：谁，在什么情境下，想完成什么任务，遇到了什么障碍。这个句子先不写产品功能。"),
        ]),
        ("v_update", "这周更新安排", [(0, 15, "本周周五休息，下周继续更新。谢谢大家。")]),
    ]
    return {"schema_version": 1,
            "creator": {"name": "小林产品笔记（虚构演示）", "platform": "local", "url": None},
            "discovery": {"status": "complete", "expected_count": 4,
                          "scope": "Four fictional videos authored for this repository's offline demonstration",
                          "observed_at": "2026-10-25T00:00:00Z", "notes": ["Synthetic evidence; no real creator, platform acquisition or model execution is represented."]},
            "videos": [{"id": vid, "title": title, "url": None, "duration_seconds": segments[-1][1],
                        "status": "ready", "transcript_source": "synthetic",
                        "segments": [{"id": f"s{i}", "start": start, "end": end, "text": body}
                                     for i, (start, end, body) in enumerate(segments, 1)]}
                       for vid, title, segments in records]}


def build_demo(workspace):
    initialize(workspace, demo_corpus(), {"goal": "独立完成一次探索性用户访谈，并写出有证据的问题假设", "level": "第一次做用户访谈", "language": "zh-CN", "minutes_per_session": 30})
    root, _, _, jobs = load_workspace(workspace)
    source_claims = {
        "v_questions": [
            ("recent-event", "concept", "询问具体经历", "用最近一次真实经历替代对未来使用意愿的提问，减少问题本身引导出的肯定。", "s1_p1", []),
            ("interview-sequence", "method", "按事件追问并分开记录", "用发生时间、处理过程和替代方案还原行为；把原话与解释分栏，保留可核对的依据。", "s2_p1", ["询问最近一次发生的时间和场景。", "追问当时的处理过程与替代办法。", "记录投入的时间，分开保存原话与自己的解释。"]),
        ],
        "v_synthesis": [
            ("group-by-task", "concept", "按任务与情境归类", "先比较同一任务下的情境与行为，不直接把功能请求当成问题分类。", "s1_p1", []),
            ("evidence-hypothesis", "method", "从证据到可验证假设", "把原话、行为和假设分开，再用反例与后续问题检查解释；少量访谈不代表总体。", "s2_p1", ["整理原话和实际行为。", "写出问题假设。", "寻找反例，确定下一次要验证的问题。"]),
        ],
        "v_foundation": [
            ("problem-solution", "concept", "区分问题与方案", "功能请求只是候选方案；问题描述需要说明人、情境、任务和障碍。", "s1_p1", []),
            ("problem-sentence", "method", "写一条不含功能的问题陈述", "用谁、情境、任务、障碍写出问题，暂时不指定产品功能。", "s2_p1", ["确定具体的人和情境。", "写清想完成的任务和遇到的障碍。", "检查是否混入尚未验证的功能方案。"]),
        ],
    }
    refs = {}
    for job in jobs:
        vid = job["video"]["id"]
        segments = {s["id"]: s for s in job["segments"]}
        claims = [{"id": cid, "kind": kind, "topic": "探索性用户访谈", "title": title,
                   "explanation": explanation, "steps": steps,
                   "evidence": [{"segment_id": sid, "quote": segments[sid]["text"]}]}
                  for cid, kind, title, explanation, sid, steps in source_claims.get(vid, [])]
        refs[vid] = [f'{job["job_id"]}/{claim["id"]}' for claim in claims]
        resources = [{"title": "访谈记录模板（四栏）", "url": None,
                      "evidence": [{"segment_id": "s3_p1", "quote": segments["s3_p1"]["text"]}]}] if vid == "v_questions" else []
        notes = {"schema_version": 1, "job_id": job["job_id"], "input_hash": job["input_hash"],
                 "disposition": "knowledge" if claims else "non_instructional",
                 "reason": "包含访谈的概念或操作步骤。" if claims else "仅为更新时间通知，没有教学知识。",
                 "claims": claims, "resources": resources,
                 "uncertainties": ["演示证据为虚构；真实访谈效果需要通过实践评估。"] if claims else []}
        write_json(root / "notes" / f'{job["job_id"]}.json', notes)
    synthesis = synthesize(root)
    modules = [
        {"id": "problem", "title": "先把问题说清楚", "prerequisites": [],
         "objectives": ["区分功能请求和问题描述", "写出包含人、情境、任务、障碍的问题陈述"],
         "lessons": [{"title": "从提醒按钮追到真实障碍", "estimated_minutes": 25,
                      "explanation": "先读问题与方案的区分。面对‘我想要提醒按钮’，不要马上设计按钮；先还原谁在什么情境下想完成什么任务。把目前不知道的部分列为待核实项，避免把自己的猜测写成用户事实。然后用一句不包含具体功能的话表达问题。这条陈述是访谈的起点，需要随后用真实经历检验。",
                      "claim_refs": refs["v_foundation"],
                      "practice": {"task": "选一个你听过的功能请求，改写为问题陈述；标出其中已知事实与待核实假设。", "success_criteria": ["包含人、情境、任务和障碍。", "不把功能名当作需求。", "未知信息明确标为待核实。"]}}]},
        {"id": "interview", "title": "围绕真实经历做访谈", "prerequisites": ["problem"],
         "objectives": ["把假设性提问改成经历提问", "记录处理过程与替代方案"],
         "lessons": [{"title": "沿着一次事件追问", "estimated_minutes": 30,
                      "explanation": "带着上一课的问题假设开始访谈。请对方讲最近一次具体经历，先确认何时发生，再追问处理过程、花费和替代办法。对方给出笼统评价时，回到那次事件的细节。记录时采用场景、原话、实际行为、待核实问题四栏；你的理解另行标注，保留之后检查的余地。",
                      "claim_refs": refs["v_questions"],
                      "practice": {"task": "准备三个关于最近一次经历的问题，完成一次练习访谈并填写四栏记录。", "success_criteria": ["问题没有预设某个功能值得使用。", "记录包含一段具体事件过程和一种替代办法。", "原话与自己的解释分开。"]}}]},
        {"id": "synthesis", "title": "形成可验证的问题假设", "prerequisites": ["interview"],
         "objectives": ["按任务和情境比较证据", "用反例约束自己的结论"],
         "lessons": [{"title": "把材料整理成下一步研究", "estimated_minutes": 30,
                      "explanation": "先按任务与情境归类访谈材料，再比较实际行为。不要因为几个人使用相同词语，就假定他们面对同一个问题。对每条问题假设，写出支持它的原话与行为，寻找可能不符合它的例子，并提出下一次访谈要验证的问题。当前结果是一组可继续研究的假设；访谈人数少时，保留对适用范围的疑问。",
                      "claim_refs": refs["v_synthesis"],
                      "practice": {"task": "从访谈记录提炼一条问题假设，附证据、一个潜在反例和一个后续验证问题。", "success_criteria": ["每条解释能找到对应原话或行为。", "不把少数访谈直接推广到全部用户。", "后续问题能够区分至少两种可能解释。"]}}]},
    ]
    write_json(root / "plan.json", {"schema_version": 1, "input_hash": synthesis["input_hash"],
                                    "title": "从零完成一次用户访谈（虚构演示）",
                                    "overview": "将按更新顺序出现的零散内容，重组为问题定义、事件访谈、证据整理三个阶段。先理解，再实践，最后留下能够复核的学习产物。",
                                    "modules": modules, "omitted_claims": [], "conflicts": [],
                                    "gaps": ["原材料没有解释如何招募受访者、获取访谈同意和选择样本，执行真实研究前需要补充。", "没有真实访谈录像可用于示范或评估提问技巧。"]})
    return render(root)


def _build_legacy_index_demo(output):
    """Demonstrate the default navigation workflow without acquiring or transcribing."""
    from pathlib import Path
    from .core import atomic_text, digest
    from .index import build_index
    corpus = demo_corpus()
    topics = []
    for tid, vid, title, deps, question, focus, check in [
        ('problem', 'v_foundation', '先把问题说清楚', [], '需求和方案有什么区别？', '观察从功能请求追问到任务与障碍的过程。', '能把一个功能请求改写为待验证的问题。'),
        ('interview', 'v_questions', '围绕真实经历做访谈', ['problem'], '怎样问到具体经历？', '留意发生时间、处理过程、替代办法三个追问。', '能提出一个不预设答案的经历问题。'),
        ('synthesis', 'v_synthesis', '整理证据与假设', ['interview'], '怎样防止把猜测当证据？', '将原话、行为和自己的解释分开。', '能为一个假设写出证据与潜在反例。')]:
        topics.append(dict(id=tid, title=title,
                           group={'problem': '01 界定问题', 'interview': '02 开展访谈', 'synthesis': '03 整理证据'}[tid],
                           question=question,
                           guidance={'problem': '先看“需求和方案要分开”。把具体的人、情境、任务和障碍写清楚，再进入提问方法；先不要急着设计功能。',
                                     'interview': '带着上一节的问题假设，寻找一次真实发生的经历。先问处理过程，再追问花费与替代办法；把原话和自己的解释分开记录。',
                                     'synthesis': '回到访谈记录，按任务与情境比较实际行为。为每个问题假设写出支持证据、一个潜在反例和下一次要验证的问题。'}[tid],
                           prerequisites=deps, watch_for=focus, self_check=check,
                           video_ids=[vid], recommended_ids=[vid],
                           task={'objective': question,
                                 'primary_video_id': vid,
                                 'stop_when': check + ' 写下一句自己的回答或尚未解决的问题，就可以停下。',
                                 'practice_minutes': 5}))
    # Two topics intentionally share a source, but select different source evidence.
    # This demonstrates topic-level association without inventing a watch interval.
    topics[0]['video_evidence'] = {'v_foundation': ['s1', 's2']}
    topics[1]['video_evidence'] = {'v_questions': ['s1']}
    topics[2]['video_ids'].append('v_questions')
    topics[2]['video_evidence'] = {'v_synthesis': ['s1', 's2'], 'v_questions': ['s2']}
    reviews = {
        video['id']: {
            'note': '仓库自写虚构文本；引文时间只展示证据关联机制，没有对应的可播放视频。',
            'evidence': [{'segment_id': segment['id'], 'quote': segment['text']}
                         for segment in video['segments']]
        } for video in corpus['videos'] if video['id'] != 'v_update'
    }
    materials = [
        ('problem', '问题陈述检查表', 'problem-checklist.md',
         '先写清谁、情境、任务与障碍，再检查有没有把功能方案混进问题。',
         '# 问题陈述检查表\n\n本项目自写演示模板，不是创作者原始课件。\n\n- 谁：\n- 在什么情境下：\n- 想完成什么任务：\n- 遇到了什么障碍：\n- 哪些是已知事实：\n- 哪些还要核实：\n\n检查：这句话是否提前指定了某个按钮或功能？\n'),
        ('interview', '四栏访谈记录', 'interview-notes.md',
         '记录具体场景、原话、实际行为和待核实问题，留出空间写自己的解释。',
         '# 四栏访谈记录\n\n本项目自写演示模板，不是创作者原始课件。\n\n| 具体场景 | 原话 | 实际行为 | 待核实问题 |\n|---|---|---|---|\n| | | | |\n\n## 我的解释（与原话分开）\n\n\n'),
        ('synthesis', '证据与假设对照表', 'evidence-log.md',
         '把问题假设、支持证据和可能的反例放在一起，再决定下一步验证什么。',
         '# 证据与假设对照表\n\n本项目自写演示模板，不是创作者原始课件。\n\n| 问题假设 | 对应原话或行为 | 潜在反例 | 下一次验证问题 |\n|---|---|---|---|\n| | | | |\n\n少量访谈不能直接代表所有用户。未知信息保留为空，完成记录也不等于掌握。\n')]
    out = Path(output)
    for _, _, filename, _, body in materials:
        # A rerun must not overwrite a learner's filled-in notes.
        if not (out/'materials'/filename).exists():
            atomic_text(out/'materials'/filename, body)
    plan = dict(schema_version=1, package_id='demo-user-interview',
                source_hash=digest(corpus), title='从零开始学用户访谈｜虚构演示',
                goal='先找知识点，再回到相应来源。', overview='将零散内容组织成“界定问题 → 开展访谈 → 整理证据”的学习路线。选择一个问题，查看对应来源、观看重点与记录模板。全部为仓库自写演示，不调用模型。',
                topics=topics, start_path=['problem', 'interview', 'synthesis'], reviews=reviews,
                learning_paths=[{'id': 'first-question', 'title': '先完成一个访谈问题',
                                 'topic_ids': ['problem', 'interview'], 'prerequisite_exemptions': []}],
                materials=[dict(title=title, description=description, origin='agent',
                                status='自写演示模板 · 本地 Markdown', url=None,
                                local_path='materials/'+filename, topic_ids=[tid])
                           for tid, title, filename, description, _ in materials],
                learning_advice=['一次选择一个知识点，尝试复述后再回到证据核对。每步的练习时间是 Agent 设计的估算。',
                                 '从资料页打开记录模板，填写自己的实际观察。空白表示尚未记录，不代表没有问题或已经通过。',
                                 '可以分别记录看过、练习、待复习和自报掌握；下次从概览继续。换浏览器或访问地址前先导出学习记录。',
                                 '完成一轮访谈后，回看自己的提问和记录：哪些是对方的事实，哪些只是自己的猜测？'],
                limitations=['全部内容为仓库自写虚构材料，没有真实原视频链接。', '4 条虚构记录中，3 条教学记录进入地图；1 条更新通知保留在 corpus 中。'])
    write_json(out/'corpus.json', corpus)
    write_json(out/'index-plan.json', plan)
    return build_index(corpus, plan, out)


def build_index_demo(output, *, scenario="concept"):
    """Exercise the default v2 learning-design workflow with authored fixtures."""
    from .scenarios import build_scenario
    return build_scenario(scenario, output)
