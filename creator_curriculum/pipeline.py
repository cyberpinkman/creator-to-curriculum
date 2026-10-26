"""Resumable agent handoffs. Derived files are never the authority for source state."""

from pathlib import Path

from .core import (ContractError, digest, make_jobs, read_json, require, validate_corpus,
                   validate_learner, validate_notes, write_json)


def load_workspace(workspace):
    root = Path(workspace)
    corpus = validate_corpus(read_json(root / "corpus.json"))
    learner = validate_learner(read_json(root / "learner.json"))
    config = read_json(root / "config.json")
    jobs = make_jobs(corpus, config.get("max_chars"))
    return root, corpus, learner, jobs


def initialize(workspace, corpus, learner, max_chars=12000):
    validate_corpus(corpus)
    validate_learner(learner)
    make_jobs(corpus, max_chars)
    root = Path(workspace)
    require(not root.exists() or not any(root.iterdir()), f"Workspace must be new or empty: {root}")
    write_json(root / "corpus.json", corpus)
    write_json(root / "learner.json", learner)
    write_json(root / "config.json", {"schema_version": 1, "max_chars": max_chars})
    return prepare(root)


def inspect(workspace):
    root, corpus, learner, jobs = load_workspace(workspace)
    accepted, pending, invalid = [], [], []
    for job in jobs:
        path = root / "notes" / f'{job["job_id"]}.json'
        if not path.exists():
            pending.append(job["job_id"])
            continue
        try:
            accepted.append((job, validate_notes(read_json(path), job)))
        except ContractError as exc:
            invalid.append({"job_id": job["job_id"], "error": str(exc)})
    ready_ids = {v["id"] for v in corpus["videos"] if v["status"] == "ready"}
    finished_jobs = {j["job_id"] for j, _ in accepted}
    analyzed = [vid for vid in ready_ids if all(j["job_id"] in finished_jobs for j in jobs if j["video"]["id"] == vid)]
    blocked = [{"id": v["id"], "title": v["title"], "status": v["status"], "reason": v["reason"]}
               for v in corpus["videos"] if v["status"] != "ready"]
    evidence_kinds = sorted({s.get("evidence_kind", "speech_transcript")
                             for v in corpus["videos"] for s in v["segments"]})
    status = {"discovery": corpus["discovery"], "inventory_count": len(corpus["videos"]),
              "evidence_basis": f'imported evidence: {", ".join(evidence_kinds) or "none"}; full audiovisual review is unverified',
              "evidence_kinds": evidence_kinds,
              "transcript_ready_count": len(ready_ids), "analyzed_video_count": len(analyzed),
              "job_count": len(jobs), "accepted_job_count": len(accepted),
              "pending_jobs": pending, "invalid_jobs": invalid, "blocked_videos": blocked,
              "all_inventory_analyzed": bool(corpus["videos"]) and len(analyzed) == len(corpus["videos"]),
              "complete_for_declared_scope": (corpus["discovery"]["status"] == "complete"
                                              and bool(corpus["videos"])
                                              and len(analyzed) == len(corpus["videos"]))}
    return root, corpus, learner, jobs, accepted, status


def prepare(workspace):
    root, _, _, jobs, _, status = inspect(workspace)
    for job in jobs:
        write_json(root / "jobs" / f'{job["job_id"]}.json', job)
    # Old files remain auditable; only this manifest defines active work.
    write_json(root / "jobs" / "index.json", {"active_jobs": [j["job_id"] for j in jobs], **status})
    (root / "notes").mkdir(exist_ok=True)
    return status


def synthesize(workspace, *, allow_partial=False, save=True):
    root, corpus, learner, _, accepted, status = inspect(workspace)
    require(not status["invalid_jobs"], "Invalid or stale notes exist; inspect status and re-extract affected jobs")
    require(allow_partial or status["complete_for_declared_scope"],
            "Coverage is incomplete or unknown. Resolve gaps, or explicitly use --allow-partial for a labeled draft")
    claims, resources, uncertainties, reviewed = [], [], [], []
    for job, notes in accepted:
        segment_map = {s["id"]: s for s in job["segments"]}

        def expand(items):
            return [{"video_id": job["video"]["id"], "video_title": job["video"]["title"],
                     "url": job["video"]["url"], "transcript_source": job["video"]["transcript_source"],
                     "segment_id": segment_map[item["segment_id"]]["source_segment_id"],
                     "evidence_kind": segment_map[item["segment_id"]].get("evidence_kind", "speech_transcript"),
                     "start": segment_map[item["segment_id"]]["start"],
                     "end": segment_map[item["segment_id"]]["end"], "quote": item["quote"]} for item in items]

        for claim in notes["claims"]:
            claims.append({**claim, "ref": f'{job["job_id"]}/{claim["id"]}', "evidence": expand(claim["evidence"])})
        for resource in notes["resources"]:
            resources.append({**resource, "origin": "creator_reference", "evidence": expand(resource["evidence"])})
        uncertainties.extend({"job_id": job["job_id"], "text": u} for u in notes["uncertainties"])
        reviewed.append({"job_id": job["job_id"], "video_id": job["video"]["id"],
                         "disposition": notes["disposition"], "reason": notes["reason"]})
    require(claims, "No supported knowledge claims are available; cannot build a curriculum")
    result = {"schema_version": 1, "creator": corpus["creator"], "learner": learner,
              "coverage": status, "claims": claims, "resources": resources,
              "uncertainties": uncertainties, "reviewed_chunks": reviewed,
              "source_hash": digest(corpus)}
    result["input_hash"] = digest(result)
    if save:
        write_json(root / "synthesis.json", result)
        # Agents can inspect one topic at a time rather than loading the whole archive.
        topics = {}
        for claim in claims:
            topics.setdefault(claim["topic"], []).append(claim)
        topic_index = []
        for name, items in sorted(topics.items()):
            relative = f"topics/{digest(name)[:16]}.json"
            write_json(root / relative, {"topic": name, "claims": items, "input_hash": result["input_hash"]})
            topic_index.append({"topic": name, "path": relative,
                                "claims": [{"ref": c["ref"], "title": c["title"], "kind": c["kind"]} for c in items]})
        write_json(root / "synthesis-index.json", {"input_hash": result["input_hash"], "learner": learner,
                                                   "coverage": status, "topics": topic_index})
    return result
