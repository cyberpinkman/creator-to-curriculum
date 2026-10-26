from pathlib import Path
import tempfile
import unittest

from creator_curriculum.core import ContractError
from creator_curriculum.usage import estimate, import_codex_usage, record_usage, usage_report, import_response_usage


class UsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_cache_is_a_subset_and_unknown_is_not_zero(self):
        record_usage(self.root, stage="extraction", provider="test", model="test", source="fixture", input_tokens=100, output_tokens=20, cached_input_tokens=60)
        record_usage(self.root, stage="transcription", provider="test", model="test", source="no usage supplied", basis="unknown")
        groups = usage_report(self.root)["groups"]
        self.assertEqual(groups["extraction:reported"]["total_tokens"], 120)
        self.assertEqual(groups["extraction:reported"]["uncached_input_tokens"], 40)
        self.assertIsNone(groups["transcription:unknown"]["total_tokens"])
        with self.assertRaises(ContractError):
            record_usage(self.root, stage="extraction", provider="test", model="test", source="fixture", input_tokens=100, output_tokens=20, cached_input_tokens=101)

    def test_cumulative_session_snapshots_are_not_double_counted(self):
        path = self.root / "session.jsonl"
        path.write_text('{"type":"event_msg","timestamp":"now","payload":{"type":"token_count","info":{"total_token_usage":{"input_tokens":100,"output_tokens":20,"cached_input_tokens":60}}}}\n')
        import_codex_usage(self.root, path)
        import_codex_usage(self.root, path)
        group = usage_report(self.root)["groups"]["development:reported"]
        self.assertEqual(group["events"], 1)
        self.assertEqual(group["total_tokens"], 120)

    def test_missing_cache_breakdown_stays_unknown(self):
        record_usage(self.root, stage="extraction", provider="test", model="test", source="fixture", input_tokens=100, output_tokens=20)
        self.assertIsNone(usage_report(self.root)["groups"]["extraction:reported"]["cached_input_tokens"])

    def test_more_short_videos_add_prompt_overhead(self):
        short = estimate(videos=60, minutes=60)
        long = estimate(videos=1, minutes=60)
        self.assertGreater(short["low"]["total_tokens"], long["low"]["total_tokens"])
        self.assertEqual(short["assumed_characters"], long["assumed_characters"])

    def test_provider_response_usage_is_independent_of_content_success(self):
        import json
        path = self.root / "response.json"
        path.write_text(json.dumps({"provider": "test", "model": "test", "ok": False,
                                   "request_id": "request-1", "usage": {"prompt_tokens": 100,
                                   "completion_tokens": 20, "prompt_tokens_details": {"cached_tokens": 60},
                                   "completion_tokens_details": {"reasoning_tokens": 5}}}))
        first = import_response_usage(self.root, path, stage="extraction")
        self.assertEqual(first["output_tokens"], 20)  # reasoning is already included
        self.assertEqual(first["cached_input_tokens"], 60)
        with self.assertRaises(ContractError):
            import_response_usage(self.root, path, stage="extraction")
        path.write_text(json.dumps({"provider": "test", "model": "test", "usage": None}))
        event = import_response_usage(self.root, path, stage="extraction", event_id="unknown")
        self.assertEqual(event["basis"], "unknown")
        self.assertIsNone(event["input_tokens"])


if __name__ == "__main__":
    unittest.main()
