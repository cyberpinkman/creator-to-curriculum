import copy
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from creator_curriculum.core import ContractError, digest, validate_index_plan
from creator_curriculum.demo import demo_corpus
from creator_curriculum.index import build_index


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.corpus = demo_corpus()
        self.video = self.corpus["videos"][0]
        self.plan = {"schema_version": 1, "source_hash": digest(self.corpus),
                     "title": "学习索引", "goal": "找到原视频", "overview": "导航",
                     "topics": [{"id": "start", "title": "起点", "group": "基础",
                                 "question": "先看什么？", "guidance": "选一条原视频。",
                                 "video_ids": [self.video["id"]], "recommended_ids": [self.video["id"]]}],
                     "start_path": ["start"], "reviews": {}, "limitations": ["标题归类不是内容核验。"]}

    def related_plan(self):
        plan = copy.deepcopy(self.plan)
        plan['topics'].append({**copy.deepcopy(plan['topics'][0]), 'id': 'next',
                               'title': '下一步', 'prerequisites': ['start']})
        plan['start_path'] = ['start', 'next']
        return plan

    def test_text_material_projection_preserves_bytes_and_provenance(self):
        content = '中文资料\n<script>alert("not executable")</script>\n'
        for filename, raw, preview in [
                ('notes.md', ('\ufeff' + content).encode('utf-8'), content),
                ('rows.csv', '姓名,编号\n小明,1\n'.encode('utf-8'), '姓名,编号\n小明,1\n'),
                ('large.txt', b'x' * (256 * 1024 + 1), None),
                ('legacy.txt', '中文'.encode('gbk'), None)]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                path = root / 'materials' / filename
                path.parent.mkdir()
                path.write_bytes(raw)
                resource = dict(title='原始资料', description='保持原来源状态', origin='agent',
                                status='尚待人工核对', availability='unknown',
                                local_path=f'materials/{filename}', topic_ids=['start'],
                                preview_text='不能信任计划里预填的预览')
                plan = {**self.plan, 'materials': [resource]}
                before = copy.deepcopy(plan)
                build_index(self.corpus, plan, root)
                material = json.loads((root / 'index.json').read_text())['materials'][0]
                self.assertEqual(material.get('preview_text'), preview)
                self.assertEqual(bool(material.get('preview_unavailable')), preview is None)
                self.assertEqual(path.read_bytes(), raw)
                self.assertEqual(plan, before)
                for field in ('status', 'origin', 'availability', 'local_path'):
                    self.assertEqual(material[field], resource[field])
                self.assertNotIn('<script>alert("not executable")', (root / 'index.html').read_text())

    def test_paths_require_unique_ordered_or_explicitly_exempt_prerequisites(self):
        plan = self.related_plan()
        validate_index_plan(plan, self.corpus)
        for route in (['start', 'start'], ['next', 'start'], ['next']):
            with self.subTest(route=route):
                invalid = copy.deepcopy(plan)
                invalid['start_path'] = route
                with self.assertRaises(ContractError):
                    validate_index_plan(invalid, self.corpus)
        for status in ('assumed_known', 'skipped'):
            with self.subTest(status=status):
                exempt = copy.deepcopy(plan)
                exempt['start_path'] = ['next']
                exempt['start_path_exemptions'] = [dict(topic_id='start', status=status,
                                                      reason='本路径显式声明的基础假设或缺口。')]
                validate_index_plan(exempt, self.corpus)
        for exemption in (dict(topic_id='missing', status='skipped', reason='说明'),
                          dict(topic_id='start', status='mastered', reason='说明'),
                          dict(topic_id='start', status='skipped', reason='')):
            with self.subTest(exemption=exemption):
                invalid = copy.deepcopy(plan)
                invalid['start_path_exemptions'] = [exemption]
                with self.assertRaises(ContractError):
                    validate_index_plan(invalid, self.corpus)

    def test_additional_paths_share_the_same_contract(self):
        plan = self.related_plan()
        valid = dict(id='review', title='复习路径', topic_ids=['next'],
                     prerequisite_exemptions=[dict(topic_id='start', status='assumed_known', reason='已学基础后复习。')])
        plan['learning_paths'] = [valid]
        validate_index_plan(plan, self.corpus)
        for changes in (dict(id='start'), dict(topic_ids=['next', 'next']),
                        dict(prerequisite_exemptions=[]), dict(topic_ids=['unknown'])):
            with self.subTest(changes=changes):
                invalid = copy.deepcopy(plan)
                invalid['learning_paths'][0].update(changes)
                with self.assertRaises(ContractError):
                    validate_index_plan(invalid, self.corpus)
        plan['learning_paths'].append(copy.deepcopy(valid))
        with self.assertRaises(ContractError):
            validate_index_plan(plan, self.corpus)

    def test_topic_video_evidence_must_reference_reviewed_segments_of_its_video(self):
        vid = self.video['id']
        self.plan['reviews'][vid] = dict(note='整条视频的证据汇集。', evidence=[
            dict(segment_id=segment['id'], quote=segment['text'], label='原引文')
            for segment in self.video['segments'][:2]])
        self.plan['topics'][0]['video_evidence'] = {vid: ['s1']}
        validate_index_plan(self.plan, self.corpus)
        for links in ({vid: ['s3']}, {vid: ['missing']}, {vid: ['s1', 's1']},
                      {'v_synthesis': ['s1']}, {vid: []}):
            with self.subTest(links=links):
                invalid = copy.deepcopy(self.plan)
                invalid['topics'][0]['video_evidence'] = links
                with self.assertRaises(ContractError):
                    validate_index_plan(invalid, self.corpus)

    def test_tasks_and_package_identity_are_validated_at_shared_boundary(self):
        task = dict(objective='描述一个小目标', primary_video_id=self.video['id'],
                    stop_when='留下一个问题后停下。', practice_minutes=5)
        self.plan['package_id'] = 'stable-demo'
        self.plan['topics'][0]['task'] = task
        validate_index_plan(self.plan, self.corpus)
        for changes in (dict(primary_video_id='v_synthesis'), dict(practice_minutes=0),
                        dict(practice_minutes=True), dict(objective=''), dict(stop_when='')):
            with self.subTest(changes=changes):
                invalid = copy.deepcopy(self.plan)
                invalid['topics'][0]['task'].update(changes)
                with self.assertRaises(ContractError):
                    validate_index_plan(invalid, self.corpus)
        self.plan['package_id'] = '../unsafe'
        with self.assertRaises(ContractError):
            validate_index_plan(self.plan, self.corpus)

    def test_build_keeps_topic_evidence_separate_from_full_review_and_paths_consistent(self):
        plan = self.related_plan()
        vid = self.video['id']
        plan['reviews'][vid] = dict(note='完整视频的说明', evidence=[
            dict(segment_id=segment['id'], quote=segment['text'], label='定位')
            for segment in self.video['segments'][:2]])
        plan['topics'][0]['video_evidence'] = {vid: ['s1']}
        plan['topics'][1]['video_evidence'] = {vid: ['s2']}
        with tempfile.TemporaryDirectory() as temporary:
            out = build_index(self.corpus, plan, temporary)
            payload = json.loads((out / 'index.json').read_text())
            first, second = [topic['entries'][0] for topic in payload['topics']]
            self.assertEqual([e['segment_id'] for e in first['topic_evidence']], ['s1'])
            self.assertEqual([e['segment_id'] for e in second['topic_evidence']], ['s2'])
            self.assertEqual(len(first['review']['evidence']), 2)
            self.assertEqual(first['topic_evidence'][0]['quote'], self.video['segments'][0]['text'])
            self.assertEqual(first['topic_evidence'][0]['transcript_source'], 'synthetic')
            self.assertEqual(first['topic_evidence'][0]['start'], 0)
            self.assertEqual(payload['learning_paths'][0]['topic_ids'], plan['start_path'])
            self.assertEqual(payload['topics'][0]['task']['primary_video_id'], vid)
            self.assertIsNone(payload['topics'][0]['task']['practice_minutes'])
            markdown = (out / 'README.md').read_text()
            self.assertIn('[下一步](#next)', markdown)
            self.assertIn('路径已结束', markdown)
            self.assertIn('完整视频证据', markdown)
            self.assertIn('不是完整教学区间', markdown)
            del plan['topics'][0]['video_evidence']
            build_index(self.corpus, plan, temporary)
            unbound = json.loads((out / 'index.json').read_text())['topics'][0]['entries'][0]
            self.assertEqual(unbound['topic_evidence'], [])
            self.assertEqual(len(unbound['review']['evidence']), 2)

    def test_package_id_is_independent_of_generated_content_and_order(self):
        plan = self.related_plan()
        with tempfile.TemporaryDirectory() as temporary:
            out = build_index(self.corpus, plan, temporary)
            original_payload = json.loads((out / 'index.json').read_text())
            original = original_payload['package_id']
            original_signature = original_payload['topics'][0]['source_signature']
            plan['title'] = '改名和重新生成'
            plan['topics'].reverse()
            self.corpus['discovery']['observed_at'] = '2026-10-27T00:00:00Z'
            plan['source_hash'] = digest(self.corpus)
            build_index(self.corpus, plan, temporary)
            regenerated = json.loads((out / 'index.json').read_text())
            self.assertEqual(regenerated['package_id'], original)
            self.assertEqual(regenerated['topics'][1]['source_signature'], original_signature)
            self.corpus['videos'][0]['segments'][0]['text'] += '新来源文字。'
            plan['source_hash'] = digest(self.corpus)
            build_index(self.corpus, plan, temporary)
            changed_source = json.loads((out / 'index.json').read_text())
            self.assertEqual(changed_source['package_id'], original)
            self.assertNotEqual(changed_source['topics'][1]['source_signature'], original_signature)
            plan['package_id'] = 'my-learning-pack'
            build_index(self.corpus, plan, temporary)
            self.assertEqual(json.loads((out / 'index.json').read_text())['package_id'], 'my-learning-pack')
            del plan['package_id']
            self.corpus['creator']['name'] = '另一位创作者'
            plan['source_hash'] = digest(self.corpus)
            build_index(self.corpus, plan, temporary)
            self.assertNotEqual(json.loads((out / 'index.json').read_text())['package_id'], original)

    def test_source_signature_tracks_title_and_rendered_original_evidence(self):
        # Original source text may be a title, a selected quote, or a quote in
        # the expandable full review. A label/note is interpretation instead.
        for mode in ('title_only', 'topic_quote', 'full_review_quote'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as temporary:
                corpus, plan = copy.deepcopy(self.corpus), copy.deepcopy(self.plan)
                video = corpus['videos'][0]
                vid = video['id']
                if mode == 'title_only':
                    video.update(status='missing_transcript', segments=[], reason='Title index only')
                else:
                    plan['reviews'][vid] = dict(note='Agent 的解释。', evidence=[
                        dict(segment_id='s1', quote='这种问题容易收获礼貌的肯定。'),
                        dict(segment_id='s2', quote=video['segments'][1]['text'])])
                    plan['topics'][0]['video_evidence'] = {vid: ['s1' if mode == 'topic_quote' else 's2']}
                plan['source_hash'] = digest(corpus)
                out = build_index(corpus, plan, temporary)
                before = json.loads((out / 'index.json').read_text())['topics'][0]['source_signature']
                if mode == 'title_only':
                    video['title'] = '更正后的原视频标题'
                else:
                    plan['reviews'][vid]['evidence'][0]['quote'] = '请对方讲最近一次遇到问题的具体经历。'
                plan['source_hash'] = digest(corpus)
                build_index(corpus, plan, temporary)
                after = json.loads((out / 'index.json').read_text())['topics'][0]['source_signature']
                self.assertNotEqual(before, after)

    def test_source_signature_ignores_order_and_agent_interpretation(self):
        vid, other = self.video['id'], self.corpus['videos'][1]['id']
        self.plan['topics'][0]['video_ids'].append(other)
        self.plan['reviews'][vid] = dict(note='Agent 的解释。', evidence=[
            dict(segment_id='s1', quote='这种问题容易收获礼貌的肯定。', label='解释标签'),
            dict(segment_id='s1', quote='请对方讲最近一次遇到问题的具体经历。'),
            dict(segment_id='s2', quote=self.video['segments'][1]['text'])])
        self.plan['topics'][0]['video_evidence'] = {vid: ['s1', 's2']}
        with tempfile.TemporaryDirectory() as temporary:
            out = build_index(self.corpus, self.plan, temporary)
            before = json.loads((out / 'index.json').read_text())['topics'][0]['source_signature']
            self.plan['topics'][0]['video_ids'].reverse()
            self.plan['topics'][0]['video_evidence'][vid].reverse()
            self.plan['reviews'][vid]['evidence'][0]['label'] = '新的解释标签'
            self.plan['reviews'][vid]['evidence'].reverse()
            self.plan['reviews'][vid]['note'] = '新的 Agent 解释，不是原作变化。'
            self.plan['topics'][0]['guidance'] = '新的观看建议。'
            self.corpus['videos'].reverse()
            self.plan['source_hash'] = digest(self.corpus)
            build_index(self.corpus, self.plan, temporary)
            after = json.loads((out / 'index.json').read_text())['topics'][0]['source_signature']
            self.assertEqual(before, after)

    def test_title_index_needs_no_transcript_but_cannot_claim_content_review(self):
        self.video.update(status="missing_transcript", segments=[], reason="Index only")
        self.plan["source_hash"] = digest(self.corpus)
        validate_index_plan(self.plan, self.corpus)
        mutations = [lambda p: p.update(source_hash="stale"),
                     lambda p: p["topics"][0]["video_ids"].append("invented"),
                     lambda p: p["topics"][0]["recommended_ids"].append("invented"),
                     lambda p: p["reviews"].update({self.video["id"]: {"note": "reviewed", "evidence": []}})]
        for change in mutations:
            with self.subTest(change=change):
                plan = copy.deepcopy(self.plan); change(plan)
                with self.assertRaises(ContractError):
                    validate_index_plan(plan, self.corpus)

    def test_navigation_and_material_boundaries(self):
        mutations = [lambda p: p['topics'][0].update(prerequisites=['start']),
                     lambda p: p['topics'][0].update(prerequisites=['missing'])]
        for path in ('../outside.pdf', '/tmp/outside.pdf', 'javascript:alert(1)', 'a\\b.pdf'):
            mutations.append(lambda p, path=path: p.update(materials=[dict(title='x', description='x', status='indexed', origin='external', url=None, local_path=path)]))
        for change in mutations:
            with self.subTest(change=change):
                plan = copy.deepcopy(self.plan); change(plan)
                with self.assertRaises(ContractError): validate_index_plan(plan, self.corpus)
        with tempfile.TemporaryDirectory() as temporary:
            plan = copy.deepcopy(self.plan)
            plan['materials'] = [dict(title='x', description='x', status='downloaded', origin='agent', url=None, local_path='missing.md')]
            with self.assertRaises(ContractError): build_index(self.corpus, plan, temporary)

    def test_index_exports_original_links_and_non_executable_source_text(self):
        self.video["title"] = "</script><script>alert(1)</script>"
        self.video["url"] = "https://www.youtube.com/watch?v=example"
        self.plan["source_hash"] = digest(self.corpus)
        with tempfile.TemporaryDirectory() as temporary:
            out = build_index(self.corpus, self.plan, temporary)
            page = (out / "index.html").read_text()
            self.assertNotIn("</script><script>alert(1)</script>", page)
            self.assertIn("\\u003c/script", page)
            self.assertIn(self.video["url"], (out / "video-index.csv").read_text())
            self.assertIn("标题归类", (out / "README.md").read_text())
            self.assertIn('href="index.html#topic/start"', (out / "knowledge-map.svg").read_text())

    def test_offline_reader_embeds_assets_and_preserves_literal_source_markers(self):
        class ReaderParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.in_data = False
                self.data = []
                self.remote_assets = []
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'script':
                    self.in_data = attrs.get('id') == 'data'
                    if attrs.get('src'): self.remote_assets.append(attrs['src'])
                if tag == 'link' and attrs.get('rel') == 'stylesheet':
                    self.remote_assets.append(attrs.get('href'))
            def handle_endtag(self, tag):
                if tag == 'script': self.in_data = False
            def handle_data(self, value):
                if self.in_data: self.data.append(value)

        self.plan['title'] = 'Literal __DATA__ <&> __STYLE__'
        self.plan['overview'] = '__SCRIPT__ is source text, not a template directive.'
        with tempfile.TemporaryDirectory() as temporary:
            out = build_index(self.corpus, self.plan, temporary)
            parser = ReaderParser()
            parser.feed((out / 'index.html').read_text())
            self.assertFalse(parser.remote_assets, 'The offline reader must not need remote scripts or styles')
            self.assertEqual(json.loads(''.join(parser.data)), json.loads((out / 'index.json').read_text()))


if __name__ == "__main__":
    unittest.main()
