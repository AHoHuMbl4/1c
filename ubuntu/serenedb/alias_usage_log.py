#!/usr/bin/env python3
"""Запись usage вызова openclaw agent в JSONL (контуры branch/wiki).

Читает stdout --json (файл ans), дописывает строку в журнал.
Умолчание ALIAS_USAGE_LOG=1; путь — ALIAS_USAGE_LOG_PATH или CSV_DIR/alias-usage.jsonl.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def extract_usage(resp: dict) -> dict:
    meta = resp.get("meta") or (resp.get("result") or {}).get("meta") or {}
    am = meta.get("agentMeta") or {}
    u = am.get("usage") or am.get("lastCallUsage") or {}
    return {
        "input": u.get("input"),
        "output": u.get("output"),
        "cache_read": u.get("cacheRead"),
        "cache_write": u.get("cacheWrite"),
        "total": u.get("total"),
        "model": am.get("model") or am.get("resolvedRef"),
        "provider": am.get("provider"),
        "duration_ms": meta.get("durationMs"),
    }


def cost_usd(usage: dict, provider: str, model: str) -> float:
    """Грубая оценка по прайсу deepseek из bench; vLLM = 0."""
    if provider == "vllm" or (model or "").startswith("Qwen"):
        return 0.0
    inp = float(usage.get("input") or 0)
    out = float(usage.get("output") or 0)
    cr = float(usage.get("cache_read") or 0)
    if "pro" in (model or ""):
        return (inp * 0.14 + out * 0.84 + cr * 0.028) / 1_000_000
    if "flash" in (model or ""):
        return (inp * 0.14 + out * 0.28 + cr * 0.028) / 1_000_000
    return 0.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--contour", required=True, choices=("branch", "wiki", "bench", "bot"))
    p.add_argument("--ans", required=True, help="файл stdout openclaw agent --json")
    p.add_argument("--model", default="")
    p.add_argument("--wall-ms", type=int, default=0)
    p.add_argument("--parsed", type=int, default=-1, help="строк разобрано (-1 неизвестно)")
    p.add_argument("--json-ok", type=int, default=-1)
    args = p.parse_args()

    if os.environ.get("ALIAS_USAGE_LOG", "1") == "0":
        return 0

    ans_path = Path(args.ans)
    usage: dict = {}
    if ans_path.is_file() and ans_path.stat().st_size:
        try:
            resp = json.loads(ans_path.read_text(encoding="utf-8"))
            usage = extract_usage(resp)
        except (json.JSONDecodeError, OSError):
            pass

    model = args.model or usage.get("model") or ""
    provider = usage.get("provider") or (model.split("/")[0] if "/" in model else "")
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "contour": args.contour,
        "model": model,
        "provider": provider,
        "usage": usage,
        "wall_ms": args.wall_ms,
        "parsed": args.parsed,
        "json_ok": args.json_ok,
        "cost_usd_est": round(cost_usd(usage, provider, model), 6),
    }
    log_dir = os.environ.get("CSV_DIR", "/var/lib/serenedb")
    log_path = Path(os.environ.get("ALIAS_USAGE_LOG_PATH", f"{log_dir}/alias-usage.jsonl"))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"alias_usage_log: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
