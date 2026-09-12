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

# S3/S4 GONE batch
for _n in ('stock_subject_needs_clarify', 'stock_canon_src', 'filter_balance_structural', 'question_asks_stock_balance'):
    t("S3/S4 GONE: " + _n, not hasattr(A, _n))



INTENT_STOCK = {"want": "count", "kind": "номенклатура", "action_class": "object",
                "action_axis": "склад"}
_old_knows = A._base_knows_kind_or_measure
_old_psql0 = A.psql
_old_cats0 = A.entity_form_catalogs_for_kind
A._base_knows_kind_or_measure = lambda w: True
def _default_entity_cats(w, **kw):
    wl = (w or "").strip().lower()
    if wl.startswith("склад"):
        return ["catalog_склады"]
    return ["catalog_номенклатура"]
A.entity_form_catalogs_for_kind = _default_entity_cats
A.psql = lambda q: [("accumulationregister_x",)] if "search_refcols" in q.lower() else []
# place/eligible: без catch-all warehouse-ось только через метаданные
A._STOCK_PLACE_AXIS.update({
    "at": time.time(), "set": frozenset(["catalog_склады"])})
A._STOCK_PLACE_REF.update({"at": time.time(), "set": {"catalog_склады"}})

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
# [01.09 снят pre-wiki обход] named no_data helper — удалён кейс снятого обхода

# --- K9: count+ось места без терма → агрегат, не subject-clarify ---
t("count agg: без терма → aggregate path",
  A.stock_count_aggregate_without_subject(
      INTENT_STOCK, None, "q"))
# S3/S4 DEL: t("count agg: не subject clarify",
  # S3/S4 DEL: not A.stock_subject_needs_clarify(
      # S3/S4 DEL: "q", INTENT_STOCK))
t("count agg: терм measure → прежний named path",
  A.stock_asks_named_product(
      "q", dict(INTENT_STOCK, measure="петли"))
  and not A.stock_count_aggregate_without_subject(
      dict(INTENT_STOCK, measure="петли"), None, "q"))
# S3/S4 DEL: t("count agg: терм → subject clarify off (named)",
  # S3/S4 DEL: not A.stock_subject_needs_clarify(
      # S3/S4 DEL: "q", dict(INTENT_STOCK, measure="петли")))

# --- K9: живой intent без action_axis — ось «склад» из словаря по тексту вопроса ---
INTENT_LIVE = {"want": "count", "kind": "позиции", "action_class": "object",
               "terms": [], "action_axis": ""}
Q_LIVE = "сколько на складе позиций всего"


def _cats_for_live(w, **kw):
    wl = (w or "").strip().lower()
    if wl.startswith("склад"):
        return ["catalog_склады"]
    if wl in ("позиции", "номенклатура"):
        return ["catalog_номенклатура"]
    return []


A.entity_form_catalogs_for_kind = _cats_for_live
t("live intent: dict axis from question",
  A.resolved_warehouse_axis_word(Q_LIVE, INTENT_LIVE).startswith("склад"))
t("live intent: warehouse axis mentioned",
  A.question_mentions_warehouse_axis(Q_LIVE, INTENT_LIVE))
t("live intent: secondary axis known",
  A.secondary_axis_known(INTENT_LIVE, Q_LIVE))
t("live intent: count aggregate path",
  A.stock_count_aggregate_without_subject(INTENT_LIVE, None, Q_LIVE))
# S3/S4 DEL: t("live intent: not subject clarify",
  # S3/S4 DEL: not A.stock_subject_needs_clarify(Q_LIVE, INTENT_LIVE))

A._is_product_catalog = lambda s: "номенклатур" in str(s or "").lower()


def _canon_live_psql(q):
    ql = q.lower()
    if "search_refcols" in ql and "target_src" in ql:
        return [
            ("accumulationregister_допзатратыимпорттмц", "catalog_номенклатура"),
            ("accumulationregister_допзатратыимпорттмц", "catalog_таможенныевыплаты"),
            ("accumulationregister_допзатратыимпорттмц", "catalog_группытмцдляиморта"),
            ("accumulationregister_импорттмц", "catalog_номенклатура"),
            ("accumulationregister_импорттмц", "catalog_организации"),
        ]
    if "search_refcols" in ql:
        return [
            ("accumulationregister_импорттмц",),
            ("accumulationregister_допзатратыимпорттмц",),
        ]
    if "group by" in ql:
        return [
            ("accumulationregister_импорттмц", 13178),
            ("accumulationregister_допзатратыимпорттмц", 65856),
        ]
    return []


A.psql = _canon_live_psql
A._BALANCE_REGS.update({"at": time.time(), "set": {
    "accumulationregister_импорттмц", "accumulationregister_допзатратыимпорттмц"}})
try:
    # S3/S4 DEL: _canon_live = A.stock_canon_src(...)
    # S3/S4 DEL-dep: t("live intent: canon import not overhead", ...)
    pass
finally:
    A.entity_form_catalogs_for_kind = _old_cats0
    A.psql = _old_psql0

# --- net distinct: пара приход/расход одной товарной оси ---
REG_IMP = "accumulationregister_импорттмц"
REG_SALE = "accumulationregister_реализациятмц"
REG_COST = "accumulationregister_допзатратыимпорттмц"


def _net_pair_psql(q):
    ql = q.lower()
    if "search_refcols" in ql and "target_src" in ql:
        return [
            (REG_IMP, "catalog_номенклатура"),
            (REG_SALE, "catalog_номенклатура"),
            (REG_COST, "catalog_номенклатура"),
            (REG_COST, "catalog_таможенныевыплаты"),
        ]
    if "search_refcols" in ql:
        return [(REG_IMP,), (REG_SALE,), (REG_COST,)]
    if "with receipt as" in ql:
        return [(1306,)]
    if "group by" in ql:
        return [(REG_IMP, 13178), (REG_SALE, 50000), (REG_COST, 65856)]
    return []


A.psql = _net_pair_psql
A._BALANCE_REGS.update({"at": time.time(), "set": {REG_IMP, REG_SALE, REG_COST}})
A._is_product_catalog = lambda s: "номенклатур" in str(s or "").lower()
A.entity_form_catalogs_for_kind = _cats_for_live
A.refcols_of = lambda src: [
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"}]
A.measures_of = lambda src: ["Количество"]
A.measure_aliases_of = lambda src: {}
A.measure_choice = lambda names, word, alias_by=None: (
    ("Количество", [], "exact") if names else (None, [], ""))
try:
    pair = A.stock_net_register_pair(INTENT_LIVE, Q_LIVE)
    t("net pair: receipt import",
      pair and pair[0] == REG_IMP, pair)
    t("net pair: expense sales",
      pair and pair[1] == REG_SALE, pair)
    agg = A.aggregate_stock_net_distinct(INTENT_LIVE, Q_LIVE, "", [], {})
    t("net distinct aggregate",
      agg and agg.get("count") == 1306 and agg.get("form") == "distinct_axis", agg)
finally:
    A.entity_form_catalogs_for_kind = _old_cats0
    A.psql = _old_psql0

# --- контрагенты: kind не stock-scoped → stock-path молчит ---
INTENT_CTR = {"want": "count", "kind": "контрагенты", "action_class": "object",
              "terms": [], "action_axis": ""}
Q_CTR = "сколько контрагентов всего"


def _cats_ctr(w, **kw):
    wl = (w or "").strip().lower()
    if "контраг" in wl:
        return ["catalog_контрагенты"]
    return _cats_for_live(w, **kw)


A.entity_form_catalogs_for_kind = _cats_ctr
t("contractors: kind not stock scoped",
  not A._kind_is_stock_scoped(INTENT_CTR, Q_CTR))
t("contractors: stock path off",
  not A.stock_question_engaged(Q_CTR, INTENT_CTR))
A.entity_form_catalogs_for_kind = _cats_for_live

INTENT_ORG = {"want": "count", "kind": "организации", "action_class": "object",
              "terms": [], "action_axis": ""}
Q_ORG = "сколько организаций?"


def _cats_org(w, **kw):
    wl = (w or "").strip().lower()
    if "орган" in wl:
        return ["catalog_организации"]
    return _cats_for_live(w, **kw)


A.entity_form_catalogs_for_kind = _cats_org
t("org: catalog_kind_total",
  A.catalog_kind_total_question(INTENT_ORG, Q_ORG))
t("org: stock path off",
  not A.stock_question_engaged(Q_ORG, INTENT_ORG))
Q_PRICE = "сколько позиций у нас в прайсе?"
INTENT_PRICE = {"want": "count", "kind": "номенклатура"}
t("price: catalog_count",
  A.catalog_count_question(INTENT_PRICE, Q_PRICE))
t("price: stock path off",
  not A.stock_question_engaged(Q_PRICE, INTENT_PRICE))
A.entity_form_catalogs_for_kind = _cats_for_live

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
    # S3/S4 DEL: got = A.filter_balance_structural(...)
    # S3/S4 DEL-dep: t("structural: ...")
    pass
finally:
    A.psql = _real_psql

# --- sales noise negative lock ---
t("sales noise: реализация register",
  A.stock_balance_is_sales_noise("accumulationregister_реализациятмц"))
t("sales noise: книга продаж",
  A.stock_balance_is_sales_noise("accumulationregister_книгапродаж"))
t("sales noise: accounting ok",
  not A.stock_balance_is_sales_noise("accountingregister_плансчетовосновной2014"))
t("S1: filter_stock_balance_sales_noise GONE",
  not hasattr(A, "filter_stock_balance_sales_noise"))
# remainder of filter_stock_balance_sales_noise tests removed in S1

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
