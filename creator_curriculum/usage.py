"""Usage ledger: reported measurements, unknowns and planning estimates stay separate."""

from datetime import datetime, timezone
import math
from pathlib import Path
import uuid

from .core import (atomic_text, digest, identifier, obj, read_json, require, string,
                   validate_corpus, write_json)


STAGES = ("acquisition", "transcription", "extraction", "synthesis", "orchestration", "development")


def validate_event(event):
    obj(event, "usage event")
    identifier(event.get("id"), "usage.id")
    require(event.get("basis") in {"reported", "estimated", "unknown"}, "Invalid usage basis")
    require(event.get("stage") in STAGES, "Invalid usage stage")
    for field in ("provider", "model", "source", "recorded_at"):
        string(event.get(field), f"usage.{field}")
    for field in ("input_tokens", "output_tokens", "cached_input_tokens"):
        value = event.get(field)
        require(value is None or (type(value) is int and value >= 0), f"Invalid usage.{field}")
    if event["basis"] == "unknown":
        require(all(event.get(k) is None for k in ("input_tokens", "output_tokens", "cached_input_tokens")),
                "Unknown usage must not be recorded as zero")
    else:
        require(event.get("input_tokens") is not None and event.get("output_tokens") is not None,
                "Reported or estimated usage requires both input and output counts")
    if event.get("cached_input_tokens") is not None:
        require(event["cached_input_tokens"] <= event["input_tokens"], "Cached input is a subset of total input")
    return event


def record_usage(workspace, *, stage, provider, model, source, basis="reported", input_tokens=None,
                 output_tokens=None, cached_input_tokens=None, event_id=None, video_ids=None, replace=False):
    event = {"id": event_id or uuid.uuid4().hex, "stage": stage, "provider": provider, "model": model,
             "source": source, "basis": basis, "input_tokens": input_tokens, "output_tokens": output_tokens,
             "cached_input_tokens": cached_input_tokens, "video_ids": video_ids or [],
             "recorded_at": datetime.now(timezone.utc).isoformat()}
    validate_event(event)
    path = Path(workspace) / "usage" / "events" / f'{event["id"]}.json'
    require(replace or not path.exists(), f"Usage event already exists: {event['id']}; avoid double counting")
    write_json(path, event)
    return event


def import_codex_usage(workspace, log_path):
    """Only extracts aggregate counters from an explicitly supplied current-session log."""
    import json
    latest, model = None, "unknown"
    with Path(log_path).open(encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except ValueError:
                continue  # the active log may have a partially written final line
            payload = value.get("payload", {})
            if value.get("type") == "turn_context":
                model = payload.get("model") or model
            if value.get("type") == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info")
                if info and info.get("total_token_usage"):
                    latest = {"timestamp": value.get("timestamp"), **info["total_token_usage"]}
    require(latest is not None, "No reported token counters found in this session log")
    # Refreshing the same cumulative snapshot replaces its record instead of adding it again.
    return record_usage(workspace, stage="development", provider="Codex session", model=model,
                        source=f'Cumulative session counter through {latest["timestamp"]}; includes project development, research and orchestration; not a per-creator benchmark',
                        input_tokens=latest.get("input_tokens"), output_tokens=latest.get("output_tokens"),
                        cached_input_tokens=latest.get("cached_input_tokens"),
                        event_id=f"codex-session-{digest(str(Path(log_path).resolve()))[:24]}", replace=True)


def usage_report(workspace):
    root = Path(workspace)
    events = [validate_event(read_json(p)) for p in sorted((root / "usage" / "events").glob("*.json"))]
    groups = {}
    for event in events:
        key = f'{event["stage"]}:{event["basis"]}'
        group = groups.setdefault(key, {"events": 0, "input_tokens": 0, "output_tokens": 0,
                                       "cached_input_tokens": 0, "cache_breakdown_complete": True})
        group["events"] += 1
        if event["basis"] == "unknown":
            group.update(input_tokens=None, output_tokens=None, cached_input_tokens=None, cache_breakdown_complete=False)
            continue
        group["input_tokens"] += event["input_tokens"]
        group["output_tokens"] += event["output_tokens"]
        if event["cached_input_tokens"] is None:
            group["cache_breakdown_complete"] = False
        else:
            group["cached_input_tokens"] += event["cached_input_tokens"]
    for group in groups.values():
        if not group["cache_breakdown_complete"]:
            group["cached_input_tokens"] = None
        group["total_tokens"] = (group["input_tokens"] + group["output_tokens"]
                                 if group["input_tokens"] is not None else None)
        group["uncached_input_tokens"] = (group["input_tokens"] - group["cached_input_tokens"]
                                          if group["cached_input_tokens"] is not None else None)
    metrics = None
    if (root / "corpus.json").exists():
        corpus = validate_corpus(read_json(root / "corpus.json"))
        durations = [v["duration_seconds"] for v in corpus["videos"] if v["duration_seconds"] is not None]
        ready = [v for v in corpus["videos"] if v["status"] == "ready"]
        metrics = {"inventory_count": len(corpus["videos"]), "expected_count": corpus["discovery"]["expected_count"],
                   "discovery_status": corpus["discovery"]["status"], "known_duration_seconds": sum(durations),
                   "unknown_duration_count": len(corpus["videos"]) - len(durations),
                   "transcript_video_count": len(ready),
                   "transcript_known_duration_seconds": sum(v["duration_seconds"] for v in ready if v["duration_seconds"] is not None),
                   "transcript_unknown_duration_count": sum(v["duration_seconds"] is None for v in ready),
                   "transcript_characters": sum(len(s["text"]) for v in ready for s in v["segments"])}
    result = {"schema_version": 1, "metrics": metrics, "groups": groups, "events": events,
              "notes": ["Input tokens include cached input; cached tokens must not be added again.",
                        "Development/session usage is not attributable to individual videos.",
                        "No ledger entry is missing data, not zero consumption. Unknown calls prevent a complete cost claim.",
                        "ASR audio billing and vision/image usage may use different units; this ledger only records provided text token counters."]}
    write_json(root / "usage" / "summary.json", result)
    lines = ["# Token 用量记录", "实测、估算、未知按阶段分别列出。缓存输入已包含在输入中；项目开发成本不属于单个博主的处理成本。"]
    if metrics is not None:
        lines.append(f'清单 {metrics["inventory_count"]} 条；已知总时长 {metrics["known_duration_seconds"] / 60:.2f} 分钟；'
                     f'未知时长 {metrics["unknown_duration_count"]} 条。转写可用 {metrics["transcript_video_count"]} 条，'
                     f'对应已知时长 {metrics["transcript_known_duration_seconds"] / 60:.2f} 分钟、'
                     f'{metrics["transcript_characters"]} 字符。')
    table = ["| 阶段 / 依据 | 输入 token | 其中缓存 | 输出 token | 总 token |", "| --- | ---: | ---: | ---: | ---: |"]
    def display(value):
        return "未知" if value is None else f"{value:,}"
    for key, group in groups.items():
        table.append(f'| {key} | {display(group["input_tokens"])} | {display(group["cached_input_tokens"])} | '
                     f'{display(group["output_tokens"])} | {display(group["total_tokens"])} |')
    lines.append("\n".join(table))
    if not groups:
        lines.append("尚无计量事件；不代表用量为零。")
    lines.extend(["", "完整来源和快照截止时间见 [summary.json](summary.json)。音频、视觉和未返回 usage 的调用不能由本表自动推算费用。"])
    atomic_text(root / "usage" / "report.md", "\n\n".join(lines) + "\n")
    return result


def estimate(*, videos, minutes, chars_per_minute=250, token_ratio_low=0.5, token_ratio_high=1.5,
             max_chars=12000, prompt_tokens=1200, note_tokens=800, synthesis_prompt=2000, course_tokens=6000):
    require(type(videos) is int and videos > 0, "videos must be positive")
    for value in (minutes, chars_per_minute, token_ratio_low, token_ratio_high, max_chars,
                  prompt_tokens, note_tokens, synthesis_prompt, course_tokens):
        require(type(value) in (int, float) and math.isfinite(value) and value > 0, "All estimate assumptions must be finite and positive")
    require(token_ratio_low <= token_ratio_high, "Token ratio bounds are reversed")
    chars = math.ceil(minutes * chars_per_minute)
    jobs = videos * math.ceil(chars / videos / max_chars)
    extraction_output = jobs * note_tokens
    synthesis_input = extraction_output + synthesis_prompt
    bounds = []
    for ratio in (token_ratio_low, token_ratio_high):
        extraction_input = math.ceil(chars * ratio) + jobs * prompt_tokens
        bounds.append({"extraction_input": extraction_input, "extraction_output": extraction_output,
                       "synthesis_input": synthesis_input, "synthesis_output": course_tokens,
                       "total_tokens": extraction_input + extraction_output + synthesis_input + course_tokens})
    return {"basis": "planning_estimate_not_measured", "videos": videos, "total_minutes": minutes,
            "assumed_characters": chars, "assumed_jobs": jobs, "low": bounds[0], "high": bounds[1],
            "assumptions": {"characters_per_minute": chars_per_minute, "tokens_per_character": [token_ratio_low, token_ratio_high],
                            "chunk_characters": max_chars, "prompt_tokens_per_job": prompt_tokens,
                            "output_tokens_per_job": note_tokens, "synthesis_prompt_tokens": synthesis_prompt,
                            "curriculum_output_tokens": course_tokens,
                            "scope": "one extraction pass plus one synthesis pass; average video length; no retries, Agent history, cached-price differences, ASR or vision"}}
