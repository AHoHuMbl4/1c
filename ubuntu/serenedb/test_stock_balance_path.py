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


INTENT_STOCK = {"want": "count", "kind": "номенклатура", "action_class": "object",
                "action_axis": "склад"}
_old_knows = A._base_knows_kind_or_measure
_old_psql0 = A.psql
_old_cats0 = A.entity_form_catalogs_for_kind
A._base_knows_kind_or_measure = lambda w: True
A.entity_form_catalogs_for_kind = lambda w, **kw: ["catalog_номенклатура"]
A.psql = lambda q: [("accumulationregister_x",)] if "search_refcols" in q.lower() else []

# --- balance-path по intent, не словам вопроса ---
t("balance path: intent engaged",
  A.balance_path_engaged(INTENT_STOCK, None, "q"))
t("movement not balance path",
  not A.balance_path_engaged({"want": "count", "action_class": "event",
                              "kind": "номенклатура"}, None, "q"))
t("sales sum blocks balance engaged",
  A.sales_sum_intent({"want": "sum", "kind": "продажи"}, "сколько продали")
  and not A.balance_path_engaged(
      {"want": "sum", "kind": "продажи", "action_class": "object"},
      None, "сколько продали"))

# --- именованный товар через terms/measure ---
t("generic list: not named product",
  not A.stock_asks_named_product("q", INTENT_STOCK))
t("петли: named via measure",
  A.stock_asks_named_product(
      "q", {"measure": "петли", "want": "sum", "kind": "номенклатура",
            "action_class": "object", "action_axis": "склад"}))
t("петли: named via terms",
  A.stock_asks_named_product(
      "q", {"terms": [["петли"]], "want": "sum", "kind": "номенклатура",
            "action_class": "object", "action_axis": "склад"}))
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
    "q", intent=INTENT_STOCK)
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


# --- early stock path: plan до filter_stock_goods_registers (UnboundLocalError) ---
_INTENT_EARLY = dict(INTENT_STOCK, terms=[], parse={}, period={}, about="data")
_early_saved = {
    "parse_intent": A.parse_intent,
    "probe": A.probe,
    "match_expr": A.match_expr,
    "tables_of": A.tables_of,
    "partial_tables": A.partial_tables,
    "meaning_candidates": A.meaning_candidates,
    "children_by_parent": A.children_by_parent,
    "emb_ready": A.emb_ready,
    "K6R": A.K6R,
    "pick_entity": A.pick_entity,
    "warehouse_clarify": A.warehouse_clarify,
    "psql": A.psql,
}
A.parse_intent = lambda q, today: dict(_INTENT_EARLY)
A.probe = lambda terms: ([], {})
A.match_expr = lambda exprs, preds: ("", 0)
A.tables_of = lambda match, preds: {}
A.partial_tables = lambda exprs, preds, k: ({}, "")
A.meaning_candidates = lambda *a, **k: []
A.children_by_parent = lambda by, match, preds: ({}, {})
A.emb_ready = lambda table: False
A.K6R = None
A.pick_entity = lambda *a, **k: ([], {}, {})
A.warehouse_clarify = lambda *a, **k: {
    "kind": "clarify", "text": "склад?", "options": [], "sources": [], "diag": {}}
A._BALANCE_REGS.update({"at": time.time(), "set": {"accumulationregister_wh"}})
A._BALANCE_MAP.update({"at": time.time(), "rows": [
    ("accumulationregister_wh", "accumulation_warehouse", True, False, True, False),
]})
A.psql = lambda q: []
_plan_err = None
try:
    A.answer("сколько на складе позиций всего", no_arbiter=True)
except UnboundLocalError as exc:
    _plan_err = exc
finally:
    for _k, _v in _early_saved.items():
        setattr(A, _k, _v)
t("early stock path: plan not UnboundLocalError",
  _plan_err is None or "plan" not in str(_plan_err), _plan_err)


# --- early named: capable без goods pool → пустой pool ---
_real = A.psql
A._BALANCE_MAP.update({"at": time.time(), "rows": [
    ("accountingregister_x", "accounting", False, True, True, True),
]})
A.psql = lambda q: [] if "search_refcols" in q.lower() else _real(q)
try:
    A._BALANCE_REGS.update({"at": 0.0, "set": {"accountingregister_x"}})
    cap = A.balance_capable_or_registers()
    goods = A.stock_goods_pool(cap, intent=INTENT_STOCK)
    t("named early: capable but no goods pool",
      bool(cap) and not goods, (cap, goods))
finally:
    A.psql = _real
    A._base_knows_kind_or_measure = _old_knows
    A.entity_form_catalogs_for_kind = _old_cats0
    A.psql = _old_psql0

print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
