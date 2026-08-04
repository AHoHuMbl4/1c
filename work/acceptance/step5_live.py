#!/usr/bin/env python3
"""ЖИВОЙ ЗАМЕР ШАГА 5 «СЧЁТ»: сходится ли каждое число с независимым пересчётом.

Чем отличается от `step5_bench.py`. Тот зовёт функции шага напрямую на выдуманных
множествах — это дёшево и воспроизводимо, но не отвечает на вопрос владельца «сколько
ошибок шага на НАСТОЯЩИХ вопросах». Здесь вопросы идут в работающий сервис, а проверяется
ровно то, что он посчитал на самом деле.

🔴 МЕРИЛО — ОШИБКИ ШАГА 5, А НЕ КАЧЕСТВО ОТВЕТА. Какую сущность выбрал шаг 4 и как
сформулировал шаг 6 — здесь не судится вовсе. Предмет проверки один: верно ли посчитано ТО МНОЖЕСТВО,
которое ему дали. Если шаг 4 выбрал не ту сущность, счёт по ней всё равно верен — это
ошибка чужого шага, и приписывать её сюда значит мерить не то.

Как это вообще можно проверить. Гейт исходящего сверяет ответ с тем же `agg`, который
посчитал шаг 5, — то есть своё же число и подтвердит. Поэтому шаг 5 ОБЪЯВЛЯЕТ множество,
по которому считал (`diag.счёт`: источник, условие, признак групп), и прибор пересчитывает
итог по этому объявлению **другой формулой** — развёрткой карты величин вместо точечного
обращения. Расхождение до последнего знака и есть находка прибора.

Классы ошибок шага (каждый — числом):

  E1 «число не сходится» — независимый пересчёт по объявленному множеству дал другое.
  E2 «выдуманное число» — строк со значением ноль, а величина в ответе названа: «считать
     было нечего» неотличимо от «посчитано и вышло 0» (п. 21).
  E3 «невоспроизводимо» — повторный пересчёт того же множества дал другое число (п. 3).
  E4 «множество не объявлено» — числа есть, а проверить их нечем.
  E5 «потеря молча» — часть значений не вошла в счёт (`вне_разрядности`), и об этом
     не сказано числом (п. 13).

Использование:
    ASK_BASE=ut_test python3 work/acceptance/step5_live.py [файл_набора] [сколько]

Код возврата: 0 — ошибок шага 5 нет, 1 — есть.
"""
import importlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_FILE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs/ACCEPTANCE_UT.md")
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
BASE = os.environ.get("ASK_BASE", "ut_test")


def load_env(path):
    """Окружение юнита читается КАК EnvironmentFile, а не через оболочку.

    `set -a; . файл` рвёт значения с пробелами (`SERENEDB_DSN_RO="host=… dbname=…"`) и
    молча уводит прибор в другую базу — записано в `activeContext` 04.08.
    """
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


# Порядок — как `EnvironmentFile` в юните `1c-serene-ask@`: побазовый файл сильнее общего,
# а пароли ролей и ключи лежат в общем `/etc/1c-mcp-reports.env` (`PGPASSWORD`,
# `RESOLVER_PW`). Без последнего прибор идёт в базу без пароля и падает на аутентификации.
load_env("/etc/1c-serene-ask-%s.env" % BASE)
load_env("/etc/1c-serene-ask.env")
load_env("/etc/1c-mcp-reports.env")

sys.path.insert(0, os.path.join(ROOT, "ubuntu/serenedb"))
A = importlib.import_module("serene_ask")

ASK_URL = os.environ.get("ASK_URL") or "http://127.0.0.1:8099/ask"
TOKEN = os.environ.get("ASK_TOKEN", "")
# Предел ожидания ответа сервиса — бюджет времени прибора, а не порог правильности.
# Взят с запасом от замеренного: живой ответ идёт 15-60 с (шаги 1 и 3 зовут модель по
# нескольку раз). Вынесен в окружение, чтобы на медленной машине его поднимали настройкой,
# а не правкой прибора.
TIMEOUT = int(os.environ.get("STEP5_TIMEOUT", "300"))


def questions(path):
    """Все вопросы набора: строка вида **N. «…»**. Эталоны здесь не нужны."""
    text = open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"\*\*(\d+)\.\s*«([^»]+)»", text):
        out.append((int(m.group(1)), m.group(2).strip()))
    seen, uniq = set(), []
    for n, q in out:
        if n not in seen:
            seen.add(n)
            uniq.append((n, q))
    return sorted(uniq)


def ask(question):
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(ASK_URL, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def recount(scope, measure):
    """Пересчёт объявленного множества ДРУГОЙ формулой.

    Шаг 5 достаёт величину точечно (`map_extract(nums, 'имя')[1]`); здесь карта
    РАЗВОРАЧИВАЕТСЯ и значение отбирается по ключу. Путь исполнения другой, арифметика та
    же точная (`DECIMAL`) — иначе сравнивалась бы не ошибка счёта, а невоспроизводимость
    плавающей точки, ради устранения которой шаг и переведён на точную.
    """
    src, where, nf = scope["src"], scope["where"], scope["folder_pred"]
    val = ("(SELECT TRY_CAST(max(x.value) AS DECIMAL(38,10)) "
           "  FROM unnest(map_entries(nums)) AS u(x) WHERE struct_extract(x, 'key') = %s)"
           % A.lit(measure)) if measure else "NULL::DECIMAL(38,10)"
    r = A.psql(
        "SELECT count(*) FILTER (%(nf)s), sum(v) FILTER (%(nf)s), min(v) FILTER (%(nf)s), "
        "       max(v) FILTER (%(nf)s), count(v) FILTER (%(nf)s), "
        "       count(*) FILTER (NOT (%(nf)s)) "
        "FROM (SELECT *, %(val)s AS v FROM %(src)s WHERE %(w)s)"
        % {"nf": nf, "val": val, "src": src, "w": where})
    if not r or not r[0]:
        return None
    row = r[0] + [""] * (6 - len(r[0]))
    return {"count": int(row[0] or 0), "sum": A._numN(row[1]), "min": A._numN(row[2]),
            "max": A._numN(row[3]), "count_amount": int(row[4] or 0),
            "folders": int(row[5] or 0)}


def same(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < 1e-9


def main():
    qs = questions(SET_FILE)
    if LIMIT:
        qs = qs[:LIMIT]
    if not qs:
        sys.stderr.write("вопросов не найдено в %s\n" % SET_FILE)
        return 2
    print("ЖИВОЙ ЗАМЕР ШАГА 5 — счёт против независимого пересчёта")
    print("сервис: %s   база: %s   вопросов: %d\n" % (ASK_URL, BASE, len(qs)))

    errs = {k: [] for k in ("E1 число не сходится", "E2 выдуманное число",
                            "E3 невоспроизводимо", "E4 множество не объявлено",
                            "E5 потеря молча")}
    ran = skipped = 0
    not_counted = []            # вопросы, где шаг 5 не считал, и чьё это было решение
    for n, q in qs:
        try:
            out = ask(q)
        except (urllib.error.URLError, OSError, ValueError) as e:
            print("%3d  ✗ сервис не ответил: %s" % (n, str(e)[:60]))
            skipped += 1
            continue
        diag = out.get("diag") or {}
        sc = diag.get("счёт")
        figs = out.get("figures") or {}
        kind = out.get("kind")
        if not sc:
            # Шаг 5 не запускался: отбор ничего не дал, спросили уточнение, отказ.
            # Это не его ошибка — но если числа названы, проверить их нечем.
            if figs.get("sum") is not None or figs.get("count") is not None:
                errs["E4 множество не объявлено"].append(
                    "№%d «%s»: числа есть (%s), объявления нет" % (n, q[:40], figs))
            # 🔴 ЧЕЙ ЭТО ИСХОД — ВАЖНО. Уточнение бывает и от шага 5: страж величины
            # (`measure_all_zero`, `measure_no_values`, `measure_gate`, `measure_ambiguous`)
            # — это его решение спросить вместо ответа. Всё прочее принадлежит другим
            # шагам, и записывать их в свой счёт значит мерить не своё.
            mine = [k for k in ("measure_all_zero", "measure_no_values", "measure_gate",
                                "measure_ambiguous", "measure_guess_refused")
                    if diag.get(k)]
            not_counted.append((n, kind, ",".join(mine) or "чужой шаг"))
            print("%3d  —  шаг 5 не считал (kind=%s%s)"
                  % (n, kind, (", решение шага 5: " + ",".join(mine)) if mine else ""))
            skipped += 1
            continue
        ran += 1
        measure = sc.get("величина")
        got = recount(sc, measure)
        again = recount(sc, measure)
        bad = []
        if not got:
            bad.append("пересчёт не дал строки")
        else:
            for k in ("count", "count_amount", "folders"):
                if int(sc.get({"count": "строк", "count_amount": "со_значением",
                               "folders": "групп_отброшено"}[k])) != got[k]:
                    bad.append("%s: шаг 5 говорит %s, пересчёт %s"
                               % (k, sc.get({"count": "строк",
                                             "count_amount": "со_значением",
                                             "folders": "групп_отброшено"}[k]), got[k]))
            for k in ("sum", "min", "max"):
                if k in figs and not same(figs.get(k), got[k]):
                    bad.append("%s: в ответе %r, пересчёт %r" % (k, figs.get(k), got[k]))
        if bad:
            errs["E1 число не сходится"].append("№%d «%s»: %s" % (n, q[:40], "; ".join(bad)))
        if got and again and got != again:
            errs["E3 невоспроизводимо"].append(
                "№%d «%s»: повтор дал другое (%r против %r)" % (n, q[:40], got, again))
        if int(sc.get("со_значением") or 0) == 0:
            named = [k for k in ("sum", "min", "max", "avg") if figs.get(k) is not None]
            if named:
                errs["E2 выдуманное число"].append(
                    "№%d «%s»: строк со значением 0, а названы %s" % (n, q[:40], named))
        if int(sc.get("вне_разрядности") or 0) > 0:
            errs["E5 потеря молча"].append(
                "№%d «%s»: %s значений не вошло в счёт"
                % (n, q[:40], sc.get("вне_разрядности")))
        print("%3d  %s  %-34s строк=%-7s со_знач=%-7s итог=%s"
              % (n, "ok" if not bad else "ОШИБКА",
                 (sc.get("src") or "")[:34], sc.get("строк"), sc.get("со_значением"),
                 figs.get("sum")))

    print("\n" + "=" * 74)
    print("шаг 5 считал на %d вопросах, не запускался на %d" % (ran, skipped))
    if not_counted:
        # Разделение обязательно: уточнение от стража величины — это РЕШЕНИЕ шага 5
        # (спросить вместо ответа), а всё прочее принадлежит другим шагам. Без разделения
        # доля «шаг 5 не считал» читалась бы как его бездействие.
        mine = [x for x in not_counted if x[2] != "чужой шаг"]
        print("  из них решение шага 5 (страж величины): %d — %s"
              % (len(mine), ", ".join("№%d %s" % (n, why) for n, _k, why in mine) or "нет"))
        print("  решение других шагов: %d" % (len(not_counted) - len(mine)))
    total = 0
    for k, v in errs.items():
        print("%-28s %s" % (k, "0" if not v else "%d" % len(v)))
        for line in v[:6]:
            print("      · %s" % line)
        total += len(v)
    print("=" * 74)
    print("ОШИБОК ШАГА 5: %d из %d вопросов, где он считал" % (total, ran))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
