import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from creator_curriculum.adapters import import_video_learning, normalize_playlist, parse_subtitles
from creator_curriculum.core import ContractError, validate_corpus


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_sqlite_import_preserves_missing_items_and_never_writes(self):
        path = self.root / "library.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript('''
                CREATE TABLE account_video_discoveries(id TEXT,platform TEXT,author TEXT,account_url TEXT,status TEXT,expected_count INTEGER,items_json TEXT,created_at TEXT);
                CREATE TABLE videos(id TEXT,title TEXT,source_url TEXT,duration_sec REAL);
                CREATE TABLE transcript_segments(video_id TEXT,segment_index INTEGER,start_sec REAL,end_sec REAL,text TEXT);
            ''')
            items = [{"platformVideoId": "123", "acquiredVideoId": "existing", "url": "https://www.douyin.com/video/123"},
                     {"platformVideoId": "456", "description": "No transcript", "url": "https://www.douyin.com/video/456"}]
            db.execute("INSERT INTO account_video_discoveries VALUES (?,?,?,?,?,?,?,?)", ("discovery", "douyin", "Author", "https://www.douyin.com/user/test", "success", 2, json.dumps(items), "2026-10-25"))
            db.execute("INSERT INTO videos VALUES (?,?,?,?)", ("existing", "Lesson", "https://www.douyin.com/video/123", 20))
            db.execute("INSERT INTO transcript_segments VALUES (?,?,?,?,?)", ("existing", 0, 0, 10, "A concrete statement"))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        corpus = import_video_learning(path, "discovery")
        self.assertEqual(len(corpus["videos"]), 2)
        self.assertEqual([v["status"] for v in corpus["videos"]], ["ready", "missing_transcript"])
        self.assertEqual(corpus["videos"][0]["transcript_source"], "unknown")
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        with sqlite3.connect(path) as db:
            items[0].pop('acquiredVideoId')  # list-only discoveries can reuse an exact-URL library match
            items[1]['author'] = 'Different author'
            db.execute('UPDATE account_video_discoveries SET items_json=? WHERE id=?', (json.dumps(items), 'discovery'))
        mismatched = import_video_learning(path, 'discovery')
        self.assertEqual(mismatched['videos'][0]['status'], 'ready')
        self.assertEqual(mismatched['videos'][1]['status'], 'excluded')
        self.assertEqual(mismatched['videos'][1]['source_author'], 'Different author')
        with self.assertRaises(ContractError):
            import_video_learning(path, "another")

    def test_missing_database_is_not_created(self):
        missing = self.root / "missing.sqlite"
        with self.assertRaises(ContractError):
            import_video_learning(missing, "id")
        self.assertFalse(missing.exists())

    def test_failed_discovery_preserves_authentication_cause(self):
        path = self.root / "failed.sqlite"
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE account_video_discoveries(id TEXT,platform TEXT,author TEXT,account_url TEXT,status TEXT,expected_count INTEGER,items_json TEXT,created_at TEXT,diagnostics_json TEXT)')
            db.execute('INSERT INTO account_video_discoveries VALUES (?,?,?,?,?,?,?,?,?)',
                       ('failed', 'douyin', 'Author', 'https://www.douyin.com/user/test', 'failed', 10, '[]', '2026-10-25', '{"authRequired":true,"profileDir":"/private/profile"}'))
        corpus = import_video_learning(path, 'failed')
        self.assertTrue(any('authRequired=true' in n and 'not proof' in n for n in corpus['discovery']['notes']))
        self.assertNotIn('/private/profile', json.dumps(corpus))

    def test_playlist_requires_independent_count(self):
        data = {"title": "Test", "entries": [{"id": "abc", "title": "One", "duration": 0}, {"id": "abc", "title": "Duplicate"}]}
        corpus = normalize_playlist(data, "youtube", "https://youtube.com/@test/videos")
        self.assertEqual(len(corpus["videos"]), 1)
        self.assertIsNone(corpus['videos'][0]['duration_seconds'])
        self.assertEqual(corpus["discovery"]["status"], "unknown")
        self.assertEqual(normalize_playlist(data, "youtube", "https://youtube.com/@test/videos", expected_count=1)["discovery"]["status"], "complete")
        data["entries"].append(None)
        self.assertEqual(normalize_playlist(data, "youtube", "https://youtube.com/@test/videos", expected_count=1)["discovery"]["status"], "partial")

    def test_interrupted_playlist_cannot_be_complete(self):
        data = {"entries": [{"id": "abc"}]}
        self.assertEqual(normalize_playlist(data, "youtube", "https://youtube.com/@test/videos", expected_count=1, interrupted=True)["discovery"]["status"], "partial")

    def test_srt_and_vtt_are_timestamped(self):
        samples = [("a.srt", "1\r\n00:00:01,000 --> 00:00:03,500\r\n你好\r\n世界\r\n"),
                   ("a.vtt", "WEBVTT\n\n00:01.000 --> 00:03.500 align:start\n<c>Hello</c> &amp; world\n")]
        for name, content in samples:
            with self.subTest(name=name):
                path = self.root / name
                path.write_text(content)
                cues = parse_subtitles(path)
                self.assertEqual(cues[0]["start"], 1)
                self.assertEqual(cues[0]["end"], 3.5)
                self.assertNotIn("<c>", cues[0]["text"])

    def test_plain_text_does_not_invent_timestamps(self):
        path = self.root / "plain.txt"
        path.write_text("A transcript without timing")
        with self.assertRaises(ContractError):
            parse_subtitles(path)


if __name__ == "__main__":
    unittest.main()
