"""Knowledge maps that send learners to the original videos, without a new course."""
import csv
import html
import io
import json
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
    page=HTML.replace('__TITLE__',html.escape(plan['title'])).replace('__DATA__',encoded).replace('__MAP__',svg)
    atomic_text(out/'index.html',page)
    return out.resolve()


def knowledge_map(plan):
    """Two-row overview; topic selection exposes exact prerequisite relationships."""
    groups = list(dict.fromkeys(t['group'] for t in plan['topics']))
    width=1180; columns=min(5,len(groups)); rows=(len(groups)+columns-1)//columns
    most=max(sum(t['group']==g for t in plan['topics']) for g in groups)
    row_height=max(220,100+most*34)
    height=rows*row_height+30
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="group" aria-label="知识地图：点击节点打开对应视频。阶段箭头表示建议顺序。">',
         '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8baf93"/></marker></defs>']
    cell=width/columns
    for i,g in enumerate(groups):
        row=i//columns; col=i%columns if row%2==0 else columns-1-i%columns
        x=col*cell+12;y=row*row_height+20
        if i:
            prior=(i-1)%columns if ((i-1)//columns)%2==0 else columns-1-(i-1)%columns
            py=((i-1)//columns)*row_height+40
            if (i-1)//columns==row:
                sx=prior*cell+(cell-8 if row%2==0 else 8);ex=x-4 if row%2==0 else x+cell-20
                svg.append(f'<path d="M {sx} {py} L {ex} {y+20}" stroke="#8baf93" fill="none" marker-end="url(#arrow)"/>')
            else:
                sx=x+cell/2-12
                svg.append(f'<path d="M {sx} {py+row_height-55} L {sx} {y-5}" stroke="#8baf93" fill="none" marker-end="url(#arrow)"/>')
        label=html.escape(g)
        svg.append(f'<rect x="{x}" y="{y}" width="{cell-24}" height="42" rx="7" fill="#204f3b"/><text x="{x+10}" y="{y+27}" fill="white" font-family="system-ui,sans-serif" font-size="13">{label}</text>')
        for j,t in enumerate(t for t in plan['topics'] if t['group']==g):
            ty=y+55+j*34;title=html.escape(t['title']);short=html.escape(t['title'][:17]+('…' if len(t['title'])>17 else ''))
            svg.append(f'<a href="index.html#{t["id"]}" data-map-topic="{t["id"]}" tabindex="0"><title>{title}</title><rect x="{x}" y="{ty}" width="{cell-24}" height="28" rx="5" fill="#eef4eb" stroke="#cadbc4"/><text x="{x+9}" y="{ty+19}" fill="#254331" font-family="system-ui,sans-serif" font-size="12">{short}</text></a>')
    svg.append('</svg>')
    return ''.join(svg)


HTML=r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f7f8f4;color:#18302a;font:16px/1.7 system-ui,-apple-system,"PingFang SC",sans-serif}header,main{max-width:1240px;margin:auto;padding:34px 32px}header{padding-bottom:22px}h1{font-size:32px;line-height:1.3;margin:10px 0}h2{font-size:23px;margin:0 0 8px}h3{font-size:17px;margin:0}p{margin:8px 0}a{color:#13634d;text-underline-offset:4px}small,.muted{color:#65736b}nav{position:sticky;top:12px;align-self:start;max-height:90vh;overflow:auto}nav button{display:block;width:100%;text-align:left;margin:4px 0;border:0;background:transparent;padding:9px 12px;color:inherit;border-radius:6px;cursor:pointer}button.active{background:#dceade;font-weight:650}button:focus-visible,a:focus-visible,input:focus-visible,summary:focus-visible{outline:3px solid #b67b24;outline-offset:3px}.layout{display:grid;grid-template-columns:230px 1fr;gap:36px;padding-top:6px}input{width:100%;font:inherit;border:1px solid #bbcabe;padding:11px 14px;background:white;border-radius:7px}.tools{display:flex;gap:18px;align-items:center;flex-wrap:wrap}.path{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.path a{background:#e7eee5;padding:6px 11px;border-radius:5px;text-decoration:none;font-size:14px}.map-panel{background:white;border:1px solid #dce3d8;padding:20px;border-radius:10px;margin-top:24px}.map-panel svg{display:block;width:100%;min-width:1080px}.map-scroll{overflow-x:auto}.map-panel a:hover rect,.map-panel a:focus rect{fill:#c8dfbd;stroke:#245d3e}.advice{background:#edf2e7;padding:20px 24px;border-radius:8px;margin-top:24px}.advice li{margin:8px 0}.materials-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(245px,1fr));gap:14px}.material{padding:18px;border:1px solid #dce3d8;border-radius:8px;background:white}.material p{font-size:14px}.links{display:flex;flex-wrap:wrap;gap:14px}.study-focus{border-left:3px solid #87a177;padding:4px 16px;margin:16px 0}.study-focus p{margin:6px 0}.deps{font-size:14px;display:flex;gap:10px;flex-wrap:wrap;margin:10px 0}.topic{border-top:1px solid #cad5ca;padding-top:26px;margin:30px 0}.guidance{max-width:800px;color:#4f6459}.video{background:#fff;border:1px solid #dce3d8;border-radius:8px;padding:18px 20px;margin:12px 0}.video a{font-weight:600;text-decoration:none}.video a:hover{text-decoration:underline}.meta{font-size:13px;color:#6f7c73;margin-bottom:6px}.badge{color:#176244;background:#e6f2e6;padding:2px 7px;border-radius:4px;margin-right:8px}.review{font-size:14px;color:#58695c;padding-top:8px}.review blockquote{border-left:2px solid #c1d1bd;margin:8px 0;padding-left:12px}details{margin-top:14px}summary{cursor:pointer;color:#526c5a}footer{border-top:1px solid #d0d9ce;padding:18px 0;font-size:13px;color:#6d776f}[hidden]{display:none!important}@media(max-width:760px){header,main{padding:22px 18px}.layout{grid-template-columns:1fr;gap:10px}nav{position:static;max-height:190px;border-bottom:1px solid #dce3d8}nav button{display:inline-block;width:auto}h1{font-size:26px}.video{padding:16px}}@media print{nav,input,.tools{display:none}.layout{display:block}.topic{break-inside:avoid}body{background:white}a{color:#18302a}}</style>
<header><small>CREATOR TO CURRICULUM / 原视频学习导航</small><h1 id="title"></h1><p id="overview"></p><p class="muted" id="stats"></p><div class="links"><a href="#knowledge-map">知识地图</a><a href="#learning-advice">学习建议</a><a href="#materials">素材与课件</a></div><section class="map-panel" id="knowledge-map"><h2>知识地图</h2><p class="muted">点击节点定位原视频。阶段箭头是建议顺序；每个知识点另列先修与后续节点。手机可横向滑动。</p><div class="map-scroll">__MAP__</div><a href="knowledge-map.svg" download>保存地图 SVG</a></section><section class="advice" id="learning-advice"><h2>怎样使用这份导航</h2><ol id="advice"></ol></section><h2 style="margin-top:28px">起步路径</h2><div class="path" id="path"></div><label for="search">查找知识点或视频</label><input id="search" type="search" placeholder="例如：字母音、ee ea、音节、深蹲"><div class="tools"><p id="resultCount" aria-live="polite"></p><a href="video-index.csv" download>下载视频索引 CSV</a><a href="README.md">Markdown 目录</a></div><details><summary>范围与依据</summary><div id="limits"></div></details></header>
<main class="layout"><nav aria-label="知识结构" id="nav"></nav><div><div id="content"></div><footer>学习顺序与归类由 Agent 整理。点击视频标题前往创作者原作；视频可能因平台权限、登录状态或下架而不可访问。已观看与掌握情况由你自行记录。</footer></div></main>
<section id="materials" style="max-width:1240px;margin:0 auto;padding:16px 32px 48px"><h2>学习素材与课件</h2><p class="muted">来源身份与获取状态分开记录。第三方材料仅用于本地学习；链接不会自动变成已下载。</p><div class="materials-grid" id="material-list"></div><p><a href="materials.md">资料清单 Markdown</a></p></section>
<script id="data" type="application/json">__DATA__</script><script>
const d=JSON.parse(document.getElementById('data').textContent);let chosen='',query='';const $=id=>document.getElementById(id);const node=(tag,txt,cls)=>{const e=document.createElement(tag);if(txt!==undefined)e.textContent=txt;if(cls)e.className=cls;return e};
$('title').textContent=d.title;$('overview').textContent=d.overview;$('stats').textContent=`${d.topics.length} 个知识点 · ${d.indexed_count} 条原视频 · ${d.review_count} 条有转写/OCR辅助归类`;
for(const a of d.learning_advice||[])$('advice').append(node('li',a));
for(const m of d.materials||[]){const box=node('article',undefined,'material');box.append(node('small',({creator:'创作者原作 / 片段',external:'外部补充资料',agent:'Agent 学习提示'})[m.origin]+' · '+m.status));box.append(node('h3',m.title));box.append(node('p',m.description));const links=node('div',undefined,'links');if(m.local_path){const a=node('a','打开本地文件');a.href=m.local_path;links.append(a)}if(m.url){const a=node('a','原始入口');a.href=m.url;a.target='_blank';a.rel='noopener noreferrer';links.append(a)}for(const tid of m.topic_ids||[]){const a=node('a',d.topics.find(t=>t.id===tid).title);a.href='#'+tid;a.onclick=e=>{e.preventDefault();selectTopic(tid)};links.append(a)}box.append(links);$('material-list').append(box)}
function selectTopic(id){chosen=id;query='';$('search').value='';render();$('content').scrollIntoView({behavior:'smooth',block:'start'});history.replaceState(null,'','#'+id)}
for(const a of document.querySelectorAll('[data-map-topic]'))a.addEventListener('click',e=>{e.preventDefault();selectTopic(a.dataset.mapTopic)});
for(const l of d.limitations||[])$('limits').append(node('p',l));
for(const [i,id] of d.start_path.entries()){const t=d.topics.find(x=>x.id===id);const a=node('a',`${i+1}. ${t.title}`);a.href='#'+id;a.onclick=e=>{e.preventDefault();selectTopic(id)};$('path').append(a);}
const all=node('button','全部知识点');all.onclick=()=>{chosen='';render()};$('nav').append(all);for(const t of d.topics){const b=node('button',t.title);b.dataset.topic=t.id;b.onclick=()=>{chosen=t.id;render();$('content').scrollIntoView({behavior:'smooth',block:'start'})};$('nav').append(b)}
function duration(s){if(s==null)return '时长未知';const whole=Math.round(s);return Math.floor(whole/60)+'分'+whole%60+'秒'}
function card(v){const box=node('article',undefined,'video');const meta=node('div',undefined,'meta');if(v.recommended)meta.append(node('span','先看','badge'));meta.append(document.createTextNode(duration(v.duration_seconds)+' · '+v.basis));box.append(meta);const a=node('a',v.title);if(v.url){a.href=v.url;a.target='_blank';a.rel='noopener noreferrer'}box.append(a);if(v.review){const det=node('details',undefined,'review');det.append(node('summary','内容定位依据'));det.append(node('p',v.review.note));for(const e of v.review.evidence||[])det.append(node('blockquote',(e.label?e.label+' · ':'')+duration(e.start)+'–'+duration(e.end)+' · '+(e.evidence_kind==='screen_ocr'?'画面 OCR':'机器转写')+'：'+e.quote));box.append(det)}return box;}
function render(){$('content').replaceChildren();const found=new Set();for(const b of $('nav').querySelectorAll('button'))b.classList.toggle('active',(b.dataset.topic||'')===chosen);for(const t of d.topics){if(chosen&&chosen!==t.id)continue;const matches=value=>query.split(/\s+/).every(q=>value.toLowerCase().includes(q));const match=matches(t.title+' '+t.question+' '+t.guidance);const entries=t.entries.filter(v=>!query||match||matches(v.title+' '+(v.review?.note||'')));if(!entries.length)continue;entries.forEach(v=>found.add(v.id));const sec=node('section',undefined,'topic');sec.id=t.id;sec.append(node('small',t.group));sec.append(node('h2',t.title));sec.append(node('p',t.question));sec.append(node('p',t.guidance,'guidance'));for(const [label,ids] of [['先修：',t.prerequisites||[]],['接下来可学：',d.topics.filter(x=>(x.prerequisites||[]).includes(t.id)).map(x=>x.id)]]){if(ids.length){const row=node('div',label,'deps');for(const id of ids){const a=node('a',d.topics.find(x=>x.id===id).title);a.href='#'+id;a.onclick=e=>{e.preventDefault();selectTopic(id)};row.append(a)}sec.append(row)}}const focus=node('div',undefined,'study-focus');if(t.watch_for)focus.append(node('p','观看重点：'+t.watch_for));if(t.self_check)focus.append(node('p','看完自查：'+t.self_check));sec.append(focus);const first=entries.filter(v=>v.recommended),rest=entries.filter(v=>!v.recommended);for(const v of first)sec.append(card(v));if(rest.length){const details=node('details');details.open=Boolean(query)||!first.length;details.append(node('summary',`展开 ${rest.length} 条同主题补充视频`));for(const v of rest)details.append(card(v));sec.append(details)}$('content').append(sec)}$('resultCount').textContent=`当前匹配 ${found.size} 条视频`;if(!found.size)$('content').append(node('p','没有匹配结果。可清空关键词，或切换到全部知识点。'));}
$('search').addEventListener('input',e=>{query=e.target.value.trim().toLowerCase();render()});const initial=location.hash.slice(1);if(d.topics.some(t=>t.id===initial))chosen=initial;render();
</script></html>'''
