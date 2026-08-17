#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ШАГ 1 замера Qwen vLLM: механические ворота до прогона /ask.

Пишет JSON в BENCH_OUT (умолчание work/acceptance/runs/qwen-gates-20260817.json).

Запуск:
  set -a; . /etc/1c-embed.env; set +a
  export DEEPSEEK_BASE=https://a1f19thc-8000.thundercompute.net
  export DEEPSEEK_API_KEY=$EMBED_API_KEY DEEPSEEK_MODEL=Qwen3.8-27B
  export ASK_THINKING_OFF_BODY=1
  python3 work/acceptance/qwen_llm_gates.py
"""
import json
import os
import re
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
os.environ.setdefault("ASK_TOKEN", "bench")

import serene_ask as A  # noqa: E402

DOC = os.path.join(ROOT, "docs", "ACCEPTANCE_UT.md")
OUT = os.environ.get("BENCH_OUT", os.path.join(ROOT, "work", "acceptance", "runs",
                                                "qwen-gates-20260817.json"))
JSON_N = int(os.environ.get("GATE_JSON_N", "50"))
DET_Q = os.environ.get("GATE_DET_Q", "На какую сумму мы продали товары в январе 2024?")
DET_REP = int(os.environ.get("GATE_DET_REP", "5"))


def load_questions(n):
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read()
    qs = [q for _, q in re.findall(r"^\*\*(\d+)\. «(.+?)»\*\*", text, re.M)]
    return qs[:n]


def chat_raw(body):
    req = urllib.request.Request(A.DS_BASE + "/v1/chat/completions",
                                 data=json.dumps(body).encode(), method="POST")
    req.add_header("Authorization", "Bearer " + A.DS_KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "curl/8.5.0")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def gate_thinking():
    msgs = [{"role": "user", "content": "Reply with one word: OK"}]
    rows = []
    for label, extra in (("default", False), ("thinking_off", True)):
        body = {"model": A.DS_MODEL, "temperature": 0, "max_tokens": 64, "messages": msgs}
        if extra:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        t0 = time.time()
        try:
            data = chat_raw(body)
        except Exception as e:  # noqa: BLE001
            rows.append({"mode": label, "error": "%s: %s" % (type(e).__name__, e),
                         "sec": round(time.time() - t0, 2)})
            continue
        sec = round(time.time() - t0, 2)
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        usage = data.get("usage") or {}
        rows.append({
            "mode": label,
            "sec": sec,
            "content_len": len(msg.get("content") or ""),
            "reasoning_len": len(msg.get("reasoning_content") or ""),
            "reasoning_tokens": usage.get("reasoning_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "usage_keys": sorted(usage.keys()),
            "content_preview": (msg.get("content") or "")[:120],
            "reasoning_preview": (msg.get("reasoning_content") or "")[:120],
        })
    today = time.strftime("%Y-%m-%d")
    intent_rows = []
    for label, use_extra in (("default", False), ("thinking_off_body", True)):
        saved = A.ASK_THINKING_OFF_BODY
        A.ASK_THINKING_OFF_BODY = use_extra
        msgs = [{"role": "system", "content": A.INTENT_SYS},
                {"role": "user", "content": "today=%s\n\nQuestion: %s" % (today, DET_Q)}]
        body = A._ds_chat_body(msgs, max_tokens=400)
        if not use_extra:
            body.pop("extra_body", None)
        try:
            data = chat_raw(body)
        except Exception as e:  # noqa: BLE001
            intent_rows.append({"mode": label, "error": str(e)})
            A.ASK_THINKING_OFF_BODY = saved
            continue
        A.ASK_THINKING_OFF_BODY = saved
        raw = A._ds_chat_content(data) or ""
        blocks = A._json_blocks(raw)
        ok = False
        parsed = None
        if blocks:
            try:
                parsed = json.loads(blocks[0])
                ok = isinstance(parsed, dict) and "want" in parsed
            except ValueError:
                pass
        intent_rows.append({
            "mode": label,
            "raw_len": len(raw or ""),
            "json_blocks": len(blocks),
            "parse_ok": ok,
            "has_prose_outside_json": bool(raw and blocks and (
                raw.strip() != blocks[0] and not raw.strip().startswith("```"))),
            "parsed_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else [],
            "raw_head": (raw or "")[:200],
        })
    return {"simple_chat": rows, "parse_intent_probe": intent_rows}


def gate_json_discipline():
    A.INTENT_MEMO = 0
    A.INTENT_SAMPLES = 1
    A.INTENT_LEAD = 1
    today = time.strftime("%Y-%m-%d")
    qs = load_questions(JSON_N)
    valid = truncated = failed = 0
    rows = []
    for i, q in enumerate(qs, 1):
        t0 = time.time()
        err = None
        d = None
        try:
            d = A.parse_intent(q, today)
            valid += 1
        except Exception as e:  # noqa: BLE001
            err = "%s: %s" % (type(e).__name__, e)
            failed += 1
        sec = round(time.time() - t0, 2)
        p = (d or {}).get("parse") or {}
        if p.get("lost"):
            truncated += 1
        rows.append({"i": i, "q": q[:80], "sec": sec, "error": err,
                     "lost": p.get("lost"), "fixed": p.get("fixed")})
    return {
        "n": len(qs),
        "valid_rate": valid / max(1, len(qs)),
        "valid": valid,
        "failed": failed,
        "post_trim_lost": truncated,
        "rows": rows,
    }


def gate_determinism():
    A.INTENT_MEMO = 0
    A.INTENT_SAMPLES = 1
    A.INTENT_LEAD = 1
    today = time.strftime("%Y-%m-%d")
    keys = []
    for _ in range(DET_REP):
        d = A.parse_intent(DET_Q, today)
        keys.append(json.dumps({k: d.get(k) for k in
                                ("terms", "kind", "measure", "want", "period", "amount", "about")},
                               ensure_ascii=False, sort_keys=True))
    uniq = len(set(keys))
    return {"question": DET_Q, "repeats": DET_REP, "unique": uniq,
            "stable": uniq == 1, "variants": list(set(keys))}


def gate_usage_sample():
    body = A._ds_chat_body([{"role": "user", "content": "Say hi in JSON: {\"ok\":true}"}],
                           max_tokens=32)
    data = chat_raw(body)
    usage = data.get("usage") or {}
    msg = ((data.get("choices") or [{}])[0].get("message") or {})
    return {
        "usage": usage,
        "usage_keys": sorted(usage.keys()),
        "message_keys": sorted(msg.keys()),
        "diag_tokens_shape": A._TokenAcc().diag_dict() | {"calls": 0},
    }


def main():
    if not A.DS_KEY:
        raise SystemExit("DEEPSEEK_API_KEY не задан")
    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": A.DS_MODEL,
        "base": A.DS_BASE,
        "thinking_off_body": A.ASK_THINKING_OFF_BODY,
        "thinking": gate_thinking(),
        "json_discipline": gate_json_discipline(),
        "determinism": gate_determinism(),
        "usage_sample": gate_usage_sample(),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("gates → %s" % OUT)
    t = report["thinking"]["simple_chat"]
    print("thinking: default reasoning_len=%s off=%s" % (
        t[0]["reasoning_len"], t[1]["reasoning_len"]))
    j = report["json_discipline"]
    print("json: valid %d/%d (%.0f%%), lost=%d" % (
        j["valid"], j["n"], 100 * j["valid_rate"], j["post_trim_lost"]))
    d = report["determinism"]
    print("determinism: %d/%d unique" % (d["unique"], d["repeats"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
