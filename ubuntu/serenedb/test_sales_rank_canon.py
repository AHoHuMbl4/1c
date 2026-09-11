#!/usr/bin/env python3
"""В2 негатив: sales rank-prefer / force-money снесены; classifiers живы."""
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
os.environ["ASK_SALES_RANK_CANON"] = "1"

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


ask_blob = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted(ASK.glob("*.py")))

for name in ("prefer_entity_for_sales", "sales_canon_force_pool",
             "sales_force_money_measure", "sales_rank_resolve_measure",
             "sales_rank_canon_measure", "sales_rank_product_axis"):
    t("gone %s" % name, name not in ask_blob)
    t("no attr %s" % name, not hasattr(A, name))

t("sales_rank_engaged callable", callable(A.sales_rank_engaged))
t("sales_sum_intent callable", callable(A.sales_sum_intent))
t("_sales_rank_top_n жив", callable(getattr(A, "_sales_rank_top_n", None)))

# engaged: compare off
t("engaged OFF на compare",
  not A.sales_rank_engaged(
      {"want": "list", "kind": "продажи"}, {},
      "эта неделя лучше прошлой или хуже?",
      ["accumulationregister_реализациятмц"]))

# sum path still classified
t("sum force_money GONE — sales_sum_intent on",
  A.sales_sum_intent({"want": "sum", "kind": "продажи"}, "сколько продали?"))
t("flag1: sum не sales_rank_engaged без lift/cands",
  not A.sales_rank_engaged({"want": "sum", "kind": "продажи"}, {},
                           "сколько продали?", []))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
