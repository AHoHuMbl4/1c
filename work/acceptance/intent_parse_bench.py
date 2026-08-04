#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ПРИБОР: что шаг 1 (разбор вопроса) делает на настоящих вопросах.

Зачем. Шаг 1 — вход всего пути: `terms` идут в буквальный отбор, `kind` — в отбор по
смыслу и в выбор сущности, `measure` — в выбор величины, `period`/`amount` — в условия
SQL. Его выход не мерил ни один прибор: качество судили по конечному ответу, у которого
разброс ±1-2 верных из десяти, а вклад шага 1 в этот разброс был неизвестен.

Прибор зовёт РАБОЧУЮ функцию `serene_ask.parse_intent` — ту же, что исполняет сервис, а
не её копию. К базе он не ходит: шаг 1 видит только текст вопроса.

Что меряется, по вопросам приёмочного набора:

  1. УСТОЙЧИВОСТЬ — один и тот же вопрос разбирается `REPEATS` раз; расхождение хоть в
     одном поле считается неустойчивостью. Это нижняя граница разброса всего ответа:
     что разобрано по-разному, дальше и отбирается по-разному.
  2. ФОРМА — сколько разборов потребовали починки (`parse.fixed`) и у скольких потерялось
     условие вопроса (`parse.lost`). И то и другое считает код шага 1, а не прибор.
  3. ИНВАРИАНТЫ, проверяемые без знания базы:
     * род записей и имя величины не попали в `terms` — `terms` держат ЗНАЧЕНИЯ, что
       стоят в самой записи (имя контрагента, товар), и род записей там превращает
       отбор в поиск слова «продажа» по всем строкам;
  Отдельной строкой (⚠, не нарушение) — условия, которых нет в тексте цифрами: порог и
  границы периода. Так выглядит и законный разбор («с нулевой суммой» → порог 0), и
  придуманное условие, поэтому решение по ним остаётся за глазами, а не за прибором.
  Отдельными числами: у скольких вопросов расходятся прогоны внутри одного разбора
  (`parse.unstable`), у скольких условие домыслено (`parse.assumed`) и у скольких `kind`
  остался пустым — пустой `kind` не нарушение (вопрос «На какую сумму?» рода записей не
  называет), но шаги 3 и 4 остаются без «о чём вопрос», и это видно числом.

  Сверки «правильно ли понят вопрос» здесь нет намеренно: это потребовало бы моей
  разметки, а она мерила бы мои представления. Прибор меряет то, что проверяется
  механически, и показывает разбор целиком — чтобы разметку можно было сделать глазами.

Запуск (ключ модели — из окружения сервиса, в командную строку он не попадает):
    sg 1c-secrets -c 'ASK_ENV_FILES=/etc/1c-mcp-reports.env:/etc/1c-embed.env:\\
        /etc/1c-serene-ask-ut_test.env REPEATS=3 \\
        python3 work/acceptance/intent_parse_bench.py 1 58'

Окружение: ASK_ENV_FILES — файлы окружения сервиса через двоеточие (разбираются как
           systemd, см. `load_env`); REPEATS (умолчание 2); MEMO (умолчание 0 — память
           разобранных вопросов выключена, меряется согласие модели);
           ACCEPTANCE_DOC (умолчание docs/ACCEPTANCE_UT.md).
"""
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "ubuntu", "serenedb"))
os.environ.setdefault("ASK_TOKEN", "bench")


# 🔴 Через оболочку (`set -a; . файл`) эти файлы читаются неверно: значение с пробелами
# (`SERENEDB_DSN_RO=host=… port=… dbname=ut_test`) распадается по словам, и до кода
# доезжает `host=127.0.0.1` — прибор молча уходит в ДРУГУЮ базу на порт 5432 и меряет не
# то. Поймано пробой 04.08: `near_tables` отдавала пустые перечни на всех вопросах.
def load_env(paths):
    """Окружение сервиса — разбором `EnvironmentFile`, как это делает systemd."""
    for p in paths.split(":"):
        if not p:
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip()
            if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ[k.strip()] = v


if os.environ.get("ASK_ENV_FILES"):
    load_env(os.environ["ASK_ENV_FILES"])

import serene_ask as A  # noqa: E402

# 🔴 ПАМЯТЬ РАЗОБРАННЫХ ВОПРОСОВ ЗДЕСЬ ВЫКЛЮЧЕНА. В сервисе она делает повтор вопроса
# тождественным по построению — и прибор, меряющий устойчивость, показывал бы работу
# памяти, а не согласие модели. `MEMO=512` включает её обратно, чтобы проверить и её.
A.INTENT_MEMO = int(os.environ.get("MEMO", "0"))

DOC = os.environ.get("ACCEPTANCE_DOC", os.path.join(ROOT, "docs", "ACCEPTANCE_UT.md"))
# Разметка вопросов: что шаг 1 обязан вынуть из текста. Пустой путь — сверки нет, прибор
# меряет только устойчивость и форму.
CASES = os.environ.get("INTENT_CASES",
                       os.path.join(ROOT, "work", "acceptance", "intent_cases.tsv"))
REPEATS = int(os.environ.get("REPEATS", "2"))
FROM = int(sys.argv[1]) if len(sys.argv) > 1 else 1
TO = int(sys.argv[2]) if len(sys.argv) > 2 else 58
# Своя выборка вопросов — файлом по строке на вопрос. Нужна, чтобы мерить шаг 1 на базе,
# у которой приёмочного набора ещё нет.
QFILE = os.environ.get("QUESTIONS_FILE", "")

# Знаки, по которым слово вопроса сравнивается с термом: сравниваются только буквы и
# цифры в нижнем регистре. Списка слов здесь нет — язык вопроса любой.
_WORD = re.compile(r"[^\w]+", re.U)


def norm(s):
    return _WORD.sub(" ", (s or "").lower()).strip()


def questions():
    if QFILE:
        with open(QFILE, encoding="utf-8") as fh:
            qs = [l.strip() for l in fh if l.strip()]
        return list(enumerate(qs, 1))
    with open(DOC, encoding="utf-8") as fh:
        text = fh.read()
    out = [(int(n), q) for n, q in re.findall(r"^\*\*(\d+)\. «(.+?)»\*\*", text, re.M)]
    return [(n, q) for n, q in out if FROM <= n <= TO]


def digits(s):
    """Числа текста без разделителей разрядов: «1 137 949,71» → «113794971»."""
    return set(re.findall(r"\d+", (s or "").replace(" ", "").replace(" ", "")
                          .replace(",", "").replace(".", "")))


def invariants(q, d):
    """Разбор против инвариантов: (нарушения, условия не из текста вопроса).

    Нарушение — то, что противоречит устройству разбора и держится кодом (род записей
    или имя величины в `terms`). Условие «не из текста» нарушением не считается: «с
    нулевой суммой» законно даёт порог 0, хотя цифры 0 в вопросе нет. Оно печатается
    отдельно, потому что тем же способом выглядит и придуманное условие.
    """
    bad, derived = [], []
    named = {norm(x) for x in (d.get("kind"), d.get("measure")) if x}
    for group in d.get("terms") or []:
        for alt in group:
            if norm(alt) in named:
                bad.append("род записей или величина в terms: «%s»" % alt)
    qd = digits(q)
    amt = d.get("amount") or {}
    for key in ("value", "value2"):
        v = amt.get(key)
        if v is None:
            continue
        vs = ("%d" % v) if float(v) == int(v) else ("%s" % v).replace(".", "")
        if not any(vs in x or x in vs for x in qd):
            derived.append("порог %s цифрами не назван" % vs)
    for edge, val in (d.get("period") or {}).items():
        if not any(val[:4] in x for x in qd):
            derived.append("год периода %s (%s) не назван" % (val[:4], edge))
    return bad, derived


def cases():
    """Разметка вопросов из `intent_cases.tsv`: номер → ожидаемое от разбора."""
    out = {}
    try:
        with open(CASES, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return out
    for line in lines:
        if not line.strip() or line.startswith("#") or line.startswith("no\t"):
            continue
        p = line.split("\t")
        if len(p) < 7 or not p[0].strip().isdigit():
            continue
        out[int(p[0])] = dict(want=p[1].strip(), terms=p[2].strip(), period=p[3].strip(),
                              amount=p[4].strip(), measure=p[5].strip(), kind=p[6].strip())
    return out


def score(exp, d):
    """Расхождения разбора с разметкой вопроса. Пустой список — разобрано как сказано."""
    bad = []
    p = d.get("parse") or {}
    if exp["want"] != "*" and d.get("want") != exp["want"]:
        bad.append("want=%s, ожидалось %s" % (d.get("want"), exp["want"]))

    if exp["terms"] != "*":
        groups = d.get("terms") or []
        want_terms = [] if exp["terms"] == "-" else [w.strip() for w in exp["terms"].split(",")]
        flat = " | ".join(norm(a) for g in groups for a in g)
        for w in want_terms:
            if norm(w) not in flat:
                bad.append("в terms нет значения «%s»" % w)
        if len(groups) != len(want_terms):
            bad.append("понятий в terms %d, ожидалось %d" % (len(groups), len(want_terms)))

    if exp["period"] != "*":
        per = d.get("period") or {}
        got = "%s..%s" % (per.get("from", ""), per.get("to", "")) if per else "-"
        if exp["period"] == "-" and per:
            bad.append("период %s, вопрос его не называет" % got)
        elif exp["period"] == "~":
            if per and not p.get("assumed"):
                bad.append("период %s взят без пометки допущения" % got)
        elif exp["period"] not in ("-", "~") and got != exp["period"]:
            bad.append("период %s, ожидался %s" % (got, exp["period"]))

    if exp["amount"] != "*":
        amt = d.get("amount") or {}
        got = ("%s:%s" % (amt.get("op"), _fmt_num(amt.get("value")))) if amt else "-"
        if got != exp["amount"]:
            bad.append("порог %s, ожидался %s" % (got, exp["amount"]))

    if exp["measure"] == "+" and not d.get("measure"):
        bad.append("величина не названа, а вопрос её называет")
    if exp["measure"] == "-" and d.get("measure"):
        bad.append("названа величина «%s», а вопрос её не называет" % d.get("measure"))

    if exp["kind"] != "*":
        got = norm(d.get("kind"))
        if exp["kind"] == "-":
            if got:
                bad.append("kind=«%s», а вопрос рода записей не называет" % d.get("kind"))
        elif not got:
            bad.append("kind пуст, ожидалось одно из: %s" % exp["kind"])
        elif not any(s and s in got for s in (norm(x) for x in exp["kind"].split("|"))):
            bad.append("kind=«%s», ожидалось одно из: %s" % (d.get("kind"), exp["kind"]))
    return bad


def _fmt_num(v):
    if v is None:
        return ""
    return "%d" % v if float(v) == int(v) else ("%s" % v)


def key_of(d):
    """Сравнимый вид разбора: поля, которые задают работу шагов 2-5."""
    return json.dumps({k: d.get(k) for k in
                       ("terms", "kind", "measure", "want", "period", "amount", "about")},
                      ensure_ascii=False, sort_keys=True)


def main():
    if not A.DS_KEY:
        return "не задан DEEPSEEK_API_KEY — прибор зовёт ту же модель, что и сервис"
    qs = questions()
    if not qs:
        return "вопросов не найдено: %s" % (QFILE or DOC)
    today = time.strftime("%Y-%m-%d")
    unstable = lost = fixed = broken = failed = 0
    inner = assumed = nokind = mismatch = 0
    marks = cases()
    rows = []
    for no, q in qs:
        seen, first, err, sec, drafts = {}, None, None, 0.0, []
        for _ in range(REPEATS):
            t0 = time.time()
            try:
                d = A.parse_intent(q, today)
            except Exception as e:                  # noqa: BLE001 — сеть, модель, разбор
                err = "%s: %s" % (type(e).__name__, e)
                break
            sec += time.time() - t0
            k = key_of(d)
            seen[k] = seen.get(k, 0) + 1
            drafts.append(d)
            if first is None:
                first = d
        if err or first is None:
            failed += 1
            print("%2d %-52s 🔴 %s" % (no, q[:52], err))
            rows.append({"no": no, "q": q, "error": err})
            continue
        p = first.get("parse") or {}
        bad, derived = invariants(q, first)
        if len(seen) > 1:
            unstable += 1
        if p.get("lost"):
            lost += 1
        if p.get("fixed"):
            fixed += 1
        if p.get("unstable"):
            inner += 1
        if p.get("assumed"):
            assumed += 1
        if not first.get("kind"):
            nokind += 1
        if bad:
            broken += 1
        # Сверка с разметкой вопроса — по КАЖДОМУ повтору: «ноль ошибок устойчиво»
        # значит, что мимо разметки не ушёл ни один прогон, а не только первый.
        exp = marks.get(no)
        wrong = []
        if exp:
            for d in drafts:
                for b in score(exp, d):
                    if b not in wrong:
                        wrong.append(b)
            if wrong:
                mismatch += 1
        print("%2d %-52s %4.1fс %s" % (no, q[:52], sec / max(1, REPEATS),
                                       "устойчив" if len(seen) == 1 else "🔴 РАЗНЫЙ РАЗБОР"))
        print("   kind=%s | want=%s | measure=%s | terms=%s%s%s"
              % (first.get("kind"), first.get("want"), first.get("measure"),
                 json.dumps(first.get("terms"), ensure_ascii=False),
                 " | period=%s" % json.dumps(first.get("period"), ensure_ascii=False)
                 if first.get("period") else "",
                 " | amount=%s" % json.dumps(first.get("amount"), ensure_ascii=False)
                 if first.get("amount") else ""))
        if p.get("lost") or p.get("fixed") or p.get("assumed") or p.get("unstable"):
            print("   разбор: потеряно=%s починено=%s домыслено=%s разошлось=%s (прогонов %s)"
                  % (p.get("lost") or "—", p.get("fixed") or "—",
                     p.get("assumed") or "—", p.get("unstable") or "—",
                     p.get("samples")))
        for b in bad:
            print("   🔴 %s" % b)
        for b in wrong:
            print("   🔴 мимо разметки: %s" % b)
        for b in derived:
            print("   ⚠ %s" % b)
        if len(seen) > 1:
            for k, n in seen.items():
                print("   вариант ×%d: %s" % (n, k[:220]))
        rows.append({"no": no, "q": q, "parse": first, "variants": len(seen),
                     "invariants": bad, "derived": derived, "mismatch": wrong,
                     "sec": round(sec / max(1, REPEATS), 2)})

    n = len(qs)
    print("\nИТОГ по %d вопросам, повторов %d" % (n, REPEATS))
    print("  разбор не получен:            %d" % failed)
    print("  разный разбор при повторе:    %d" % unstable)
    print("  прогоны разошлись внутри:     %d" % inner)
    print("  потеряно условие вопроса:     %d" % lost)
    print("  форма чинилась кодом:         %d" % fixed)
    print("  условие домыслено:            %d" % assumed)
    print("  kind не заполнен:             %d" % nokind)
    print("  нарушен инвариант:            %d" % broken)
    if marks:
        print("  🔴 РАЗОБРАНО НЕ КАК СКАЗАНО:  %d из %d (разметка %s)"
              % (mismatch, len([1 for no, _ in qs if no in marks]),
                 os.path.basename(CASES)))
    out = os.environ.get("BENCH_OUT")
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"repeats": REPEATS, "rows": rows}, fh, ensure_ascii=False, indent=1)
        print("  разборы целиком:              %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
