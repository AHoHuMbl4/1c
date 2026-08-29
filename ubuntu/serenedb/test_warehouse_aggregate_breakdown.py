#!/usr/bin/env python3
"""K7/K8-ф3: stock aggregate markers, product-axis canon, breakdown fallback (offline)."""
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
Q_TOGETHER = "сколько позиций на всех складах вместе?"
Q_BREAK = "покажи остатки по каждому складу"
Q_PLAIN = "сколько на складе?"

t("stock engaged: на складе + всего", A.stock_question_engaged(Q_TOTAL))
t("stock engaged: на всех вместе", A.stock_question_engaged(Q_TOGETHER))
t("aggregate marker: всего", A.question_has_aggregate_total_marker(Q_TOTAL))
t("aggregate marker: вместе+склад", A.question_has_aggregate_total_marker(Q_TOGETHER))
t("skip warehouse clarify: всего",
  A.stock_skips_warehouse_clarify(Q_TOTAL))
t("skip warehouse clarify: по каждому",
  A.stock_skips_warehouse_clarify(Q_BREAK))
t("per-axis breakdown", A.question_wants_per_axis_breakdown(Q_BREAK))
t("rank всего not aggregate",
  not A.question_has_aggregate_total_marker("больше всего продаж"))

t("asks stock: на складе", A.question_asks_stock_balance(Q_TOTAL))
t("asks stock: marker class not phrase-only",
  A.question_asks_stock_balance("what is in stock today"))

_cands = ["catalog_номенклатура", "accumulationregister_импорттмц",
          "accumulationregister_номерабсо"]
_old_psql = A.psql
A._BALANCE_REGS.update({"at": 0.0, "set": set()})
A._BALANCE_MAP.update({"at": time.time(), "rows": []})


def _mock_psql(q):
    ql = q.lower()
    if "search_refcols" in ql:
        return [("accumulationregister_импорттмц", "catalog_номенклатура")]
    if "search_meta" in ql and "balance_registers" in ql:
        return [("",)]
    if "group by" in ql and "src_table" in ql:
        return [("accumulationregister_импорттмц", 100)]
    return []


A.psql = _mock_psql
try:
    pool = A.stock_goods_pool()
    t("goods pool: import in", "accumulationregister_импорттмц" in pool, sorted(pool))
    t("goods pool: BSO out", "accumulationregister_номерабсо" not in pool)
    canon = A.stock_canon_src(_cands, Q_TOTAL)
    t("stock_canon: import not BSO", canon == "accumulationregister_импорттмц", canon)
finally:
    A.psql = _old_psql

_real_agg = A.aggregate
A.aggregate = lambda src, match, preds, measure=None: {
    "count": 42, "sum": None, "src": src, "measure": measure,
    "folders": 0, "out_of_range": 0, "count_amount": 42}
A.warehouse_axis_values = lambda limit=20: ["WH-1", "WH-2", "WH-3"]
try:
    fb = A.stock_breakdown_leader_fallback(
        Q_BREAK, "accumulationregister_x", "", [], "Количество",
        {}, None, time.time())
    t("fallback: kind=figures", fb and fb.get("kind") == "figures", fb)
    t("aggregate: fallback None",
      A.stock_breakdown_leader_fallback(
          Q_TOTAL, "x", "", [], None, {}, None, time.time()) is None)
finally:
    A.aggregate = _real_agg

try:
    t("warehouse clarify plain",
      A.warehouse_clarify(Q_PLAIN, {}, {}, 0.0) is not None)
finally:
    pass

print()
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    sys.exit(1)
