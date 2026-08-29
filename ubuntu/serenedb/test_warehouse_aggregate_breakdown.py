#!/usr/bin/env python3
"""K9-ф3: structural warehouse/balance path (intent + metadata, not question words)."""
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


INTENT_GOODS = {"want": "count", "kind": "номенклатура", "action_class": "object",
                "action_axis": "склад"}
INTENT_LIST = {"want": "list", "kind": "склад", "action_class": "object",
               "action_axis": "номенклатура"}
INTENT_AGG = dict(INTENT_GOODS)

_old_k = A._base_knows_kind_or_measure
A._base_knows_kind_or_measure = lambda w: True
A.entity_form_catalogs_for_kind = lambda w, **kw: ["catalog_номенклатура"]
A.psql = lambda q: [("accumulationregister_x",)] if "search_refcols" in q.lower() else []

t("balance engaged", A.balance_path_engaged(INTENT_GOODS, None, "q"))
t("aggregate skip wh", A.stock_skips_warehouse_clarify("q", INTENT_AGG))
t("list breakdown", A.question_wants_per_axis_breakdown("q", INTENT_LIST))

A._base_knows_kind_or_measure = _old_k
_mock_base = A.psql


def _mock_psql(q):
    if "search_refcols" in q.lower():
        return [("accumulationregister_импорттмц",)]
    if "group by" in q.lower():
        return [("accumulationregister_импорттмц", 100)]
    return []


A.psql = _mock_psql
A.entity_form_catalogs_for_kind = lambda w, **kw: ["catalog_номенклатура"]
A._BALANCE_REGS.update({"at": 0.0, "set": set()})
try:
    canon = A.stock_canon_src(
        ["accumulationregister_номерабсо", "accumulationregister_импорттмц"],
        "q", INTENT_GOODS)
    t("canon import", canon == "accumulationregister_импорттмц", canon)
finally:
    A.psql = _mock_base

A.aggregate = lambda *a, **k: {
    "count": 42, "sum": None, "src": "x", "measure": None,
    "folders": 0, "out_of_range": 0, "count_amount": 42}
A.axis_catalog_values = lambda axis_word=None, limit=20, intent=None, **kw: [
    "WH-1", "WH-2"]
t("fallback figures",
  A.stock_breakdown_leader_fallback(
      "q", "x", "", [], "m", {}, None, time.time(), intent=INTENT_LIST)
  and True)

print("%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    sys.exit(1)
