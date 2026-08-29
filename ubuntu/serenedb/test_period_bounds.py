#!/usr/bin/env python3
"""Граница периода: полный день включительно, outside_period без строк внутри окна."""
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
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


DAY = "2026-08-17"
NEXT = "2026-08-18"
PREV = "2026-08-16"
period = {"from": DAY, "to": DAY}
preds = A.period_preds(period)

t("period_preds: нет <= to",
  all("<=" not in p or "doc_date" not in p for p in preds), preds)
t("period_preds: верхняя граница полусоткрытая",
  any("INTERVAL 1 day" in p for p in preds), preds)
t("period_preds: from/to",
  preds == ["doc_date >= '%s'" % DAY,
            "doc_date < ('%s'::date + INTERVAL 1 day)" % DAY], preds)

# K2: «с 1 по 15» — явный диапазон дней месяца, не amount/terms.
mdr = A.month_day_range_from_question("Сколько отгрузили с 1 по 15", "2026-08-29")
t("month_day_range: с 1 по 15",
  mdr and mdr.get("from") == "2026-08-01" and mdr.get("to") == "2026-08-15", mdr)
preds_m = A.period_preds({"from": mdr["from"], "to": mdr["to"]})
t("month_day_range: preds полусоткрытые",
  preds_m == ["doc_date >= '2026-08-01'",
              "doc_date < ('2026-08-15'::date + INTERVAL 1 day)"], preds_m)
intent_m = {
    "period": {},
    "terms": [["1"], ["15"], ["2"]],
    "amount": {"op": "=", "value": 1},
    "parse": {"assumed": ["period.from", "period.to"]},
}
A.repair_period_from_question(intent_m, "Сколько отгрузили с 1 по 15", "2026-08-29")
t("repair: period from/to",
  intent_m.get("period", {}).get("from") == "2026-08-01"
  and intent_m.get("period", {}).get("to") == "2026-08-15",
  intent_m.get("period"))
t("repair: terms без 1/15",
  intent_m.get("terms") == [["2"]], intent_m.get("terms"))
t("repair: amount сброшен", intent_m.get("amount") == {}, intent_m.get("amount"))
t("repair: assumed снят",
  "assumed" not in (intent_m.get("parse") or {}),
  intent_m.get("parse"))

# Живой SereneDB: строка 15:53 того же дня — внутри «вчера», полночь N+1 — нет.
if os.environ.get("SERENEDB_DSN_RO"):
    import subprocess

    def q(sql):
        env = os.environ.copy()
        p = subprocess.run(
            ["psql", os.environ["SERENEDB_DSN_RO"], "-v", "ON_ERROR_STOP=1", "-tA", "-c", sql],
            capture_output=True, text=True, env=env)
        if p.returncode != 0:
            raise RuntimeError(p.stderr[:200])
        return p.stdout.strip()

    where_in = " AND ".join(preds)
    where_out = " AND ".join([
        "doc_date >= '%s'" % NEXT,
        "doc_date < ('%s'::date + INTERVAL 1 day)" % NEXT,
    ])
    t("SQL: 15:53 внутри периода",
      q("SELECT count(*) FROM (SELECT TIMESTAMP '%s 15:53:00' AS doc_date) x "
        "WHERE %s" % (DAY, where_in)) == "1")
    t("SQL: полночь N+1 вне периода «вчера»",
      q("SELECT count(*) FROM (SELECT TIMESTAMP '%s 00:00:00' AS doc_date) x "
        "WHERE %s" % (NEXT, where_in)) == "0")
    t("SQL: <= to отбрасывает дневную строку (дефект п.13)",
      q("SELECT count(*) FROM (SELECT TIMESTAMP '%s 15:53:00' AS doc_date) x "
        "WHERE doc_date <= '%s'" % (DAY, DAY)) == "0")
    t("SQL: outside NOT(period) не считает 15:53 внешней",
      q("SELECT count(*) FROM (SELECT TIMESTAMP '%s 15:53:00' AS doc_date) x "
        "WHERE doc_date IS NOT NULL AND NOT (%s)" % (DAY, where_in)) == "0")
    t("SQL: outside NOT(period) считает полночь N+1",
      q("SELECT count(*) FROM (SELECT TIMESTAMP '%s 00:00:00' AS doc_date) x "
        "WHERE doc_date IS NOT NULL AND NOT (%s)" % (NEXT, where_in)) == "1")

print("---")
print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
