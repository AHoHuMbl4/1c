#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Параллельность и латентность Qwen :8098 (локальный /ask, без бота).

BENCH_OUT — JSON с p50/p90 и прогоном parallel=4.
"""
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("BENCH_OUT", os.path.join(ROOT, "work", "acceptance", "runs",
                                                "qwen-latency-20260817.json"))
ASK_URL = os.environ.get("ASK_URL", "http://127.0.0.1:8098/ask")
TOKEN = os.environ.get("ASK_TOKEN", "")
TIMEOUT = int(os.environ.get("ASK_TIMEOUT", "600"))
QUESTIONS = [
    "На какую сумму мы продали товары в январе 2024?",
    "Сколько документов реализации за 2023 год?",
    "Какая сумма закупок у поставщика Ромашка?",
    "Сколько контрагентов в базе?",
]


def load_token():
    for p in ("/etc/1c-mcp-reports.env", "/etc/1c-serene-ask.env"):
        try:
            for line in open(p, encoding="utf-8"):
                if line.startswith("ASK_TOKEN="):
                    return line.split("=", 1)[1].strip().strip("\"'")
        except OSError:
            pass
    return TOKEN


def ask(q):
    body = json.dumps({"question": q}).encode()
    req = urllib.request.Request(ASK_URL, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + (TOKEN or load_token()))
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = json.loads(r.read().decode())
    return round(time.time() - t0, 2), data.get("kind"), (data.get("diag") or {}).get("tokens")


def pct(vals, p):
    if not vals:
        return 0.0
    s = sorted(vals)
    i = min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))
    return s[i]


def seq_run(qs):
    rows = []
    for q in qs:
        try:
            sec, kind, tok = ask(q)
            rows.append({"q": q, "sec": sec, "kind": kind, "tokens": tok, "ok": True})
        except Exception as e:  # noqa: BLE001
            rows.append({"q": q, "error": str(e)[:200], "ok": False})
    return rows


def par_run(qs, workers):
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ask, q): q for q in qs}
        for fut in as_completed(futs):
            q = futs[fut]
            try:
                sec, kind, tok = fut.result()
                rows.append({"q": q, "sec": sec, "kind": kind, "tokens": tok, "ok": True})
            except Exception as e:  # noqa: BLE001
                rows.append({"q": q, "error": str(e)[:200], "ok": False})
    return rows


def main():
    global TOKEN
    TOKEN = load_token()
    if not TOKEN:
        raise SystemExit("ASK_TOKEN не задан")
    seq = seq_run(QUESTIONS)
    secs = [r["sec"] for r in seq if r.get("ok")]
    par4 = par_run(QUESTIONS, 4)
    par_secs = [r["sec"] for r in par4 if r.get("ok")]
    report = {
        "ask_url": ASK_URL,
        "sequential": seq,
        "sequential_p50": pct(secs, 50),
        "sequential_p90": pct(secs, 90),
        "sequential_mean": round(statistics.mean(secs), 2) if secs else None,
        "parallel4": par4,
        "parallel4_p50": pct(par_secs, 50),
        "parallel4_p90": pct(par_secs, 90),
        "parallel4_max": max(par_secs) if par_secs else None,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("latency → %s" % OUT)
    print("seq p50=%.1fs p90=%.1fs | par4 p50=%.1fs p90=%.1fs max=%.1fs" % (
        report["sequential_p50"], report["sequential_p90"],
        report["parallel4_p50"], report["parallel4_p90"],
        report["parallel4_max"] or 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
