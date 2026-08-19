#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Оффлайн-замки для ubuntu/serenedb/ab_scorer.py (v2: digits/kind/clarify/name).

Цель: проверить разбор TSV и чистые функции вердиктов без вызовов /ask и psql.
"""

import os
import sys


PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import ab_scorer as S  # noqa: E402


def mk_out(kind, text="", diag=None, figures=None, totals=None, options=None):
    return {
        "kind": kind,
        "text": text,
        "diag": diag or {},
        "figures": figures or {},
        "totals": totals or {},
        "options": options or [],
    }


def test_load_gold():
    path = os.path.join(ROOT, "ab-gold-okna.tsv")
    rows = S.load_gold(path)
    t("tsv v2: 25 строк", len(rows) == 25, len(rows))
    modes = {r.get("mode") for r in rows}
    t("tsv v2: есть digits/kind/clarify/name", {"digits", "kind", "clarify", "name"} <= modes, modes)


def test_digits():
    ok, defect, fact = S.score_digits("123.45", mk_out("answer", text="Итого 123.45"))
    t("digits: совпадение в text", ok, (defect, fact))

    ok, defect, fact = S.score_digits("123.45", mk_out("figures", text="", figures={"sum": 123.45}))
    t("digits: совпадение в figures", ok, (defect, fact))

    ok, defect, _fact = S.score_digits("123.45", mk_out("answer", text="Итого 999"))
    t("digits: несовпадение => FAIL", not ok and defect == "число не сошлось", (defect,))


def test_kind():
    sql_period = "FROM accumulationregister_реализациятмц doc_date"
    ok, defect, fact = S.score_kind(sql_period, "0", mk_out("figures", text=""))
    t("kind: период+0 => figures", ok, (defect, fact))

    ok, defect, _fact = S.score_kind(sql_period, "0", mk_out("no_data", text=""))
    t("kind: wrong d.kind => FAIL", (not ok and defect == "kind не тот"), defect)

    sql_stock = "SELECT 0"
    ok, defect, _fact = S.score_kind(sql_stock, "0", mk_out("no_data", text="нет данных"))
    t("kind: stock+0 => no_data", ok, (defect, _fact))


def test_clarify():
    out = mk_out(
        "clarify",
        text="уточнение",
        options=[
            {"label": "вариант 0", "decision_id": "d1"},
            {"label": "вариант 1", "decision_id": "d2"},
        ],
    )
    ok, defect, _fact = S.score_clarify("0", out)
    t("clarify: kind=clarify и needle найден в options", ok, defect)

    ok, defect, _fact = S.score_clarify("0", mk_out("answer", text="итог"))
    t("clarify: wrong kind => FAIL", (not ok and defect == "kind не тот"), defect)


def test_name():
    ok, defect, _fact = S.score_name("Alice|123.45", mk_out("answer", text="Лидер Alice, сумма 123.45"))
    t("name: top-1 name+number", ok, defect)

    want = "Ivan = 10 | Petr = 20"
    out = mk_out("answer", text="Топ: Ivan = 10 | Petr = 20")
    ok, defect, _fact = S.score_name(want, out)
    t("name: top-3: несколько пар", ok, defect)

    out = mk_out("answer", text="Топ: Ivan = 10")
    ok, defect, _fact = S.score_name(want, out)
    t("name: missing name/number => FAIL", (not ok and defect in ("имя не найдено", "число не сошлось")), defect)


def test_choose_clarify_option():
    opts = [
        {"label": "Алиса 1", "decision_id": "d1"},
        {"label": "Боб 2", "decision_id": "d2"},
    ]
    chosen = S.choose_clarify_option(opts, "Алиса")
    t("choose_clarify_option: находит по подстроке", chosen and chosen.get("decision_id") == "d1", chosen)


def main():
    test_load_gold()
    test_digits()
    test_kind()
    test_clarify()
    test_name()
    test_choose_clarify_option()
    print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
          else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()

