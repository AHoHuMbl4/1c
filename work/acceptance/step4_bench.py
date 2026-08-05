#!/usr/bin/env python3
"""ПРИБОР ШАГА 4: какую сущность выбрал живой сервис — и ошибся ли он.

Зачем отдельный прибор. Мерило владельца 03.08 — **число ОШИБОК, цель ноль**; уточнение и
отказ ошибкой не считаются. Приёмка через бота меряет весь путь сразу, стоит дороже и
несёт разброс ±1-3 ответа из десяти. Здесь меряется ТОЛЬКО шаг 4: какая сущность стала
`diag.focus` и совпала ли она с эталонной сущностью набора.

Что делает:
  1. берёт пары «вопрос → эталонная сущность» ИЗ ПРИЁМОЧНОГО НАБОРА (разбор один на все
     приборы — `entity_choice_bench.pairs`);
  2. зовёт ЖИВОЙ сервис ответов `POST /ask` — то есть настоящие шаги 1-7, а не их копию;
  3. разносит исход по четырём классам и печатает сводку по мерилу владельца — счёту
     неверных ответов при цели ноль;
  4. кладёт построчную выкладку (`DUMP=<файл>`), чтобы два прогона сравнивались
     поимённо, а не только счётом.

Классы исхода:
  ВЕРНО    — ответ дан, и выбранная сущность из семьи эталона;
  НЕВЕРНО  — ответ дан, но сущность чужая. ЭТО И ЕСТЬ МЕРИЛО, его считаем;
  СПРОСИЛ  — система вернула уточнение (`kind=clarify`). По мерилу не ошибка;
  ОТКАЗ    — `no_data` / пустой ответ. Не ошибка, но и не польза (п. 21).

🔴 ЧЕСТНЫЕ ГРАНИЦЫ — читать до того, как ссылаться на числа.
1. **Это НЕ замер качества ответов.** Прямой вызов `/ask` минует бота и перефразирование
   по вики, и по `HOW_NOT_TO §1.30` качество ответов им не меряют. Здесь он законен
   ровно потому, что меряется другое: вход шага 4 фиксирован текстом вопроса, а значит два
   прогона сравнимы между собой.
2. **Ответ модели не детерминирован.** `REPEAT=<n>` гоняет каждый вопрос n раз и печатает
   разброс. Сравнение прогонов без знания разброса ничего не значит (`HOW_NOT_TO §1.34`).
3. **Прогон платный** — каждый вопрос это несколько вызовов модели ответов.
4. Табличная часть засчитывается за свой документ (`search_tables.parent`), как и в
   соседних приборах: шапка против строк — не та ошибка, которую меряет шаг 4.

Использование:
    sg 1c-secrets -c 'set -a; . /etc/1c-serene-ask.env; set +a; \
        SERENEDB_DSN_RO="host=… dbname=ut_test" \
        DUMP=work/acceptance/runs/<метка>.tsv \
        python3 work/acceptance/step4_bench.py [от] [до]'
Окружение: ASK_TOKEN (обязателен), ASK_URL (умолчание http://127.0.0.1:8099),
           SERENEDB_DSN_RO — для таблицы родства.
"""
import importlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = os.environ.get("SET_FILE", os.path.join(ROOT, "docs/ACCEPTANCE_UT.md"))
ASK_URL = os.environ.get("ASK_URL", "http://127.0.0.1:8099").rstrip("/")
ASK_TOKEN = os.environ.get("ASK_TOKEN", "")
REPEAT = int(os.environ.get("REPEAT", "1"))
TIMEOUT = int(os.environ.get("ASK_TIMEOUT", "600"))

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Границы диапазона снимаются ДО подмены sys.argv: `entity_choice_bench` читает набор из
# sys.argv[1] на импорте, и без подмены он разобрал бы как набор наш собственный аргумент.
ARGS = sys.argv[1:]
sys.argv = [sys.argv[0], SET_FILE]
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

A = importlib.import_module("serene_ask")
B = importlib.import_module("entity_choice_bench")

if not ASK_TOKEN:
    sys.exit("не задан ASK_TOKEN — сервис ответов отвечает 401")


def ask(question):
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(ASK_URL + "/ask", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + ASK_TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"kind": "http_%d" % e.code, "diag": {}}
    except Exception as e:                       # noqa: BLE001 — сеть/таймаут
        return {"kind": "сбой: %s" % str(e)[:40], "diag": {}}


def verdict(out, want_family, fam_of):
    # 🔴 СБОЙ ПРОВЕРЯЕТСЯ ПЕРВЫМ, И ЭТО НЕ ПОРЯДОК РАДИ ПОРЯДКА. В первой редакции условие
    # «нет выбранной сущности → ОТКАЗ» стояло выше проверки вида ответа, и когда у модели
    # ответов кончился баланс (`HTTP 402`, сервис честно отдаёт 503), прибор записал все
    # 44 вопроса как «ОТКАЗ» за одну секунду — то есть выдал сломанный прогон за
    # осмысленный замер. Различать «система отказалась» и «замер не состоялся» — то самое,
    # на чём уже спотыкались (§0 `HOW_NOT_TO`, сломанный прибор приёмки 02.08).
    kind = out.get("kind") or "?"
    got = (out.get("diag") or {}).get("focus") or ""
    if kind not in ("answer", "figures", "clarify", "no_data"):
        return "СБОЙ", got
    if kind == "clarify":
        return "СПРОСИЛ", got
    if kind == "no_data" or not got:
        return "ОТКАЗ", got
    return ("ВЕРНО" if fam_of.get(got, got) == want_family else "НЕВЕРНО"), got


def main():
    pairs = B.pairs(SET_FILE)
    lo = int(ARGS[0]) if len(ARGS) > 0 else 1
    hi = int(ARGS[1]) if len(ARGS) > 1 else len(pairs)
    pairs = pairs[lo - 1:hi]
    fam_of = {}
    for r in A.psql("SELECT src_table, coalesce(nullif(parent,''), src_table) "
                    "FROM %s" % A.TABLES):
        if r and r[0]:
            fam_of[r[0]] = r[1]

    dump = open(os.environ["DUMP"], "w", encoding="utf-8") if os.environ.get("DUMP") else None
    tally = {}
    per_q = []
    t_start = time.time()
    for i, (q, want) in enumerate(pairs, lo):
        wf = fam_of.get(want, want)
        seen = []
        for _ in range(REPEAT):
            t0 = time.time()
            out = ask(q)
            v, got = verdict(out, wf, fam_of)
            d = out.get("diag") or {}
            # Признаки, которыми шаг 4 сам себя проверяет. Нужны, чтобы отличить
            # «ошиблись молча» от «ошиблись, но защита сработала».
            flags = [n for n, k in (("расхождение", "signals_disagree"),
                                    ("арбитр-детектор", "arbiter_detected"),
                                    ("арбитр", "arbiter"),
                                    ("смысл принёс", "by_meaning"),
                                    ("выбор без опоры", "unsupported_pick")) if d.get(k)]
            seen.append((v, got, round(time.time() - t0, 1), ",".join(flags)))
            tally[v] = tally.get(v, 0) + 1
        per_q.append((i, q, want, seen))
        v0, got0, sec0, fl0 = seen[0]
        mark = "🔴" if any(s[0] == "НЕВЕРНО" for s in seen) else "  "
        print("%s %2d. %-44s %-8s %-38s %4.0fс %s"
              % (mark, i, q[:44], v0, got0[:38], sec0, fl0), flush=True)
        if REPEAT > 1 and len({s[0] for s in seen}) > 1:
            print("      ⚠ разброс между повторами: %s" % ", ".join(s[0] for s in seen))
        if dump:
            for v, got, sec, fl in seen:
                dump.write("%d\t%s\t%s\t%s\t%s\t%s\n" % (i, q, want, got, v, fl))
    if dump:
        dump.close()

    n = sum(tally.values())
    print("\n" + "=" * 74)
    print("МЕРИЛО ВЛАДЕЛЬЦА: СЧЁТ НЕВЕРНЫХ, ЦЕЛЬ НОЛЬ — вопросов %d, прогонов %d, %.0f мин"
          % (len(pairs), n, (time.time() - t_start) / 60.0))
    print("  🔴 НЕВЕРНО (цель — ноль) : %d" % tally.get("НЕВЕРНО", 0))
    for k in ("ВЕРНО", "СПРОСИЛ", "ОТКАЗ", "СБОЙ"):
        if tally.get(k):
            print("     %-8s             : %d" % (k, tally[k]))
    bad = [(i, q, want, seen) for i, q, want, seen in per_q
           if any(s[0] == "НЕВЕРНО" for s in seen)]
    if bad:
        print("\nНЕВЕРНО выбранная сущность (вопрос → что взяли / эталон):")
        for i, q, want, seen in bad:
            got = next(s[1] for s in seen if s[0] == "НЕВЕРНО")
            fl = next(s[3] for s in seen if s[0] == "НЕВЕРНО")
            print("  %2d. %s\n      взято: %s\n      эталон: %s\n      защита: %s"
                  % (i, q[:66], got, want, fl or "не сработала ни одна"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
