"""Shared evidence contracts. All adapters and exports pass through this boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def obj(value, where):
    require(isinstance(value, dict), f"{where}: expected an object")
    return value


def sequence(value, where, *, nonempty=False):
    require(isinstance(value, list), f"{where}: expected an array")
    require(not nonempty or bool(value), f"{where}: must not be empty")
    return value


def string(value, where):
    require(isinstance(value, str) and bool(value.strip()), f"{where}: expected nonempty text")
    return value


def identifier(value, where):
    string(value, where)
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{1,120}", value)), f"{where}: use letters, digits, _ or -")
    return value


def number(value, where):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            f"{where}: expected finite nonnegative number")
    return value


def url(value, where, *, optional=False):
    if optional and value is None:
        return value
    string(value, where)
    parsed = urlsplit(value)
    require(parsed.scheme in {"https", "http"} and bool(parsed.hostname)
            and not parsed.username and not parsed.password
            and not any(c.isspace() for c in value), f"{where}: expected public HTTP(S) URL")
    return value


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ContractError(f"Cannot read JSON: {path}: {exc}") from exc


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_corpus(corpus):
    obj(corpus, "corpus")
    require(corpus.get("schema_version") == 1, "corpus.schema_version must be 1")
    creator = obj(corpus.get("creator"), "creator")
    string(creator.get("name"), "creator.name")
    require(creator.get("platform") in {"douyin", "bilibili", "youtube", "local"}, "Unsupported platform")
    url(creator.get("url"), "creator.url", optional=True)
    discovery = obj(corpus.get("discovery"), "discovery")
    require(discovery.get("status") in {"complete", "partial", "unknown", "failed"}, "Invalid discovery status")
    string(discovery.get("scope"), "discovery.scope")
    string(discovery.get("observed_at"), "discovery.observed_at")
    for note in sequence(discovery.get("notes"), "discovery.notes"):
        string(note, "discovery note")
    expected = discovery.get("expected_count")
    require(expected is None or (type(expected) is int and expected >= 0), "Invalid expected_count")
    videos = sequence(corpus.get("videos"), "videos")
    ids = set()
    for video in videos:
        obj(video, "video")
        vid = identifier(video.get("id"), "video.id")
        require(vid not in ids, f"Duplicate video: {vid}")
        ids.add(vid)
        string(video.get("title"), f"{vid}.title")
        url(video.get("url"), f"{vid}.url", optional=True)
        duration = video.get("duration_seconds")
        if duration is not None:
            number(duration, f"{vid}.duration_seconds")
            require(duration > 0, f"{vid}: known video duration must be positive; use null for unknown")
        require(video.get("status") in {"ready", "missing_transcript", "failed", "excluded"}, f"{vid}: invalid status")
        if video.get("source_author") is not None:
            string(video["source_author"], f"{vid}.source_author")
            require(video["source_author"] == creator["name"] or video["status"] == "excluded",
                    f"{vid}: source author label differs from the target; keep excluded pending identity review")
        require(video.get("transcript_source") in {
            "machine_transcript", "platform_subtitles", "human_transcript", "unknown", "synthetic"
        }, f"{vid}: invalid transcript_source")
        segments = sequence(video.get("segments"), f"{vid}.segments")
        require((video["status"] == "ready") == bool(segments), f"{vid}: only ready videos may have segments; ready requires evidence")
        if video["status"] != "ready":
            string(video.get("reason"), f"{vid}.reason")
        segment_ids = set()
        previous_start = -1
        for segment in segments:
            obj(segment, f"{vid}.segment")
            sid = identifier(segment.get("id"), f"{vid}.segment.id")
            require(sid not in segment_ids, f"{vid}: duplicate segment {sid}")
            segment_ids.add(sid)
            start = number(segment.get("start"), f"{vid}/{sid}.start")
            end = number(segment.get("end"), f"{vid}/{sid}.end")
            require(start < end and start >= previous_start, f"{vid}/{sid}: invalid timestamp order")
            require(duration is None or end <= duration + 1, f"{vid}/{sid}: exceeds duration")
            previous_start = start
            string(segment.get("text"), f"{vid}/{sid}.text")
    if discovery["status"] == "complete":
        require(expected is not None and expected == len(videos), "Complete discovery requires an independently declared count equal to the inventory")
    return corpus


def validate_learner(learner):
    obj(learner, "learner")
    for key in ("goal", "level", "language"):
        string(learner.get(key), f"learner.{key}")
    require(type(learner.get("minutes_per_session")) is int and learner["minutes_per_session"] > 0,
            "learner.minutes_per_session must be a positive integer")
    return learner


def make_jobs(corpus, max_chars=12000):
    require(type(max_chars) is int and max_chars >= 100, "max_chars must be an integer >= 100")
    jobs = []
    for video in corpus["videos"]:
        if video["status"] != "ready":
            continue
        parts = []
        for segment in video["segments"]:
            for offset in range(0, len(segment["text"]), max_chars):
                parts.append({**segment, "id": f'{segment["id"]}_p{offset // max_chars + 1}',
                              "source_segment_id": segment["id"],
                              "text": segment["text"][offset:offset + max_chars]})
        chunks, current, size = [], [], 0
        for part in parts:
            if current and size + len(part["text"]) > max_chars:
                chunks.append(current)
                current, size = [], 0
            current.append(part)
            size += len(part["text"])
        if current:
            chunks.append(current)
        for index, chunk in enumerate(chunks, 1):
            job = {"schema_version": 1, "job_id": f'v{digest(video["id"])[:16]}_{index:04d}',
                   "video": {k: video[k] for k in ("id", "title", "url", "transcript_source")},
                   "video_hash": digest(video), "chunk": index, "total_chunks": len(chunks),
                   "segments": chunk}
            job["input_hash"] = digest(job)
            jobs.append(job)
    return jobs


def validate_evidence(evidence, job, where):
    segments = {segment["id"]: segment for segment in job["segments"]}
    for item in sequence(evidence, f"{where}.evidence", nonempty=True):
        obj(item, "evidence")
        segment = segments.get(item.get("segment_id"))
        require(segment is not None, f"{where}: evidence references an unknown segment")
        quote = string(item.get("quote"), f"{where}.quote")
        require(quote in segment["text"], f"{where}: quote is not verbatim in the referenced segment")


def validate_notes(notes, job):
    obj(notes, "notes")
    require(notes.get("schema_version") == 1, "notes.schema_version must be 1")
    require(notes.get("job_id") == job["job_id"], "Notes refer to another job")
    require(notes.get("input_hash") == job["input_hash"], "Stale notes: source evidence changed; re-extract this job")
    require(notes.get("disposition") in {"knowledge", "non_instructional"}, "Invalid notes disposition")
    string(notes.get("reason"), "notes.reason")
    claims = sequence(notes.get("claims"), "notes.claims")
    require((notes["disposition"] == "knowledge") == bool(claims), "Knowledge requires claims; non_instructional must have no claims")
    ids = set()
    for claim in claims:
        obj(claim, "claim")
        cid = identifier(claim.get("id"), "claim.id")
        require(cid not in ids, f"Duplicate claim: {cid}")
        ids.add(cid)
        for field in ("title", "explanation", "topic"):
            string(claim.get(field), f"claim.{field}")
        require(claim.get("kind") in {"concept", "method", "example", "caveat"}, "Invalid claim kind")
        validate_evidence(claim.get("evidence"), job, cid)
        for step in sequence(claim.get("steps", []), "claim.steps"):
            string(step, "step")
        if claim["kind"] == "method":
            require(bool(claim.get("steps")), "A method requires concrete steps")
    for resource in sequence(notes.get("resources"), "notes.resources"):
        obj(resource, "resource")
        string(resource.get("title"), "resource.title")
        validate_evidence(resource.get("evidence"), job, "resource")
        link = url(resource.get("url"), "resource.url", optional=True)
        # A known title is useful even without a verified link. Never guess a URL.
        if link is not None:
            require(any(link in item["quote"] for item in resource["evidence"]),
                    "Creator resource URL must occur in cited evidence; use null if only the title is known")
    for issue in sequence(notes.get("uncertainties"), "notes.uncertainties"):
        string(issue, "uncertainty")
    return notes


def validate_plan(plan, synthesis):
    obj(plan, "plan")
    require(plan.get("schema_version") == 1, "plan.schema_version must be 1")
    require(plan.get("input_hash") == synthesis["input_hash"], "Stale plan: evidence or learner profile changed; regenerate synthesis and plan")
    for field in ("title", "overview"):
        string(plan.get(field), f"plan.{field}")
    available = {claim["ref"] for claim in synthesis["claims"]}
    used, ids = set(), set()
    modules = sequence(plan.get("modules"), "plan.modules", nonempty=True)
    for module in modules:
        obj(module, "module")
        mid = identifier(module.get("id"), "module.id")
        require(mid not in ids, f"Duplicate module: {mid}")
        ids.add(mid)
        string(module.get("title"), "module.title")
        for objective in sequence(module.get("objectives"), "module.objectives", nonempty=True):
            string(objective, "objective")
        for lesson in sequence(module.get("lessons"), "module.lessons", nonempty=True):
            obj(lesson, "lesson")
            for field in ("title", "explanation"):
                string(lesson.get(field), f"lesson.{field}")
            refs = sequence(lesson.get("claim_refs"), "lesson.claim_refs", nonempty=True)
            for ref in refs:
                string(ref, "claim_ref")
                require(ref in available, f"Unknown claim reference: {ref}")
            used.update(refs)
            practice = obj(lesson.get("practice"), "practice")
            string(practice.get("task"), "practice.task")
            for criterion in sequence(practice.get("success_criteria"), "practice.success_criteria", nonempty=True):
                string(criterion, "success criterion")
            require(type(lesson.get("estimated_minutes")) is int and lesson["estimated_minutes"] > 0,
                    "lesson.estimated_minutes must be a positive integer")
    # Validate the prerequisite graph at its owning boundary, independent of export order.
    graph = {}
    for module in modules:
        deps = sequence(module.get("prerequisites"), "module.prerequisites")
        for dep in deps:
            string(dep, "prerequisite")
            require(dep in ids, f"Unknown prerequisite: {dep}")
        graph[module["id"]] = deps
    visited, visiting, order = set(), set(), []

    def visit(mid):
        require(mid not in visiting, "Prerequisite graph contains a cycle")
        if mid in visited:
            return
        visiting.add(mid)
        for dep in graph[mid]:
            visit(dep)
        visiting.remove(mid)
        visited.add(mid)
        order.append(mid)

    for mid in graph:
        visit(mid)
    omitted = set()
    for item in sequence(plan.get("omitted_claims"), "plan.omitted_claims"):
        obj(item, "omitted claim")
        ref = string(item.get("ref"), "omitted claim.ref")
        require(ref in available and ref not in used and ref not in omitted, f"Invalid omitted claim: {ref}")
        string(item.get("reason"), "omitted claim.reason")
        omitted.add(ref)
    require(available == used | omitted, "Every extracted claim must be taught or explicitly omitted with a reason")
    for gap in sequence(plan.get("gaps"), "plan.gaps"):
        string(gap, "gap")
    for conflict in sequence(plan.get("conflicts"), "plan.conflicts"):
        obj(conflict, "conflict")
        string(conflict.get("description"), "conflict.description")
        refs = sequence(conflict.get("claim_refs"), "conflict.claim_refs", nonempty=True)
        require(len(refs) >= 2 and all(isinstance(ref, str) and ref in available for ref in refs), "Conflict needs at least two existing claims")
    return order
