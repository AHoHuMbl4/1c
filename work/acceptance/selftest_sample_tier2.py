#!/usr/bin/env python3
"""Стратифицированная выборка яруса 2: каждая 10-я деловая сущность.

Читает runs/selftest-<база>.jsonl, оставляет вопросы сущностей с индексами
0,10,20,… в отсортированном списке src_table. Детерминировано: два прогона
дают байт-в-байт один файл.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE") or (sys.argv[1] if len(sys.argv) > 1 else "ut_test")
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
SRC = os.path.join(RUNS, "selftest-%s.jsonl" % BASE)
OUT = os.path.join(RUNS, "selftest-%s-tier2.jsonl" % BASE)
STEP = int(os.environ.get("SELFTEST_SAMPLE_STEP", "10"))

def main():
    qs = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
    ents = sorted({q["src_table"] for q in qs})
    keep = set(ents[i] for i in range(0, len(ents), STEP))
    out = [q for q in qs if q["src_table"] in keep]
    with open(OUT, "w", encoding="utf-8") as fh:
        for q in out:
            fh.write(json.dumps(q, ensure_ascii=False, sort_keys=True) + "\n")
    print("%s: сущностей %d, выборка %d (шаг %d), вопросов %d -> %s"
          % (BASE, len(ents), len(keep), STEP, len(out), OUT))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
