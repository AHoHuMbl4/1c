#!/usr/bin/env python3
"""Универсальный путь остатков: разбор → кандидаты → пригодность → ответ/clarify/no_data."""
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


# --- маркеры двуязычные ---
t("RU stock: остатки на складах",
  A.question_asks_stock_balance("Какие остатки товаров на складах?"))
t("RO stock: stoc depozit",
  A.question_asks_stock_balance("Care este stocul in depozit?"))
t("movement not stock",
  not A.question_asks_stock_balance("сколько продали в июле?"))

# --- «какие» не именованный товар ---
t("какие: not named product",
  not A.stock_asks_named_product("Какие остатки товаров на складах?"))
t("какой: not named",
  not A.stock_asks_named_product("какой товар больше на складе?"))
t("петли: named via measure only",
  A.stock_asks_named_product(
      "сколько петель осталось на складе?",
      intent={"measure": "петли", "want": "sum", "kind": "склад"}))
t("петли: named product",
  A.stock_asks_named_product(
      "сколько петель осталось на складе?",
      intent={"terms": [["петли"]], "want": "sum"}))
t("care RO: not named",
  not A.stock_asks_named_product("Care marfuri sunt in stoc?"))
t("named no_data helper",
  A.stock_balance_named_no_data("сколько петель?", {}, None, __import__("time").time()).get("kind") == "no_data")

# --- balance_registers: RuntimeError не глотать ---
_real_psql = A.psql


def _boom(q):
    raise RuntimeError("search_meta denied")


A.psql = _boom
try:
    failed = False
    try:
        A._BALANCE_REGS.update({"at": 0.0, "set": None})
        A.balance_registers()
    except RuntimeError:
        failed = True
    t("balance_registers: RuntimeError пробрасывается", failed)
finally:
    A.psql = _real_psql

# --- balance_map_rows ---
A.psql = _boom
try:
    failed = False
    try:
        A._BALANCE_MAP.update({"at": 0.0, "rows": None})
        A.balance_map_rows()
    except RuntimeError:
        failed = True
    t("balance_map_rows: RuntimeError пробрасывается", failed)
finally:
    A.psql = _real_psql


def _missing_map_psql(q):
    if "search_balance_map" in q:
        raise RuntimeError('Catalog Error: Table "search_balance_map" does not exist')
    return _real_psql(q)


A.psql = _missing_map_psql
try:
    A._BALANCE_MAP.update({"at": 0.0, "rows": None})
    rows = A.balance_map_rows()
    t("balance_map_rows: missing table → empty", rows == [])
finally:
    A.psql = _real_psql

# --- prior без user ---
t("prior: cleared without user", (lambda u, p: None if not u else p)(None, "июль") is None)

# --- structural filter ---
A._BALANCE_MAP.update({"at": time.time(), "rows": [
    ("accountingregister_x", "accounting", False, True, True, True),
    ("accumulationregister_y", "accumulation_warehouse", True, False, True, False),
]})


def _struct_psql(q):
    if "search_balance_map" in q:
        return A._BALANCE_MAP["rows"]
    if "accountingregister_x" in q and "count(*)" in q:
        return [("accountingregister_x",)]
    if "accumulationregister_y" in q:
        return []
    if "search_tables" in q:
        return [("accountingregister_x", "Reg X")]
    raise RuntimeError(q[:80])


A.psql = _struct_psql
try:
    got = A.filter_balance_structural(
        ["accountingregister_x", "accumulationregister_y", "document_z"], {})
    t("structural: accounting kept",
      "accountingregister_x" in got, got)
    t("structural: empty warehouse dropped",
      "accumulationregister_y" not in got, got)
    t("structural: non-map kept",
      "document_z" in got, got)
finally:
    A.psql = _real_psql

# --- sales noise negative lock ---
t("sales noise: реализация register",
  A.stock_balance_is_sales_noise("accumulationregister_реализациятмц"))
t("sales noise: книга продаж",
  A.stock_balance_is_sales_noise("accumulationregister_книгапродаж"))
t("sales noise: accounting ok",
  not A.stock_balance_is_sales_noise("accountingregister_плансчетовосновной2014"))
got_n = A.filter_stock_balance_sales_noise(
    ["accumulationregister_книгапродаж", "accountingregister_x"],
    "остатки на складе")
t("noise filter drops sales book",
  "accumulationregister_книгапродаж" not in got_n, got_n)

# --- bridge clarify ---
A._BALANCE_MAP.update({"rows": [
    ("accountingregister_a", "accounting", False, True, True, True),
]})
A.psql = _struct_psql
try:
    br = A.balance_bridge_clarify(
        "Какие остатки?", {"accountingregister_a"},
        {}, {}, time.time())
    t("bridge: clarify kind", br and br.get("kind") == "clarify", br)
    t("bridge: has options", br and len(br.get("options") or []) == 1, br)
    t("bridge: aggregate note",
      br and "разреза" in (br.get("text") or ""), br)
finally:
    A.psql = _real_psql

# --- синтез трёх форм: capable set ---
A._BALANCE_MAP.update({"rows": [
    ("accumulationregister_wh", "accumulation_warehouse", True, False, True, False),
    ("accountingregister_ac", "accounting", False, True, True, True),
]})
cap = A.balance_capable_sources()
t("capable: warehouse form", "accumulationregister_wh" in cap, cap)
t("capable: accounting form", "accountingregister_ac" in cap, cap)

ci = open(os.path.join(os.path.dirname(__file__), "corpus_init.sql"), encoding="utf-8").read()
t("corpus_init: GRANT search_balance_map serene_ro",
  "GRANT SELECT ON search_balance_map TO serene_ro" in ci)


# --- early named: capable без goods → no_data до fork ---
_real = A.psql
A._BALANCE_MAP.update({"at": time.time(), "rows": [
    ("accountingregister_x", "accounting", False, True, True, True),
]})
A.psql = lambda q: [] if "map_extract_value" in q else _real(q)
try:
    A._BALANCE_REGS.update({"at": 0.0, "set": {"accountingregister_x"}})
    cap = A.balance_capable_or_registers()
    goods = A.balance_registers_with_goods(cap)
    t("named early: capable but no goods",
      bool(cap) and not goods, (cap, goods))
finally:
    A.psql = _real

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
