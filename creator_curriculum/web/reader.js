/* All source strings enter the page as text. Only validated links become hrefs. */
'use strict';
const data = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
const el = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const topics = new Map(data.topics.map(topic => [topic.id, topic]));
const groups = [...new Set(data.topics.map(topic => topic.group))];
const paths = data.learning_paths;
const designed = data.schema_version === 2;
const activities = new Map((data.activities || []).map(activity => [activity.id, activity]));
const capabilities = new Map((data.capabilities || []).map(capability => [capability.id, capability]));
const pathSteps = Object.fromEntries(paths.filter(path => Array.isArray(path.steps)).map(path =>
  [path.id, Object.fromEntries(path.steps.map(step => [step.id, step.topic_id]))]));
const progress = C2CProgress.create({
  packageId: data.package_id, topicIds: [...topics.keys()], pathIds: paths.map(path => path.id),
  pathTopics: Object.fromEntries(paths.map(path => [path.id, path.topic_ids])), pathSteps,
  topicVersions: Object.fromEntries(data.topics.map(topic => [topic.id, topic.source_signature])),
  feedbackContext: data.feedback_context || null, learningFeedback: data.learning_feedback || null,
  storage: {getItem: key => localStorage.getItem(key), setItem: (key, value) => localStorage.setItem(key, value)}
});
const selectedPath = () => paths.find(path => path.id === progress.state.selected_path_id) || paths[0];
const studyStep = (path = selectedPath()) => path.steps?.find(step => step.id === progress.state.study_step_ids?.[path.id]) || null;
const studyTopic = (path = selectedPath()) => {
  if (designed) return topics.get(studyStep(path)?.topic_id) || null;
  const id = progress.state.study_topic_ids?.[path.id];
  return path.topic_ids.includes(id) ? topics.get(id) : null;
};
const recordLabels = {watched: '已看过', practiced: '已尝试练习', review: '待复习', mastered: '自报已掌握'};
const workOriginLabels = {learner: '自己完成', assisted: '借助帮助完成', reference: '参考答案或 Agent 生成', unknown: '来源不确定'};
const feedbackActionLabels = {continue: '继续下一步', retry: '再做一次当前任务', revisit: '回顾前面的步骤', switch_path: '换一条路径', resolve_gap: '先补齐条件', request_evidence: '先补充产物证据', finish: '收束当前活动'};
function recordSummary(id) {
  const record = progress.state.topics[id] || {};
  return Object.entries(recordLabels).filter(([key]) => record[key]).map(([, label]) => label).join(' · ') || '尚未标记观看或练习';
}
function refreshSaveStatus(message = '') {
  const status = progress.status();
  const notice = $('record-status');
  notice.replaceChildren();
  for (const text of [status.error, ...status.warnings].filter(Boolean)) notice.append(el('p', text));
  notice.hidden = !notice.children.length;
  if (!notice.hidden) notice.append(routeLink('查看与导出学习记录 →', 'progress'));
  for (const panel of document.querySelectorAll('[data-source-topic]')) {
    const id = panel.dataset.sourceTopic;
    if (!status.changed_topic_ids.includes(id) && !status.unversioned_topic_ids.includes(id) && panel.querySelector('button')) panel.remove();
  }
  for (const node of document.querySelectorAll('[data-save-status]')) {
    node.textContent = status.error ? '未保存到浏览器；当前改动仍可导出。' : message || (status.persisted ? '已保存在此浏览器' : '勾选和笔记会保存在此浏览器');
  }
  refreshGuidancePanels();
}
function pathControl() {
  const box = el('div', undefined, 'path-control');
  const label = el('label', '当前学习路径'); label.htmlFor = 'path-select';
  const select = el('select'); select.id = 'path-select';
  const savedPathExists = paths.some(path => path.id === progress.state.selected_path_id);
  if (!savedPathExists) {
    const missing = el('option', '上次路径不可用，请选择'); missing.value = ''; missing.disabled = true; select.append(missing);
  }
  for (const path of paths) { const option = el('option', path.title); option.value = path.id; select.append(option); }
  select.value = savedPathExists ? selectedPath().id : '';
  select.addEventListener('change', () => { progress.selectPath(select.value); render(false); $('path-select').focus(); });
  box.append(label, select);
  const exemptions = selectedPath().prerequisite_exemptions || [];
  if (exemptions.length) {
    const details = disclosure('这条路径的先修假设与缺口');
    for (const item of exemptions) details.append(el('p', `${topics.get(item.topic_id).title} · ${item.status === 'assumed_known' ? '假设已具备' : '已声明跳过的缺口'}：${item.reason}`));
    details.append(el('p', '路径声明不代表你的掌握状态；需要时可自由回看先修。', 'muted'));
    box.append(details);
  }
  const capabilityExemptions = selectedPath().capability_exemptions || [];
  if (capabilityExemptions.length) {
    const details = disclosure('这条路径对已有能力的假设');
    for (const item of capabilityExemptions) details.append(el('p', `${capabilities.get(item.capability_id).title} · ${item.status === 'assumed_known' ? '假设已具备' : '保留为跳过缺口'}：${item.reason}`));
    details.append(el('p', '这是路径的规划前提，不会标记你已掌握。', 'muted'));
    box.append(details);
  }
  return box;
}
function taskCard(topic, onOverview = false) {
  const box = el('aside', undefined, 'task-card');
  box.append(el('h2', onOverview ? '这次只做一小步' : '当前任务'), el('p', topic.task.objective, 'prose'));
  const video = topic.entries.find(entry => entry.id === topic.task.primary_video_id);
  if (video) {
    box.append(video.url ? externalLink('打开本次原视频 ↗', video.url, 'task-source') : el('p', '此演示没有可播放的原视频', 'muted'));
    box.append(el('p', `原视频完整时长：${duration(video.duration_seconds)}；${topic.task.practice_minutes == null ? '练习时间未估算' : `练习约 ${topic.task.practice_minutes} 分钟（估算）`}。${video.topic_evidence?.length ? '进入知识点后可按证据位置手动定位；引文长度不代表教学时长。' : '尚无本知识点的内容定位，请带着问题核对原视频。'}`, 'task-meta'));
  }
  box.append(el('p', '停在这里：' + topic.task.stop_when, 'task-stop'));
  if (onOverview) box.append(el('p', recordSummary(topic.id), 'muted'), studyLink(studyTopic()?.id === topic.id ? '继续学习 →' : '开始这一步 →', topic.id, selectedPath().id, 'action'));
  return box;
}
function recordEditor(topic) {
  const section = el('section', undefined, 'record-editor');
  section.append(el('h2', designed ? '知识点记录' : '留下这一步的记录'), el('p', designed ? '同一知识点下的活动共用这些标记与笔记；活动位置分别保存。打开来源或进入下一步不会自动标为掌握。' : '由你分别标记；打开视频和进入下一步不会自动标为掌握。', 'muted'));
  const sourceStatus = progress.status();
  if (sourceStatus.changed_topic_ids.includes(topic.id) || sourceStatus.unversioned_topic_ids.includes(topic.id)) {
    const review = el('aside', undefined, 'source-review');
    review.dataset.sourceTopic = topic.id;
    review.append(el('p', '这条记录的来源已变化或无法确认。核对当前来源后，再明确确认；保存笔记和修改标记不会代替这一步。'));
    const acknowledge = el('button', '我已核对当前来源'); acknowledge.type = 'button';
    acknowledge.addEventListener('click', () => {
      const result = progress.acknowledgeSource(topic.id);
      if (result.ok) {
        const feedback = el('p', result.persisted ? '已确认当前来源。原学习标记保持不变。' : '已在本页确认来源，但尚未保存到浏览器，请导出备份。');
        feedback.tabIndex = -1; feedback.setAttribute('role', 'status'); review.replaceChildren(feedback); feedback.focus();
      }
      refreshSaveStatus(result.error || '');
    });
    review.append(acknowledge); section.append(review);
  }
  const record = progress.state.topics[topic.id] || {};
  const fields = el('div', undefined, 'record-flags');
  for (const [key, text] of Object.entries(recordLabels)) {
    const label = el('label'); const checkbox = el('input'); checkbox.type = 'checkbox'; checkbox.checked = !!record[key]; checkbox.dataset.record = key;
    checkbox.addEventListener('change', () => { progress.updateTopic(topic.id, {[key]: checkbox.checked}); refreshSaveStatus(); });
    label.append(checkbox, text); fields.append(label);
  }
  const label = el('label', '笔记或卡点（可选）'); label.htmlFor = 'topic-notes';
  const notes = el('textarea'); notes.id = 'topic-notes'; notes.rows = 3; notes.value = record.notes || ''; notes.placeholder = '记下自己的尝试或下次要解决的问题';
  notes.addEventListener('input', () => { progress.updateTopic(topic.id, {notes: notes.value}); refreshSaveStatus(); });
  const status = el('p', '', 'save-status'); status.dataset.saveStatus = ''; status.setAttribute('role', 'status');
  section.append(fields, label, notes, status, routeLink('导出 / 导入学习记录 →', 'progress'));
  return section;
}
function downloadRecord(text, name) {
  const url = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
  const link = el('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function progressView() {
  const section = heading('我的学习记录', data.creator.name);
  section.append(el('p', '个人标记与本地尝试保存在此浏览器。换浏览器、移动文件或更换本地服务地址前，请导出备份。导出文件含你的私人笔记和产物内容，请自行保管。', 'prose lede'));
  const actions = el('div', undefined, 'record-actions');
  const exportButton = el('button', '导出学习记录'); exportButton.type = 'button'; exportButton.addEventListener('click', () => downloadRecord(progress.exportText(), data.package_id + '-progress.json'));
  const importLabel = el('label', '导入本学习包的记录'); importLabel.htmlFor = 'import-progress';
  const input = el('input'); input.type = 'file'; input.id = 'import-progress'; input.accept = '.json,application/json';
  const feedback = el('p', '', 'save-status'); feedback.setAttribute('role', 'status');
  input.addEventListener('change', async () => {
    const file = input.files[0]; if (!file) return;
    try {
      const result = progress.importText(await file.text());
      if (result.ok) { render(false); $('import-result').textContent = result.persisted ? '已导入并保存。' : '已读入当前页面，但未保存到浏览器；请导出备份。'; }
      else feedback.textContent = result.error;
    } catch { feedback.textContent = '无法读取文件，原记录未被替换。'; }
    input.value = ''; refreshSaveStatus();
  });
  actions.append(exportButton, importLabel, input);
  if (progress.raw !== null) {
    const rescue = el('button', '导出原始存储备份'); rescue.type = 'button'; rescue.addEventListener('click', () => downloadRecord(progress.raw, data.package_id + '-original-record.json')); actions.append(rescue);
  }
  feedback.id = 'import-result';
  section.append(actions, el('p', '导入会合并不同知识点；同一知识点以导入文件为准。尝试与建议采用记录只追加，同一标识内容冲突时整份文件不导入。旧文件不会清除已有尝试，缺失的知识点仍保留。建议先导出当前记录。', 'muted'), feedback);
  const drafts = progress.draftEntries();
  if (drafts.length) {
    section.append(el('h2', `未提交草稿 · ${drafts.length} 份`), el('p', '导出会保留以下全部草稿文字；草稿不是正式尝试，不作为反馈证据。要取得反馈，请进入对应步骤，明确保存本次尝试。', 'feedback-notice'));
    for (const {draft, stale} of drafts) {
      const item = disclosure(`${draft.updated_at} · ${draft.path_id} / ${draft.step_id}`, 'attempt-item');
      if (stale) item.append(el('p', '这是旧学习计划的草稿，只保留原文，不会自动提交到新任务。', 'feedback-notice'));
      for (const [field, label] of [['response', '未提交内容'], ['artifact_refs_text', '产物位置或引用'], ['blocker', '卡点']]) {
        if (draft[field]) item.append(el('h4', label), el('p', draft[field], 'saved-note'));
      }
      item.append(el('p', '产物来源：' + workOriginLabels[draft.work_origin], 'attempt-meta'));
      const path = paths.find(value => value.id === draft.path_id), step = path?.steps?.find(value => value.id === draft.step_id);
      if (!stale && step) item.append(stepLink('继续填写这份草稿 →', step, path));
      section.append(item);
    }
  }
  section.append(pathControl());
  const active = studyTopic(), activeStep = studyStep();
  if (designed && activeStep) section.append(el('p', '当前学习任务：'), stepLink(activities.get(activeStep.activity_id).title + ' →', activeStep, selectedPath(), undefined, true));
  else if (active && !designed) section.append(el('p', '当前学习任务：'), studyLink(active.title + ' →', active.id, selectedPath().id));
  else section.append(el('p', '当前路径尚未设置学习任务；可以从概览选择一步开始。', 'muted'));
  if (progress.state.last_topic_id) section.append(el('p', '最近查阅：' + (topics.get(progress.state.last_topic_id)?.title || progress.state.last_topic_id)));
  if (progress.attemptEntries().length) {
    section.append(el('h2', '各步骤的尝试'), el('p', '导出包含本地尝试和建议采用记录。工作区只读记录由 Agent 保存，刷新页面读取；它们不会自动写入浏览器或本地导出文件。', 'muted'));
    const attempts = el('div', undefined, 'attempt-history');
    for (const entry of progress.attemptEntries().slice().reverse()) {
      const item = attemptHistoryItem(entry), path = paths.find(value => value.id === entry.attempt.path_id);
      const step = path?.steps?.find(value => value.id === entry.attempt.step_id);
      if (step) item.append(stepLink('查看此步骤 →', step, path));
      attempts.append(item);
    }
    section.append(attempts);
  }
  if (progress.feedbackEntries().length) {
    const history = disclosure('全部 Agent 反馈（包括已移除步骤的历史）', 'feedback-history');
    for (const item of progress.feedbackEntries().slice().reverse()) history.append(feedbackCard(item, () => render(false)));
    section.append(history);
  }
  const records = Object.entries(progress.state.topics);
  if (!records.length) section.append(el('p', '还没有个人标记。进入一个知识点后即可记录。', 'empty-state'));
  for (const [id, record] of records) {
    const item = el('section', undefined, 'progress-item'); const h = el('h2');
    h.append(topics.has(id) ? topicLink(topics.get(id).title, id) : el('span', '当前目录未包含：' + id));
    item.append(h, el('p', recordSummary(id), 'muted')); if (record.notes) item.append(el('p', record.notes, 'saved-note')); section.append(item);
  }
  return section;
}
const routeLink = (label, route, className) => {
  const link = el('a', label, className);
  link.href = '#' + route;
  link.dataset.route = '';
  return link;
};
const topicLink = (label, id, className) => routeLink(label, C2CRoutes.topic(id), className);
const studyLink = (label, id, pathId, className) => {
  const link = topicLink(label, id, className);
  link.dataset.studyPath = pathId;
  link.dataset.studyTopic = id;
  return link;
};
const stepLink = (label, step, path, className, start = false) => {
  const link = routeLink(label, C2CRoutes.study(path.id, step.id), className);
  if (start) { link.dataset.studyPath = path.id; link.dataset.studyStep = step.id; }
  return link;
};
const externalLink = (label, href, className) => {
  const link = el('a', label, className);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
};
const originLabels = {creator: '创作者原作 / 片段', external: '外部补充资料', agent: 'Agent 学习提示'};
let currentRoute = 'overview', returnRoute = 'overview';
let materialFilter = 'all', selectedOutlineTopic = null;

function timestamp(seconds) {
  const n = Math.floor(seconds);
  return Math.floor(n / 60) + ':' + String(n % 60).padStart(2, '0');
}
function duration(seconds) {
  if (seconds == null) return '时长未知';
  const n = Math.round(seconds);
  if (n >= 3600) return `${Math.floor(n / 3600)} 小时 ${Math.floor(n % 3600 / 60)} 分钟`;
  return n >= 60 ? `${Math.floor(n / 60)} 分 ${n % 60} 秒` : `${n} 秒`;
}
function readableTitle(title) {
  const text = title.replace(/#[^\s#]+/g, '').trim() || title;
  // Platforms sometimes put a multi-paragraph caption in the title field.
  // Keep the complete source in the disclosure, and a short label in every list.
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const first = Array.from(lines[0] || text);
  return first.slice(0, 120).join('') + (lines.length > 1 || first.length > 120 ? '…' : '');
}
function heading(title, eyebrow) {
  const section = el('section', undefined, 'reading-column');
  if (eyebrow) section.append(el('p', eyebrow, 'breadcrumb'));
  section.append(el('h1', title));
  return section;
}
function disclosure(label, className) {
  const details = el('details', undefined, className);
  details.append(el('summary', label));
  return details;
}
function evidenceList(evidence, video) {
  const list = el('ul', undefined, 'evidence-list');
  for (const item of evidence) {
    const row = el('li');
    const time = el('div', `证据位于 ${timestamp(item.start)}–${timestamp(item.end)}`, 'evidence-time');
    time.append(el('span', item.evidence_kind === 'screen_ocr' ? '画面 OCR' : '转写文本', 'evidence-kind'));
    const body = el('div');
    if (item.label) body.append(el('p', item.label, 'evidence-label'));
    body.append(el('blockquote', item.quote), el('small', `段 ID：${item.segment_id} · 来源：${item.transcript_source || 'unknown'}`));
    const copy = el('button', '复制定位时间'); copy.type = 'button'; copy.className = 'copy-time';
    copy.addEventListener('click', async () => {
      try { await navigator.clipboard.writeText(timestamp(item.start)); copy.textContent = '已复制'; }
      catch { copy.textContent = `请手动复制：${timestamp(item.start)}`; }
    });
    body.append(copy); row.append(time, body); list.append(row);
  }
  return list;
}
function videoRow(video, compact = false) {
  const article = el('article', undefined, 'video');
  const evidence = video.topic_evidence || [];
  const meta = el('div', undefined, 'video-meta');
  if (video.recommended) meta.append(el('span', '建议先看', 'recommended'));
  meta.append(el('span', duration(video.duration_seconds)), el('span', evidence.length ? '本知识点有证据定位' : '本知识点依据标题归类'));
  article.append(meta);
  const title = readableTitle(video.title);
  const link = video.url ? externalLink(title, video.url, 'video-title') : el('span', title, 'video-title');
  link.title = video.title; article.append(link);
  if (video.url) article.append(el('span', '↗ 原视频', 'external-mark'));
  if (evidence.length) {
    article.append(el('p', '本知识点证据位置：' + evidence.map(item => timestamp(item.start)).join('、'), 'topic-locations'));
    const relevant = disclosure('核对本知识点的引文与来源', 'source-details topic-evidence');
    relevant.append(el('p', '这些时间只定位引文，不是完整教学区间。打开原视频后手动定位，并核对前后内容。转写 / OCR 可能有误。', 'full-title'), evidenceList(evidence, video));
    article.append(relevant);
  }
  if (video.review || title !== video.title) {
    const details = disclosure(video.review ? '查看整条视频的完整证据（含其他主题）' : '查看完整原视频标题', 'source-details full-evidence');
    if (title !== video.title) details.append(el('p', video.title, 'full-title'));
    if (video.review) {
      details.append(el('p', video.review.note, 'video-summary'));
      if (!evidence.length) details.append(el('p', '该视频有内容证据，但尚未关联到当前知识点；不据此确认本主题内容。', 'full-title'));
      details.append(evidenceList(video.review.evidence || [], video));
    }
    article.append(details);
  }
  return article;
}
const activityLabels = {understand: '理解概念', practice: '操作练习', create: '制作产物', compare: '比较判断', lookup: '按需查阅'};
const coverageLabels = {supported: '已有内容支持', candidate: '候选内容待核对', missing: '作者内容有缺口', conflicting: '条件或观点待比较'};
const readinessLabels = {ready: '准备条件齐全', needs_review: '还需核对', blocked: '先补齐条件'};
const availabilityLabels = {available: '可取得', unavailable: '暂不可取得', unknown: '可用性待确认'};

function textList(items, ordered = false, className) {
  const list = el(ordered ? 'ol' : 'ul', undefined, className);
  for (const item of items) list.append(el('li', item));
  return list;
}
function readinessNotice(readiness) {
  const box = el('div', undefined, 'readiness-note');
  const status = readiness?.status || 'needs_review';
  box.dataset.readiness = status;
  box.append(el('p', readinessLabels[status] || status, 'readiness-label'));
  if (readiness?.issues?.length) box.append(textList(readiness.issues));
  return box;
}
function learnerBrief() {
  const learner = data.learner;
  const section = el('section', undefined, 'learner-brief');
  section.append(el('h2', '这份路径为谁设计'), el('p', learner.goal, 'prose'));
  const modes = {systematic: '系统学习', problem: '解决问题', explore: '浏览探索'};
  section.append(el('p', `${modes[learner.mode]} · 当前基础：${learner.level || '待确认'} · 每次可用时间：${learner.minutes_per_session == null ? '待确认' : learner.minutes_per_session + ' 分钟'}`, 'muted'));
  const details = disclosure('已有基础、约束与规划假设');
  for (const [key, label] of [['prior_knowledge', '用户说明的已有基础'], ['constraints', '使用条件'], ['assumptions', '规划假设']]) {
    details.append(el('h3', label));
    details.append(learner[key]?.length ? textList(learner[key]) : el('p', '尚未提供', 'muted'));
  }
  section.append(details);
  return section;
}
function coverageView() {
  const section = el('section', undefined, 'capability-coverage');
  section.append(el('h2', '目标需要的能力与缺口'));
  const counts = {};
  for (const capability of capabilities.values()) counts[capability.coverage.status] = (counts[capability.coverage.status] || 0) + 1;
  section.append(el('p', Object.entries(counts).map(([status, count]) => `${coverageLabels[status]} ${count} 项`).join(' · '), 'muted'));
  const details = disclosure('查看每项能力的覆盖和后续处理');
  for (const capability of capabilities.values()) {
    const item = el('article', undefined, 'capability-item');
    item.append(el('h3', capability.title), el('p', capability.outcome));
    item.append(el('p', `${capability.required ? '目标必需' : '可选拓展'} · ${coverageLabels[capability.coverage.status]}`, 'coverage-label'));
    item.append(el('p', capability.coverage.reason));
    if (capability.coverage.next_action) item.append(el('p', '下一步处理：' + capability.coverage.next_action));
    if (capability.prerequisites?.length) item.append(el('p', '依赖：' + capability.prerequisites.map(id => capabilities.get(id).title).join('、'), 'muted'));
    details.append(item);
  }
  section.append(details, el('p', '覆盖状态是 Agent 对材料的组织判断，不表示你已经掌握，也不是作者内容已获人工核验。', 'muted'));
  if (data.learning_design?.issues?.length) {
    const issues = el('aside', undefined, 'design-issues');
    issues.append(el('h3', '这份计划仍需处理'), textList(data.learning_design.issues));
    section.append(issues);
  }
  return section;
}
function activitySources(activity, topic) {
  return activity.sources.map(source => {
    const entry = topic.entries.find(entry => entry.id === source.video_id);
    return {...entry, ...source, id: source.video_id,
      evidence: source.evidence || (entry?.review?.evidence || []).filter(e => source.segment_ids.includes(e.segment_id))};
  });
}
function activityCard(activity, path, step, compact = false) {
  const topic = topics.get(activity.topic_id);
  const box = el('aside', undefined, 'task-card activity-card');
  box.append(el('p', activityLabels[activity.kind], 'activity-kind'), el('h2', activity.title), el('p', activity.objective, 'prose'));
  box.append(readinessNotice(step.readiness));
  if (!compact) box.append(el('h3', '这次怎么做'), textList(activity.instructions, true, 'activity-instructions'));
  box.append(el('p', '留下的产物：' + activity.output, 'activity-output'));
  if (!compact) box.append(el('h3', '完成后自查'), textList(activity.success_criteria));
  box.append(el('p', '停在这里：' + activity.stop_when, 'task-stop'));
  const sources = activitySources(activity, topic);
  const primary = sources.find(source => source.id === activity.primary_video_id);
  if (primary) {
    box.append(primary.url ? externalLink('打开本次主要来源 ↗', primary.url, 'task-source') : el('p', '该来源未提供可打开的链接。', 'muted'));
    box.append(el('p', `原视频完整时长：${duration(primary.duration_seconds)}；${activity.practice_minutes == null ? '实践时间未估算' : `实践约 ${activity.practice_minutes} 分钟（估算）`}。此估算不含查阅与准备，不能据此保证整次学习符合时间预算。`, 'task-meta'));
  }
  const required = activity.required_materials || (activity.required_material_ids || []).map(id => {
    const material_index = data.materials.findIndex(material => material.id === id);
    return {...data.materials[material_index], material_index};
  });
  if (required.length) {
    box.append(el('h3', '本次必需资料'));
    const list = el('ul');
    for (const material of required) {
      const item = el('li');
      item.append(routeLink(material.title, 'materials/' + material.material_index), ` · ${availabilityLabels[material.availability]}`);
      list.append(item);
    }
    box.append(list);
  }
  if (!compact) {
    const details = disclosure('核对本次活动选用的来源与引文', 'activity-sources');
    details.append(el('p', '时间只用于定位引文，不是完整教学区间；请回原作核对上下文。', 'muted'));
    for (const source of sources) {
      details.append(source.url ? externalLink(source.title, source.url) : el('p', source.title));
      details.append(source.evidence.length ? evidenceList(source.evidence, source) : el('p', '仅有来源入口，当前活动尚无内容定位。', 'muted'));
    }
    box.append(details);
  } else {
    const active = studyStep(path)?.id === step.id;
    const blocked = step.readiness?.status === 'blocked';
    box.append(stepLink(active ? '继续查看当前任务 →' : blocked ? '查看这一步的缺口 →' : '开始这一步 →', step, path, 'action', active || !blocked));
  }
  return box;
}
function stepList(path, steps = path.steps, offset = 0) {
  const list = el('ol', undefined, 'path-list');
  list.style.setProperty('--path-offset', offset); list.start = offset + 1;
  for (const step of steps) {
    const activity = activities.get(step.activity_id);
    const item = el('li');
    item.append(stepLink(activity.title, step, path), el('p', `${activityLabels[activity.kind]} · ${readinessLabels[step.readiness?.status] || '待核对'}`), el('p', step.reason));
    list.append(item);
  }
  return list;
}
function activityChoices(topic) {
  const section = el('section', undefined, 'activity-choices');
  section.append(el('h2', '这个知识点可以怎样学'), el('p', '选择具体活动查看；查阅知识点不会改变当前学习位置。', 'muted'));
  let count = 0;
  for (const path of paths) {
    const matching = path.steps.filter(step => step.topic_id === topic.id);
    if (!matching.length) continue;
    count += matching.length;
    section.append(el('h3', path.title));
    const list = el('ul');
    for (const step of matching) {
      const activity = activities.get(step.activity_id), item = el('li');
      item.append(stepLink(`第 ${path.steps.indexOf(step) + 1} 步 · ${activity.title}`, step, path), el('p', activity.output));
      list.append(item);
    }
    section.append(list);
  }
  if (!count) section.append(el('p', '当前作为参考知识点保留，尚未安排学习活动。', 'muted'));
  return section;
}
function designedOverview() {
  const [title, ...subtitle] = data.title.split(/[｜|]/);
  const section = heading(title.trim(), subtitle.join(' · ').trim() || '原视频学习导航');
  section.append(el('p', data.overview, 'prose lede'), learnerBrief(), pathControl());
  const path = selectedPath(), active = studyStep(path);
  if (active) section.append(guidancePanel(path, active));
  section.append(el('h2', path.title), el('p', '这条路径的产物：' + path.outcome), el('p', path.reason, 'muted'));
  section.append(readinessNotice(path.readiness));
  const next = active || path.steps[0];
  if (next) section.append(activityCard(activities.get(next.activity_id), path, next, true));
  else section.append(el('p', '这条路径尚无可安排的活动，先处理下方的能力缺口。', 'empty-state'));
  if (active && active.id !== path.steps[0]?.id) section.append(stepLink('查看这条路径的起点 →', path.steps[0], path));
  const last = topics.get(progress.state.last_topic_id);
  if (last) section.append(topicLink('最近查阅：' + last.title + ' →', last.id));
  section.append(routeLink('我的学习记录 · 导出 / 导入', 'progress'), el('h2', '学习步骤'), stepList(path, path.steps.slice(0, 5)));
  if (path.steps.length > 5) {
    const more = disclosure(`查看后 ${path.steps.length - 5} 步`, 'route-more');
    more.append(stepList(path, path.steps.slice(5), 5)); section.append(more);
  }
  section.append(coverageView(), routeLink('查看来源范围与依据 →', 'scope'));
  return section;
}
function appendAttemptContent(container, attempt) {
  container.append(el('p', `步骤：${attempt.path_id} / ${attempt.step_id} · 活动：${attempt.activity_id}`, 'attempt-meta'));
  container.append(el('p', '产物来源：' + workOriginLabels[attempt.work_origin], 'attempt-meta'));
  if (attempt.response) container.append(el('h4', '本次内容'), el('p', attempt.response, 'saved-note'));
  if (attempt.artifact_refs.length) container.append(el('h4', '产物位置或引用'), textList(attempt.artifact_refs), el('p', '这里只记录引用，不代表文件已经上传或被查看。', 'muted'));
  if (attempt.blocker) container.append(el('h4', '卡点'), el('p', attempt.blocker, 'saved-note'));
  const criteria = disclosure('当时的任务标准'); criteria.append(textList(attempt.criteria)); container.append(criteria);
}
function attemptHistoryItem(entry) {
  const attempt = entry.attempt;
  const item = disclosure(`${attempt.created_at} · ${workOriginLabels[attempt.work_origin]}`, 'attempt-item');
  const persisted = progress.status().persisted;
  const provenance = entry.origin === 'workspace' ? '工作区只读记录 · 未写入此浏览器' : entry.origin === 'both' ?
    (persisted ? '此浏览器与工作区均有相同记录' : '本页与工作区均有相同记录 · 本页修改尚未全部保存') :
    (persisted ? '此浏览器记录' : '本页记录 · 尚未全部保存到浏览器，请导出备份');
  item.append(el('p', provenance, 'attempt-meta'));
  if (entry.stale) item.append(el('p', '学习计划已变化：这是历史尝试，不会自动归入当前任务。', 'feedback-notice'));
  appendAttemptContent(item, attempt);
  if (entry.conflict) {
    const conflict = disclosure('查看同标识的工作区原记录', 'feedback-notice');
    conflict.append(el('p', '本地与工作区的内容不同；两份内容均保留，相关建议不能采用。请导出交由 Agent 核对。'));
    appendAttemptContent(conflict, entry.workspace_attempt); item.append(conflict);
  }
  item.append(el('p', '尝试标识：' + attempt.id, 'attempt-meta'));
  return item;
}
function feedbackCard(feedback, refreshHistory) {
  const card = el('article', undefined, 'feedback-card');
  const labels = {current: '当前反馈', stale: '计划已变化 · 历史反馈', superseded: '已有后续尝试或反馈 · 历史记录'};
  const outcomeLabels = {met: '本次符合', needs_work: '需要再练', not_observed: '尚未观察到'};
  card.append(el('h3', labels[feedback.status]), el('p', feedback.summary, 'saved-note'), el('p', 'Agent 对本次尝试的判断，不代表已经掌握整项能力。', 'muted'));
  const criteria = el('ol', undefined, 'feedback-criteria');
  for (const criterion of feedback.criteria) {
    const row = el('li');
    row.append(el('h4', feedback.attempt.criteria[criterion.criterion_index]), el('p', outcomeLabels[criterion.result], 'feedback-outcome'), el('p', criterion.reason));
    for (const evidence of criterion.evidence) {
      if (evidence.field === 'response') row.append(el('p', '来自本次提交的原文：', 'attempt-meta'), el('blockquote', evidence.quote, 'saved-note'));
      else {
        const observation = feedback.observations.find(item => item.id === evidence.observation_id);
        if (observation) row.append(el('p', '依据 Agent 实际观察：' + observation.id + ' · ' + observation.artifact_ref, 'attempt-meta'));
      }
    }
    criteria.append(row);
  }
  card.append(criteria);
  if (feedback.observations.length) {
    const observations = disclosure('Agent 对产物的实际观察与边界', 'feedback-observations');
    for (const observation of feedback.observations) {
      observations.append(el('h4', observation.id + ' · ' + ({read: '阅读', view: '查看', run: '运行'}[observation.method] || observation.method)),
        el('p', '产物引用：' + observation.artifact_ref), el('p', observation.observation, 'saved-note'), el('p', '观察边界：' + observation.limitations, 'muted'));
    }
    card.append(observations);
  }
  const action = feedback.next_action;
  card.append(el('h4', '下一步建议：' + feedbackActionLabels[action.kind]), el('p', action.reason), textList(action.instructions, true),
    el('p', '留下的产物：' + action.output), el('p', '停在这里：' + action.stop_when));
  if (action.kind === 'finish') card.append(el('p', '收束这次活动不会标记已掌握，也不会消除来源分歧或能力缺口。', 'muted'));
  if (action.target) {
    const path = paths.find(item => item.id === action.target.path_id), step = path?.steps?.find(item => item.id === action.target.step_id);
    if (step) card.append(stepLink('先查看建议指向的步骤 →', step, path), el('p', '查看只用于查阅；采用建议才会调整当前学习位置。', 'attempt-meta'));
  }
  const controls = el('div', undefined, 'record-actions');
  const adopt = el('button', feedback.adopted ? '已采用此建议' : '采用此建议'); adopt.type = 'button'; adopt.disabled = !feedback.actionable;
  const resultMessage = el('p', feedback.adoption_reason || '采用只记录你的选择，并按建议调整位置；不会改动个人学习标记。', 'save-status'); resultMessage.setAttribute('role', 'status');
  adopt.addEventListener('click', () => {
    const result = progress.adoptFeedback(feedback.id);
    refreshSaveStatus();
    if (!result.ok) { resultMessage.textContent = result.error; return; }
    refreshHistory(); refreshGuidancePanels();
    if (result.target) navigate(C2CRoutes.study(result.target.path_id, result.target.step_id));
  });
  controls.append(adopt); card.append(controls, resultMessage);
  return card;
}
function guidanceContent(pathId, stepId) {
  const guidance = progress.currentGuidance(pathId, stepId);
  if (!guidance) return null;
  const box = el('aside', undefined, 'adopted-guidance');
  box.append(el('h2', guidance.active ? '当前采用的指导' : '已采用指导 · 现为历史'));
  if (!guidance.active) box.append(el('p', guidance.reason, 'feedback-notice'));
  const feedback = guidance.feedback;
  if (feedback) {
    const sourcePath = paths.find(path => path.id === feedback.attempt.path_id), sourceStep = sourcePath?.steps?.find(step => step.id === feedback.attempt.step_id);
    box.append(el('p', '这份安排来自你明确采用的原次反馈，不是对当前步骤或这次产物的新评估。', 'muted'));
    if (sourceStep) box.append(stepLink(`查看原反馈步骤：${sourcePath.title} / ${activities.get(sourceStep.activity_id).title} →`, sourceStep, sourcePath));
    else box.append(routeLink('查看原反馈与采用历史 →', 'progress'));
    if (guidance.active) {
      const action = feedback.next_action;
      box.append(el('h3', feedbackActionLabels[action.kind]), el('p', action.reason), textList(action.instructions, true),
        el('p', '这次留下：' + action.output, 'activity-output'), el('p', '停在这里：' + action.stop_when));
      if (action.kind === 'finish') box.append(el('p', '这里只收束这次活动，不会标记掌握或改变能力覆盖。', 'muted'));
    }
  } else box.append(routeLink('查看学习记录 →', 'progress'));
  return box;
}
function guidancePanel(path, step) {
  const panel = el('div'); panel.dataset.guidancePanel = ''; panel.dataset.pathId = path.id; panel.dataset.stepId = step.id;
  const content = guidanceContent(path.id, step.id); if (content) panel.append(content); else panel.hidden = true;
  return panel;
}
function refreshGuidancePanels() {
  for (const panel of document.querySelectorAll('[data-guidance-panel]')) {
    const content = guidanceContent(panel.dataset.pathId, panel.dataset.stepId);
    panel.replaceChildren(); panel.hidden = !content; if (content) panel.append(content);
  }
}
function attemptSection(path, step) {
  const section = el('section', undefined, 'attempt-section');
  section.append(el('h2', '留下这次尝试，取得下一步指导'), el('p', '填写时自动保存草稿，刷新可恢复；草稿不会成为学习证据。明确保存为一次尝试后，才交给 Agent 反馈。', 'muted'));
  const draft = progress.draft(path.id, step.id) || {response: '', artifact_refs_text: '', blocker: '', work_origin: 'unknown', pending_attempt_id: null};
  const form = el('form', undefined, 'attempt-form');
  function area(field, labelText, rows, placeholder) {
    const label = el('label', labelText); label.htmlFor = 'attempt-' + field;
    const input = el('textarea'); input.id = label.htmlFor; input.rows = rows; input.value = draft[field]; input.placeholder = placeholder;
    form.append(label, input); return input;
  }
  const response = area('response', '我这次做出的内容', 4, '粘贴自己的复述、解答、练习结果或制作说明');
  const refs = area('artifact_refs_text', '产物位置或引用（可选，每行一个）', 2, '文件路径或链接；填写引用不会上传文件');
  const blocker = area('blocker', '卡在哪里（可选）', 2, '做到哪一步、有什么疑问、缺什么条件');
  const originLabel = el('label', '这份产物是怎样完成的'); originLabel.htmlFor = 'attempt-origin';
  const origin = el('select'); origin.id = originLabel.htmlFor;
  for (const [value, label] of Object.entries(workOriginLabels)) { const option = el('option', label); option.value = value; origin.append(option); }
  origin.value = draft.work_origin; form.append(originLabel, origin);
  const controls = el('div', undefined, 'record-actions');
  const save = el('button', draft.pending_attempt_id ? '重试保存本次尝试' : '保存为一次新尝试'); save.type = 'submit';
  const exportButton = el('button', progress.draft(path.id, step.id) ? '保存本次尝试并导出' : '导出学习记录给 Agent'); exportButton.type = 'button';
  exportButton.addEventListener('click', () => {
    const saved = updateDraft();
    if (!saved.ok) { notice.textContent = saved.error; return; }
    if (progress.draft(path.id, step.id)) submit(true);
    else downloadRecord(progress.exportText(), data.package_id + '-progress.json');
  });
  controls.append(save, exportButton);
  const notice = el('p', draft.pending_attempt_id ? '上次尝试仍待保存，内容已恢复；重试不会重复添加。' : progress.draft(path.id, step.id) ? '已恢复此步骤的未提交草稿。' : '', 'save-status'); notice.setAttribute('role', 'status');
  form.append(controls, notice);
  const history = el('div', undefined, 'attempt-history'), feedback = el('div', undefined, 'feedback-history');
  function refreshHistory() {
    history.replaceChildren(); feedback.replaceChildren();
    const entries = progress.attemptEntries(path.id, step.id), responses = progress.feedbackEntries(path.id, step.id);
    if (entries.length) {
      history.append(el('h3', '此步骤的尝试记录'));
      for (const entry of entries.slice().reverse()) history.append(attemptHistoryItem(entry));
    }
    feedback.append(el('h3', 'Agent 反馈与下一步'));
    if (!responses.length) feedback.append(el('p', '还没有这个步骤的反馈。保存并导出学习记录给 Agent，请 Agent 记录反馈并更新学习页，再刷新。也可以直接在对话里提供自己的产物和卡点。', 'muted'));
    for (const item of responses.slice().reverse()) feedback.append(feedbackCard(item, refreshHistory));
  }
  const fields = () => ({response: response.value, artifact_refs_text: refs.value, blocker: blocker.value, work_origin: origin.value});
  function updateDraft() {
    const result = progress.saveDraft(path.id, step.id, fields());
    const current = progress.draft(path.id, step.id);
    save.textContent = current?.pending_attempt_id ? '重试保存本次尝试' : '保存为一次新尝试';
    exportButton.textContent = current ? '保存本次尝试并导出' : '导出学习记录给 Agent';
    notice.textContent = !result.ok ? result.error : !result.persisted ? '草稿仅在本页，未保存到浏览器。请导出备份后再关闭；输入内容仍保留。' : current ? '草稿已自动保存；尚未提交为正式尝试。' : '草稿已清空，已有尝试保持不变。';
    refreshSaveStatus();
    return result;
  }
  form.addEventListener('input', updateDraft);
  function submit(andExport = false) {
    const saved = updateDraft();
    if (!saved.ok) { notice.textContent = saved.error; return; }
    const result = progress.submitDraft(path.id, step.id);
    if (!result.ok) { notice.textContent = result.error; return; }
    if (result.persisted) {
      response.value = ''; refs.value = ''; blocker.value = ''; origin.value = 'unknown';
      save.textContent = '保存为一次新尝试'; exportButton.textContent = '导出学习记录给 Agent';
      notice.textContent = andExport ? '已保存这次尝试并导出学习记录。请交给 Agent 反馈，更新学习页后再刷新。' : '已保存这次尝试。可导出给 Agent 取得反馈；下次提交会新增一条记录。';
    } else {
      save.textContent = '重试保存本次尝试';
      notice.textContent = '这次尝试已保留在本页，尚未保存到浏览器。输入保持不变，请导出备份；重试保存不会重复添加。';
    }
    if (andExport) downloadRecord(progress.exportText(), data.package_id + '-progress.json');
    refreshHistory(); refreshSaveStatus(); refreshGuidancePanels();
  }
  form.addEventListener('submit', event => { event.preventDefault(); submit(); });
  section.append(form, el('p', '页面只保存与展示。Agent 根据实际产物给反馈；产物引用本身不能证明已查看。工作区只读记录不会自动写入此浏览器。', 'muted'), history, feedback);
  refreshHistory();
  return section;
}
function stepView(path, step) {
  const activity = activities.get(step.activity_id), topic = topics.get(step.topic_id);
  const section = heading(activity.title, path.title);
  const position = path.steps.indexOf(step);
  section.append(el('p', `第 ${position + 1} / ${path.steps.length} 步 · ${topic.title}`, 'path-position'), el('p', step.reason, 'prose lede'));
  const isCurrent = progress.state.selected_path_id === path.id && studyStep(path)?.id === step.id;
  section.append(isCurrent ? el('p', '这是当前学习任务；临时查阅其他知识点后仍从此步骤继续。', 'study-position') : stepLink('设为当前学习任务', step, path, 'action', true));
  section.append(guidancePanel(path, step));
  section.append(activityCard(activity, path, step), topicLink('查阅知识点与全部相关来源：' + topic.title + ' →', topic.id));
  if (data.feedback_context) section.append(attemptSection(path, step));
  section.append(recordEditor(topic));
  const navigation = el('nav', undefined, 'path-navigation'); navigation.setAttribute('aria-label', '沿当前路径前进');
  if (position + 1 < path.steps.length) {
    const next = path.steps[position + 1], blocked = next.readiness?.status === 'blocked';
    navigation.append(stepLink((blocked ? '查看下一步的缺口：' : '下一步：') + activities.get(next.activity_id).title + ' →', next, path, 'action', !blocked));
  } else navigation.append(el('p', '已到这条路径的最后一步。请对照阶段产物和自查标准回顾自己的结果。'));
  if (position > 0) navigation.append(stepLink('← 上一步：' + activities.get(path.steps[position - 1].activity_id).title, path.steps[position - 1], path, undefined, true));
  navigation.append(routeLink('回到学习概览 →', 'overview'));
  section.append(navigation);
  return section;
}
function pathList(ids, offset = 0) {
  const list = el('ol', undefined, 'path-list');
  list.style.setProperty('--path-offset', offset);
  list.start = offset + 1;
  for (const id of ids) {
    const topic = topics.get(id);
    const item = el('li');
    item.append(topicLink(topic.title, id), el('p', topic.question));
    list.append(item);
  }
  return list;
}
function overview() {
  if (designed) return designedOverview();
  const [title, ...subtitle] = data.title.split(/[｜|]/);
  const section = heading(title.trim(), subtitle.join(' · ').trim() || '原视频学习导航');
  section.append(el('p', data.overview, 'prose lede'));
  if (data.learning_design?.status === 'legacy') section.append(el('p', data.learning_design.issues.join(' '), 'muted'));
  const stats = el('div', undefined, 'stats');
  for (const [count, label] of [[data.topics.length, '个知识点'], [data.indexed_count, '条原视频'], [data.materials?.length || 0, '项资料']]) {
    const item = el('span'); item.append(el('strong', count), label); stats.append(item);
  }
  section.append(stats);
  section.append(pathControl());
  const path = selectedPath();
  const active = studyTopic(path);
  const last = topics.get(progress.state.last_topic_id);
  if (active) section.append(el('p', '当前学习任务：' + active.title, 'study-position'));
  const taskTopic = active || topics.get(path.topic_ids[0]);
  if (taskTopic) section.append(taskCard(taskTopic, true));
  if (active && active.id !== path.topic_ids[0]) section.append(studyLink('从当前路径起点重新开始 →', path.topic_ids[0], path.id));
  if (last && last.id !== active?.id) section.append(topicLink('最近查阅：' + last.title + ' →', last.id));
  section.append(el('p', '目录、搜索和先修链接用于自由查阅，不改变当前学习任务。也可以进入任一步，将它设为当前任务。', 'muted'), routeLink('我的学习记录 · 导出 / 导入', 'progress'));
  section.append(el('h2', path.title), pathList(path.topic_ids.slice(0, 5)));
  if (path.topic_ids.length > 5) {
    const more = disclosure(`继续查看后 ${path.topic_ids.length - 5} 步`, 'route-more');
    more.append(pathList(path.topic_ids.slice(5), 5)); section.append(more);
  }
  const note = el('p', `${data.review_count} 条视频有转写 / OCR 辅助定位，其余依据标题归类。学习顺序由 Agent 整理。`, 'overview-note');
  note.append(' ', routeLink('查看范围与依据', 'scope'));
  section.append(note);
  return section;
}
function topicView(topic) {
  const section = heading(topic.title, topic.group);
  section.append(el('p', topic.question, 'question'), el('p', topic.guidance, 'prose lede'));
  const path = selectedPath(), position = path.topic_ids.indexOf(topic.id);
  if (designed) {
    section.append(el('p', '知识点查阅 · 当前路径：' + path.title, 'path-position'), activityChoices(topic));
  } else {
  section.append(el('p', position < 0 ? `自由查阅 · 当前路径：${path.title}` : `${path.title} · 第 ${position + 1} / ${path.topic_ids.length} 步`, 'path-position'), taskCard(topic));
  const active = studyTopic(path);
  const studyPosition = el('div', undefined, 'study-controls');
  if (active?.id === topic.id) studyPosition.append(el('p', '这是当前学习任务；临时查阅其他内容后仍可从这里继续。', 'muted'));
  else {
    if (active) studyPosition.append(studyLink('返回当前学习任务：' + active.title + ' →', active.id, path.id));
    if (position >= 0) studyPosition.append(studyLink('设为当前学习任务', topic.id, path.id));
  }
  section.append(studyPosition);
  }
  if (topic.prerequisites?.length) {
    const prerequisites = el('div', undefined, 'prerequisites');
    prerequisites.append(el('span', '建议先了解'));
    for (const id of topic.prerequisites) prerequisites.append(topicLink(topics.get(id).title, id));
    section.append(prerequisites);
    for (const item of path.prerequisite_exemptions || []) {
      if (topic.prerequisites.includes(item.topic_id)) section.append(el('p', `${topics.get(item.topic_id).title}：本路径${item.status === 'assumed_known' ? '假设已具备' : '已声明跳过此缺口'}。${item.reason}；这不代表你的掌握状态。`, 'muted'));
    }
  }
  if (topic.watch_for) {
    const focus = el('aside', undefined, 'focus-note');
    focus.append(el('h2', '观看时留意'), el('p', topic.watch_for, 'prose'));
    section.append(focus);
  }
  const head = el('div', undefined, 'section-head');
  head.append(el('h2', '对应原视频'), el('span', `${topic.entries.length} 条`));
  section.append(head);
  const first = topic.entries.filter(video => video.recommended);
  const rest = topic.entries.filter(video => !video.recommended);
  for (const video of first) section.append(videoRow(video));
  if (rest.length && first.length) {
    const more = disclosure(`同主题补充视频 · ${rest.length} 条`, 'more-videos');
    for (const video of rest) more.append(videoRow(video));
    section.append(more);
  } else for (const video of rest) section.append(videoRow(video));
  if (topic.self_check) {
    const check = el('aside', undefined, 'check-note');
    check.append(el('h2', '看完后，试着回答'), el('p', topic.self_check, 'prose'));
    section.append(check);
  }
  const relevant = (data.materials || []).filter(material => material.topic_ids?.includes(topic.id));
  if (relevant.length) {
    const materials = el('div', undefined, 'next-topics');
    materials.append(el('h2', '相关学习资料'));
    for (const material of relevant) materials.append(routeLink(material.title, 'materials/' + data.materials.indexOf(material)));
    section.append(materials);
  }
  section.append(recordEditor(topic));
  const navigation = el('nav', undefined, 'path-navigation'); navigation.setAttribute('aria-label', '沿当前路径前进');
  if (designed) {
    const active = studyStep(path);
    if (active) navigation.append(stepLink('返回当前学习任务：' + activities.get(active.activity_id).title + ' →', active, path));
    navigation.append(routeLink('回到学习概览 →', 'overview'));
  } else if (position >= 0 && position + 1 < path.topic_ids.length) {
    const nextId = path.topic_ids[position + 1]; navigation.append(studyLink('下一步：' + topics.get(nextId).title + ' →', nextId, path.id, 'action'));
  } else if (position >= 0) navigation.append(el('p', '这条路径已到最后一步。可以在这里停下，或回顾仍需练习的知识点。'), routeLink('回到学习概览 →', 'overview'));
  else navigation.append(routeLink('回到当前学习路径 →', 'overview'));
  if (!designed && position > 0) navigation.append(studyLink('← 上一步：' + topics.get(path.topic_ids[position - 1]).title, path.topic_ids[position - 1], path.id));
  section.append(navigation);
  const next = data.topics.filter(candidate => candidate.prerequisites?.includes(topic.id) && candidate.id !== path.topic_ids[position + 1]);
  if (next.length) {
    const links = el('nav', undefined, 'next-topics');
    links.setAttribute('aria-label', '其他可选分支');
    links.append(el('h2', '其他可选分支'));
    for (const item of next) links.append(topicLink(item.title + ' →', item.id));
    section.append(links);
  }
  return section;
}
function mapView() {
  const section = heading('知识地图', data.creator.name);
  section.classList.remove('reading-column');
  section.append(el('p', '按主题找到要解决的问题。点击知识点查看原视频；进入后可沿先修与后续知识点继续学习。分组顺序是学习建议。', 'map-intro'));
  const grid = el('div', undefined, 'map-groups');
  for (const group of groups) {
    const branch = el('section', undefined, 'map-group');
    branch.append(el('h2', group));
    const list = el('ul', undefined, 'map-branches');
    for (const topic of data.topics.filter(topic => topic.group === group)) {
      const item = el('li');
      item.append(topicLink(topic.title, topic.id), el('span', `${topic.entries.length} 条`, 'count'));
      list.append(item);
    }
    branch.append(list); grid.append(branch);
  }
  const exportRow = el('p', undefined, 'map-export');
  const download = el('a', '保存完整知识地图 SVG'); download.href = 'knowledge-map.svg'; download.download = '';
  exportRow.append(download);
  section.append(grid, exportRow);
  return section;
}
function adviceView() {
  const section = heading('怎样使用这份导航', '学习建议');
  section.append(el('p', `学习目标：${data.goal}`, 'prose lede'));
  const list = el('ol', undefined, 'advice-list');
  for (const advice of data.learning_advice || []) list.append(el('li', advice));
  if (!list.children.length) section.append(el('p', '当前尚未整理额外学习建议。', 'prose'));
  section.append(list, routeLink('查看建议起步顺序 →', 'overview'));
  return section;
}
function materialsView(selectedIndex = null) {
  const section = heading('素材与课件', data.creator.name);
  section.append(el('p', '原作片段、外部资料和学习提示分别标明来源。已取得的文件可直接打开，未取得的资料保留入口和状态。', 'map-intro'));
  const filters = el('div', undefined, 'resource-filters');
  filters.setAttribute('aria-label', '按资料来源筛选');
  filters.setAttribute('role', 'group');
  for (const [value, label] of [['all', '全部'], ['creator', '创作者'], ['external', '外部补充'], ['agent', '学习提示']]) {
    const button = el('button', label); button.type = 'button';
    button.dataset.filter = value;
    button.setAttribute('aria-pressed', String(materialFilter === value));
    button.addEventListener('click', () => {
      materialFilter = value;
      render(false);
      document.querySelector(`[data-filter="${value}"]`).focus();
    });
    filters.append(button);
  }
  if (selectedIndex === null) section.append(filters);
  else section.append(routeLink('← 查看全部资料', 'materials'));
  const materials = (data.materials || []).filter((material, index) => selectedIndex === null ? (materialFilter === 'all' || material.origin === materialFilter) : index === selectedIndex);
  if (!materials.length) section.append(el('p', '这一类暂时没有资料。', 'empty-state'));
  for (const material of materials) {
    const article = el('article', undefined, 'material');
    const visual = el('div', undefined, 'material-visual');
    const ext = material.local_path?.split('.').pop().toLowerCase();
    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext)) {
      const image = el('img'); image.src = material.local_path; image.alt = material.title; image.loading = 'lazy';
      visual.append(image);
    } else visual.append(el('span', ext ? ext.toUpperCase() : '入口', 'file-label'));
    const body = el('div');
    body.append(el('div', `${originLabels[material.origin]} · ${material.status}${material.availability ? ' · ' + availabilityLabels[material.availability] : ''}`, 'material-meta'), el('h2', material.title), el('p', material.description));
    const actions = el('div', undefined, 'material-actions');
    const hasTextPreview = typeof material.preview_text === 'string';
    const textPreviewUnavailable = typeof material.preview_unavailable === 'string';
    if (hasTextPreview && selectedIndex === null) actions.append(routeLink('阅读资料', 'materials/' + data.materials.indexOf(material)));
    if (material.local_path) {
      const file = externalLink(hasTextPreview || textPreviewUnavailable ? '下载原文件' : '打开本地文件', material.local_path);
      if (hasTextPreview || textPreviewUnavailable) { file.download = ''; file.removeAttribute('target'); }
      actions.append(file);
    }
    if (material.url) actions.append(externalLink('原始入口 ↗', material.url));
    body.append(actions);
    if (selectedIndex !== null && hasTextPreview) {
      body.append(el('h3', '文件原文', 'material-text-heading'), el('pre', material.preview_text, 'material-text-preview'));
    } else if (selectedIndex !== null && textPreviewUnavailable) body.append(el('p', material.preview_unavailable, 'muted'));
    if (material.topic_ids?.length) {
      const related = el('div', undefined, 'material-topics');
      for (const id of material.topic_ids) related.append(topicLink(topics.get(id).title, id));
      body.append(related);
    }
    article.append(visual, body); section.append(article);
  }
  const exportRow = el('p', undefined, 'map-export');
  const link = el('a', '打开资料清单 Markdown'); link.href = 'materials.md'; exportRow.append(link); section.append(exportRow);
  return section;
}
function scopeView() {
  const section = heading('范围与依据', '阅读说明');
  section.append(el('p', `清单共 ${data.inventory_count} 条，索引纳入 ${data.indexed_count} 条原视频，其中 ${data.review_count} 条有转写 / OCR 辅助归类。数量不代表已观看或人工核验。`, 'prose lede'));
  const list = el('ul', undefined, 'scope-list');
  list.append(el('li', '“依据标题”表示初步归类；“有内容定位”表示附有机器转写或画面 OCR 的片段与位置，仍需核对原作。'));
  for (const limitation of data.limitations || []) list.append(el('li', limitation));
  section.append(list);
  const exports = el('div', undefined, 'material-actions');
  for (const [file, label] of [['README.md', 'Markdown 目录'], ['video-index.csv', '视频索引 CSV'], ['knowledge-map.svg', '知识地图 SVG'], ['index.json', '结构化索引 JSON']]) {
    const link = el('a', label); link.href = file; link.download = ''; exports.append(link);
  }
  section.append(exports);
  return section;
}
function searchView(query) {
  const section = heading('搜索结果', '在全部知识点与原视频中查找');
  const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  const matches = text => words.every(word => text.toLocaleLowerCase().includes(word));
  const results = [], uniqueVideos = new Set();
  for (const topic of data.topics) {
    const activityText = [...activities.values()].filter(activity => activity.topic_id === topic.id).map(activity => [activity.title, activity.objective, activity.output].join(' ')).join(' ');
    const topicMatch = matches([topic.group, topic.title, topic.question, topic.guidance, topic.watch_for || '', activityText].join(' '));
    const entries = topic.entries.filter(video => topicMatch || matches([video.title, ...(video.topic_evidence || []).map(e => (e.label || '') + ' ' + e.quote)].join(' ')));
    if (entries.length) {
      entries.forEach(video => uniqueVideos.add(video.id));
      results.push({topic, entries});
    }
  }
  const count = el('p', `${results.length} 个知识点 · ${uniqueVideos.size} 条原视频`, 'map-intro');
  count.setAttribute('role', 'status');
  section.append(count);
  for (const {topic, entries} of results) {
    const group = el('section', undefined, 'result-group');
    const title = el('h2'); title.append(topicLink(topic.title + ' →', topic.id)); group.append(title);
    for (const video of entries) group.append(videoRow(video, true));
    section.append(group);
  }
  if (!results.length) {
    const empty = el('div', undefined, 'empty-state');
    empty.append(el('h2', '没有找到对应内容'), el('p', '试试更短的词，或从知识地图按主题查找。'), routeLink('打开知识地图 →', 'knowledge-map'));
    section.append(empty);
  }
  return section;
}
function readRoute() {
  try { return decodeURIComponent(location.hash.slice(1)) || 'overview'; }
  catch { return 'overview'; }
}
function navigate(route, {replace = false, focus = true} = {}) {
  if (!currentRoute.startsWith('search=')) returnRoute = currentRoute;
  if (readRoute() !== route) history[replace ? 'replaceState' : 'pushState'](null, '', '#' + encodeURI(route));
  render(focus);
}
function render(focus = false) {
  const resolved = C2CRoutes.resolve(readRoute(), topics.keys(), pathSteps);
  currentRoute = resolved.route;
  if (readRoute() !== currentRoute) history.replaceState(null, '', '#' + encodeURI(currentRoute));
  let content, view = currentRoute, query = '';
  if (resolved.topicId !== null) {
    if (progress.state.last_topic_id !== resolved.topicId) progress.visit(resolved.topicId);
    if (resolved.stepId) {
      const path = paths.find(path => path.id === resolved.pathId);
      content = stepView(path, path.steps.find(step => step.id === resolved.stepId));
    } else content = topicView(topics.get(resolved.topicId));
    view = 'topic';
  }
  else if (currentRoute.startsWith('search=')) { query = currentRoute.slice(7); content = searchView(query); view = 'search'; }
  else if (currentRoute === 'knowledge-map') { content = mapView(); view = 'map'; }
  else if (currentRoute === 'learning-advice') { content = adviceView(); view = 'advice'; }
  else if (currentRoute === 'materials') content = materialsView();
  else if (/^materials\/\d+$/.test(currentRoute)) { content = materialsView(Number(currentRoute.split('/')[1])); view = 'materials'; }
  else if (currentRoute === 'scope') content = scopeView();
  else if (currentRoute === 'progress') content = progressView();
  else { content = overview(); view = 'overview'; }
  $('content').replaceChildren(content);
  refreshSaveStatus();
  document.title = content.querySelector('h1').textContent + ' · ' + data.creator.name;
  if ($('search').value !== query) $('search').value = query;
  $('clear-search').hidden = !query;
  for (const link of document.querySelectorAll('[data-view]')) {
    if (link.dataset.view === view) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  }
  if (view === 'topic' && selectedOutlineTopic !== currentRoute) {
    for (const group of $('outline').querySelectorAll('details')) group.open = false;
    selectedOutlineTopic = currentRoute;
  }
  const outlineRoute = resolved.topicId !== null ? C2CRoutes.topic(resolved.topicId) : currentRoute;
  for (const link of $('outline').querySelectorAll('a')) {
    if (link.hash === '#' + outlineRoute) {
      link.setAttribute('aria-current', 'page');
      link.closest('details').open = true;
    } else link.removeAttribute('aria-current');
  }
  $('topic-select').value = resolved.topicId !== null ? C2CRoutes.topic(resolved.topicId) : 'overview';
  if (focus) { window.scrollTo(0, 0); $('content').focus({preventScroll: true}); }
}
$('creator-name').textContent = data.creator.name;
$('outline-count').textContent = `${data.topics.length} 个知识点 · ${groups.length} 个分组`;
for (const group of groups) {
  const details = disclosure(group, 'outline-group'); details.open = group === groups[0];
  const optgroup = el('optgroup'); optgroup.label = group;
  for (const topic of data.topics.filter(topic => topic.group === group)) {
    const link = topicLink('', topic.id);
    link.append(el('span', topic.title), el('span', topic.entries.length, 'count'));
    details.append(link);
    const option = el('option', topic.title); option.value = C2CRoutes.topic(topic.id); optgroup.append(option);
  }
  $('outline').append(details); $('topic-select').append(optgroup);
}
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault(); $('content').focus(); $('content').scrollIntoView();
});
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-route]');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  if (link.dataset.studyPath) {
    const result = link.dataset.studyStep ? progress.startStep(link.dataset.studyPath, link.dataset.studyStep) : progress.startTask(link.dataset.studyPath, link.dataset.studyTopic);
    if (!result.ok) { refreshSaveStatus(result.error); return; }
  }
  navigate(decodeURIComponent(link.hash.slice(1)));
});
$('topic-select').addEventListener('change', event => navigate(event.target.value));
$('search').addEventListener('input', event => {
  const query = event.target.value;
  if (query.trim()) navigate('search=' + query, {replace: currentRoute.startsWith('search='), focus: false});
  else navigate(returnRoute, {replace: currentRoute.startsWith('search='), focus: false});
});
$('clear-search').addEventListener('click', () => {
  navigate(returnRoute, {replace: true, focus: false}); $('search').focus();
});
window.addEventListener('hashchange', () => render(true));
window.addEventListener('beforeunload', event => {
  if (progress.draftEntries().length && !progress.status().persisted) { event.preventDefault(); event.returnValue = ''; }
});
const preference = {
  get(key) { try { return localStorage.getItem('c2c-' + key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem('c2c-' + key, value); } catch { /* file:// may disallow storage */ } }
};
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
let theme = preference.get('theme');
function applyTheme() {
  if (!['light', 'dark'].includes(theme)) theme = systemTheme.matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  $('theme-toggle').textContent = theme === 'dark' ? '浅色' : '深色';
  $('theme-toggle').setAttribute('aria-label', theme === 'dark' ? '切换为浅色阅读' : '切换为深色阅读');
}
$('theme-toggle').addEventListener('click', () => {
  theme = theme === 'dark' ? 'light' : 'dark'; preference.set('theme', theme); applyTheme();
});
systemTheme.addEventListener('change', () => { if (!preference.get('theme')) { theme = null; applyTheme(); } });
let fontSize = Number(preference.get('size')) || 17;
function applyFont() {
  fontSize = Math.min(22, Math.max(15, fontSize));
  document.documentElement.style.setProperty('--reading-size', fontSize + 'px');
  $('smaller').disabled = fontSize <= 15; $('larger').disabled = fontSize >= 22;
}
$('smaller').addEventListener('click', () => { fontSize--; applyFont(); preference.set('size', fontSize); });
$('larger').addEventListener('click', () => { fontSize++; applyFont(); preference.set('size', fontSize); });
applyTheme(); applyFont(); render();
