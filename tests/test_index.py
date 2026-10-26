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
            self.assertIn('href="index.html#start"', (out / "knowledge-map.svg").read_text())

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
