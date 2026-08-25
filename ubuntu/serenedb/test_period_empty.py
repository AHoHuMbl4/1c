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
# bfe4166: при money+measure figures.sum — строка "0.00" (деньги в figures),
# не float 0.0; ноль в периоде по-прежнему, без all-time подмены.
t("figures.sum=0", out.get("figures", {}).get("sum") in (0, 0.0, "0.00"),
  out.get("figures", {}).get("sum"))
t("figures.outside_period", out.get("figures", {}).get("outside_period") == OKNA_OUTSIDE)
t("figures.count=0", out.get("figures", {}).get("count") == 0)
t("diag.period_empty", out.get("diag", {}).get("period_empty") is True)

# --- hotfix 18.08: пустое «позавчера» не recount all-time и не 503 ---
intent_pz = {
    "want": "sum",
    "period": {"from": "2026-08-16", "to": "2026-08-16"},
    "parse": {"assumed": ["period.from", "period.to"]},
    "amount": {},
}
agg0 = dict(agg, count=0, sum=0.0, src="document_реализациятмц",
            outside_period=8246)
t("позавчера: period_empty при count=0",
  A.period_empty_outcome(agg0, "drop_assumed", intent_pz, {}))
alltime = dict(agg0, count=8246, sum=79752611.64, count_amount=8246,
               date_min="2024-01-30", date_max="2026-12-31")
t("all-time итог не period_empty при count>0",
  not A.period_empty_outcome(alltime, "drop_assumed", intent_pz, {}))
txt_pz = A.format_period_empty_text(
    "сколько продали позавчера всего?", agg0, intent_pz, "Всего",
    "document_реализациятмц", True)
t("позавчера текст: 16.08", "16.08" in txt_pz, txt_pz)
t("позавчера текст: нет all-time 79752611",
  "79752611" not in txt_pz.replace(" ", "").replace("\u00a0", ""), txt_pz)

try:
    filled, _bad = A._fill_figures(
        "За 16.08 продали {total} с {date_min} по {date_max}.",
        alltime, [], True, {}, slot_mode="sum")
    t("fill all-time: не TypeError", True)
    t("fill all-time: сумма подставилась",
      "79" in filled.replace("\u00a0", "").replace(" ", ""), filled)
except TypeError as e:
    t("fill all-time: не TypeError", False, e)

rows_ok = [["k", "document_реализациятмц", 100.5, "2026-12-31", 0, "док"]] * 25
rows_mix = rows_ok + [79752611.64]
try:
    A.copied_figures("Итого {total}.", alltime, rows_mix)
    t("copied_figures: хвост-float не TypeError", True)
except TypeError as e:
    t("copied_figures: хвост-float не TypeError", False, e)
try:
    seen = A.rows_seen(rows_mix)
    t("rows_seen: хвост-float не TypeError", True)
    t("rows_seen: 25 строк корпуса", len(seen) == 25, len(seen))
except TypeError as e:
    t("rows_seen: хвост-float не TypeError", False, e)

src = open(A.__file__, encoding="utf-8").read()
t("пустое окно не зовёт drop_period_preds",
  "intent, preds = drop_period_preds" not in src)
t("флаг period_window_empty", "period_window_empty" in src)
t("пустышка меры не пивотит пустое окно",
  "if _мертва and not diag.get(\"period_window_empty\")" in src)
t("compose не режет r[5] вслепую",
  "doc, dt, amt = r[5], r[3], r[2]" in src)

out_pz = A.build_period_empty_answer(
    "сколько продали позавчера всего?", agg0, intent_pz, "Всего",
    "document_реализациятмц", "", [], True, "sum",
    None, None, {}, grain, [], 0, [], 0.0, "Всего")
t("позавчера kind=answer", out_pz.get("kind") == "answer", out_pz.get("kind"))
# bfe4166: sum как "0.00"; проверка — не all-time 79752611.
t("позавчера figures.sum=0 не all-time",
  out_pz.get("figures", {}).get("sum") in (0, 0.0, "0.00"),
  out_pz.get("figures"))

print("\nИТОГ:", "ok — все %d проверок прошли" % PASS if not FAIL
      else "FAIL — %d из %d: %s" % (len(FAIL), PASS + len(FAIL), ", ".join(FAIL)))
sys.exit(1 if FAIL else 0)
