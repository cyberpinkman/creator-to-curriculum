"""Explicit source adapters. No credentials or original media are copied into the repo."""

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sqlite3
import subprocess

from .core import ContractError, digest, require, url, validate_corpus


def now():
    return datetime.now(timezone.utc).isoformat()


def known_duration(value):
    return value if type(value) in (int, float) and value > 0 else None


def import_video_learning(db_path, discovery_id):
    path = Path(db_path).expanduser().resolve()
    require(path.is_file(), f"video-learning database does not exist: {path}")
    # URI mode=ro prevents creating a different empty database or mutating the library.
    try:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")  # one consistent snapshot across discovery and transcript reads
            row = db.execute("SELECT * FROM account_video_discoveries WHERE id = ?", (discovery_id,)).fetchone()
            require(row is not None, f"Unknown discovery_id: {discovery_id}")
            require(row["platform"] in {"douyin", "youtube", "bilibili", "local"}, "Unsupported source platform")
            items = json.loads(row["items_json"])
            require(isinstance(items, list), "Invalid discovery items_json")
            videos = []
            for item in items:
                acquired = item.get("acquiredVideoId")
                source = db.execute("SELECT * FROM videos WHERE id = ?", (acquired,)).fetchone() if acquired else None
                if source is None and item.get("url"):
                    matches = db.execute("SELECT * FROM videos WHERE source_url = ?", (item["url"],)).fetchall()
                    require(len(matches) <= 1, "Ambiguous library records for a source URL; provide an explicit acquiredVideoId")
                    source = matches[0] if matches else None
                    acquired = source["id"] if source else acquired
                segments = db.execute(
                    "SELECT start_sec,end_sec,text FROM transcript_segments WHERE video_id = ? ORDER BY segment_index",
                    (acquired,)).fetchall() if source else []
                normalized = [{"id": f"s{i:05d}", "start": s["start_sec"], "end": s["end_sec"], "text": s["text"]}
                              for i, s in enumerate(segments, 1) if s["text"].strip()]
                item_id = item.get("platformVideoId") or digest(item.get("url"))[:16]
                source_author = item.get("author") or (source["author"] if source and "author" in source.keys() else None)
                author_mismatch = bool(source_author and source_author != (row["author"] or "Unknown creator"))
                videos.append({"id": f"vl_{item_id}", "source_library_id": acquired,
                               "source_author": source_author,
                               "title": (source["title"] if source else item.get("description")) or str(item_id),
                               "url": item.get("url") or (source["source_url"] if source else None),
                               "duration_seconds": known_duration(source["duration_sec"] if source else item.get("durationSec")),
                               "status": "excluded" if author_mismatch else ("ready" if normalized else "missing_transcript"),
                               "reason": ("Source author label differs from target; retained for identity review" if author_mismatch
                                          else ("" if normalized else "No timestamped transcript in the selected library snapshot")),
                               "transcript_source": "unknown", "segments": [] if author_mismatch else normalized})
            corpus = {"schema_version": 1,
                      "creator": {"name": row["author"] or "Unknown creator", "platform": row["platform"], "url": row["account_url"]},
                      "discovery": {"status": {"success": "complete", "partial": "partial", "failed": "failed"}.get(row["status"], "unknown"),
                                    "scope": "Works returned by the selected video-learning account discovery snapshot",
                                    "expected_count": row["expected_count"], "observed_at": row["created_at"],
                                    "notes": [f"Imported discovery {discovery_id}; source database opened read-only.",
                                              "Transcript provenance is unknown in this schema; it is not human-verified.",
                                              "No visual evidence imported; slides, demos and on-screen formulas remain unchecked."]},
                      "videos": videos}
            if "diagnostics_json" in row.keys():
                diagnostics = json.loads(row["diagnostics_json"])
                if isinstance(diagnostics, dict) and (diagnostics.get("authRequired") is True or diagnostics.get("authSuspected") is True):
                    label = "authRequired=true" if diagnostics.get("authRequired") is True else "authSuspected=true"
                    corpus["discovery"]["notes"].append(
                        f"Source adapter inferred an authentication issue ({label}); this is not proof that public access requires login. Check the selected browser profile and upstream diagnostics.")
                if isinstance(diagnostics, dict) and diagnostics.get("paginationBudgetExhausted") is True:
                    corpus["discovery"]["notes"].append("Source pagination budget was exhausted while more pages remained; inventory is incomplete.")
            # A newer source schema or discrepancy must not inherit an older success label.
            if corpus["discovery"]["status"] == "complete" and row["expected_count"] != len(videos):
                corpus["discovery"]["status"] = "partial"
            return validate_corpus(corpus)
    except (sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ContractError(f"Incompatible video-learning snapshot: {exc}") from exc


def normalize_playlist(data, platform, account_url, *, expected_count=None, interrupted=False):
    require(isinstance(data, dict), "yt-dlp result must be an object")
    entries = data.get("entries")
    require(isinstance(entries, list), "Expected a channel or playlist with entries, not an individual video")
    videos, seen, unresolved = [], set(), 0
    for item in entries:
        if not isinstance(item, dict) or item.get("_type") == "playlist" or not item.get("id"):
            unresolved += 1
            continue
        item_id = str(item["id"])
        if item_id in seen:
            continue
        seen.add(item_id)
        link = item.get("webpage_url") or item.get("url")
        if not isinstance(link, str) or not link.startswith(("https://", "http://")):
            # YouTube flat entries use their video id. Bilibili entries require a real URL.
            link = f"https://www.youtube.com/watch?v={item_id}" if platform == "youtube" else None
        videos.append({"id": f"v_{digest(item_id)[:24]}", "platform_video_id": item_id,
                       "title": item.get("title") or item_id, "url": link,
                       "duration_seconds": known_duration(item.get("duration")), "status": "missing_transcript",
                       "reason": "Inventory only; import timestamped subtitles or an ASR transcript",
                       "transcript_source": "unknown", "segments": []})
    status = "unknown"
    if interrupted or unresolved or (expected_count is not None and expected_count != len(videos)):
        status = "partial"
    elif expected_count is not None and expected_count == len(videos):
        status = "complete"
    return validate_corpus({"schema_version": 1,
                           "creator": {"name": data.get("channel") or data.get("uploader") or data.get("title") or "Unknown creator",
                                       "platform": platform, "url": account_url},
                           "discovery": {"status": status, "expected_count": expected_count,
                                         "scope": "The exact channel tab or playlist URL provided; other tabs and private works are outside this snapshot",
                                         "observed_at": now(), "notes": [
                                             f"yt-dlp flat inventory; unresolved entries: {unresolved}; nonzero exit: {interrupted}.",
                                             "The returned entry count does not independently prove account completeness."]},
                           "videos": videos})


def discover(account_url, platform, expected_count=None, executable="yt-dlp"):
    url(account_url, "account URL")
    require(platform in {"youtube", "bilibili"}, "Use video-learning MCP for Douyin account discovery")
    try:
        result = subprocess.run([executable, "--ignore-config", "--flat-playlist", "--dump-single-json",
                                 "--skip-download", "--ignore-errors", "--", account_url],
                                capture_output=True, text=True, timeout=300, check=False)
    except FileNotFoundError as exc:
        raise ContractError("yt-dlp is not installed; install it separately or import a corpus") from exc
    except subprocess.TimeoutExpired as exc:
        raise ContractError("Discovery timed out; no inventory saved. Try a specific channel tab or use an exported inventory") from exc
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        # Do not echo tool stderr: it can include URLs with credentials or signed media links.
        raise ContractError(f"yt-dlp did not return an inventory (exit {result.returncode}); check access with yt-dlp locally") from exc
    return normalize_playlist(data, platform, account_url, expected_count=expected_count, interrupted=result.returncode != 0)


def parse_subtitles(path):
    """SRT/WebVTT cue parser. JSON is the canonical alternative for external ASR."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        require(isinstance(value, list), "Transcript JSON must be an array of {id,start,end,text}")
        return value
    timing = re.compile(r"(?m)^((?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3})\s+-->\s+((?:\d{2,}:)?\d{2}:\d{2}[.,]\d{3})[^\n]*\n")

    def seconds(value):
        parts = [float(p) for p in value.replace(",", ".").split(":")]
        return sum(n * 60 ** i for i, n in enumerate(reversed(parts)))

    segments = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        match = timing.search(block.replace("\r\n", "\n"))
        if not match:
            continue
        normalized = block.replace("\r\n", "\n")
        body = html.unescape(re.sub(r"<[^>]*>", "", normalized[match.end():])).strip()
        if body:
            segments.append({"id": f"s{len(segments) + 1:05d}", "start": seconds(match[1]), "end": seconds(match[2]), "text": body})
    require(segments, "No timestamped subtitle cues found")
    return segments
