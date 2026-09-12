#!/usr/bin/env python3
"""S3: warehouse/balance legacy helpers снесены; balance_path_engaged + catalogs живы."""
import os
import sys

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


for name in ("stock_skips_warehouse_clarify", "stock_canon_src",
             "axis_catalog_values", "stock_breakdown_leader_fallback"):
    t("S3 GONE: " + name, not hasattr(A, name))

INTENT_GOODS = {"want": "count", "kind": "номенклатура", "action_class": "object",
                "action_axis": "склад"}
INTENT_LIST = {"want": "list", "kind": "склад", "action_class": "object",
               "action_axis": "номенклатура"}

_old_k = A._base_knows_kind_or_measure
A._base_knows_kind_or_measure = lambda w: True
A.entity_form_catalogs_for_kind = lambda w, **kw: ["catalog_номенклатура"]
A.psql = lambda q: [("accumulationregister_x",)] if "search_refcols" in q.lower() else []

t("balance engaged", A.balance_path_engaged(INTENT_GOODS, None, "q"))
t("list breakdown", A.question_wants_per_axis_breakdown("q", INTENT_LIST))
t("entity_form_catalogs_for_kind жив",
  callable(getattr(A, "entity_form_catalogs_for_kind", None)))

A._base_knows_kind_or_measure = _old_k

print("%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    sys.exit(1)
