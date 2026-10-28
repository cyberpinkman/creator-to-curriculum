"""Small authored cases for the default learning-design workflow.

These fixtures demonstrate different learning decisions, not model generation or
real creator coverage. Source text, timestamps and materials are all synthetic.
"""

from pathlib import Path

from .core import atomic_text, digest, write_json


def _source(vid, title, *passages):
    return dict(id=vid, title=title, url=None, duration_seconds=30 * len(passages),
                status='ready', transcript_source='synthetic',
                segments=[dict(id=f's{i}', start=(i - 1) * 30, end=i * 30, text=body)
                          for i, body in enumerate(passages, 1)])


def _ref(vid, *segments):
    return dict(video_id=vid, segment_ids=list(segments))


def _topic(tid, title, question, guidance, *videos, prerequisites=()):
    return dict(id=tid, title=title, group='本次学习的知识点', question=question,
                guidance=guidance, video_ids=list(videos), recommended_ids=list(videos),
                prerequisites=list(prerequisites))


def _capability(cid, title, outcome, sources, *, prerequisites=(), status='supported',
                reason='自写演示文本包含本项所需的说明；不是实际学习表现。', next_action=None,
                required=True):
    coverage = dict(status=status, reason=reason, sources=sources)
    if next_action is not None:
        coverage['next_action'] = next_action
    return dict(id=cid, title=title, outcome=outcome, required=required,
                prerequisites=list(prerequisites), coverage=coverage)


def _activity(aid, title, topic_id, capabilities, kind, objective, instructions,
              output, criteria, stop, sources, *, materials=(), minutes=5):
    return dict(id=aid, title=title, topic_id=topic_id, capability_ids=capabilities,
                kind=kind, objective=objective, instructions=instructions, output=output,
                success_criteria=criteria, stop_when=stop, primary_video_id=sources[0]['video_id'],
                sources=sources, required_material_ids=list(materials), practice_minutes=minutes)


def _path(pid, title, outcome, reason, *steps, capability_exemptions=(),
          prerequisite_exemptions=()):
    return dict(id=pid, title=title, outcome=outcome, reason=reason,
                steps=[dict(id=sid, activity_id=aid, reason=why) for sid, aid, why in steps],
                capability_exemptions=list(capability_exemptions),
                prerequisite_exemptions=list(prerequisite_exemptions))


def _material(mid, title, description, filename, *topics, available=True):
    result = dict(id=mid, title=title, description=description, origin='agent',
                  availability='available' if available else 'unavailable',
                  status='仓库自写演示材料' if available else '需要用户提供，演示不含该文件',
                  topic_ids=list(topics), url=None)
    if filename is not None:
        result['local_path'] = 'materials/' + filename
    return result


def _case(name, title, goal, videos, topics, capabilities, activities, paths,
          materials=(), files=None, *, level='初次接触本主题', minutes=20,
          mode='systematic', known=(), constraints=(), assumptions=()):
    corpus = dict(schema_version=1,
                  creator=dict(name=title + '（虚构创作者）', platform='local', url=None),
                  discovery=dict(status='complete', expected_count=len(videos),
                                 scope='本仓库逐条编写的合成案例；不是公开账号发现结果。',
                                 observed_at='2026-10-27T00:00:00Z',
                                 notes=['全部来源和时间戳为合成演示，没有平台采集或真实视听审核。']),
                  videos=videos)
    learner = dict(schema_version=1, goal=goal, level=level, language='zh-CN',
                   minutes_per_session=minutes, mode=mode, prior_knowledge=list(known),
                   constraints=list(constraints), assumptions=list(assumptions))
    reviews = {v['id']: dict(note='仓库自写文本。时间仅演示定位机制，没有可播放的原片。',
                            evidence=[dict(segment_id=s['id'], quote=s['text'])
                                      for s in v['segments']]) for v in videos}
    for topic in topics:
        topic['video_evidence'] = {
            v['id']: [s['id'] for s in v['segments']]
            for v in videos if v['id'] in topic['video_ids']}
    plan = dict(schema_version=2, package_id='demo-design-' + name,
                source_hash=digest(corpus), learner_hash=digest(learner),
                title=title + '｜合成学习案例', goal=goal,
                overview='这是自写案例，展示从学习需求、能力覆盖到具体活动的规划。' + paths[0]['outcome'],
                topics=topics, capabilities=capabilities, activities=activities, paths=paths,
                reviews=reviews, materials=list(materials),
                learning_advice=['先查看当前活动需要的资料、产物与停止点，再开始尝试。',
                                 '来源覆盖是 Agent 的组织判断；完成记录不自动证明掌握。'],
                limitations=['全部来源为合成文本，没有真实博主或可播放原视频。',
                             '案例用于验证通用架构，不代表教学效果或真实平台能力已获验证。'])
    return corpus, learner, plan, dict(files or {})


def _concept():
    videos = [
        _source('scale', '比例尺说明了什么',
                '图上距离与实际距离用相同单位比较。比例尺一比一万表示图上一厘米对应实际一万厘米。',
                '比例尺只描述距离对应关系，不能单独告诉我们道路是否可通行。'),
        _source('distance', '把图上距离换成实际距离',
                '先写出图上距离，再乘比例尺的后项，最后把厘米换成米。图上两厘米在一比一万的图中对应二百米。')]
    topics = [
        _topic('scale', '理解比例尺', '比例尺能够说明什么？', '先理解对应关系，再处理单位换算。', 'scale'),
        _topic('distance', '估算实际距离', '怎样从图上距离得到实际距离？',
               '保留单位和中间步骤，检查结果是否把厘米直接当成米。', 'distance', prerequisites=('scale',))]
    capabilities = [
        _capability('interpret-scale', '解释比例尺', '解释一比一万，并指出一个它不能说明的问题。', [_ref('scale', 's1', 's2')]),
        _capability('convert-distance', '换算距离', '记录图上两厘米到实际二百米的换算步骤。',
                    [_ref('distance', 's1')], prerequisites=('interpret-scale',))]
    activities = [
        _activity('explain-scale', '解释一个比例尺', 'scale', ['interpret-scale'], 'understand',
                  '用自己的话解释一比一万，区分距离信息与通行条件。',
                  ['读比例尺定义，先写出图上一厘米对应的实际距离。', '写一个比例尺能回答的问题，再写一个它不能回答的问题。'],
                  '一段解释，以及一个例子和一个反例。',
                  ['比较的两边使用同样单位。', '没有从比例尺直接推出道路可通行。'],
                  '留下解释、例子和反例后停下；不要求学习其他地图符号。', [_ref('scale', 's1', 's2')]),
        _activity('calculate-distance', '完成一次单位换算', 'distance', ['convert-distance'], 'practice',
                  '完成图上两厘米在一比一万地图中的距离换算。',
                  ['写出两厘米乘一万的结果并保留单位。', '转换成米，回到演示文本核对差异。'],
                  '一行计算、单位转换和一次核对记录。', ['中间结果为二万厘米。', '最终结果为二百米，并保留单位。'],
                  '完成一题并记下核对结果后停下；有错误时保留原尝试。', [_ref('distance', 's1')])]
    paths = [_path('start', '先理解，再计算', '解释比例尺并完成一次距离换算。',
                   '先明确单位对应关系，后做计算，避免只记乘法步骤。',
                   ('explain', 'explain-scale', '先理解比例尺的含义与边界。'),
                   ('calculate', 'calculate-distance', '用一个可核对的结果应用刚才的解释。'))]
    return _case('concept', '小地图的距离', '读懂比例尺并完成一次实际距离换算。',
                 videos, topics, capabilities, activities, paths)


def _practice():
    videos = [
        _source('clean', '清理名单前先保留原表',
                '先复制原表，在副本中清理姓名两侧的空格。清理前后都记录行数，原表不覆盖。',
                '两个姓名相同不一定是重复记录，先对比编号，再标记需要核实的行，不直接删除。')]
    topics = [_topic('table-cleanup', '清理与核对名单', '如何清理格式而不误删记录？',
                     '在副本上操作，先处理空格，再依据编号检查疑似重复。', 'clean')]
    capabilities = [
        _capability('preserve-input', '保留原始数据', '保留原表，并记录原行数。', [_ref('clean', 's1')]),
        _capability('clean-and-check', '清理并核对', '清理空格，按编号标记疑似重复而不删除。',
                    [_ref('clean', 's1', 's2')], prerequisites=('preserve-input',))]
    activities = [
        _activity('copy-table', '建立工作副本', 'table-cleanup', ['preserve-input'], 'practice',
                  '把示例名单复制为工作副本，记录原始行数。',
                  ['打开示例 CSV，另存一份工作副本。', '记录表头之外的记录数，保留原文件。'],
                  '一个工作副本和原始记录数。', ['原表仍可打开且未改写。', '记录数不把表头计入。'],
                  '保留副本与行数记录后停下。', [_ref('clean', 's1')], materials=('sample-table',)),
        _activity('clean-table', '清理空格并标记疑似重复', 'table-cleanup', ['clean-and-check'], 'practice',
                  '在副本中处理姓名两侧空格，再用编号核对疑似重复。',
                  ['只清理姓名两侧的空格，保存操作前后行数。', '比较相同姓名的编号，把疑似重复标出来。'],
                  '清理后的副本，以及包含编号和理由的疑似重复记录。',
                  ['清理后记录数与原表一致。', '同名不同编号没有直接删除。', '编号重复有核对标记。'],
                  '留下一份副本和核对记录后停下，不处理原材料没有说明的合并规则。',
                  [_ref('clean', 's1', 's2')], materials=('sample-table',), minutes=8)]
    paths = [_path('start', '保留、操作、核对', '完成一次可回溯的名单清理。',
                   '先确保原数据可恢复，再执行可检查的操作。',
                   ('copy', 'copy-table', '建立可以回退的起点。'),
                   ('clean', 'clean-table', '在副本上操作，并记录尚不能判断的重复。'))]
    material = _material('sample-table', '自写名单 CSV', '保留空格、同名不同编号与一条重复编号，供有限练习。',
                         'sample-table.csv', 'table-cleanup')
    return _case('practice', '名单清理练习', '保留原表，清理名单格式并标记疑似重复。',
                 videos, topics, capabilities, activities, paths, [material],
                 {'materials/sample-table.csv': 'id,name\n101, 小林 \n102,小林\n101, 小林\n103,小周 \n'},
                 known=('会打开并另存 CSV 文件。',), constraints=('仅使用示例数据，不操作真实人员名单。',))


def _project():
    videos = [
        _source('poster', '活动海报从信息草稿开始',
                '先写清活动名称、时间、地点和参加者需要带什么，再做视觉排版。缺少的信息留待确认。',
                '把活动名称放在最醒目的位置，时间地点作为第二层，把补充说明放在最后。'),
        _source('review', '改稿先看读者能否找到信息',
                '检查读者能否快速找到时间、地点和参加条件。只调整影响查找的信息，不为改稿重新写全部内容。')]
    topics = [_topic('poster', '活动海报', '怎样让读者找到参加活动所需的信息？',
                     '同一知识点先用于列信息，再用于制作；改稿路径采用另一项活动。', 'poster', 'review')]
    capabilities = [
        _capability('brief', '整理活动信息', '形成包含名称、时间、地点和参加条件的信息稿。', [_ref('poster', 's1')]),
        _capability('layout', '组织信息层级', '将信息稿变成三个层级的海报草稿。',
                    [_ref('poster', 's2')], prerequisites=('brief',))]
    activities = [
        _activity('draft-brief', '写出海报信息稿', 'poster', ['brief'], 'create',
                  '为一次虚构换书活动写四项必要信息。',
                  ['填写活动名称、时间、地点和参加条件。', '不知道的内容标为待确认，不自行补成事实。'],
                  '一份四项信息稿。', ['四项均有内容或明确的待确认标记。', '没有把未知安排写成已确认。'],
                  '四项信息都有去处后停下，暂不设计画面。', [_ref('poster', 's1')], materials=('poster-brief',)),
        _activity('make-poster', '制作海报草稿', 'poster', ['layout'], 'create',
                  '用上一份信息稿做三个层级的海报草稿。',
                  ['先放活动名称，再放时间地点，最后放补充说明。', '检查草稿没有漏掉信息稿中的参加条件。'],
                  '一张海报草稿或标明三个层级的线框图。',
                  ['名称、时间地点、说明有清楚层级。', '参加条件能找到，待确认项继续标明。'],
                  '保存一版草稿并核对四项信息后停下；不要求完成正式发布。',
                  [_ref('poster', 's1', 's2')], materials=('poster-brief',), minutes=12),
        _activity('revise-poster', '只修改一处查找障碍', 'poster', ['layout'], 'create',
                  '利用已有海报信息稿，修改最难找到的一项信息。',
                  ['查看自写海报样稿，指出时间或地点的查找障碍。', '只调整一处信息的位置或层级，保留修改前后版本。'],
                  '一组改前、改后对照和修改理由。', ['修改理由对应读者查找信息的问题。', '没有改变活动事实。'],
                  '完成一处修改与对照记录后停下。', [_ref('review', 's1'), _ref('poster', 's2')],
                  materials=('poster-draft',), minutes=8)]
    paths = [
        _path('start', '从信息到海报', '先有信息稿，再留下一张海报草稿。',
              '同一主题的两次活动承担不同阶段，不能用进入过知识点代表两个阶段都完成。',
              ('brief', 'draft-brief', '先明确需要传达的信息。'),
              ('layout', 'make-poster', '将信息转成可查看的作品。')),
        _path('revise', '已有信息稿，直接改一处', '保留一次有理由的局部改稿。',
              '适用于已经有信息稿的人；复用知识点，采用改稿活动。',
              ('revision', 'revise-poster', '从一个具体查找问题开始修改。'),
              capability_exemptions=[dict(capability_id='brief', status='assumed_known',
                                          reason='此路径假设使用者已有四项活动信息；这不是掌握认证。')])]
    materials = [
        _material('poster-brief', '四项信息稿', '填写本次海报的信息；未知继续标为待确认。', 'poster-brief.md', 'poster'),
        _material('poster-draft', '改稿样例', '自写文字样稿，供比较信息查找顺序。', 'poster-draft.md', 'poster')]
    files = {'materials/poster-brief.md': '# 虚构活动信息稿\n\n- 名称：\n- 时间：\n- 地点：\n- 参加条件：\n',
             'materials/poster-draft.md': '# 换一本书\n\n请带一本愿意交换的书。\n\n这是一次自写的虚构活动。\n\n时间：周六 14:00；地点：社区阅览室。\n'}
    return _case('project', '换书活动海报', '做出一版信息完整、层级清楚的虚构活动海报。',
                 videos, topics, capabilities, activities, paths, materials, files,
                 constraints=('仅制作虚构草稿，不发布活动信息。',))


def _comparison():
    videos = [
        _source('single-list', '只留一张总清单的观点',
                '我认为所有项目都只需一张总清单，拆成多个看板只会增加管理时间。这里没有比较不同团队规模。'),
        _source('separate-boards', '每个人使用独立看板的观点',
                '我认为所有项目都应为每个人设独立看板，一张总清单无法明确责任。这里没有说明个人项目是否适用。')]
    topics = [_topic('workflow-choice', '比较任务组织观点', '两种相反建议分别依赖什么条件？',
                     '保留两条主张及其缺失条件，暂不把它们拼成统一做法。', 'single-list', 'separate-boards')]
    sources = [_ref('single-list', 's1'), _ref('separate-boards', 's1')]
    capabilities = [_capability('choose-workflow', '判断适用条件',
                                '根据团队规模与责任分工判断适用方式；条件不足时明确保留结论。', sources,
                                status='conflicting', reason='两段自写材料都作全称判断，且没有提供足够的适用条件。',
                                next_action='补查团队规模、责任分工与管理成本的具体案例，再决定能否选择。')]
    activities = [_activity('compare-claims', '列出主张、条件和待核实项', 'workflow-choice',
                            ['choose-workflow'], 'compare', '比较两条观点，指出做决定还缺什么信息。',
                            ['分别抄出两条主张，并标明来自哪段材料。',
                             '列出团队规模、责任分工等未说明的条件。', '记录一个下一步可核实的问题，当前不宣布某一种普遍正确。'],
                            '一张主张—条件对照表，以及暂不能下结论的原因。',
                            ['两条来源各自保留。', '未说明的条件与来源原话分开。', '没有把互相矛盾的主张合成一个操作步骤。'],
                            '完成对照与缺口记录后停下，等待补充条件。', sources, minutes=10)]
    paths = [_path('start', '先比较，再决定是否补查', '得到可继续核实的对照表，暂不选择统一方案。',
                   '当前材料有冲突，路径以明确分歧和条件为阶段产物。',
                   ('compare', 'compare-claims', '先看清分歧，再决定补查内容。'))]
    return _case('comparison', '任务组织观点比较', '比较任务组织建议，判断还缺哪些条件才能应用。',
                 videos, topics, capabilities, activities, paths, mode='explore',
                 level=None, minutes=None, assumptions=('尚未提供实际项目规模，暂以比较观点为本次目标。',))


def _lookup():
    videos = [
        _source('export', '透明背景导出的一个入口',
                '本例中的图像编辑器导出菜单有 PNG 格式和保留透明背景选项；JPEG 不保留这个透明通道。'),
        _source('rename', '批量命名前看预览',
                '批量命名以前先复制输入文件，在预览中确认前缀和序号，再执行到副本。此片段不介绍文件管理基础。')]
    topics = [
        _topic('export', '查找导出格式', '哪种格式保留透明背景？', '先查格式和选项名称，记录需要在实际工具确认的入口。', 'export'),
        _topic('rename', '批量命名', '怎样避免批量命名覆盖原文件？', '当前缺少文件管理基础与用户输入文件，保留明确的准备条件。', 'rename')]
    capabilities = [
        _capability('export-format', '找到导出格式', '记录透明背景对应的格式和待确认菜单入口。', [_ref('export', 's1')]),
        _capability('file-basics', '复制与恢复文件', '能够在副本中操作并恢复原文件。', [], status='missing',
                    reason='本组碎片材料没有解释文件复制、目录或恢复方法。',
                    next_action='先补充文件管理基础的来源，或由用户明确说明已有这项能力。'),
        _capability('batch-name', '按前缀和序号命名', '在副本中预览并执行批量命名。',
                    [_ref('rename', 's1')], prerequisites=('file-basics',))]
    activities = [
        _activity('find-export', '留下格式与入口记录', 'export', ['export-format'], 'lookup',
                  '从碎片教程中找到透明背景导出的格式与选项。',
                  ['读取格式说明，记录 PNG 和保留透明背景选项。', '写下实际工具菜单仍待确认，不填写未经核对的位置。'],
                  '一条格式选择记录和待确认入口。', ['没有选择不保留透明通道的 JPEG。', '没有猜测实际软件的菜单位置。'],
                  '能说明格式选择和剩余入口问题后停下。', [_ref('export', 's1')], minutes=3),
        _activity('rename-copy', '在文件副本上预览命名', 'rename', ['batch-name'], 'lookup',
                  '待基础和输入文件齐备后，查找批量命名入口并预览命名。',
                  ['先确认文件复制与恢复方法，取得可练习的文件副本。', '在预览中检查活动名前缀与编号，只对副本执行。'],
                  '一组副本的命名预览和操作记录。', ['原文件可恢复。', '预览符合前缀与编号要求。'],
                  '完成一组副本的预览记录后停下；准备条件未齐时不执行。', [_ref('rename', 's1')],
                  materials=('input-images',), minutes=8)]
    paths = [_path('start', '先解决能查到的问题', '先确定导出格式，再明确命名任务的准备缺口。',
                   '当前资料足以支持格式查找，尚不足以支持安全的批量操作。',
                   ('format', 'find-export', '这一步可以先留下明确查找结果。'),
                   ('naming', 'rename-copy', '完成基础与材料准备后再进行文件操作。'))]
    materials = [_material('input-images', '需要练习的图片副本', '由用户提供可用于练习的文件副本；当前没有取得。',
                           None, 'rename', available=False)]
    return _case('lookup', '碎片工具技巧查阅', '查找透明背景导出方式，并准备按活动名编号的文件副本。',
                 videos, topics, capabilities, activities, paths, materials, mode='problem',
                 level=None, minutes=15, constraints=('尚未提供实际软件版本和输入图片。',))


_SCENARIOS = {'concept': _concept, 'practice': _practice, 'project': _project,
              'comparison': _comparison, 'lookup': _lookup}


def scenario_names():
    return tuple(_SCENARIOS)


def scenario_data(name):
    """Return fresh (corpus, learner, plan, material-files) authored data."""
    if name not in _SCENARIOS:
        raise ValueError(f'Unknown scenario: {name}; choose from {", ".join(_SCENARIOS)}')
    return _SCENARIOS[name]()


def build_scenario(name, output):
    """Build one offline v2 example without overwriting filled material files."""
    from .index import build_index

    corpus, learner, plan, files = scenario_data(name)
    out = Path(output)
    for relative, body in files.items():
        path = out / relative
        if not path.exists():
            atomic_text(path, body)
    write_json(out / 'corpus.json', corpus)
    write_json(out / 'learner.json', learner)
    write_json(out / 'index-plan.json', plan)
    return build_index(corpus, plan, out, learner=learner)


def feedback_scenario_state(name, context):
    """Return authored feedback examples, never an evaluator of arbitrary work.

    All statements below are deliberately written test submissions and reviews.
    No real learner performance is inferred from these examples, source text,
    completion flags or matching words. Current core contracts validate them.
    """
    from .core import (index_learning_feedback, require, validate_learning_attempt,
                       validate_learning_feedback)

    require(name in _SCENARIOS, f'Unknown feedback scenario: {name}')
    require(context['package_id'] == 'demo-design-' + name, 'Feedback demo context belongs to another scenario')
    steps = {(s['path_id'], s['step_id']): s for s in context['steps']}
    state = dict(schema_version=1, package_id=context['package_id'], attempts=[], feedback=[])
    marker = '【合成演示，非真实学习者记录】'
    prefix = 'demo-feedback-' + name + '-'
    suffix = context['context_hash'][:12]

    def add(label, path, step, response, results, summary, kind, instructions, output,
            stop, *, target=None, origin='learner', blocker=''):
        selected = steps[(path, step)]
        require(len(results) == len(selected['success_criteria']), 'Authored review no longer matches scenario criteria')
        ordinal = len(state['attempts']) + 1
        attempt = dict(schema_version=1, id=prefix + label + '-attempt-' + suffix,
                       package_id=context['package_id'], context_hash=context['context_hash'],
                       path_id=path, step_id=step, activity_id=selected['activity_id'],
                       created_at=f'2026-10-27T00:{ordinal * 2:02d}:00Z', work_origin=origin,
                       response=marker + response, artifact_refs=[], blocker=blocker,
                       criteria=list(selected['success_criteria']))
        feedback = dict(schema_version=1, id=prefix + label + '-review-' + suffix,
                        attempt_id=attempt['id'], attempt_hash=digest(attempt),
                        context_hash=context['context_hash'], created_at=f'2026-10-27T00:{ordinal * 2 + 1:02d}:00Z',
                        summary=marker + summary, observations=[],
                        criteria=[dict(criterion_index=i, result=result,
                                       evidence=[dict(field='response', quote=quote)] if quote else [], reason=reason)
                                  for i, (result, quote, reason) in enumerate(results)],
                        next_action=dict(kind=kind, reason=summary, instructions=instructions,
                                         output=output, stop_when=stop,
                                         target=dict(path_id=target[0], step_id=target[1]) if target else None))
        validate_learning_attempt(attempt, context)
        validate_learning_feedback(feedback, attempt, context)
        state['attempts'].append(attempt)
        state['feedback'].append(feedback)

    if name == 'concept':
        add('unit-misconception', 'start', 'explain',
            '一比一万就是图上一厘米等于实际一万米。地图给出了距离，所以这条道路一定可以通行。',
            [('needs_work', '图上一厘米等于实际一万米', '比例尺比较的两边尚未统一单位。'),
             ('needs_work', '这条道路一定可以通行', '距离信息被扩大成了通行结论；演示来源没有提供这个依据。')],
            '这次合成回答暴露了单位和结论边界两处具体问题，先缩小到两句话重试。', 'retry',
            ['回看比例尺定义，先把两边都写成厘米。', '补一句比例尺能够说明什么、不能说明什么。'],
            '一条同单位解释和一条结论边界说明。', '写出这两句话后停下；保留前一次尝试。',
            target=('start', 'explain'))
        add('bounded-explanation', 'start', 'explain',
            '一比一万表示图上一厘米对应实际一万厘米，两边都是厘米。比如图上两厘米对应二万厘米。'
            '这只能说明距离对应关系，不能说明道路一定可以通行。',
            [('met', '图上一厘米对应实际一万厘米，两边都是厘米', '所提交解释的比较单位一致，并给出了同单位例子。'),
             ('met', '不能说明道路一定可以通行', '回答明确保留了比例尺不能支持的结论边界。')],
            '本次合成产物符合这一步的两项标准，可以继续一次换算练习；不据此认证掌握。', 'continue',
            ['进入一次距离换算活动，先保留厘米中间结果。', '再换算成米，记录核对结果。'],
            '一行计算、单位转换和核对记录。', '完成一题并记下核对结果后停下。',
            target=('start', 'calculate'))
    elif name == 'practice':
        add('no-inspectable-output', 'start', 'clean',
            '我看过教程，也试着清理了。现在还没有能提供的副本和行数记录。',
            [('not_observed', None, '没有操作前后行数或可检查的副本，无法判断记录数是否保持。'),
             ('not_observed', None, '没有具体行记录，无法判断同名不同编号如何处理。'),
             ('not_observed', None, '没有提交重复编号的核对标记。')],
            '看过和试过不能替代产物。当前缺少可核对内容，结果保持未知。', 'request_evidence',
            ['保留原表；能够另存时提供工作副本引用及操作前后的行数。',
             '提供一条疑似重复标记和理由；不能另存时先说明工具限制。'],
            '副本引用、前后行数及一条重复核对记录，或仍未解决的工具限制。',
            '提供最少可核对记录即可；不要为了交作业补造结果。',
            blocker='当前设备只方便查看文件，尚未确认能否另存副本。')
        add('reference-is-not-performance', 'start', 'clean',
            '这是参考答案或 Agent 生成的说明，不是我的操作产物：应保留四行，编号 101 重复需标记，'
            '编号 102 虽同名也应保留。',
            [('not_observed', None, '参考答案中的行数不能证明学习者实际保留了记录。'),
             ('not_observed', None, '参考说明不能证明学习者没有误删同名记录。'),
             ('not_observed', None, '没有学习者自己的重复核对产物。')],
            '参考答案可用于理解要求，但不能把它评为学习者已经完成。', 'request_evidence',
            ['在可操作工具中留下自己的副本和核对记录。', '如果仍缺工具，说明阻碍，暂不执行真实数据操作。'],
            '自己的操作产物或明确的工具阻碍记录。', '提交一份可核对的记录后停下。', origin='reference')
    elif name == 'project':
        add('missing-entry-condition', 'start', 'brief',
            '虚构活动名称：换一本书；时间：周六 14:00；地点：社区阅览室；参加条件：',
            [('needs_work', '参加条件：', '第四项内容仍为空，也没有明确的待确认标记。'),
             ('met', '地点：社区阅览室；参加条件：', '所提交草稿保留了未填写的条件，没有把这一项写成已确认安排。')],
            '先补齐信息稿的第四项；修改当前活动即可，不需要重做整个主题。', 'retry',
            ['补上参加条件。若目前不知道，明确写“待确认”。', '保留已有三项信息及前一版记录。'],
            '四项均有内容或待确认标记的信息稿。', '四项都有去处后停下，不自行设计活动事实。',
            target=('start', 'brief'))
        add('explicit-unknown-is-allowed', 'start', 'brief',
            '虚构活动名称：换一本书；时间：周六 14:00；地点：社区阅览室；参加条件：待确认。'
            '参加条件尚未提供，我没有自行补定。',
            [('met', '活动名称：换一本书；时间：周六 14:00；地点：社区阅览室；参加条件：待确认',
              '四项均有内容或明确的待确认标记，符合当前阶段的标准。'),
             ('met', '参加条件：待确认', '草稿本身保留了待确认标记，没有把未知条件提升为已确认事实。')],
            '本阶段允许保留待确认项，信息稿可进入草稿排版；事实缺口继续保留。', 'continue',
            ['沿用这份信息稿制作三个层级的海报草稿。', '参加条件仍标为待确认，不自行补造。'],
            '保留待确认项的海报草稿或线框图。', '核对四项信息没有丢失后停下，不发布活动。',
            target=('start', 'layout'))
    elif name == 'comparison':
        add('unsupported-combined-rule', 'start', 'compare',
            '来源 A 主张“所有项目都只需一张总清单”；来源 B 主张“所有项目都应为每个人设独立看板”。'
            '所以任何项目先建总清单，再给每人开独立看板，两个步骤都必需。',
            [('met', '来源 A 主张“所有项目都只需一张总清单”；来源 B 主张“所有项目都应为每个人设独立看板”',
              '这次提交分别保留了两条来源主张。'),
             ('needs_work', '任何项目先建总清单，再给每人开独立看板，两个步骤都必需',
              '尚未补出适用条件，却把建议扩大成任何项目都必须遵守的结论。'),
             ('needs_work', '先建总清单，再给每人开独立看板', '两条冲突建议被拼成连续操作，来源没有支持这个组合。')],
            '保留已有的来源摘录，撤回缺少条件的统一步骤，补出待核实问题。', 'retry',
            ['将两条主张并列，暂不合并成操作步骤。', '列出团队规模、分工等缺少的条件和一个待核实问题。'],
            '两条主张及适用条件的对照记录。', '对照与待核实项写清后停下，不必当场决定统一方案。',
            target=('start', 'compare'))
        add('complete-comparison-with-uncertainty', 'start', 'compare',
            '来源 A 主张“所有项目都只需一张总清单”；来源 B 主张“所有项目都应为每个人设独立看板”。'
            '两段都未提供团队规模、责任分工与管理成本的比较，这些是待核实条件。'
            '我暂不把两条相反主张合成统一做法。下一步要核实：各做法用于多少人、怎样分工的实际项目？',
            [('met', '来源 A 主张“所有项目都只需一张总清单”；来源 B 主张“所有项目都应为每个人设独立看板”',
              '对照保留了两条来源的不同主张。'),
             ('met', '两段都未提供团队规模、责任分工与管理成本的比较，这些是待核实条件',
              '未说明条件明确列为待核实，没有混进原话。'),
             ('met', '我暂不把两条相反主张合成统一做法', '没有把冲突观点拼成一个操作步骤。')],
            '这次比较产物符合活动标准，可以结束对照任务；来源分歧及实际选型仍未解决。', 'finish',
            ['保留对照表与缺失条件。', '需要实际选择方案时，再围绕团队规模和分工补充具体案例。'],
            '可继续核实的对照记录；没有统一方案结论。', '完成对照记录后停下，保留不确定性。')
    elif name == 'lookup':
        add('unavailable-prerequisite-and-input', 'start', 'naming',
            '我找到 PNG 格式的说明，但尚未提供待命名的图片，也不清楚如何复制并恢复原文件。',
            [('not_observed', None, '没有副本或恢复方法的证据，不能判断原文件是否可恢复。'),
             ('not_observed', None, '没有命名预览，无法核对前缀和编号。')],
            '当前阻碍是先修与输入文件尚未齐备，不能据此判断命名能力或继续批量操作。', 'resolve_gap',
            ['先确认文件复制和恢复方法，已有这项能力时明确说明依据。',
             '取得允许练习的文件副本，再请 Agent 更新准备条件并检查任务。'],
            '先修说明与可用副本的资料引用；未满足项继续列出。',
            '准备条件未齐前不执行批量命名。', blocker='缺少输入图片副本，文件管理基础尚未确认。')
    index_learning_feedback(context, state)
    return state


def build_feedback_scenario(name, output):
    """Opt-in demo history; never overwrite or mix in actual user records."""
    from .core import index_learning_feedback, read_json, require
    from .feedback import feedback_context_for_workspace
    from .index import build_index

    require(name in _SCENARIOS, f'Unknown feedback scenario: {name}')
    out = Path(output)
    state_path = out / 'feedback-state.json'
    previous = read_json(state_path) if state_path.exists() else None
    prefix = 'demo-feedback-' + name + '-'
    if previous is not None:
        require(isinstance(previous, dict) and previous.get('package_id') == 'demo-design-' + name,
                'Feedback demo output contains another learning package; use a new output directory')
        for key in ('attempts', 'feedback'):
            require(isinstance(previous.get(key), list) and
                    all(isinstance(record, dict) and isinstance(record.get('id'), str) and
                        record['id'].startswith(prefix) for record in previous[key]),
                    'Feedback demo output contains non-demo records; use a new output directory')
        require(all((out / filename).is_file() for filename in ('corpus.json', 'learner.json', 'index-plan.json')),
                'Existing demo history has no complete workspace; use a new output directory')
        index_learning_feedback(feedback_context_for_workspace(out), previous)
    build_scenario(name, out)
    context = feedback_context_for_workspace(out)
    fresh = feedback_scenario_state(name, context)
    merged = previous or dict(schema_version=1, package_id=fresh['package_id'], attempts=[], feedback=[])
    for key in ('attempts', 'feedback'):
        by_id = {record['id']: record for record in merged[key]}
        for record in fresh[key]:
            existing = by_id.get(record['id'])
            require(existing is None or digest(existing) == digest(record),
                    'A demo history ID has different content; use a new output directory')
            if existing is None:
                merged[key].append(record)
                by_id[record['id']] = record
    index_learning_feedback(context, merged)
    write_json(state_path, merged)
    return build_index(read_json(out / 'corpus.json'), read_json(out / 'index-plan.json'), out,
                       learner=read_json(out / 'learner.json'))
