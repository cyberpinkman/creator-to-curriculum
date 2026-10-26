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
const routeLink = (label, route, className) => {
  const link = el('a', label, className);
  link.href = '#' + route;
  link.dataset.route = '';
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
  return title.replace(/#[^\s#]+/g, '').trim() || title;
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
function videoRow(video, compact = false) {
  const article = el('article', undefined, 'video');
  const meta = el('div', undefined, 'video-meta');
  if (video.recommended) meta.append(el('span', '建议先看', 'recommended'));
  meta.append(el('span', duration(video.duration_seconds)), el('span', video.review ? '有内容定位' : '依据标题'));
  article.append(meta);
  const title = readableTitle(video.title);
  const link = video.url ? externalLink(title, video.url, 'video-title') : el('span', title, 'video-title');
  link.title = video.title;
  article.append(link);
  if (video.url) article.append(el('span', '↗ 原视频', 'external-mark'));
  if (video.review && !compact) article.append(el('p', video.review.note, 'video-summary'));
  if (video.review || title !== video.title) {
    const details = disclosure(video.review ? '查看时间定位与原文依据' : '查看完整原视频标题', 'source-details');
    if (title !== video.title) details.append(el('p', video.title, 'full-title'));
    if (video.review) {
      if (compact) details.append(el('p', video.review.note, 'video-summary'));
      details.append(el('p', '打开原视频后，按下列时间手动定位。机器转写 / OCR 可能有误，请核对原作。', 'full-title'));
      const list = el('ul', undefined, 'evidence-list');
      for (const evidence of video.review.evidence || []) {
        const item = el('li');
        const time = el('div', `${timestamp(evidence.start)}–${timestamp(evidence.end)}`, 'evidence-time');
        time.append(el('span', evidence.evidence_kind === 'screen_ocr' ? '画面 OCR' : '机器转写', 'evidence-kind'));
        const body = el('div');
        if (evidence.label) body.append(el('p', evidence.label, 'evidence-label'));
        body.append(el('blockquote', evidence.quote));
        item.append(time, body);
        list.append(item);
      }
      details.append(list);
    }
    article.append(details);
  }
  return article;
}
function pathList(ids, offset = 0) {
  const list = el('ol', undefined, 'path-list');
  list.style.setProperty('--path-offset', offset);
  list.start = offset + 1;
  for (const id of ids) {
    const topic = topics.get(id);
    const item = el('li');
    item.append(routeLink(topic.title, id), el('p', topic.question));
    list.append(item);
  }
  return list;
}
function overview() {
  const [title, ...subtitle] = data.title.split(/[｜|]/);
  const section = heading(title.trim(), subtitle.join(' · ').trim() || '原视频学习导航');
  section.append(el('p', data.overview, 'prose lede'));
  const stats = el('div', undefined, 'stats');
  for (const [count, label] of [[data.topics.length, '个知识点'], [data.indexed_count, '条原视频'], [data.materials?.length || 0, '项资料']]) {
    const item = el('span'); item.append(el('strong', count), label); stats.append(item);
  }
  section.append(stats);
  if (data.start_path.length) section.append(routeLink('从第一个知识点开始 →', data.start_path[0], 'action'));
  section.append(el('h2', '建议起步顺序'), pathList(data.start_path.slice(0, 5)));
  if (data.start_path.length > 5) {
    const more = disclosure(`继续查看后 ${data.start_path.length - 5} 步`, 'route-more');
    more.append(pathList(data.start_path.slice(5), 5)); section.append(more);
  }
  const note = el('p', `${data.review_count} 条视频有转写 / OCR 辅助定位，其余依据标题归类。学习顺序由 Agent 整理。`, 'overview-note');
  note.append(' ', routeLink('查看范围与依据', 'scope'));
  section.append(note);
  return section;
}
function topicView(topic) {
  const section = heading(topic.title, topic.group);
  section.append(el('p', topic.question, 'question'), el('p', topic.guidance, 'prose lede'));
  if (topic.prerequisites?.length) {
    const prerequisites = el('div', undefined, 'prerequisites');
    prerequisites.append(el('span', '建议先了解'));
    for (const id of topic.prerequisites) prerequisites.append(routeLink(topics.get(id).title, id));
    section.append(prerequisites);
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
  const next = data.topics.filter(candidate => candidate.prerequisites?.includes(topic.id));
  if (next.length) {
    const links = el('nav', undefined, 'next-topics');
    links.setAttribute('aria-label', '接下来可学');
    links.append(el('h2', '接下来可学'));
    for (const item of next) links.append(routeLink(item.title + ' →', item.id));
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
      item.append(routeLink(topic.title, topic.id), el('span', `${topic.entries.length} 条`, 'count'));
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
    body.append(el('div', `${originLabels[material.origin]} · ${material.status}`, 'material-meta'), el('h2', material.title), el('p', material.description));
    const actions = el('div', undefined, 'material-actions');
    if (material.local_path) actions.append(externalLink('打开本地文件', material.local_path));
    if (material.url) actions.append(externalLink('原始入口 ↗', material.url));
    body.append(actions);
    if (material.topic_ids?.length) {
      const related = el('div', undefined, 'material-topics');
      for (const id of material.topic_ids) related.append(routeLink(topics.get(id).title, id));
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
    const topicMatch = matches([topic.group, topic.title, topic.question, topic.guidance, topic.watch_for || ''].join(' '));
    const entries = topic.entries.filter(video => topicMatch || matches([video.title, video.review?.note || '', ...(video.review?.evidence || []).map(e => (e.label || '') + ' ' + e.quote)].join(' ')));
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
    const title = el('h2'); title.append(routeLink(topic.title + ' →', topic.id)); group.append(title);
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
  currentRoute = readRoute();
  let content, view = currentRoute, query = '';
  if (topics.has(currentRoute)) { content = topicView(topics.get(currentRoute)); view = 'topic'; }
  else if (currentRoute.startsWith('search=')) { query = currentRoute.slice(7); content = searchView(query); view = 'search'; }
  else if (currentRoute === 'knowledge-map') { content = mapView(); view = 'map'; }
  else if (currentRoute === 'learning-advice') { content = adviceView(); view = 'advice'; }
  else if (currentRoute === 'materials') content = materialsView();
  else if (/^materials\/\d+$/.test(currentRoute)) { content = materialsView(Number(currentRoute.split('/')[1])); view = 'materials'; }
  else if (currentRoute === 'scope') content = scopeView();
  else { content = overview(); view = 'overview'; }
  $('content').replaceChildren(content);
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
  for (const link of $('outline').querySelectorAll('a')) {
    if (link.hash === '#' + currentRoute) {
      link.setAttribute('aria-current', 'page');
      link.closest('details').open = true;
    } else link.removeAttribute('aria-current');
  }
  $('topic-select').value = topics.has(currentRoute) ? currentRoute : 'overview';
  if (focus) { window.scrollTo(0, 0); $('content').focus({preventScroll: true}); }
}
$('creator-name').textContent = data.creator.name;
$('outline-count').textContent = `${data.topics.length} 个知识点 · ${groups.length} 个分组`;
for (const group of groups) {
  const details = disclosure(group, 'outline-group'); details.open = group === groups[0];
  const optgroup = el('optgroup'); optgroup.label = group;
  for (const topic of data.topics.filter(topic => topic.group === group)) {
    const link = routeLink('', topic.id);
    link.append(el('span', topic.title), el('span', topic.entries.length, 'count'));
    details.append(link);
    const option = el('option', topic.title); option.value = topic.id; optgroup.append(option);
  }
  $('outline').append(details); $('topic-select').append(optgroup);
}
document.querySelector('.skip-link').addEventListener('click', event => {
  event.preventDefault(); $('content').focus(); $('content').scrollIntoView();
});
document.addEventListener('click', event => {
  const link = event.target.closest('a[data-route]');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault(); navigate(decodeURIComponent(link.hash.slice(1)));
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
