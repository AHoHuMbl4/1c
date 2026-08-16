#!/usr/bin/env python3
"""ПРОВЕРКА ПРОГОНА САМОПРОВЕРКИ: достижимость сущности и верность атома.

План `docs/PLAN_ANSWER_CONTRACT.md` §4, замок 17 (§10): слепое пятно — ЧИСЛО
на каждой базе, рост метрики — брак.

(а) ДОСТИЖИМОСТЬ: породившая сущность совпала с `diag.focus` ответа или вошла
    в варианты уточнения (`options[].src`).
(б) ВЕРНОСТЬ АТОМА: число ответа (`figures.count` / `figures.sum`, а в ветке
    clarify со встречным вопросом — `totals[величина].sum`) сверяется с прямым
    пересчётом по корпусу ТОЙ ЖЕ формулой, что `aggregate` в `serene_ask.py`
    (папки отбрасываются признаком платформы `IsFolder`, сложение — точное
    `DECIMAL(38,10)`). Правду считает SQL, не модель (фаза 4 PLAN_AUTONOMY).

Классы исходов (каждый промах — поимённо, с классом причины):
  ok               — достигнута и атом сошёлся (или считать нечего);
  не выбрана       — ответ ушёл по ДРУГОЙ сущности (focus ≠ породившая);
  не достигнута    — ни focus, ни варианты уточнения не содержат сущность;
  отказ при данных — сущность выбрана, данные есть, а ответ «данных нет» (п. 21);
  не та величина   — сущность та, но посчитана другая величина;
  атом не объявлен — ответ есть, а числа для сверки в нём нет;
  атом не сошёлся  — число ответа ≠ прямой пересчёт;
  пустая сущность  — в корпусе нет строк, честный «нет данных» (не промах,
                     но и не доказательство достижимости);
  сбой             — HTTP/таймаут/недоступность сервиса.

Метрика на базу: доля недостижимых сущностей (с данными) и доля неверных
атомов из проверенных.

Использование:
    ASK_BASE=ut_test python3 work/acceptance/selftest_check.py

Пишет:
  work/acceptance/runs/selftest-<база>-truth.json   — кэш прямого пересчёта;
  work/acceptance/runs/selftest-<база>-report.json  — метрики и расклад классов;
  work/acceptance/selftest-misses-<база>.jsonl      — регресс-набор промахов.
"""
import json
import os
import sys
from decimal import Decimal, InvalidOperation

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE = os.environ.get("ASK_BASE") or (sys.argv[1] if len(sys.argv) > 1 else "ut_test")
RUNS = os.path.join(ROOT, "work", "acceptance", "runs")
# SELFTEST_* — ярус 2 (tier2) не затирает полный набор / старые отчёты.
LIST = os.environ.get("SELFTEST_LIST") or os.path.join(RUNS, "selftest-%s.jsonl" % BASE)
RESULTS = os.environ.get("SELFTEST_OUT") or os.path.join(RUNS, "selftest-%s-results.jsonl" % BASE)
TRUTH = os.environ.get("SELFTEST_TRUTH") or os.path.join(RUNS, "selftest-%s-truth.json" % BASE)
REPORT = os.environ.get("SELFTEST_REPORT") or os.path.join(RUNS, "selftest-%s-report.json" % BASE)
MISSES = os.environ.get("SELFTEST_MISSES") or os.path.join(
    ROOT, "work", "acceptance", "selftest-misses-%s.jsonl" % BASE)

# Та же формула, что `aggregate` (serene_ask.py): папка — не запись, признак —
# реквизит платформы IsFolder из типизированной карты flags.
NF = "NOT coalesce(map_extract_value(flags, 'IsFolder'), false)"
# Сравнение сумм — до копейки: ответ сервиса отдаёт float, пересчёт — DECIMAL.
SUM_TOL = Decimal("0.01")


def load_env(path):
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-mcp-reports.env")

sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
import serene_ask as A  # noqa: E402


def build_ts():
    try:
        r = A.psql("SELECT coalesce(max(v),0) FROM search_quality WHERE k='build_ts'")
        return int(float(r[0][0])) if r and r[0] else 0
    except RuntimeError:
        return 0


def compute_truth():
    """Прямой пересчёт по корпусу двумя проходами: счёты по сущностям и суммы
    по (сущность, величина). Та же арифметика, что у aggregate."""
    counts = {}
    for r in A.psql("SELECT src_table, count(*) FILTER (WHERE %(nf)s), "
                    "count(*) FILTER (WHERE NOT (%(nf)s)) "
                    "FROM %(c)s GROUP BY src_table" % {"nf": NF, "c": A.CORPUS}):
        if r and r[0]:
            counts[r[0]] = [int(r[1] or 0), int(r[2] or 0)]
    sums = {}
    q = ("SELECT src_table, struct_extract(x,'key'), "
         "sum(TRY_CAST(x.value AS DECIMAL(38,10))) FILTER (WHERE %(nf)s), "
         "count(TRY_CAST(x.value AS DECIMAL(38,10))) FILTER (WHERE %(nf)s) "
         "FROM %(c)s, unnest(map_entries(nums)) AS u(x) "
         "WHERE nums IS NOT NULL GROUP BY 1, 2" % {"nf": NF, "c": A.CORPUS})
    for r in A.psql(q):
        if r and r[0] and len(r) > 1 and r[1]:
            sums["%s\tsum\t%s" % (r[0], r[1])] = r[2] if r[2] != "" else None
            sums["%s\tn\t%s" % (r[0], r[1])] = int(r[3] or 0)
    truth = {"build_ts": build_ts(), "counts": counts, "sums": sums}
    with open(TRUTH, "w", encoding="utf-8") as fh:
        json.dump(truth, fh, ensure_ascii=False)
    return truth


def load_truth():
    try:
        with open(TRUTH, encoding="utf-8") as fh:
            t = json.load(fh)
        if t.get("build_ts") == build_ts():
            return t
    except (OSError, ValueError):
        pass
    return compute_truth()


def dec(v):
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


def sum_equal(got, want):
    """Сошлась ли сумма: want — строка DECIMAL из пересчёта или None (нечего
    считать); got — число из ответа сервиса."""
    if want is None:
        return got is None
    if got is None:
        return False
    g, w = dec(got), dec(want)
    return g is not None and w is not None and abs(g - w) <= SUM_TOL


def classify(rec, res, truth):
    """Класс исхода одного вопроса + (достигнута?, атом проверен?, атом верен?)."""
    if res.get("http") != 200 or res.get("error"):
        return "сбой", False, False, False, {}
    src, kind = rec["src_table"], res.get("kind")
    focus, options = res.get("focus"), res.get("options") or []
    reached = (focus == src) or (src in options)
    n_rows = (truth["counts"].get(src) or [0, 0])[0]
    detail = {}
    if rec["qkind"] == "count":
        expected = n_rows
        got = (res.get("figures") or {}).get("count")
    else:
        m = rec["measure"]
        expected = truth["sums"].get("%s\tsum\t%s" % (src, m))
        got = (res.get("figures") or {}).get("sum")
        if got is None:
            got = (res.get("totals") or {}).get(m)
        used = ((res.get("diag") or {}).get("measure"))
        if kind in ("answer", "figures") and focus == src and used and used != m:
            return "не та величина", True, False, False, {"measure_used": used}
    empty = (expected == 0) if rec["qkind"] == "count" else \
        (truth["sums"].get("%s\tn\t%s" % (src, rec["measure"]), 0) == 0)
    if kind in ("answer", "figures"):
        if focus != src:
            return "не выбрана", False, False, False, {"focus": focus}
        if got is None:
            if empty:
                return "пустая сущность", True, False, False, {}
            return "атом не объявлен", True, False, False, {}
        if rec["qkind"] == "count":
            ok = int(got) == expected
        else:
            ok = sum_equal(got, expected)
        detail = {"expected": expected, "got": got}
        return ("ok" if ok else "атом не сошёлся"), True, True, ok, detail
    if kind == "no_data":
        if focus == src and not empty:
            return "отказ при данных", True, False, False, {}
        if empty:
            return "пустая сущность", reached, False, False, {}
        return "не достигнута", reached, False, False, {"focus": focus}
    # clarify и прочие исходы: атом сверяем, если величина объявлена в totals.
    if got is not None and rec["qkind"] == "sum":
        ok = sum_equal(got, expected)
        detail = {"expected": expected, "got": got}
        if not ok:
            return "атом не сошёлся", reached, True, False, detail
        return "ok", reached, True, True, detail
    if empty:
        return "пустая сущность", reached, False, False, {}
    return ("ok" if reached else "не достигнута"), reached, False, False, \
        {"focus": focus}


def main():
    questions = {q["id"]: q for q in
                 (json.loads(line) for line in open(LIST, encoding="utf-8") if line.strip())}
    results = {}
    for line in open(RESULTS, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            results[r["id"]] = r  # повтор прогона — свежая запись сильнее
    truth = load_truth()
    classes = {}
    misses = []
    ents, ents_data, ents_reached = {}, {}, set()
    atoms_checked = atoms_wrong = 0
    secs = []
    for qid, rec in sorted(questions.items()):
        res = results.get(qid)
        if not res:
            continue
        cls, reached, checked, atom_ok, detail = classify(rec, res, truth)
        classes[cls] = classes.get(cls, 0) + 1
        if res.get("sec"):
            secs.append(res["sec"])
        src = rec["src_table"]
        ents[src] = ents.get(src, False) or reached
        if (truth["counts"].get(src) or [0])[0] > 0:
            ents_data[src] = ents_data.get(src, False) or reached
            if reached:
                ents_reached.add(src)
        if checked:
            atoms_checked += 1
            atoms_wrong += 0 if atom_ok else 1
        if cls not in ("ok", "пустая сущность"):
            misses.append(dict({"id": qid, "class": cls, "src_table": src,
                                "label": rec["label"], "question": rec["question"],
                                "kind": res.get("kind"), "focus": res.get("focus"),
                                "options": res.get("options"),
                                "text": res.get("text"), "error": res.get("error")},
                               **detail))
    with open(MISSES, "w", encoding="utf-8") as fh:
        for m in misses:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    n_data = len(ents_data)
    unreachable = sorted(s for s, ok in ents_data.items() if not ok)
    report = {
        "base": BASE,
        "build_ts": truth.get("build_ts"),
        "questions_total": len(questions),
        "answered": len(results),
        "entities": len(ents),
        "entities_with_data": n_data,
        "entities_reached": len(ents_reached),
        "unreachable_share": (round(len(unreachable) / n_data, 4) if n_data else None),
        "unreachable_entities": unreachable,
        "atoms_checked": atoms_checked,
        "atoms_wrong": atoms_wrong,
        "wrong_atom_share": (round(atoms_wrong / atoms_checked, 4)
                             if atoms_checked else None),
        "classes": dict(sorted(classes.items(), key=lambda kv: -kv[1])),
        "sec_median": (sorted(secs)[len(secs) // 2] if secs else None),
    }
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in report.items() if k != "unreachable_entities"},
                     ensure_ascii=False, indent=2, sort_keys=True))
    print("промахов: %d -> %s" % (len(misses), MISSES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
