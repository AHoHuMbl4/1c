#!/usr/bin/env python3
"""K7: агрегат-маркер снимает складскую развилку; «пo каждому» ≠ no_data.

Оффлайн. Запуск: python3 ubuntu/serenedb/test_warehouse_aggregate_breakdown.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


Q_TOTAL = "сколько на складе позиций всего?"
Q_EACH = "Покажите остатки по каждому складу отдельно"
Q_LIST = "Покажите список складов с количеством позиций по каждому"
Q_PLAIN = "Сколько осталось на складе?"

# ── aggregate marker снимает warehouse clarify ───────────────────────────────
t("«всего»: aggregate marker",
  A.question_has_aggregate_total_marker(Q_TOTAL))
t("«всего»: skip warehouse clarify",
  A.stock_skips_warehouse_clarify(Q_TOTAL))
t("plain stock: НЕ skip clarify",
  not A.stock_skips_warehouse_clarify(Q_PLAIN))
t("rank «больше всего»: не aggregate marker",
  not A.question_has_aggregate_total_marker(
      "какого товара больше всего на складе?"))

# ── «пo каждому» снимает warehouse clarify ───────────────────────────────────
t("«пo каждому»: breakdown",
  A.question_wants_per_axis_breakdown(Q_EACH))
t("«пo каждому»: skip warehouse clarify",
  A.stock_skips_warehouse_clarify(Q_EACH))
t("list+пo каждому: breakdown без stock-маркера",
  A.question_wants_per_axis_breakdown(
      Q_LIST, intent={"want": "list", "kind": "склад"}))
t("list: warehouse axis class",
  A.question_mentions_warehouse_axis(Q_LIST))
t("list+пo каждому: skip warehouse clarify",
  A.stock_skips_warehouse_clarify(
      Q_LIST, intent={"want": "list", "kind": "склад"}))

# ── warehouse_clarify: gated ─────────────────────────────────────────────────
_old_wh = A.warehouse_axis_values
A.warehouse_axis_values = lambda limit=20: ["A", "B", "C"]
t("plain: warehouse clarify строится",
  A.warehouse_clarify(Q_PLAIN, {}, {}, 0.0) is not None)
t("всего: clarify не нужен — skip flag",
  A.stock_skips_warehouse_clarify(Q_TOTAL))
A.warehouse_axis_values = _old_wh

# ── breakdown fallback: итог+люк, не no_data ─────────────────────────────────
_real_agg = A.aggregate
A.aggregate = lambda src, match, preds, measure=None: {
    "count": 42, "sum": None, "src": src, "measure": measure,
    "folders": 0, "out_of_range": 0, "count_amount": 42}
A.warehouse_axis_values = lambda limit=20: ["WH-1", "WH-2", "WH-3"]
try:
    fb = A.stock_breakdown_leader_fallback(
        Q_EACH, "accumulationregister_x", "", [], "Количество",
        {}, None, time.time(), intent={"want": "count"})
    t("fallback: kind=figures", fb and fb.get("kind") == "figures", fb)
    t("fallback: text with count",
      fb and "42" in (fb.get("text") or ""), fb.get("text") if fb else None)
    t("fallback: loophole options",
      fb and len(fb.get("options") or []) == 3, fb)
    t("fallback: not no_data",
      fb and fb.get("kind") != "no_data")
    t("plain stock: fallback None",
      A.stock_breakdown_leader_fallback(
          Q_PLAIN, "x", "", [], None, {}, None, time.time()) is None)
    fb_list = A.stock_breakdown_leader_fallback(
        Q_LIST, "catalog_wh", "", [], None, {}, None, time.time(),
        intent={"want": "list", "kind": "склад"},
        cands=["accumulationregister_goods"])
    t("list: fallback from catalog to balance src",
      fb_list and fb_list.get("kind") == "figures", fb_list)
    A.warehouse_axis_values = lambda limit=20: ["only"]
    t("single warehouse: fallback None",
      A.stock_breakdown_leader_fallback(
          Q_EACH, "x", "", [], None, {}, None, time.time()) is None)
finally:
    A.aggregate = _real_agg
    A.warehouse_axis_values = _old_wh

# ── fork place clarify bypass ────────────────────────────────────────────────
_ord = [
    {"srcs": ["reg_a"], "atom": A.build_answer_atom(
        operation="count", exact_value=7, proof_status=A.PROOF_COMPUTED),
     "row": {"count": 7, "folders": 0, "sums": {}}},
    {"srcs": ["reg_b"], "atom": A.build_answer_atom(
        operation="count", exact_value=3, proof_status=A.PROOF_COMPUTED),
     "row": {"count": 3, "folders": 0, "sums": {}}},
]
A.warehouse_axis_values = lambda limit=20: ["WH-A", "WH-B"]
try:
    res = A.fork_outcome_c(
        Q_EACH, {"reason": "unsigned_class"}, {}, {},
        {}, cut=None, t0=time.time(), picked_src="reg_a",
        intent={"want": "count", "kind": "остатки"})
    t("fork C place+breakdown: not clarify",
      res and res.get("kind") != "clarify", res)
    t("fork C place+breakdown: figures or unavailable",
      res and res.get("kind") in ("figures", "unavailable"), res)
finally:
    A.warehouse_axis_values = _old_wh

print()
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
