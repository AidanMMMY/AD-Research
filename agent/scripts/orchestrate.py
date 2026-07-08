#!/usr/bin/env python3
"""orchestrate.py - AD-Research Tier-1 data collection orchestrator.

Maps a natural-language task description to one or more worker scripts, runs
them (via run_worker.sh or directly), and aggregates the normalized JSON output
into a single bundle.

Input:
    JSON via --task '...' or stdin:
        {
          "task":     "collect 24h China finance news + US sentiment",
          "keywords": ["NVDA", "宏观"],   # optional, currently unused for routing
          "hours":    24,                  # default 24
          "sources":  ["cls", "eastmoney_news", "xueqiu_hot", "reddit_finance"],  # optional
          "mode":     "docker",            # "docker" (run_worker.sh) or "local" (host python)
          "output":   "/data/ad-research/aggregate.json"
        }

Routing rules (in priority order):
    1. If --sources provided, use them verbatim.
    2. Otherwise, keyword-based:
        - mentions "CN"/"A股"/"财联社"/"东方财富" -> cls + eastmoney_news
        - mentions "xueqiu"/"雪球"               -> xueqiu_hot
        - mentions "reddit"/"WSB"/"wallstreetbets"-> reddit_finance
        - mentions "all" or empty                -> all 4
        - default                                -> cls + eastmoney_news

Output:
    Writes the aggregated list to args.output, plus per-source side files.

Usage:
    python orchestrate.py --task 'collect 24h CN news' --hours 24
    echo '{"task":"all","hours":24}' | python orchestrate.py --output /tmp/agg.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

WORKERS_DIR = Path("/root/ad-research/agent/workers")
RUN_WORKER = Path("/root/ad-research/agent/scripts/run_worker.sh")
OUTPUT_ROOT = Path("/data/ad-research")

WORKER_TO_SUBDIR = {
    "cls": "cls",
    "eastmoney_news": "eastmoney_news",
    "xueqiu_hot": "xueqiu",
    "reddit_finance": "reddit",
}

CN_PAT = re.compile(r"(cn|a股|财联社|东方财富|china|中文|沪深)", re.I)
XUEQIU_PAT = re.compile(r"(xueqiu|雪球)", re.I)
REDDIT_PAT = re.compile(r"(reddit|wsb|wallstreetbets|wall\s*street\s*bets)", re.I)
ALL_PAT = re.compile(r"(\ball\b|全部|所有)", re.I)


def pick_sources(task: str, hours: int, explicit: list[str] | None) -> list[str]:
    if explicit:
        unknown = [s for s in explicit if s not in WORKER_TO_SUBDIR]
        if unknown:
            raise SystemExit(f"unknown sources: {unknown}; valid: {list(WORKER_TO_SUBDIR)}")
        return explicit
    picked: set[str] = set()
    if ALL_PAT.search(task):
        picked.update(WORKER_TO_SUBDIR.keys())
    if CN_PAT.search(task):
        picked.update(["cls", "eastmoney_news"])
    if XUEQIU_PAT.search(task):
        picked.add("xueqiu_hot")
    if REDDIT_PAT.search(task):
        picked.add("reddit_finance")
    if not picked:
        picked.update(["cls", "eastmoney_news"])
    return sorted(picked)


def run_worker_docker(worker: str, hours: int, output_host: Path,
                      extra: list[str]) -> int:
    cmd = ["bash", str(RUN_WORKER), worker, str(output_host),
           "--hours", str(hours)] + extra
    print(f"[orch] $ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd)


def run_worker_local(worker: str, hours: int, output_host: Path,
                     extra: list[str]) -> int:
    script = WORKERS_DIR / f"{worker}.py"
    if not script.exists():
        print(f"[orch] worker not found: {script}", file=sys.stderr)
        return 1
    cmd = ["python3", str(script), "--hours", str(hours),
           "--output", str(output_host)] + extra
    print(f"[orch] $ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd)


def collect(workers: list[str], hours: int, mode: str,
            aggregate_path: Path) -> dict:
    summary: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hours": hours,
        "mode": mode,
        "results": {},
        "total_items": 0,
    }
    for w in workers:
        subdir = WORKER_TO_SUBDIR[w]
        out_path = OUTPUT_ROOT / subdir / "today.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        runner = run_worker_docker if mode == "docker" else run_worker_local
        rc = runner(w, hours, out_path, [])
        items: list[dict] = []
        err = None
        if rc == 0 and out_path.exists():
            try:
                items = json.loads(out_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                err = f"failed to parse {out_path}: {e}"
        elif rc != 0:
            err = f"worker exited {rc}"
        summary["results"][w] = {
            "exit_code": rc,
            "output_path": str(out_path),
            "item_count": len(items) if isinstance(items, list) else 0,
            "size_bytes": out_path.stat().st_size if out_path.exists() else 0,
            "error": err,
        }
        summary["total_items"] += summary["results"][w]["item_count"]
        print(f"[orch] {w}: rc={rc} items={summary['results'][w]['item_count']}",
              flush=True)
    aggregate_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[orch] aggregate -> {aggregate_path} ({aggregate_path.stat().st_size} bytes)")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AD-Research Tier-1 orchestrator")
    p.add_argument("--task", default="all",
                   help="natural-language task description (default: all)")
    p.add_argument("--hours", type=int, default=24,
                   help="time window in hours (default: 24)")
    p.add_argument("--sources", default="",
                   help="comma-separated worker names to force-run")
    p.add_argument("--mode", choices=["docker", "local"], default="docker",
                   help="execution mode (default: docker via run_worker.sh)")
    p.add_argument("--output", type=Path,
                   default=Path("/data/ad-research/aggregate.json"),
                   help="aggregate summary output path")
    p.add_argument("--stdin", action="store_true",
                   help="read task JSON from stdin instead of --task/--sources")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.stdin:
        raw = sys.stdin.read().strip()
        if not raw:
            print("[orch] --stdin but stdin empty", file=sys.stderr)
            return 64
        cfg = json.loads(raw)
        task = cfg.get("task", "all")
        hours = int(cfg.get("hours", args.hours))
        explicit = cfg.get("sources")
        mode = cfg.get("mode", args.mode)
        out = Path(cfg.get("output", args.output))
    else:
        task = args.task
        hours = args.hours
        explicit = [s.strip() for s in args.sources.split(",") if s.strip()] or None
        mode = args.mode
        out = args.output

    workers = pick_sources(task, hours, explicit)
    print(f"[orch] task={task!r} hours={hours} workers={workers} mode={mode}")
    summary = collect(workers, hours, mode, out)
    failed = [w for w, r in summary["results"].items() if r["exit_code"] != 0]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())