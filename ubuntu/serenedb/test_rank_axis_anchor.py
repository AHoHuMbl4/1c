#!/usr/bin/env python3
"""Rank axis ticket, measure anchor, stock no_data — оффлайн замки (18.08)."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# --- дефект 1: билет оси не схлопывает rank в скаляр ---
intent_top = {"want": "list", "kind": "товар", "amount": {"value": 1}}
plan_top = {}
grain_rank = {"grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "clarify": None}
ticket = A.grain_dec_from_axis_ticket(intent_top, plan_top, grain_rank, "refs_map.ТМЦ")
t("axis ticket grain=group", ticket.get("grain") == "group", ticket)
t("axis ticket form=rank", ticket.get("form") == "rank", ticket)
t("axis ticket col preserved", ticket.get("col") == "refs_map.ТМЦ", ticket)

intent_sum = {"want": "sum", "amount": {}}
ticket_sum = A.grain_dec_from_axis_ticket(
    intent_sum, {"compute": "sum"}, {"form": "number"}, "refs_map.ТМЦ")
t("axis ticket sum keeps form=number", ticket_sum.get("form") == "number", ticket_sum)

t("rank_intent ≡ breakdown for list",
  A.rank_intent_from(intent_top, plan_top)
  == A.question_wants_breakdown(intent_top, plan_top))

# --- дефект 2: якорение меры на рейтинг товара ---
names = ["Себестоимость", "Количество", "Всего"]
hint = A.rank_measure_hint(
    names, {"want": "list", "kind": "товар"}, "какого товара больше всего")
t("rank measure hint → Количество", hint == "Количество", hint)
t("rank measure skip when measure set",
  A.rank_measure_hint(names, {"want": "list", "measure": "Всего"},
                      "какого товара больше всего") is None)
t("rank measure skip on sum",
  A.rank_measure_hint(names, {"want": "sum"}, "сколько всего") is None)

# --- дефект 3: остаток без balance_registers → no_data ---
A._BALANCE_REGS.update({"at": 0.0, "set": frozenset()})
t("stock balance question",
  A.question_asks_stock_balance("какого товара больше всего на складе?"))
t("movement question not stock",
  not A.question_asks_stock_balance("какого товара больше всего по реализации"))
gap = A.stock_balance_no_data(
    "какого товара больше всего на складе?", {}, {}, time.time())
t("stock gap kind=no_data", gap and gap.get("kind") == "no_data", gap)
t("stock gap honest text", gap and "остатках" in (gap.get("text") or ""), gap)

A._BALANCE_REGS.update({"set": frozenset(["accumulationregister_остатки"])})
t("stock with balance regs → proceed",
  A.stock_balance_no_data("остаток на складе", {}, {}, time.time()) is None)

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
