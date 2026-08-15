#!/usr/bin/env python3
"""Оффлайн-пробы чистых функций детектора развилки (shadow, включён по умолчанию).

Детектор (`PLAN_ANSWER_CONTRACT` §3) считает полный круг одним SQL и сводит ячейки в
классы эквивалентности типизированным атомом. Здесь проверяется та часть, которая не
требует базы: сведение в классы (`fork_classes`) и выбор относящихся величин
(`_fork_relevant`, тем же `measure_choice`, что выбор величины ответа).

Запуск:  python3 ubuntu/serenedb/test_fork_detector.py
Без базы, сети и вызовов модели.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS = 0
FAIL = []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


# ── fork_classes: классы по типизированному атому без src ───────────────────────────
t("одинаковый атом у двух src — один класс (A, согласие)",
  len(A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)})) == 1)
t("разные суммы — два класса (развилка видна кодом)",
  len(A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=200.0)})) == 2)
t("разный счёт — два класса",
  len(A.fork_classes({"a": row(19), "b": row(20)})) == 2)
t("папки — дискриминатор: 19 записей ≠ 19 групп",
  len(A.fork_classes({"a": row(19, 0), "b": row(19, 5)})) == 2)
t("копейка в сумме — округление round 2, один класс",
  len(A.fork_classes({"a": row(1, Сумма=100.001), "b": row(1, Сумма=100.004)})) == 1)
t("копейка расхождения — разные классы, допуска нет",
  len(A.fork_classes({"a": row(1, Сумма=100.0), "b": row(1, Сумма=100.01)})) == 2)
t("величины с разными именами не схлопываются: разные атомы",
  len(A.fork_classes({"a": row(1, Сумма=5.0), "b": row(1, Стоимость=5.0)})) == 2)
t("src в атом не входит: три src с одним атомом — один класс из трёх",
  sorted(A.fork_classes({"a": row(7), "b": row(7), "c": row(7)}).values(),
         key=len)[-1] == ["a", "b", "c"] or
  sorted(next(iter(A.fork_classes({"a": row(7), "b": row(7), "c": row(7)}).values())))
  == ["a", "b", "c"])
t("пустой круг — классов нет",
  A.fork_classes({}) == {})

# ── _fork_relevant: величины, относящиеся к слову вопроса ────────────────────────────
t("точное совпадение слова — одна величина",
  A._fork_relevant("сумма", ["Сумма", "СуммаНДС"], {}) == ["Сумма"])
t("слова нет — величин в атоме нет",
  A._fork_relevant("", ["Сумма"], {}) == [])
t("величин нет — атом по счёту",
  A._fork_relevant("сумма", [], {}) == [])
t("несколько подходящих — все в атом (как measure_alts)",
  sorted(A._fork_relevant("цена", ["ЦенаЗакупки", "ЦенаПродажи"], {}))
  == ["ЦенаЗакупки", "ЦенаПродажи"])

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    sys.exit(1)
print("все", PASS, "проверок зелёные")
