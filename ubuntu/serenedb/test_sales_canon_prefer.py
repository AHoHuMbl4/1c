#!/usr/bin/env python3
"""В2 негатив: prefer/force/lock выбора сущности продаж снесены из ask/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"
sys.path.insert(0, str(ROOT))
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


GONE = (
    "prefer_entity_for_sales",
    "sales_canon_force_pool",
    "sales_force_money_measure",
    "sales_canon_src",
    "sales_canon_engaged",
    "prefer_entity_for_catalog_count",
    "period_zero_why_question",
    "sales_rank_resolve_measure",
)

ask_blob = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted(ASK.glob("*.py")))
z20 = (ASK / "z20_ask_main_http.py").read_text(encoding="utf-8")

for name in GONE:
    t("gone in ask/: %s" % name, name not in ask_blob)
    t("not attr serene_ask: %s" % name, not hasattr(A, name))

for name in ("prefer_entity_for_sales", "prefer_entity_for_rank",
             "prefer_entity_for_catalog_count", "sales_canon_force_pool",
             "sales_force_money_measure", "sales_canon_src"):
    t("z20 no call %s" % name, name not in z20)

t("sales_sum_intent жив", callable(getattr(A, "sales_sum_intent", None)))
t("S3: sales_rank_engaged GONE", not hasattr(A, "sales_rank_engaged"))
t("sales_noncanon_focus жив", callable(getattr(A, "sales_noncanon_focus", None)))
t("sales intent продали", A.sales_sum_intent({"want": "sum", "kind": "продажи"},
                                              "сколько продали сегодня?"))
t("sales intent не прайс", not A.sales_sum_intent({"want": "count"},
                                                  "сколько позиций у нас в прайсе?"))
t("noncanon книга", A.sales_noncanon_focus("accumulationregister_книгапродаж"))
t("canon регистр", not A.sales_noncanon_focus("accumulationregister_реализациятмц"))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
