#!/usr/bin/env python3
"""Пустой период: kind=answer с нулём, outside_period, без refuse/figures."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []
OKNA_OUTSIDE = 77381  # живой okna 18.08, accumulationregister_реализациятмц


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


intent_named = {
    "want": "sum",
    "period": {"from": "2026-08-17", "to": "2026-08-17"},
    "amount": {},
}
intent_yesterday = {
    "want": "sum",
    "period": {"from": "2026-08-17", "to": "2026-08-17"},
    "parse": {"assumed": ["period.from", "period.to"]},
    "amount": {},
}
agg = {
    "count": 0,
    "sum": 0.0,
    "min": None,
    "max": None,
    "avg": None,
    "outside_period": OKNA_OUTSIDE,
    "measure": "Всего",
    "src": "accumulationregister_реализациятмц",
}
Q = "сколько продали вчера всего?"

t("period_given + empty_period",
  A.period_empty_outcome(agg, "empty_period", intent_named, {}))
t("вчера: drop_assumed + outside_period",
  A.period_empty_outcome(agg, "drop_assumed", intent_yesterday, {}))
t("не empty при no_data без outside",
  not A.period_empty_outcome({"count": 0, "sum": 0.0}, "no_data",
                             intent_yesterday, {}))
t("не empty после period_assumed_dropped",
  not A.period_empty_outcome(agg, "drop_assumed", intent_yesterday,
                             {"period_assumed_dropped": True}))

txt = A.format_period_empty_text(
    Q, agg, intent_yesterday, "Всего", agg["src"], True,
    near_min="2026-08-28", near_max="2026-08-28")
t("текст содержит 0", "— 0" in txt or " 0" in txt, txt)
t("текст содержит outside_period", str(OKNA_OUTSIDE) in txt.replace(" ", ""), txt)
t("текст содержит ближайшие даты", "28.08" in txt, txt)
t("не refuse", "Проверенный ответ" not in txt, txt)

filled, bad = A._fill_figures(
    "За период записей {count}, итог {total}.", agg, [], True, {}, slot_mode="sum")
t("{count}=0 подставляется на sum", "{count}" not in filled and bad == [], filled)

miss = A.asked_figure_missing(txt, agg, "sum", True)
t("asked_figure_missing доволен текстом с нулём", miss is None, miss)

grain = {"grain": "row", "form": "number", "clarify": None}
out = A.build_period_empty_answer(
    Q, agg, intent_yesterday, "Всего", agg["src"], "", [], True, "sum",
    None, None, {}, grain, [], 0, [], 0.0, "Всего")
t("kind=answer", out.get("kind") == "answer", out.get("kind"))
t("figures.sum=0", out.get("figures", {}).get("sum") == 0.0)
t("figures.outside_period", out.get("figures", {}).get("outside_period") == OKNA_OUTSIDE)
t("figures.count=0", out.get("figures", {}).get("count") == 0)
t("diag.period_empty", out.get("diag", {}).get("period_empty") is True)

print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
      else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
