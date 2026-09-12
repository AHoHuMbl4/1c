#!/usr/bin/env python3
"""Волна W / Z2 §3.3: plain count без breakdown → нет axis-clarify; rank → есть."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
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


z20 = (ROOT / "ask" / "z20_ask_main_http_legacy.py").read_text(encoding="utf-8")
z10 = (ROOT / "ask" / "z10_rank.py").read_text(encoding="utf-8")

# диск: kind не подставляется при plain
t("диск: _plain_ax гейт", "_plain_ax" in z20 and "question_wants_breakdown" in z20)
t("диск: count_question_skips_axis(..., plan)",
  "count_question_skips_axis(intent, measure, grain_dec, plan)" in z20)
t("z10: want ''|count|list",
  'want not in ("", "count", "list")' in z10
  or "want not in ('', 'count', 'list')" in z10)

grain_axis = {"grain": "group", "col": "X", "form": "number",
              "named_gis": [], "clarify": "axis"}

# plain count → skip
t("skip: want=count без measure",
  A.count_question_skips_axis({"want": "count"}, None, grain_axis) is True)
t("skip: want='' без measure",
  A.count_question_skips_axis({"want": ""}, None, grain_axis) is True)
t("skip: want=list без amount",
  A.count_question_skips_axis({"want": "list"}, None, grain_axis) is True)
t("нет skip: list+amount (разрез)",
  A.count_question_skips_axis(
      {"want": "list", "amount": {"value": 3}}, None, grain_axis) is False)

# breakdown / measure → не skip
t("нет skip: measure задана",
  A.count_question_skips_axis({"want": "count"}, "Сумма", grain_axis) is False)
t("нет skip: want=sum (total_question другой страж)",
  A.count_question_skips_axis({"want": "sum"}, None, grain_axis) is False)
t("нет skip: amount.value (breakdown)",
  A.count_question_skips_axis(
      {"want": "count", "amount": {"value": 5}}, None, grain_axis) is False)
t("нет skip: question_wants_breakdown list+amount",
  A.question_wants_breakdown({"want": "list", "amount": {"value": 3}}) is True
  or A.question_wants_breakdown({"want": "list"}) is True)

# rank: axis clarify остаётся (skip не глушит rank-путь в decide_grain)
t("rank_intent_from на топ",
  A.rank_intent_from({"want": "list"}, {}, "топ 10 по сумме")
  or A.rank_intent_from({"want": "list"}, {"compute": "max"}, "рейтинг"))

# total skip по-прежнему для sum
t("total_question_skips_axis sum",
  A.total_question_skips_axis(
      {"want": "sum"}, None, grain_axis, plan={"compute": "sum"},
      question="итого продаж") is True)


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
