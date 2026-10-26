import argparse
import json
from pathlib import Path
import sys

from .adapters import discover, import_video_learning, parse_subtitles
from .core import ContractError, read_json, require, validate_corpus, write_json
from .pipeline import initialize, inspect, load_workspace, prepare, synthesize
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
    demo = commands.add_parser("demo", help="Build a complete fictional example offline; no model or download required")
    demo.add_argument("--out", default=".learning/demo")
    index = commands.add_parser("build-index", help="Build a knowledge map and original-video index without full transcription")
    index.add_argument("--corpus", required=True)
    index.add_argument("--plan", required=True)
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
        return {"index": str(build_index_demo(args.out)), "source": "Fictional authored example; no model calls"}
    if args.command == "build-index":
        return {"index": str(build_index(read_json(args.corpus), read_json(args.plan), args.out))}
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
        root, corpus, _, _ = load_workspace(args.workspace)
        video = next((v for v in corpus["videos"] if v["id"] == args.video), None)
        require(video is not None, f"Unknown video: {args.video}")
        video.update(segments=parse_subtitles(args.file), status="ready", reason="", transcript_source=args.source)
        validate_corpus(corpus)
        write_json(root / "corpus.json", corpus)
        return prepare(root)
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
