#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ШАГ 4 замера: 3 чанка branch_alias через ds_chat (шлюз бота не трогаем)."""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
sys.path.insert(0, os.path.join(ROOT, "work", "entity-choice"))

import alias_agent_bench as ab  # noqa: E402
import serene_ask as A  # noqa: E402

OUT = os.environ.get("BENCH_OUT", os.path.join(ROOT, "work", "acceptance", "runs",
                                                "qwen-branch-chunks-20260817.json"))
CHUNKS = int(os.environ.get("BRANCH_CHUNKS", "3"))
PROMPT_HEAD = ab.BRANCH_PROMPT_HEAD


def main():
    results = []
    for i in range(1, CHUNKS + 1):
        pay, _ = ab.branch_payload(batch=i, src_chunk=40)
        if not pay:
            results.append({"chunk": i, "error": "empty payload", "sec": 0})
            continue
        payload = PROMPT_HEAD + json.dumps(pay, ensure_ascii=False)
        t0 = time.time()
        raw = A.ds_chat([{"role": "user", "content": payload}], max_tokens=900)
        sec = round(time.time() - t0, 2)
        blocks = A._json_blocks(raw or "")
        ok = False
        if blocks:
            try:
                ok = isinstance(json.loads(blocks[0]), dict)
            except ValueError:
                pass
        results.append({"chunk": i, "forks": len(pay), "sec": sec,
                        "json_ok": ok, "raw_len": len(raw or "")})
    total = sum(r.get("sec", 0) for r in results)
    report = {"chunks": CHUNKS, "total_sec": total,
              "mean_sec": round(total / max(1, len(results)), 2),
              "model": A.DS_MODEL, "rows": results}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("branch chunks → %s (total %.0fs)" % (OUT, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
