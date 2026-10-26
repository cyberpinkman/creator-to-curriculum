import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from creator_curriculum.core import (ContractError, make_jobs, read_json, validate_corpus,
                                     validate_notes, validate_plan, write_json)
from creator_curriculum.demo import build_demo, demo_corpus
from creator_curriculum.pipeline import initialize, inspect, load_workspace, prepare, synthesize
from creator_curriculum.render import render, timestamp_url


class EvidenceContractTests(unittest.TestCase):
    def test_chunking_preserves_all_text_and_bounds_size(self):
        corpus = demo_corpus()
        corpus["videos"][0]["segments"][0]["text"] *= 100
        jobs = make_jobs(validate_corpus(corpus), 100)
        for video in corpus["videos"]:
            actual = ''.join(s["text"] for j in jobs if j["video"]["id"] == video["id"] for s in j["segments"])
            self.assertEqual(actual, ''.join(s["text"] for s in video["segments"]))
        self.assertTrue(all(sum(len(s["text"]) for s in j["segments"]) <= 100 for j in jobs))
        self.assertEqual(len(jobs), len({j["job_id"] for j in jobs}))

    def test_corpus_invariant_matrix(self):
        mutations = [
            lambda c: c["videos"].append(copy.deepcopy(c["videos"][0])),
            lambda c: c["discovery"].update(expected_count=None),
            lambda c: c["videos"][0].update(segments=[]),
            lambda c: c["videos"][0]["segments"][0].update(end=float("nan")),
            lambda c: c["videos"][0]["segments"][0].update(start=-1),
            lambda c: c["videos"][0]["segments"][0].update(end=10000),
            lambda c: c["videos"][0].update(url="javascript:alert(1)"),
            lambda c: c["videos"][0].update(id="../../elsewhere"),
            lambda c: c["videos"][0].update(source_author="A different creator"),
            lambda c: c["videos"][0].update(duration_seconds=0),
            lambda c: c["videos"][0]["segments"][0].update(evidence_kind="human_verified_video"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                corpus = demo_corpus()
                mutation(corpus)
                with self.assertRaises(ContractError):
                    validate_corpus(corpus)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace"
        self.pack = build_demo(self.root)

    def test_full_learning_pack_and_order(self):
        status = inspect(self.root)[-1]
        self.assertTrue(status["complete_for_declared_scope"])
        self.assertEqual(status["analyzed_video_count"], 4)
        self.assertEqual(len(list((self.pack / "lessons").glob("*.md"))), 3)
        self.assertTrue((self.pack / "courseware.md").exists())
        synthesis = synthesize(self.root)
        plan = read_json(self.root / "plan.json")
        plan["modules"].reverse()
        self.assertEqual(validate_plan(plan, synthesis), ["problem", "interview", "synthesis"])

    def test_exact_evidence_boundary(self):
        job = load_workspace(self.root)[-1][0]
        original = read_json(self.root / "notes" / f'{job["job_id"]}.json')
        mutations = [
            lambda n: n.update(input_hash="old"),
            lambda n: n["claims"][0]["evidence"][0].update(segment_id="invented"),
            lambda n: n["claims"][0]["evidence"][0].update(quote="Something the creator did not say"),
            lambda n: n["claims"][0].update(evidence=[]),
            lambda n: n["resources"][0].update(url="https://example.com/invented.pdf"),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                notes = copy.deepcopy(original)
                mutation(notes)
                with self.assertRaises(ContractError):
                    validate_notes(notes, job)

    def test_evidence_modality_survives_synthesis_and_rendering(self):
        corpus = read_json(self.root / "corpus.json")
        corpus["videos"][0]["segments"][0]["evidence_kind"] = "screen_ocr"
        write_json(self.root / "corpus.json", corpus)
        jobs = prepare(self.root)
        for job in load_workspace(self.root)[-1]:
            path = self.root / "notes" / f'{job["job_id"]}.json'
            note = read_json(path)
            note["input_hash"] = job["input_hash"]
            write_json(path, note)
        synthesis = synthesize(self.root)
        self.assertIn("screen_ocr", synthesis["coverage"]["evidence_basis"])
        evidence = [e for c in synthesis["claims"] for e in c["evidence"]]
        self.assertTrue(any(e.get("evidence_kind") == "screen_ocr" for e in evidence))
        plan = read_json(self.root / "plan.json")
        plan["input_hash"] = synthesis["input_hash"]
        write_json(self.root / "plan.json", plan)
        pack = render(self.root)
        self.assertIn("抽帧画面文字", (pack / "index.md").read_text())
        self.assertNotIn("没有导入画面证据", (pack / "gaps.md").read_text())

    def test_source_changes_invalidate_notes_before_export(self):
        corpus = read_json(self.root / "corpus.json")
        corpus["videos"][0]["segments"][0]["text"] += "修订"
        write_json(self.root / "corpus.json", corpus)
        self.assertTrue(inspect(self.root)[-1]["invalid_jobs"])
        with self.assertRaisesRegex(ContractError, "Invalid or stale"):
            synthesize(self.root, allow_partial=True)
        self.assertTrue(self.pack.exists())  # previous revision remains auditable

    def test_learner_changes_invalidate_plan(self):
        learner = read_json(self.root / "learner.json")
        learner["goal"] = "Teach someone else"
        write_json(self.root / "learner.json", learner)
        with self.assertRaisesRegex(ContractError, "Stale plan"):
            render(self.root)

    def test_missing_jobs_are_visible_and_default_build_is_blocked(self):
        job = load_workspace(self.root)[-1][0]
        (self.root / "notes" / f'{job["job_id"]}.json').unlink()
        status = inspect(self.root)[-1]
        self.assertEqual(status["analyzed_video_count"], 3)
        self.assertFalse(status["complete_for_declared_scope"])
        with self.assertRaisesRegex(ContractError, "Coverage"):
            synthesize(self.root)
        partial = synthesize(self.root, allow_partial=True)
        self.assertEqual(len(partial["coverage"]["pending_jobs"]), 1)

    def test_unknown_account_total_is_not_complete(self):
        corpus = read_json(self.root / "corpus.json")
        corpus["discovery"].update(status="unknown", expected_count=None)
        write_json(self.root / "corpus.json", corpus)
        status = inspect(self.root)[-1]
        self.assertTrue(status["all_inventory_analyzed"])
        self.assertFalse(status["complete_for_declared_scope"])
        with self.assertRaises(ContractError):
            render(self.root)
        synthesis = synthesize(self.root, allow_partial=True)
        plan = read_json(self.root / "plan.json")
        plan["input_hash"] = synthesis["input_hash"]
        write_json(self.root / "plan.json", plan)
        out = render(self.root, allow_partial=True)
        self.assertIn("部分覆盖草稿", (out / "index.md").read_text())

    def test_prerequisite_and_claim_accounting_boundary(self):
        synthesis = synthesize(self.root)
        original = read_json(self.root / "plan.json")
        mutations = [
            lambda p: p["modules"][0].update(prerequisites=["synthesis"]),
            lambda p: p["modules"][0].update(prerequisites=["unknown"]),
            lambda p: p["modules"][0]["lessons"][0].update(claim_refs=["fake/claim"]),
            lambda p: p["modules"][0]["lessons"][0]["claim_refs"].pop(),
            lambda p: p["modules"][0]["lessons"][0]["practice"].update(success_criteria=[]),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(original)
                mutation(plan)
                with self.assertRaises(ContractError):
                    validate_plan(plan, synthesis)

    def test_one_finished_chunk_is_not_a_finished_video(self):
        write_json(self.root / "config.json", {"max_chars": 100})
        status = prepare(self.root)
        self.assertFalse(status["all_inventory_analyzed"])
        self.assertTrue(status["pending_jobs"] or status["invalid_jobs"])

    def test_stale_files_outside_active_manifest_do_not_count(self):
        write_json(self.root / "notes" / "orphan.json", {"invalid": True})
        self.assertTrue(inspect(self.root)[-1]["complete_for_declared_scope"])

    def test_rebuild_preserves_progress_and_is_reproducible(self):
        (self.root / "progress.md").write_text("My own learning evidence", encoding="utf-8")
        self.assertEqual(render(self.root), self.pack)
        self.assertEqual((self.root / "progress.md").read_text(), "My own learning evidence")

    def test_cli_roundtrip_and_error_exit(self):
        result = subprocess.run([sys.executable, "-m", "creator_curriculum", "status", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["analyzed_video_count"], 4)
        result = subprocess.run([sys.executable, "-m", "creator_curriculum", "build", str(self.root / "missing")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stderr))

    def test_timestamp_links_preserve_context(self):
        self.assertEqual(timestamp_url("https://www.youtube.com/watch?v=abc&list=xyz&t=9", 30), "https://www.youtube.com/watch?v=abc&list=xyz&t=30")
        self.assertEqual(timestamp_url("https://www.douyin.com/video/123", 30), "https://www.douyin.com/video/123")


if __name__ == "__main__":
    unittest.main()
