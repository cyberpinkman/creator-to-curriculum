"""Shared evidence contracts. All adapters and exports pass through this boundary."""

from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime
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
            require(segment.get("evidence_kind", "speech_transcript") in {"speech_transcript", "screen_ocr"},
                    f"{vid}/{sid}: invalid evidence_kind; machine evidence cannot assert human verification")
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


def validate_index_learner(learner):
    """A planning brief keeps unknown starting ability and time explicitly unknown."""
    obj(learner, "index learner")
    require(type(learner.get("schema_version")) is int and learner["schema_version"] == 1,
            "learner.schema_version must be 1")
    for field in ("goal", "language"):
        string(learner.get(field), f"learner.{field}")
    require("level" in learner and "minutes_per_session" in learner,
            "learner must declare level and minutes_per_session; use null for unknown")
    if learner["level"] is not None:
        string(learner["level"], "learner.level")
    minutes = learner["minutes_per_session"]
    require(minutes is None or (type(minutes) is int and minutes > 0),
            "learner.minutes_per_session must be a positive integer or null")
    require(learner.get("mode") in ("systematic", "problem", "explore"), "Invalid learner.mode")
    for field in ("prior_knowledge", "constraints", "assumptions"):
        for item in sequence(learner.get(field), f"learner.{field}"):
            string(item, f"learner.{field} item")
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


def index_paths(plan):
    """One canonical path projection for every index consumer, after validation."""
    if plan.get("schema_version") == 2:
        activities = {activity["id"]: activity for activity in plan["activities"]}
        paths = []
        for path in sorted(plan["paths"], key=lambda item: item["id"] != "start"):
            steps = [{**step, "topic_id": activities[step["activity_id"]]["topic_id"]}
                     for step in path["steps"]]
            paths.append({**path, "steps": steps,
                          "topic_ids": list(dict.fromkeys(step["topic_id"] for step in steps))})
        return paths
    return [dict(id="start", title="建议起步路径", topic_ids=plan["start_path"],
                 prerequisite_exemptions=plan.get("start_path_exemptions", [])),
            *plan.get("learning_paths", [])]


def index_task(topic):
    """A small task is distinct from full-video duration and learner mastery."""
    defaults = dict(
        objective=topic["question"],
        primary_video_id=(topic.get("recommended_ids") or topic["video_ids"])[0],
        stop_when=topic.get("self_check", "看一条主要原视频，记下一点收获或一个疑问后停下。"),
        practice_minutes=None)
    return {**defaults, **topic.get("task", {})}


def index_package_id(plan, corpus):
    """Use creator identity, never inventory/order/title, for legacy plan continuity."""
    creator = corpus["creator"]
    identity = {"platform": creator["platform"], "identity": creator.get("url") or creator["name"]}
    return plan.get("package_id", "creator-" + digest(identity)[:24])


def validate_index_paths(plan, graph):
    seen_paths = set()
    sequence(plan.get("learning_paths", []), "index.learning_paths")
    for path in index_paths(plan):
        obj(path, "index path")
        pid = identifier(path.get("id"), "path.id")
        require(pid not in seen_paths, f"Duplicate path: {pid}; start is reserved for start_path")
        seen_paths.add(pid)
        string(path.get("title"), f"path {pid}.title")
        available = set()
        for exemption in sequence(path.get("prerequisite_exemptions", []), f"path {pid}.prerequisite_exemptions"):
            obj(exemption, "path prerequisite exemption")
            tid = identifier(exemption.get("topic_id"), "exemption.topic_id")
            require(tid in graph and tid not in available, f"Path {pid}: unknown or duplicate prerequisite exemption {tid}")
            require(isinstance(exemption.get("status"), str) and exemption["status"] in {"assumed_known", "skipped"}, f"Path {pid}: invalid prerequisite exemption status")
            string(exemption.get("reason"), f"path {pid}.exemption.reason")
            available.add(tid)
        seen = set()
        for tid in sequence(path.get("topic_ids"), f"path {pid}.topic_ids"):
            identifier(tid, f"path {pid} topic")
            require(tid in graph, f"Path {pid}: unknown topic {tid}")
            require(tid not in seen, f"Path {pid}: duplicate topic {tid}")
            missing = [dep for dep in graph[tid] if dep not in available]
            require(not missing, f"Path {pid}: {tid} requires earlier topics or explicit prerequisite exemptions: {', '.join(missing)}")
            seen.add(tid)
            available.add(tid)


def validate_index_plan(plan, corpus, learner=None):
    """A navigational index may use titles; it must not promote them to content evidence."""
    validate_corpus(corpus)
    obj(plan, "index plan")
    require(type(plan.get("schema_version")) is int and plan["schema_version"] in {1, 2},
            "index.schema_version must be 1 or 2")
    require(plan.get("source_hash") == digest(corpus), "Stale index: source inventory changed")
    for field in ("title", "goal", "overview"):
        string(plan.get(field), f"index.{field}")
    if "package_id" in plan:
        identifier(plan["package_id"], "index.package_id")
    videos = {v["id"]: v for v in corpus["videos"]}
    ids, used = set(), set()
    topics = sequence(plan.get("topics"), "index.topics", nonempty=True)
    for topic in topics:
        obj(topic, "index topic")
        tid = identifier(topic.get("id"), "topic.id")
        require(tid not in ids, f"Duplicate topic: {tid}")
        ids.add(tid)
        for field in ("title", "group", "question", "guidance"):
            string(topic.get(field), f"topic.{field}")
        seen = set()
        for vid in sequence(topic.get("video_ids"), "topic.video_ids", nonempty=True):
            require(vid in videos and vid not in seen, f"Unknown or duplicate video in topic: {vid}")
            require(videos[vid]["status"] != "excluded", "Excluded source identity cannot enter an index")
            seen.add(vid); used.add(vid)
        for vid in sequence(topic.get("recommended_ids", []), "topic.recommended_ids"):
            require(vid in seen, "Recommended video must belong to its topic")
    graph = {}
    for topic in topics:
        deps = sequence(topic.get("prerequisites", []), "topic.prerequisites")
        require(all(dep in ids for dep in deps), "Unknown index prerequisite")
        graph[topic["id"]] = deps
        for field in ("watch_for", "self_check"):
            if field in topic:
                string(topic[field], f"topic.{field}")
    visiting, visited = set(), set()
    def visit(tid):
        require(tid not in visiting, "Index prerequisite graph contains a cycle")
        if tid in visited: return
        visiting.add(tid)
        for dep in graph[tid]: visit(dep)
        visiting.remove(tid); visited.add(tid)
    for tid in ids: visit(tid)
    if plan["schema_version"] == 1:
        sequence(plan.get("start_path"), "index.start_path")
        validate_index_paths(plan, graph)
    for resource in sequence(plan.get("materials", []), "index.materials"):
        obj(resource, "index material")
        for field in ("title", "description", "status"):
            string(resource.get(field), f"material.{field}")
        require(resource.get("origin") in {"creator", "external", "agent"}, "Invalid material origin")
        url(resource.get("url"), "material.url", optional=True)
        for tid in sequence(resource.get("topic_ids", []), "material.topic_ids"):
            require(tid in ids, "Material references an unknown topic")
        if resource.get("local_path") is not None:
            path = Path(string(resource["local_path"], "material.local_path"))
            require(not any(c in resource["local_path"] for c in (":", "?", "#", "\\")) and not path.is_absolute() and ".." not in path.parts, "Material path must stay inside the index folder")
    for vid, review in obj(plan.get("reviews", {}), "index.reviews").items():
        require(vid in used, "Review must belong to an indexed video")
        obj(review, "index review")
        string(review.get("note"), "review.note")
        # Quote validation is shared with curriculum extraction. No title-only shortcut.
        validate_evidence(review.get("evidence"), {"segments": videos[vid]["segments"]}, "index review")
        for entry in review["evidence"]:
            if "label" in entry:
                string(entry["label"], "index evidence label")
    for topic in topics:
        tid = topic["id"]
        if "task" in topic:
            task = obj(topic["task"], f"topic {tid}.task")
            for field in ("objective", "stop_when"):
                string(task.get(field), f"topic {tid}.task.{field}")
            require(task.get("primary_video_id") in topic["video_ids"], f"Topic {tid}: task video must belong to its topic")
            minutes = task.get("practice_minutes")
            require(minutes is None or (type(minutes) is int and minutes > 0),
                    f"Topic {tid}: practice_minutes must be a positive integer estimate or null")
        for vid, refs in obj(topic.get("video_evidence", {}), f"topic {tid}.video_evidence").items():
            require(vid in topic["video_ids"], f"Topic {tid}: evidence video {vid} must belong to its topic")
            review = plan.get("reviews", {}).get(vid)
            require(review is not None, f"Topic {tid}: video {vid} has no reviewed evidence")
            available = {entry["segment_id"] for entry in review["evidence"]}
            seen = set()
            for sid in sequence(refs, f"topic {tid}.video_evidence.{vid}", nonempty=True):
                identifier(sid, f"topic {tid} evidence segment")
                require(sid in available and sid not in seen,
                        f"Topic {tid}: unknown, unreviewed or duplicate evidence segment {vid}/{sid}")
                seen.add(sid)
    for advice in sequence(plan.get("learning_advice", []), "index.learning_advice"):
        string(advice, "learning advice")
    for note in sequence(plan.get("limitations", []), "index.limitations"):
        string(note, "index limitation")
    if plan["schema_version"] == 2:
        _validate_index_design(plan, videos, graph, learner)
    return used


def _index_sources(sources, plan, videos, where, *, allowed=None, nonempty=False):
    """Validate selections against the same already-validated quotation boundary."""
    selected, refs = set(), set()
    for source in sequence(sources, f"{where}.sources", nonempty=nonempty):
        obj(source, f"{where}.source")
        vid = identifier(source.get("video_id"), f"{where}.video_id")
        require(vid in videos and vid not in selected, f"{where}: unknown or duplicate source {vid}")
        require(videos[vid]["status"] != "excluded", f"{where}: excluded source {vid}")
        require(allowed is None or vid in allowed, f"{where}: source must belong to its topic")
        selected.add(vid)
        available = {item["segment_id"] for item in plan.get("reviews", {}).get(vid, {}).get("evidence", [])}
        seen = set()
        for sid in sequence(source.get("segment_ids"), f"{where}.segment_ids"):
            identifier(sid, f"{where}.segment_id")
            require(sid in available and sid not in seen, f"{where}: unknown, unreviewed or duplicate segment {vid}/{sid}")
            seen.add(sid)
            refs.add((vid, sid))
    return selected, refs


def _index_ids(values, available, where, *, nonempty=False):
    seen = set()
    for value in sequence(values, where, nonempty=nonempty):
        identifier(value, where)
        require(value in available and value not in seen, f"{where}: unknown or duplicate ID {value}")
        seen.add(value)
    return seen


def _validate_index_design(plan, videos, topic_graph, learner):
    validate_index_learner(learner)
    require(plan.get("learner_hash") == digest(learner),
            "Stale index: learner brief changed; review and replan before updating learner_hash")
    require(plan["goal"] == learner["goal"], "Index goal must match its learner brief")
    require("start_path" not in plan and "learning_paths" not in plan,
            "Index v2 uses paths; start_path and learning_paths are derived outputs")

    capabilities = {}
    for capability in sequence(plan.get("capabilities"), "index.capabilities", nonempty=True):
        obj(capability, "capability")
        cid = identifier(capability.get("id"), "capability.id")
        require(cid not in capabilities, f"Duplicate capability: {cid}")
        for field in ("title", "outcome"):
            string(capability.get(field), f"capability {cid}.{field}")
        require(type(capability.get("required")) is bool, f"capability {cid}.required must be boolean")
        coverage = obj(capability.get("coverage"), f"capability {cid}.coverage")
        status = coverage.get("status")
        require(status in ("supported", "candidate", "missing", "conflicting"), f"capability {cid}: invalid coverage status")
        string(coverage.get("reason"), f"capability {cid}.coverage.reason")
        source_ids, refs = _index_sources(coverage.get("sources"), plan, videos, f"capability {cid}")
        if status == "supported":
            require(refs, f"Capability {cid}: supported coverage needs selected source evidence")
        elif status == "missing":
            require(not source_ids, f"Capability {cid}: missing coverage cannot assert source support")
        elif status == "candidate":
            require(source_ids, f"Capability {cid}: candidate coverage needs a source candidate")
        else:
            require(len(refs) >= 2, f"Capability {cid}: conflicting coverage needs at least two evidence references")
        if status != "supported":
            string(coverage.get("next_action"), f"capability {cid}.coverage.next_action")
        capabilities[cid] = capability
    cap_graph = {cid: _index_ids(cap.get("prerequisites"), capabilities, f"capability {cid}.prerequisites")
                 for cid, cap in capabilities.items()}
    visiting, visited = set(), set()

    def visit(cid):
        require(cid not in visiting, "Capability prerequisite graph contains a cycle")
        if cid in visited:
            return
        visiting.add(cid)
        for dep in cap_graph[cid]:
            visit(dep)
        visiting.remove(cid)
        visited.add(cid)

    for cid in capabilities:
        visit(cid)

    materials = {}
    for resource in plan.get("materials", []):
        mid = identifier(resource.get("id"), "material.id")
        require(mid not in materials, f"Duplicate material: {mid}")
        availability = resource.get("availability")
        require(availability in ("available", "unavailable", "unknown"), f"Material {mid}: invalid availability")
        require(availability != "available" or resource.get("url") or resource.get("local_path"),
                f"Material {mid}: available material needs an actual URL or local file")
        materials[mid] = resource
    topics = {topic["id"]: topic for topic in plan["topics"]}
    activities = {}
    for activity in sequence(plan.get("activities"), "index.activities"):
        obj(activity, "activity")
        aid = identifier(activity.get("id"), "activity.id")
        require(aid not in activities, f"Duplicate activity: {aid}")
        tid = identifier(activity.get("topic_id"), f"activity {aid}.topic_id")
        require(tid in topics, f"Activity {aid}: unknown topic")
        require(activity.get("kind") in ("understand", "practice", "create", "compare", "lookup"),
                f"Activity {aid}: invalid learning kind")
        for field in ("title", "objective", "output", "stop_when"):
            string(activity.get(field), f"activity {aid}.{field}")
        for field in ("instructions", "success_criteria"):
            for item in sequence(activity.get(field), f"activity {aid}.{field}", nonempty=True):
                string(item, f"activity {aid}.{field} item")
        _index_ids(activity.get("capability_ids"), capabilities, f"activity {aid}.capability_ids", nonempty=True)
        sources, _ = _index_sources(activity.get("sources"), plan, videos, f"activity {aid}",
                                    allowed=topics[tid]["video_ids"], nonempty=True)
        primary = identifier(activity.get("primary_video_id"), f"activity {aid}.primary_video_id")
        require(primary in sources, f"Activity {aid}: primary video must be a selected source")
        _index_ids(activity.get("required_material_ids"), materials, f"activity {aid}.required_material_ids")
        require("practice_minutes" in activity, f"Activity {aid}: declare practice_minutes or null")
        minutes = activity["practice_minutes"]
        require(minutes is None or (type(minutes) is int and minutes > 0),
                f"Activity {aid}: practice_minutes must be a positive integer estimate or null")
        activities[aid] = activity

    path_ids, used_activities = set(), set()
    for path in sequence(plan.get("paths"), "index.paths", nonempty=True):
        obj(path, "path")
        pid = identifier(path.get("id"), "path.id")
        require(pid not in path_ids, f"Duplicate path: {pid}")
        path_ids.add(pid)
        for field in ("title", "outcome", "reason"):
            string(path.get(field), f"path {pid}.{field}")
        seen_capabilities = set()
        for exemption in sequence(path.get("capability_exemptions", []), f"path {pid}.capability_exemptions"):
            obj(exemption, "capability exemption")
            cid = identifier(exemption.get("capability_id"), "exemption.capability_id")
            require(cid in capabilities and cid not in seen_capabilities,
                    f"Path {pid}: unknown or duplicate capability exemption {cid}")
            require(exemption.get("status") in ("assumed_known", "skipped"), f"Path {pid}: invalid capability exemption status")
            string(exemption.get("reason"), f"path {pid}.capability exemption reason")
            seen_capabilities.add(cid)
        available_topics = set()
        for exemption in sequence(path.get("prerequisite_exemptions", []), f"path {pid}.prerequisite_exemptions"):
            obj(exemption, "topic prerequisite exemption")
            tid = identifier(exemption.get("topic_id"), "exemption.topic_id")
            require(tid in topics and tid not in available_topics, f"Path {pid}: unknown or duplicate topic exemption {tid}")
            require(exemption.get("status") in ("assumed_known", "skipped"), f"Path {pid}: invalid topic exemption status")
            string(exemption.get("reason"), f"path {pid}.topic exemption reason")
            available_topics.add(tid)
        seen_steps = set()
        for step in sequence(path.get("steps"), f"path {pid}.steps"):
            obj(step, "path step")
            sid = identifier(step.get("id"), f"path {pid}.step.id")
            require(sid not in seen_steps, f"Path {pid}: duplicate step {sid}")
            seen_steps.add(sid)
            aid = identifier(step.get("activity_id"), f"path {pid}.step.activity_id")
            require(aid in activities, f"Path {pid}: unknown activity {aid}")
            string(step.get("reason"), f"path {pid}.step.reason")
            tid = activities[aid]["topic_id"]
            missing = [dep for dep in topic_graph[tid] if dep not in available_topics]
            require(not missing, f"Path {pid}: {tid} requires earlier topics or explicit prerequisite exemptions: {', '.join(missing)}")
            available_topics.add(tid)
            used_activities.add(aid)
    require("start" in path_ids, "Index v2 requires exactly one default path with id start")
    require(used_activities == set(activities), "Every activity must belong to a path")


def index_learning_design(plan, corpus, learner=None):
    """Project planning readiness without asserting truth, mastery, or total study time."""
    validate_index_plan(plan, corpus, learner)
    paths = index_paths(plan)
    if plan["schema_version"] == 1:
        return {"status": "legacy", "issues": ["此学习包使用兼容导航，尚未评估学习需求、能力覆盖与具体活动。"], "paths": paths}
    capabilities = {cap["id"]: cap for cap in plan["capabilities"]}
    activities = {activity["id"]: activity for activity in plan["activities"]}
    materials = {material["id"]: material for material in plan.get("materials", [])}
    issues = []
    if learner["level"] is None:
        issues.append("已有基础尚未明确；路径起点需要确认。")
    if learner["minutes_per_session"] is None:
        issues.append("每次可用时间未知；尚不能判断任务的时间适配。")
    if learner["assumptions"]:
        issues.append("学习需求仍有明确列出的假设，需在使用时核对。")
    for path in paths:
        available = {item["capability_id"] for item in path.get("capability_exemptions", [])
                     if item["status"] == "assumed_known"}
        addressed = set(available)
        for step in path["steps"]:
            activity = activities[step["activity_id"]]
            blocked, review = [], []
            selected_refs = {(source["video_id"], sid) for source in activity["sources"]
                             for sid in source["segment_ids"]}
            required = {dep for cid in activity["capability_ids"] for dep in capabilities[cid]["prerequisites"]}
            for cid in sorted(required - available):
                blocked.append(f'先修能力尚未安排或仍有缺口：{capabilities[cid]["title"]}。')
            for cid in activity["capability_ids"]:
                cap = capabilities[cid]
                status = cap["coverage"]["status"]
                if status == "missing":
                    blocked.append(f'当前来源缺少支持：{cap["title"]}。{cap["coverage"]["next_action"]}')
                elif status != "supported":
                    review.append(f'能力来源需要补查：{cap["title"]}。{cap["coverage"]["next_action"]}')
                else:
                    coverage_refs = {(source["video_id"], sid) for source in cap["coverage"]["sources"]
                                     for sid in source["segment_ids"]}
                    if not selected_refs.intersection(coverage_refs):
                        review.append(f'本活动选用片段尚未关联到能力覆盖依据：{cap["title"]}。请核对并明确来源关联。')
            if any(not source["segment_ids"] for source in activity["sources"]):
                review.append("所选学习材料仍含标题候选；需要确认能支持本次活动。")
            for mid in activity["required_material_ids"]:
                if materials[mid]["availability"] != "available":
                    blocked.append(f'必需资料尚不可用或未确认：{materials[mid]["title"]}。')
            if (learner["minutes_per_session"] is not None and activity["practice_minutes"] is not None
                    and activity["practice_minutes"] > learner["minutes_per_session"]):
                review.append("仅练习时间估算已超过本次可用时间；请拆分活动，观看与准备时间另计。")
            status = "blocked" if blocked else "needs_review" if review else "ready"
            step["readiness"] = {"status": status, "issues": blocked + review}
            addressed.update(activity["capability_ids"])
            if status == "ready":
                available.update(activity["capability_ids"])
        path_issues = [message for step in path["steps"] for message in step["readiness"]["issues"]]
        if not path["steps"]:
            path_issues.append("尚无可开始的学习活动；先处理覆盖缺口并补充路径。")
        if path["id"] == "start":
            for cid, capability in capabilities.items():
                if capability["required"] and cid not in addressed:
                    path_issues.append(f'目标所需能力尚未安排活动或声明已有基础：{capability["title"]}。')
        statuses = [step["readiness"]["status"] for step in path["steps"]]
        status = ("blocked" if not statuses or all(value == "blocked" for value in statuses)
                  else "needs_review" if path_issues else "ready")
        path["readiness"] = {"status": status, "issues": list(dict.fromkeys(path_issues))}
    default = next(path for path in paths if path["id"] == "start")
    issues.extend(f'{path["title"]}：{message}' for path in paths for message in path["readiness"]["issues"])
    status = "blocked" if default["readiness"]["status"] == "blocked" else "partial" if issues else "ready"
    return {"status": status, "issues": list(dict.fromkeys(issues)), "paths": paths}


def _feedback_fields(value, required, where, optional=()):
    obj(value, where)
    require(all(isinstance(key, str) for key in value), f"{where}: field names must be strings")
    require(not set(required) - set(value), f"{where}: missing fields {sorted(set(required) - set(value))}")
    require(not set(value) - set(required) - set(optional),
            f"{where}: unsupported fields {sorted(set(value) - set(required) - set(optional))}")
    if "schema_version" in required:
        require(type(value["schema_version"]) is int and value["schema_version"] == 1,
                f"{where}.schema_version must be 1")


def _feedback_hash(value, where):
    string(value, where)
    require(bool(re.fullmatch(r"[0-9a-fA-F]{64}", value)), f"{where}: expected SHA-256 hex")
    return value


def _feedback_date(value, where):
    string(value, where)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError(f"{where}: expected ISO date-time with timezone") from error
    require("T" in value and parsed.tzinfo is not None, f"{where}: expected ISO date-time with timezone")


def _feedback_copy(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def index_feedback_context(plan, corpus, learner, material_hashes=None):
    """Capture the inputs governing one feedback cycle, never learner performance."""
    design = index_learning_design(plan, corpus, learner)
    if plan["schema_version"] == 1:
        return None
    material_hashes = {} if material_hashes is None else obj(material_hashes, "material_hashes")
    local_materials = {item["id"] for item in plan.get("materials", []) if item.get("local_path")}
    for mid, value in material_hashes.items():
        identifier(mid, "material_hashes material ID")
        require(mid in local_materials, f"material_hashes: unknown local material {mid}")
        _feedback_hash(value, f"material_hashes.{mid}")
    activities = {activity["id"]: activity for activity in plan["activities"]}
    steps = []
    for path in design["paths"]:
        for step in path["steps"]:
            activity = activities[step["activity_id"]]
            steps.append({"path_id": path["id"], "step_id": step["id"],
                          **{key: activity[key] for key in ("topic_id", "title", "kind", "objective", "output",
                                                           "instructions", "success_criteria", "stop_when",
                                                           "sources", "required_material_ids")},
                          "activity_id": activity["id"], "reason": step["reason"], "readiness": step["readiness"]})
    return _feedback_copy({"schema_version": 1, "package_id": index_package_id(plan, corpus),
                           "context_hash": digest({"plan": plan, "learner": learner,
                                                   "source_hash": digest(corpus), "material_hashes": material_hashes}),
                           "steps": steps})


def _feedback_context_steps(context):
    """Context must come from the current validated plan, not an imported record."""
    obj(context, "feedback context")
    require(type(context.get("schema_version")) is int and context["schema_version"] == 1,
            "feedback context.schema_version must be 1")
    identifier(context.get("package_id"), "feedback context.package_id")
    _feedback_hash(context.get("context_hash"), "feedback context.context_hash")
    steps = {}
    for step in sequence(context.get("steps"), "feedback context.steps"):
        obj(step, "feedback context step")
        for key in ("path_id", "step_id", "activity_id", "topic_id"):
            identifier(step.get(key), f"feedback step.{key}")
        key = (step["path_id"], step["step_id"])
        require(key not in steps, "feedback context contains duplicate path/step bindings")
        for criterion in sequence(step.get("success_criteria"), "feedback step.success_criteria", nonempty=True):
            string(criterion, "feedback success criterion")
        readiness = obj(step.get("readiness"), "feedback step.readiness")
        require(readiness.get("status") in ("ready", "needs_review", "blocked"), "Invalid feedback step readiness")
        steps[key] = step
    return steps


def validate_learning_attempt(attempt, context=None):
    """Validate an immutable attempt; old contexts are readable without rebinding."""
    _feedback_fields(attempt, ("schema_version", "id", "package_id", "context_hash", "path_id", "step_id",
                              "activity_id", "created_at", "work_origin", "response", "artifact_refs", "blocker", "criteria"),
                     "learning attempt")
    for field in ("id", "package_id", "path_id", "step_id", "activity_id"):
        identifier(attempt[field], f"attempt.{field}")
    _feedback_hash(attempt["context_hash"], "attempt.context_hash")
    _feedback_date(attempt["created_at"], "attempt.created_at")
    require(attempt["work_origin"] in ("learner", "assisted", "reference", "unknown"), "Invalid attempt.work_origin")
    for field in ("response", "blocker"):
        require(isinstance(attempt[field], str), f"attempt.{field} must be text")
    artifacts = set()
    for ref in sequence(attempt["artifact_refs"], "attempt.artifact_refs"):
        string(ref, "attempt.artifact_ref")
        require(ref not in artifacts, "Duplicate attempt artifact reference")
        artifacts.add(ref)
    require(attempt["response"].strip() or attempt["blocker"].strip() or artifacts,
            "An attempt needs a response, artifact reference, or explicit blocker")
    for criterion in sequence(attempt["criteria"], "attempt.criteria", nonempty=True):
        string(criterion, "attempt criterion")
    if context is not None:
        steps = _feedback_context_steps(context)
        require(attempt["package_id"] == context["package_id"], "Attempt belongs to another learning package")
        require(attempt["context_hash"] == context["context_hash"], "Stale attempt: learning context changed")
        step = steps.get((attempt["path_id"], attempt["step_id"]))
        require(step is not None, "Attempt references an unknown current path/step")
        require(attempt["activity_id"] == step["activity_id"], "Attempt activity does not match its path/step")
        require(attempt["criteria"] == step["success_criteria"], "Attempt criteria do not match the current activity")
    return attempt


def _validate_feedback_action(action, attempt, context, all_met):
    _feedback_fields(action, ("kind", "reason", "instructions", "output", "stop_when", "target"), "feedback next_action")
    kind = action["kind"]
    require(kind in ("continue", "retry", "revisit", "switch_path", "resolve_gap", "request_evidence", "finish"),
            "Invalid feedback next_action.kind")
    for field in ("reason", "output", "stop_when"):
        string(action[field], f"next_action.{field}")
    for instruction in sequence(action["instructions"], "next_action.instructions", nonempty=True):
        string(instruction, "next_action instruction")
    navigation = kind in ("continue", "retry", "revisit", "switch_path")
    if navigation:
        _feedback_fields(action["target"], ("path_id", "step_id"), "next_action.target")
        for field in ("path_id", "step_id"):
            identifier(action["target"][field], f"next_action.target.{field}")
    else:
        require(action["target"] is None, f"Action {kind} must not set a learning target")
    if context is None:
        return
    steps = _feedback_context_steps(context)
    key = (attempt["path_id"], attempt["step_id"])
    source = steps[key]  # validate_learning_attempt already checked this binding.
    same_path = [candidate for candidate in steps if candidate[0] == key[0]]
    position = same_path.index(key)
    target_key = (action["target"]["path_id"], action["target"]["step_id"]) if navigation else None
    if navigation:
        require(target_key in steps, "Feedback target does not exist in the current plan")
    if kind == "continue":
        require(all_met and attempt["work_origin"] in ("learner", "assisted"),
                "Continue requires evidence for every criterion of this attempt")
        require(source["readiness"]["status"] == "ready", "Cannot continue from a step that is not ready")
        require(position + 1 < len(same_path) and target_key == same_path[position + 1],
                "Continue must target the immediately following step on the same path")
        require(steps[target_key]["readiness"]["status"] == "ready", "Cannot continue to a step that is not ready")
    elif kind == "retry":
        require(target_key == key, "Retry must target the current step")
        require(source["readiness"]["status"] != "blocked", "Blocked step needs its gaps resolved before retry")
    elif kind == "revisit":
        require(target_key in same_path[:position], "Revisit must target an earlier step on the same path")
        require(steps[target_key]["readiness"]["status"] != "blocked", "Cannot revisit a blocked target as a learning action")
    elif kind == "switch_path":
        require(target_key[0] != key[0], "Switch path must target another path")
        first = next(candidate for candidate in steps if candidate[0] == target_key[0])
        require(target_key == first, "Switch path must start at the first step of the target path")
        require(steps[target_key]["readiness"]["status"] != "blocked", "Cannot switch to a blocked target")
    elif kind == "finish":
        require(position == len(same_path) - 1, "Finish is only valid at the final step of a path")
        require(all_met and attempt["work_origin"] in ("learner", "assisted"),
                "Finish requires evidence for every criterion of this attempt")
        require(source["readiness"]["status"] != "blocked", "A blocked step cannot be marked finished")


def validate_learning_feedback(feedback, attempt, context=None):
    """Check reported evidence and safe action wiring, not the Agent's semantic judgment."""
    validate_learning_attempt(attempt, context)
    _feedback_fields(feedback, ("schema_version", "id", "attempt_id", "attempt_hash", "context_hash", "created_at",
                               "summary", "criteria", "next_action"), "learning feedback", optional=("observations",))
    for field in ("id", "attempt_id"):
        identifier(feedback[field], f"feedback.{field}")
    _feedback_hash(feedback["attempt_hash"], "feedback.attempt_hash")
    _feedback_hash(feedback["context_hash"], "feedback.context_hash")
    _feedback_date(feedback["created_at"], "feedback.created_at")
    string(feedback["summary"], "feedback.summary")
    require(feedback["attempt_id"] == attempt["id"], "Feedback references another attempt")
    require(feedback["attempt_hash"] == digest(attempt), "Feedback is stale or the attempt content changed")
    require(feedback["context_hash"] == attempt["context_hash"], "Feedback context does not match its attempt")
    observations = {}
    for observation in sequence(feedback.get("observations", []), "feedback.observations"):
        _feedback_fields(observation, ("id", "artifact_ref", "method", "observation", "limitations"), "feedback observation")
        oid = identifier(observation["id"], "observation.id")
        require(oid not in observations, "Duplicate feedback observation ID")
        string(observation["artifact_ref"], "observation.artifact_ref")
        require(observation["artifact_ref"] in attempt["artifact_refs"], "Observation references an unsubmitted artifact")
        require(observation["method"] in ("read", "view", "run"), "Invalid observation method")
        for field in ("observation", "limitations"):
            string(observation[field], f"observation.{field}")
        observations[oid] = observation
    assessed = {}
    for criterion in sequence(feedback["criteria"], "feedback.criteria", nonempty=True):
        _feedback_fields(criterion, ("criterion_index", "result", "evidence", "reason"), "feedback criterion")
        index = criterion["criterion_index"]
        require(type(index) is int and 0 <= index < len(attempt["criteria"]), "Invalid feedback criterion index")
        require(index not in assessed, "Duplicate feedback criterion index")
        result = criterion["result"]
        require(result in ("met", "needs_work", "not_observed"), "Invalid feedback criterion result")
        string(criterion["reason"], "feedback criterion.reason")
        evidence = sequence(criterion["evidence"], "feedback criterion.evidence", nonempty=result != "not_observed")
        if result != "not_observed":
            require(attempt["work_origin"] in ("learner", "assisted"),
                    "Reference or unknown-origin work cannot establish learner performance")
        for item in evidence:
            obj(item, "feedback evidence")
            if "observation_id" in item:
                _feedback_fields(item, ("observation_id",), "feedback evidence")
                oid = identifier(item["observation_id"], "evidence.observation_id")
                require(oid in observations, "Feedback evidence references an unknown observation")
            else:
                _feedback_fields(item, ("field", "quote"), "feedback evidence")
                require(item["field"] == "response", "Only submitted response text can be quoted as learner evidence")
                quote = string(item["quote"], "feedback evidence.quote")
                require(quote in attempt["response"], "Feedback quote is not verbatim in the submitted response")
        assessed[index] = result
    require(set(assessed) == set(range(len(attempt["criteria"]))), "Feedback must address every frozen criterion exactly once")
    _validate_feedback_action(feedback["next_action"], attempt, context, all(value == "met" for value in assessed.values()))
    return feedback


def current_learning_attempts(context, attempts):
    """Select the latest current-context attempts from already validated history.

    Delayed old-version imports remain history, never a replacement for a current
    task submission. Repeated immutable IDs do not move a submission to the end.
    """
    latest, seen = {}, set()
    for attempt in attempts:
        if attempt['id'] in seen:
            continue
        seen.add(attempt['id'])
        if attempt['context_hash'] == context['context_hash']:
            latest[(attempt['path_id'], attempt['step_id'])] = attempt
    return list(latest.values())


def index_learning_feedback(context, state):
    """Keep immutable history visible; only the latest valid guidance is actionable."""
    if context is not None:
        _feedback_context_steps(context)
    if state is None:
        return {"schema_version": 1, "package_id": context["package_id"] if context else None,
                "attempts": [], "feedback": []}
    _feedback_fields(state, ("schema_version", "package_id", "attempts", "feedback"), "feedback state")
    identifier(state["package_id"], "feedback state.package_id")
    attempts_input = sequence(state["attempts"], "feedback state.attempts")
    feedback_input = sequence(state["feedback"], "feedback state.feedback")
    if context is None:
        require(not attempts_input and not feedback_input, "Feedback history requires a v2 learning context")
        return _feedback_copy(state)
    require(state["package_id"] == context["package_id"], "Feedback state belongs to another learning package")
    attempts = {}
    for attempt in attempts_input:
        validate_learning_attempt(attempt)
        require(attempt["package_id"] == state["package_id"], "Attempt belongs to another learning package")
        aid = attempt["id"]
        if aid in attempts:
            require(attempt == attempts[aid], f"Immutable attempt ID already contains different content: {aid}")
            continue
        if attempt["context_hash"] == context["context_hash"]:
            validate_learning_attempt(attempt, context)
        attempts[aid] = attempt
    latest_attempts = {(attempt['path_id'], attempt['step_id']): attempt['id']
                       for attempt in current_learning_attempts(context, attempts.values())}
    feedback_records, latest_feedback = {}, {}
    for feedback in feedback_input:
        obj(feedback, "learning feedback")
        aid = identifier(feedback.get("attempt_id"), "feedback.attempt_id")
        require(aid in attempts, "Feedback references an unknown attempt")
        attempt = attempts[aid]
        validate_learning_feedback(feedback, attempt,
                                   context if attempt["context_hash"] == context["context_hash"] else None)
        fid = feedback["id"]
        if fid in feedback_records:
            require(feedback == feedback_records[fid], f"Immutable feedback ID already contains different content: {fid}")
            continue
        feedback_records[fid] = feedback
        latest_feedback[aid] = fid
    projected = []
    for fid, feedback in feedback_records.items():
        attempt = attempts[feedback["attempt_id"]]
        if attempt["context_hash"] != context["context_hash"]:
            status = "stale"
        elif (latest_attempts[(attempt["path_id"], attempt["step_id"])] != attempt["id"]
              or latest_feedback[attempt["id"]] != fid):
            status = "superseded"
        else:
            status = "current"
        projected.append({**feedback, "status": status, "actionable": status == "current", "attempt": attempt})
    return _feedback_copy({"schema_version": 1, "package_id": state["package_id"],
                           "attempts": list(attempts.values()), "feedback": projected})


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
