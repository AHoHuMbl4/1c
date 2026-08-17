#!/usr/bin/env python3
"""Отчёт расхода OpenClaw по контурам за период (15–17.08 и далее).

Источники:
  - alias-usage.jsonl (branch/wiki после правки 17.08)
  - work/acceptance/runs/alias-bench-* (замеры 17.08, DeepSeek pro)
  - work/acceptance/runs/alias-agent-bench-* (если есть)

Usage шлюза в gateway.log не агрегируется — только agentMeta из --json.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "work" / "acceptance" / "runs"
DEFAULT_LOG = Path("/var/lib/serenedb/alias-usage.jsonl")


def day(ts: str) -> str:
    return (ts or "")[:10]


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def from_bench_runs(since: str, until: str) -> list[dict]:
    rows = []
    for p in sorted(RUNS.glob("alias-bench-*/*.json")):
        if p.name in ("summary.json",):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        ts = "2026-08-17T12:00:00Z"  # bench day
        if ts[:10] < since or ts[:10] > until:
            continue
        u = d.get("usage") or {}
        kind = d.get("kind") or "bench"
        contour = "branch" if kind == "branch" else ("wiki" if "wiki" in kind else "bench")
        rows.append({
            "ts": ts,
            "contour": contour,
            "model": d.get("model") or u.get("model"),
            "usage": u,
            "wall_ms": d.get("ms"),
            "cost_usd_est": _cost(u, d.get("model") or ""),
            "source": str(p.relative_to(ROOT)),
        })
    # overhead control
    oh = RUNS / "alias-bench-20260817-overhead" / "branch_chunk40.json"
    if oh.is_file():
        d = json.loads(oh.read_text())
        u = d.get("usage") or {}
        rows.append({
            "ts": "2026-08-17T10:00:00Z",
            "contour": "branch",
            "model": d.get("model"),
            "usage": u,
            "wall_ms": d.get("ms"),
            "cost_usd_est": _cost(u, d.get("model") or ""),
            "source": "alias-bench-overhead",
        })
    ctrl_path = RUNS / "alias-bench-20260817-overhead" / "control.msg"
    return rows


def _cost(u: dict, model: str) -> float:
    inp = float(u.get("input") or 0)
    out = float(u.get("output") or 0)
    cr = float(u.get("cache_read") or 0)
    m = (model or "").lower()
    if "vllm" in m or "qwen" in m:
        return 0.0
    if "pro" in m:
        return (inp * 0.14 + out * 0.84 + cr * 0.028) / 1_000_000
    if "flash" in m:
        return (inp * 0.14 + out * 0.28 + cr * 0.028) / 1_000_000
    return 0.0


def aggregate(rows: list[dict], since: str, until: str) -> dict:
    by = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0, "total": 0, "usd": 0.0, "ms": 0})
    for r in rows:
        d = day(r.get("ts", ""))
        if d and (d < since or d > until):
            continue
        key = (d or "unknown", r.get("contour", "?"), (r.get("model") or "?")[:40])
        u = r.get("usage") or {}
        b = by[key]
        b["calls"] += 1
        b["in"] += int(u.get("input") or 0)
        b["out"] += int(u.get("output") or 0)
        b["total"] += int(u.get("total") or 0)
        b["usd"] += float(r.get("cost_usd_est") or 0)
        b["ms"] += int(r.get("wall_ms") or 0)
    return dict(by)


def main() -> int:
    since = sys.argv[1] if len(sys.argv) > 1 else "2026-08-15"
    until = sys.argv[2] if len(sys.argv) > 2 else "2026-08-17"
    log_path = Path(os.environ.get("ALIAS_USAGE_LOG_PATH", str(DEFAULT_LOG)))

    rows = load_jsonl(log_path)
    rows.extend(from_bench_runs(since, until))
    agg = aggregate(rows, since, until)

    lines = [
        f"# Расход OpenClaw {since} … {until}",
        f"# Журнал: {log_path} ({len(load_jsonl(log_path))} строк)",
        "",
        "| день | контур | модель | вызовов | in | out | total tok | USD est | wall ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    tot_usd = 0.0
    for (d, contour, model), v in sorted(agg.items()):
        tot_usd += v["usd"]
        lines.append(
            f"| {d} | {contour} | {model} | {v['calls']} | {v['in']} | {v['out']} | "
            f"{v['total']} | {v['usd']:.4f} | {v['ms']} |"
        )
    lines.extend([
        "",
        f"**Итого USD est:** {tot_usd:.4f}",
        "",
        "## Примечания",
        "- **15–16.08:** шлюз usage не писал в файл; оценка по bench 17.08 (DeepSeek pro).",
        "- **Бот-диалоги:** gateway.log не агрегирует токены; нужен diagnostics или session jsonl undebot.",
        "- **vLLM словари:** cost=0; журнал alias-usage.jsonl с 17.08.",
    ])
    text = "\n".join(lines) + "\n"
    print(text, end="")
    report_path = ROOT / "work" / "acceptance" / "runs" / f"gateway-usage-{since.replace('-','')}-{until.replace('-','')}.json"
    report_path.write_text(
        json.dumps({"since": since, "until": until, "aggregate": {str(k): v for k, v in agg.items()}, "total_usd": tot_usd}, indent=2),
        encoding="utf-8",
    )
    md_path = report_path.with_suffix(".md")
    md_path.write_text(text, encoding="utf-8")
    print(f"JSON: {report_path}")
    print(f"MD: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
