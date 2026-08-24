#!/usr/bin/env python3
"""Compare-продажи: diff двух окон (SCORER #6/#7, фаза A)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


TODAY = "2026-08-23"
intent_week = {
    "period": {"from": "2026-08-17", "to": "2026-08-23"},
    "want": "sum",
}
t("#6 sales_compare_intent",
  A.sales_compare_intent(intent_week, "эта неделя лучше прошлой или хуже?"))
p1, p2, fid = A.sales_compare_windows(intent_week, TODAY,
                                      "эта неделя лучше прошлой или хуже?")
t("#6 windows: wtd form", fid == "wtd")
t("#6 cur week Mon→today",
  p1.get("from") == "2026-08-17" and p1.get("to") == TODAY)
t("#6 prior week aligned",
  p2.get("from") == "2026-08-10" and p2.get("to") == "2026-08-16")

intent_month = {
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "want": "sum",
}
t("#7 sales_compare_intent",
  A.sales_compare_intent(intent_month,
                         "в этом месяце продали больше, чем в прошлом?"))
m1, m2, mfid = A.sales_compare_windows(intent_month, TODAY,
                                       "в этом месяце продали больше, чем в прошлом?")
t("#7 windows: mtd form", mfid == "mtd")
t("#7 cur MTD", m1.get("from") == "2026-08-01" and m1.get("to") == TODAY)
t("#7 prior MTD Jul", m2.get("from") == "2026-07-01" and m2.get("to") == "2026-07-23")

GOLD6 = 817289.51
GOLD7 = 579169.67

def _mock_agg(src, match, preds, measure=None):
    fr = next((p.split("'")[1] for p in (preds or []) if "doc_date >=" in p), "")
    if fr == "2026-08-17":
        return {"count": 100, "sum": 1000000.0, "src": src, "measure": measure}
    if fr == "2026-08-10":
        return {"count": 80, "sum": 1000000.0 - GOLD6, "src": src, "measure": measure}
    if fr == "2026-08-01":
        return {"count": 200, "sum": 3346620.65, "src": src, "measure": measure}
    if fr == "2026-07-01":
        return {"count": 180, "sum": 3346620.65 - GOLD7, "src": src, "measure": measure}
    return {"count": 0, "sum": 0.0, "src": src, "measure": measure}

real_agg = A.aggregate
A.aggregate = _mock_agg
agg6 = A.aggregate_compare_sales("reg", "", p1, p2, "Всего")
t("#6 diff эталон", agg6 and abs(float(agg6["sum"]) - GOLD6) < 0.02,
  agg6.get("sum") if agg6 else None)
agg7 = A.aggregate_compare_sales("reg", "", m1, m2, "Всего")
t("#7 diff эталон", agg7 and abs(float(agg7["sum"]) - GOLD7) < 0.02,
  agg7.get("sum") if agg7 else None)
t("compare agg form", agg7 and agg7.get("form") == "compare")
A.aggregate = real_agg

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
