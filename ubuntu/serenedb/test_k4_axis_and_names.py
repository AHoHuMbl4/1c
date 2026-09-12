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
# period_assumed_needs_clarify снесён с тракта (FORBIDDEN / one_path); датчик — serene_enough.
intent_spring = {
    "want": "sum", "kind": "закупки",
    "period": {"from": "2026-03-01", "to": "2026-05-31"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
t("S1/one-path: period_assumed_needs_clarify GONE",
  not hasattr(A, "period_assumed_needs_clarify"))
t("axis: датчик period_assumed на spring",
  E.period_assumed(intent_spring))
t("axis: 2022 явный → period_assumed False",
  not E.period_assumed({
      "period": {"from": "2022-01-01", "to": "2022-12-31"},
      "parse": {"assumed": []}}))

# ── Класс money|qty (№7) ─────────────────────────────────────────────────────
# measure_class_alts ушёл с silent/fork тракта; меню мер — measure_choice + captions.
t("one-path: measure_class_alts GONE", not hasattr(A, "measure_class_alts"))
t("measure_choice жив", callable(getattr(A, "measure_choice", None)))

# ── Склад: S3 снёс question_asks/stock_subject/warehouse_clarify ─────────────
for _n in ("question_asks_stock_balance", "stock_subject_needs_clarify",
           "warehouse_clarify"):
    t("S3 GONE: " + _n, not hasattr(A, _n))
t("stock: №11 без named product",
  not A.stock_asks_named_product(
      "Сколько осталось на складе?",
      intent={"want": "sum", "terms": [], "measure": ""}))

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
