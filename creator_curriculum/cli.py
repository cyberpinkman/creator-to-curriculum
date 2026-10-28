import argparse
import json
from pathlib import Path
import sys

from .adapters import attach_transcript, discover, import_video_learning
from .core import ContractError, read_json, require, write_json
from .pipeline import initialize, inspect, prepare, synthesize
from .render import render
from .index import build_index
from .usage import STAGES, estimate, import_codex_usage, import_response_usage, record_usage, usage_report


def parser():
    result = argparse.ArgumentParser(prog="c2c", description="Turn creator evidence into a structured curriculum with your agent.")
    result.add_argument("--version", action="version", version="creator-to-curriculum 0.1.0")
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create an isolated learning workspace from a corpus")
    init.add_argument("--corpus", required=True)
    init.add_argument("--out", required=True)
    init.add_argument("--goal", required=True)
    init.add_argument("--level", default="beginner")
    init.add_argument("--language", default="zh-CN")
    init.add_argument("--minutes", type=int, default=30)
    init.add_argument("--max-chars", type=int, default=12000)
    nav_init = commands.add_parser("init-index", help="Start the default learner-aware planning handoff without full extraction")
    nav_init.add_argument("--corpus", required=True)
    nav_init.add_argument("--out", required=True)
    nav_init.add_argument("--goal", required=True)
    nav_init.add_argument("--level", help="Known starting level; omit when unknown")
    nav_init.add_argument("--minutes", type=int, help="Available minutes per session; omit when unknown")
    nav_init.add_argument("--language", default="zh-CN")
    nav_init.add_argument("--mode", choices=["systematic", "problem", "explore"], default="systematic")
    nav_init.add_argument("--known", action="append", default=[], help="Prior knowledge; repeat as needed")
    nav_init.add_argument("--constraint", action="append", default=[])
    nav_init.add_argument("--assumption", action="append", default=[])
    nav_prepare = commands.add_parser("prepare-index", help="Refresh planning inputs after source/learner edits, preserving the existing plan")
    nav_prepare.add_argument("workspace")
    attempt = commands.add_parser("record-attempt", help="Record a real learner submission or blocker; never infer mastery")
    attempt.add_argument("workspace")
    attempt.add_argument("--path", required=True)
    attempt.add_argument("--step", required=True)
    response_input = attempt.add_mutually_exclusive_group()
    response_input.add_argument("--response", default="")
    response_input.add_argument("--response-file")
    attempt.add_argument("--blocker", default="")
    attempt.add_argument("--artifact", action="append", default=[], help="Artifact reference only; not proof of inspection")
    attempt.add_argument("--work-origin", choices=["learner", "assisted", "reference", "unknown"], default="unknown")
    feedback_prepare = commands.add_parser("prepare-feedback", help="Import attempts and prepare an evidence-aware Agent review handoff")
    feedback_prepare.add_argument("workspace")
    feedback_prepare.add_argument("--attempts", help="An attempt, attempts list, or exported browser record")
    feedback_record = commands.add_parser("record-feedback", help="Validate Agent feedback, preserve history and rebuild the learning page")
    feedback_record.add_argument("workspace")
    feedback_record.add_argument("--file", required=True)
    source = commands.add_parser("import-video-learning", help="Read one discovery snapshot and its transcripts without modifying the library")
    source.add_argument("--db", required=True)
    source.add_argument("--discovery-id", required=True)
    source.add_argument("--out", required=True)
    discovery = commands.add_parser("discover", help="Experimental yt-dlp inventory for a YouTube/Bilibili channel tab or playlist")
    discovery.add_argument("--url", required=True)
    discovery.add_argument("--platform", choices=["youtube", "bilibili"], required=True)
    discovery.add_argument("--expected-count", type=int)
    discovery.add_argument("--out", required=True)
    for name in ("prepare", "status", "synthesis", "build"):
        command = commands.add_parser(name)
        command.add_argument("workspace")
        if name in {"synthesis", "build"}:
            command.add_argument("--allow-partial", action="store_true")
    attach = commands.add_parser("attach-transcript", help="Attach timestamped SRT, VTT or JSON evidence to an inventory item")
    attach.add_argument("workspace")
    attach.add_argument("--video", required=True)
    attach.add_argument("--file", required=True)
    attach.add_argument("--source", choices=["machine_transcript", "platform_subtitles", "human_transcript", "unknown"], required=True)
    nav_demo = commands.add_parser("demo-index", help="Build a fictional interactive knowledge map offline")
    nav_demo.add_argument("--out", default=".learning/demo-index")
    nav_demo.add_argument("--scenario", choices=["concept", "practice", "project", "comparison", "lookup"], default="concept")
    nav_demo.add_argument("--feedback", action="store_true", help="Include explicitly synthetic learner attempts and Agent feedback")
    demo = commands.add_parser("demo", help="Build a complete fictional example offline; no model or download required")
    demo.add_argument("--out", default=".learning/demo")
    index = commands.add_parser("build-index", help="Build a knowledge map and original-video index without full transcription")
    index.add_argument("--corpus", required=True)
    index.add_argument("--plan", required=True)
    index.add_argument("--learner", help="Current learner.json; required for v2 plans")
    index.add_argument("--out", required=True)
    usage = commands.add_parser("usage-record", help="Record provider-reported token usage or explicitly unknown usage")
    usage.add_argument("workspace")
    usage.add_argument("--stage", choices=STAGES, required=True)
    usage.add_argument("--provider", required=True)
    usage.add_argument("--model", required=True)
    usage.add_argument("--source", required=True)
    usage.add_argument("--basis", choices=["reported", "estimated", "unknown"], default="reported")
    for flag in ("input-tokens", "output-tokens", "cached-input-tokens"):
        usage.add_argument(f"--{flag}", type=int)
    usage.add_argument("--event-id")
    usage.add_argument("--video-ids", nargs="*", default=[])
    report = commands.add_parser("usage-report", help="Summarize source volume and stage-specific usage")
    report.add_argument("workspace")
    codex = commands.add_parser("usage-import-codex", help="Import an explicit session log's cumulative development counters without copying conversation content")
    codex.add_argument("workspace")
    codex.add_argument("--log", required=True)
    response = commands.add_parser("usage-import-response", help="Import saved provider counters even when content validation failed")
    response.add_argument("workspace")
    response.add_argument("--file", required=True)
    response.add_argument("--stage", choices=STAGES, required=True)
    response.add_argument("--event-id")
    response.add_argument("--video-ids", nargs="*", default=[])
    budget = commands.add_parser("estimate", help="Show a planning range with explicit assumptions; not a benchmark")
    budget.add_argument("--videos", type=int, required=True)
    budget.add_argument("--minutes", type=float, required=True, help="Total duration across all videos")
    budget.add_argument("--chars-per-minute", type=float, default=250)
    budget.add_argument("--token-ratio-low", type=float, default=0.5)
    budget.add_argument("--token-ratio-high", type=float, default=1.5)
    return result


def run(args):
    if args.command == "demo-index":
        from .demo import build_index_demo
        if args.feedback:
            from .scenarios import build_feedback_scenario
            out = build_feedback_scenario(args.scenario, args.out)
        else:
            out = build_index_demo(args.out, scenario=args.scenario)
        return {"index": str(out), "scenario": args.scenario, "synthetic_feedback": args.feedback,
                "source": "Fictional authored example; no model calls or real learner outcomes"}
    if args.command == "init-index":
        from .index_workflow import initialize_index
        return initialize_index(args.out, read_json(args.corpus), {
            "schema_version": 1, "goal": args.goal, "level": args.level, "language": args.language,
            "minutes_per_session": args.minutes, "mode": args.mode,
            "prior_knowledge": args.known, "constraints": args.constraint, "assumptions": args.assumption})
    if args.command == "prepare-index":
        from .index_workflow import prepare_index
        return prepare_index(args.workspace)
    if args.command == "record-attempt":
        from .feedback import record_attempt
        return record_attempt(args.workspace, path_id=args.path, step_id=args.step,
                              response=args.response, response_file=args.response_file,
                              blocker=args.blocker, artifact_refs=args.artifact, work_origin=args.work_origin)
    if args.command == "prepare-feedback":
        from .feedback import prepare_feedback
        return prepare_feedback(args.workspace, args.attempts)
    if args.command == "record-feedback":
        from .feedback import record_feedback
        return record_feedback(args.workspace, args.file)
    if args.command == "build-index":
        out = build_index(read_json(args.corpus), read_json(args.plan), args.out,
                          learner=read_json(args.learner) if args.learner else None)
        design = read_json(out / "learning-design.json")
        return {"index": str(out), "learning_design": str(out / "learning-design.json"),
                "planning_status": design["status"], "issues": design["issues"]}
    if args.command == "usage-import-response":
        return import_response_usage(args.workspace, args.file, stage=args.stage,
                                     event_id=args.event_id, video_ids=args.video_ids)
    if args.command == "usage-record":
        return record_usage(args.workspace, stage=args.stage, provider=args.provider, model=args.model, source=args.source,
                            basis=args.basis, input_tokens=args.input_tokens, output_tokens=args.output_tokens,
                            cached_input_tokens=args.cached_input_tokens, event_id=args.event_id, video_ids=args.video_ids)
    if args.command == "usage-report":
        return usage_report(args.workspace)
    if args.command == "usage-import-codex":
        return import_codex_usage(args.workspace, args.log)
    if args.command == "estimate":
        return estimate(videos=args.videos, minutes=args.minutes, chars_per_minute=args.chars_per_minute,
                        token_ratio_low=args.token_ratio_low, token_ratio_high=args.token_ratio_high)
    if args.command == "init":
        return initialize(args.out, read_json(args.corpus), {"goal": args.goal, "level": args.level,
                          "language": args.language, "minutes_per_session": args.minutes}, args.max_chars)
    if args.command in {"import-video-learning", "discover"}:
        require(not Path(args.out).exists(), f"Output already exists; select a new snapshot path: {args.out}")
        corpus = (import_video_learning(args.db, args.discovery_id) if args.command == "import-video-learning"
                  else discover(args.url, args.platform, args.expected_count))
        write_json(args.out, corpus)
        return {"corpus": str(Path(args.out).resolve()), "inventory_count": len(corpus["videos"]), "discovery": corpus["discovery"]}
    if args.command == "status":
        return inspect(args.workspace)[-1]
    if args.command == "prepare":
        return prepare(args.workspace)
    if args.command == "attach-transcript":
        return attach_transcript(args.workspace, args.video, args.file, args.source)
    if args.command == "synthesis":
        data = synthesize(args.workspace, allow_partial=args.allow_partial)
        return {"path": str((Path(args.workspace) / "synthesis.json").resolve()), "input_hash": data["input_hash"], "claim_count": len(data["claims"])}
    if args.command == "build":
        return {"pack": str(render(args.workspace, allow_partial=args.allow_partial).resolve())}
    if args.command == "demo":
        from .demo import build_demo
        return {"pack": str(build_demo(args.out).resolve()), "source": "Fictional authored example; no real creator analyzed"}


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except (ContractError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
