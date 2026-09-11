#!/usr/bin/env python3
"""В2 замок: до-вики перестановки сущности снесены (prefer/K6/rerank/expand/parent)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


z20 = (ASK / "z20_ask_main_http.py").read_text(encoding="utf-8")
z10 = (ASK / "z10_rank.py").read_text(encoding="utf-8")
z11 = (ASK / "z11_sales.py").read_text(encoding="utf-8")
imports = (ASK / "_imports.py").read_text(encoding="utf-8")
boot = (ASK / "_bootstrap.py").read_text(encoding="utf-8")

# (а) 0 вызовов prefer_entity_for_{sales,rank,catalog_count}
for sym in ("prefer_entity_for_sales", "prefer_entity_for_rank",
            "prefer_entity_for_catalog_count"):
    t("0 %s in z20" % sym, sym not in z20)
    t("0 %s in z10" % sym, sym not in z10)
    t("0 %s in z11" % sym, sym not in z11)

# (б) 0 K6R.apply_to_candidates в z20 и 0 импорта K6R в _imports
t("0 K6R.apply_to_candidates in z20", "K6R.apply_to_candidates" not in z20)
t("0 K6R in z20", "K6R" not in z20)
t("0 import K6R in _imports", "entity_rank_v2" not in imports and "K6R" not in imports)
t("entity_rank_v2.py файл жив", (ROOT / "entity_rank_v2.py").is_file())

# (в) 0 diag["order_by"]="rerank" на пути сущности z20
t('0 diag["order_by"]="rerank"', 'diag["order_by"] = "rerank"' not in z20)
t("0 order_by rerank assign", not re.search(
    r'order_by["\']\s*\]\s*=\s*["\']rerank["\']', z20))

# (г) 0 вызовов event_kind_catalog_expand_pool из z20
t("0 event_kind_catalog_expand_pool in z20",
  "event_kind_catalog_expand_pool" not in z20)

# (д) 0 parent-before-child reorder-блока
t("0 parent-before-child wants_number reorder",
  "wants_number and len(cands) > 1" not in z20
  or "par.get(c) in cands and par.get(c) not in placed" not in z20)
t("0 parent reorder placed loop",
  "ребёнок ждёт, пока встанет родитель" not in z20)

# (е) 0 присваиваний sales_canon_locked
t("0 sales_canon_locked assign", "sales_canon_locked" not in z20)
t("0 sales_canon_post in bootstrap", "sales_canon_post" not in boot)
t("0 fork_b sales_money in bootstrap",
  "outcome_b_deferred_sales_money" not in boot)

# ── В3 негатив: мера/ось auto-пути снесены ───────────────────────────────────
import re as _re
# call-sites (не комментарии): имя символа + '('
for sym in ("rank_deterministic_answer", "rank_gate_fallback_answer",
            "stock_breakdown_leader_fallback", "sales_money_measure",
            "sales_qty_measure"):
    hits = [m.start() for m in _re.finditer(r'\b%s\s*\(' % _re.escape(sym), z20)]
    # отфильтровать попадания только в комментариях той же строки
    real = []
    for h in hits:
        line_start = z20.rfind("\n", 0, h) + 1
        line = z20[line_start:z20.find("\n", h)]
        code = line.split("#", 1)[0]
        if sym in code and "(" in code:
            real.append(h)
    t("0 call-site %s in z20" % sym, not real, real[:3])

t("0 rank_axis_auto assign in z20",
  'diag["rank_axis_auto"]' not in z20
  and "diag['rank_axis_auto']" not in z20)
t("0 _meas_old bootstrap patch", "_meas_old" not in boot)
t("0 _skip_old bootstrap patch", "_skip_old" not in boot)
t("0 _rank_fold_old bootstrap patch", "_rank_fold_old" not in boot)

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
