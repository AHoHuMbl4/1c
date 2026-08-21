#!/usr/bin/env python3
"""Замки: канон «продали»=регистр; остаток именованный → no_data (возврат 8)."""
import os
import sys
import time

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


# --- intent ---
t("sales intent продали", A.sales_sum_intent({"want": "sum", "kind": "продажи"},
                                              "сколько продали сегодня?"))
t("sales intent наторговали", A.sales_sum_intent({"want": "sum", "measure": "торги"},
                                                 "сколько наторговали в воскресенье?"))
t("sales intent неделя лучше", A.sales_sum_intent({"want": "list"},
                                                  "эта неделя лучше прошлой или хуже?"))
t("sales intent не прайс", not A.sales_sum_intent({"want": "count"},
                                                  "сколько позиций у нас в прайсе?"))
t("sales intent не склад", not A.sales_sum_intent({"want": "sum"},
                                                 "сколько товара на складе?"))

# --- score ---
t("score: реализациятмц > книгапродаж",
  A._sales_register_score("accumulationregister_реализациятмц",
                          ["Всего", "Количество"])
  > A._sales_register_score("accumulationregister_книгапродаж",
                            ["Всего", "СуммаНДС", "СуммаБезНДС"]))


def _fake(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "parent, written_by" in q:
        return [
            ("document_реализациятмц", "", ""),
            ("accumulationregister_реализациятмц", "", "document_реализациятмц"),
            ("accumulationregister_книгапродаж", "", "document_реализациятмц"),
            ("document_приходныйкассовыйордер", "", ""),
        ]
    if "map_entries" in q or "search_measure" in q.lower() or "measures" in q.lower():
        return []
    raise RuntimeError(q[:120])


# _measures_by_src may call more SQL — stub broadly
_real_mbs = A._measures_by_src


def _fake_mbs(srcs):
    out = {}
    for s in srcs or []:
        if "реализациятмц" in s and s.startswith("accumulation"):
            out[s] = ["Всего", "Количество"]
        elif "книгапродаж" in s:
            out[s] = ["Всего", "СуммаНДС", "СуммаБезНДС"]
        else:
            out[s] = ["Всего"]
    return out


_old = A.psql
A.psql = _fake
A._measures_by_src = _fake_mbs
try:
    got = A.prefer_entity_for_sales(
        ["document_реализациятмц", "document_приходныйкассовыйордер",
         "accumulationregister_книгапродаж"],
        {"want": "sum", "kind": "продажи", "measure": "продали"},
        "сколько уже продали сегодня?")
    t("prefer: канон реализациятмц первым",
      got and got[0] == "accumulationregister_реализациятмц", got)
    t("prefer: документ регистратора снят",
      "document_реализациятмц" not in got, got)
    t("prefer: книгапродаж не первая",
      got and got[0] != "accumulationregister_книгапродаж", got)
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

# cold lift when only journals
_calls = {"cold": 0}


def _fake_cold(q):
    if "written_by IN" in q:
        return []
    if "parent, written_by" in q:
        return [
            ("documentjournal_розничнаяторговля", "", ""),
            ("documentjournal_оптоваяторговля", "", ""),
        ]
    if "LIKE 'accumulationregister_" in q and "written_by" in q and "IN" not in q:
        _calls["cold"] += 1
        return [("accumulationregister_реализациятмц",),
                ("accumulationregister_книгапродаж",)]
    if "SELECT written_by FROM" in q:
        return [("document_реализациятмц",)]
    raise RuntimeError(q[:120])


A.psql = _fake_cold
A._measures_by_src = _fake_mbs
try:
    got2 = A.prefer_entity_for_sales(
        ["documentjournal_розничнаяторговля", "documentjournal_оптоваяторговля"],
        {"want": "sum", "measure": "торги"},
        "сколько наторговали в прошедшее воскресенье?")
    t("cold lift: регистр продаж в голову",
      got2 and got2[0] == "accumulationregister_реализациятмц", got2)
    t("cold lift: SQL канона звался", _calls["cold"] >= 1, _calls)
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

# --- stock named ---
A._BALANCE_REGS.update({"at": time.time(), "set": frozenset([
    "accumulationregister_номерабсо", "accumulationregister_расчетныеначисления"])})
_real_goods = A.balance_registers_with_goods


def _no_goods(regs=None):
    return frozenset()


A.balance_registers_with_goods = _no_goods
try:
    gap = A.stock_balance_no_data(
        "сколько петель осталось на складе?", {}, {}, time.time(),
        intent={"measure": "петли", "want": "sum", "kind": "остаток"})
    t("петли: no_data при balance без ТМЦ", gap and gap.get("kind") == "no_data", gap)
    t("петли: named_absent",
      gap and (gap.get("diag") or {}).get("stock_balance_named_absent"), gap)
    gen = A.stock_balance_no_data(
        "сколько товара на складе?", {}, {}, time.time(),
        intent={"measure": "товара", "want": "sum", "kind": "товар"})
    t("товар на складе: не глушим (clarify путь)", gen is None, gen)
finally:
    A.balance_registers_with_goods = _real_goods
    A._BALANCE_REGS.update({"at": 0.0, "set": frozenset()})

gap0 = A.stock_balance_no_data("остаток на складе", {}, {}, time.time())
t("пустой balance_registers → no_data", gap0 and gap0.get("kind") == "no_data", gap0)


# --- override helpers ---
A.psql = _fake
A._measures_by_src = _fake_mbs
try:
    got3 = A.prefer_entity_for_sales(
        ["document_реализациятмц", "accumulationregister_книгапродаж",
         "accumulationregister_реализациятмц"],
        {"want": "sum", "kind": "продажи", "measure": "продали"},
        "сколько продали в прошлом месяце?")
    t("prefer: книгапродаж снята из пула",
      "accumulationregister_книгапродаж" not in got3, got3)
    t("prefer: документ снят", "document_реализациятмц" not in got3, got3)
    t("sales_canon_src lock",
      A.sales_canon_src(
          ["document_реализациятмц", "accumulationregister_книгапродаж"],
          {"want": "sum", "measure": "продали"},
          "сколько продали?") == "accumulationregister_реализациятмц")
finally:
    A.psql = _old
    A._measures_by_src = _real_mbs

t("period_zero_why sunday",
  A.period_zero_why_question("почему в воскресенье продаж ноль, это сбой?"))
t("period_zero_why not plain sales",
  not A.period_zero_why_question("сколько продали в воскресенье?"))

# catalog prefer
gotc = A.prefer_entity_for_catalog_count(
    ["informationregister_ценыноменклатуры", "document_установкаценноменклатуры",
     "catalog_номенклатура"],
    {"want": "count"}, "сколько позиций у нас в прайсе?")
t("catalog prefer: номенклатура первой",
  gotc and gotc[0] == "catalog_номенклатура", gotc)
t("catalog prefer: цены не в голове",
  gotc and "ценыноменклатуры" not in (gotc[0] or ""), gotc)

print("PASS", PASS, "FAIL", len(FAIL))
sys.exit(0 if not FAIL else 1)
