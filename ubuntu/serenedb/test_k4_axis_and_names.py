#!/usr/bin/env python3
"""K4-3 / K5: ось уточнения, склад, имена (доп. к test_k4_meta_names).

Оффлайн. Источник: docs/K4_AXIS_AND_NAMES.md §6.2–6.3.
Запуск: python3 ubuntu/serenedb/test_k4_axis_and_names.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402
import serene_enough as E  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


today = "2026-08-27"

# ── Ось периода раньше measure (№3 / защита №15) ─────────────────────────────
intent_spring = {
    "want": "sum", "kind": "закупки",
    "period": {"from": "2026-03-01", "to": "2026-05-31"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
t("axis: весна assumed (~90д) → period clarify",
  A.period_assumed_needs_clarify(intent_spring, today))
t("axis: 2022 явный → не period-clarify (№15)",
  not A.period_assumed_needs_clarify({
      "period": {"from": "2022-01-01", "to": "2022-12-31"},
      "parse": {"assumed": []}}, today))
t("axis: датчик period_assumed на spring",
  E.period_assumed(intent_spring))

# ── Класс money|qty (№7) ─────────────────────────────────────────────────────
_cls = A.measure_class_alts(
    ["Всего", "НДС", "Количество"],
    {"Всего": "итого,сумма,деньги", "Количество": "кол-во,штуки,qty"})
t("axis: want=sum без меры → money|qty, не полный nums",
  len(_cls[1]) == 2 and "НДС" not in _cls[1], _cls)

# ── Склад: bypass empty by + warehouse clarify (№11) ─────────────────────────
t("stock: маркер «осталось на складе»",
  A.question_asks_stock_balance("Сколько осталось на складе?"))
t("stock: №11 без named product",
  not A.stock_asks_named_product(
      "Сколько осталось на складе?",
      intent={"want": "sum", "terms": [], "measure": ""}))
t("stock: №11 subject_needs — False (нет леж/всех)",
  not A.stock_subject_needs_clarify(
      "Сколько осталось на складе?", {"want": "sum", "terms": []}))

wh3 = A.warehouse_clarify(
    "Сколько осталось на складе?", {}, {}, time.time(),
    warehouses=["Vitrina", "Bubuieci", "Depozit"])
t("wh: 3 склада → clarify",
  wh3 and wh3.get("kind") == "clarify" and len(wh3.get("options") or []) == 3)
t("wh: подписи человеческие",
  wh3 and all(not A.label_has_meta_src(o.get("label"))
              for o in (wh3.get("options") or [])))
t("wh: 1 склад → None",
  A.warehouse_clarify("остаток?", {}, {}, time.time(),
                      warehouses=["Vitrina"]) is None)
t("wh: 0 складов → None",
  A.warehouse_clarify("остаток?", {}, {}, time.time(),
                      warehouses=[]) is None)

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
