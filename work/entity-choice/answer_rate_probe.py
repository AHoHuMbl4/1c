#!/usr/bin/env python3
"""ПРИБОР ДОЛИ ОТВЕТОВ (п. 21): почему система не отдала то, что у неё было.

Зачем отдельно от `step4_bench.py`. Тот считает исходы (НЕВЕРНО / ВЕРНО / СПРОСИЛ /
ОТКАЗ) — этого хватает, чтобы сравнить две сборки, но не хватает, чтобы ВЫБРАТЬ форму
правила. Прогон приёмки платный и идёт больше получаса, а форм у правила «подтверждает ли
база выбор сущности» несколько. Поэтому здесь один прогон складывает ПОЛНЫЙ ответ сервиса
(вид, след, варианты уточнения) построчно в JSONL, и каждая форма считается по нему задним
числом — прибором `answer_rate_what_if.py`, без единого нового вызова модели.

Вердикт и обращение к сервису берутся у `step4_bench` как есть (`verdict`, `ask`): две
линейки на одно мерило неизбежно разойдутся, а разойдясь — обесценят сравнение.

🔴 Границы те же, что у `step4_bench` (читать их там): это не замер качества ответов,
ответ модели не детерминирован, прогон платный.

Использование:
    sg 1c-secrets -c 'set -a; . /etc/1c-mcp-reports.env; . /etc/1c-embed.env; \
        . /etc/1c-serene-ask-ut_test.env; set +a; ASK_URL=http://127.0.0.1:8199 \
        JSONL=work/acceptance/runs/<метка>.jsonl \
        python3 work/entity-choice/answer_rate_probe.py [от] [до]'
Окружение: как у `step4_bench.py`, плюс `JSONL` — куда класть полные ответы.
"""
import importlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "work/acceptance"))

S = importlib.import_module("step4_bench")       # линейка и обращение к сервису — оттуда
B = importlib.import_module("entity_choice_bench")
A = importlib.import_module("serene_ask")


def main():
    pairs = B.pairs(S.SET_FILE)
    args = [a for a in sys.argv[1:] if a.isdigit()]
    lo = int(args[0]) if args else 1
    hi = int(args[1]) if len(args) > 1 else len(pairs)
    pairs = pairs[lo - 1:hi]
    fam_of = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            fam_of[r[0]] = r[1]

    out_path = os.environ.get("JSONL")
    if not out_path:
        return "не задан JSONL — прибор существует ради полного следа, без него он лишний"
    fh = open(out_path, "w", encoding="utf-8")
    tally = {}
    t_start = time.time()
    for i, (q, want) in enumerate(pairs, lo):
        wf = fam_of.get(want, want)
        t0 = time.time()
        out = S.ask(q)
        v, got = S.verdict(out, wf, fam_of)
        tally[v] = tally.get(v, 0) + 1
        fh.write(json.dumps({"n": i, "вопрос": q, "эталон": want, "эталон_семья": wf,
                             "исход": v, "взято": got, "сек": round(time.time() - t0, 1),
                             "kind": out.get("kind"),
                             "options": out.get("options") or [],
                             "figures": out.get("figures"),
                             "diag": out.get("diag") or {}},
                            ensure_ascii=False) + "\n")
        fh.flush()
        print("%2d. %-44s %-8s %-38s %4.0fс"
              % (i, q[:44], v, got[:38], time.time() - t0), flush=True)
    fh.close()
    print("\nвопросов %d, %.0f мин: %s"
          % (len(pairs), (time.time() - t_start) / 60.0,
             ", ".join("%s %d" % kv for kv in sorted(tally.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
