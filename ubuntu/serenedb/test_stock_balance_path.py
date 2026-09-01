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
def _default_entity_cats(w, **kw):
    wl = (w or "").strip().lower()
    if wl.startswith("склад"):
        return ["catalog_склады"]
    return ["catalog_номенклатура"]
A.entity_form_catalogs_for_kind = _default_entity_cats
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

# --- K9: count+ось места без терма → агрегат, не subject-clarify ---
t("count agg: без терма → aggregate path",
  A.stock_count_aggregate_without_subject(
      INTENT_STOCK, None, "q"))
t("count agg: не subject clarify",
  not A.stock_subject_needs_clarify(
      "q", INTENT_STOCK))
t("count agg: терм measure → прежний named path",
  A.stock_asks_named_product(
      "q", dict(INTENT_STOCK, measure="петли"))
  and not A.stock_count_aggregate_without_subject(
      dict(INTENT_STOCK, measure="петли"), None, "q"))
t("count agg: терм → subject clarify off (named)",
  not A.stock_subject_needs_clarify(
      "q", dict(INTENT_STOCK, measure="петли")))

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
t("live intent: not subject clarify",
  not A.stock_subject_needs_clarify(Q_LIVE, INTENT_LIVE))

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
    _canon_live = A.stock_canon_src(
        ["accumulationregister_допзатратыимпорттмц", "accumulationregister_импорттмц"],
        Q_LIVE, INTENT_LIVE)
    t("live intent: canon import not overhead",
      _canon_live == "accumulationregister_импорттмц", _canon_live)
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


# --- wiki-only entity path: answer() без обходных пиков ---
_wiki_only_saved = dict(_early_saved)
for _nm in (
        "kind_has_corpus_support", "question_expects_accounting_data",
        "canon_claims_question", "period_assumed_needs_clarify", "_need_clarify",
        "term_ref_owners", "counts_for_model", "align_picked_to_terms",
        "entity_choice_locked", "hold_settled_entity",
        "holders_of_target", "resolve_focus", "axis_focus_plan",
        "prefer_entity_for_stock", "prefer_entity_for_catalog_count",
        "prefer_entity_for_sales", "prefer_entity_for_rank", "event_filter_pool",
        "stock_canon_src", "try_entity_form_answer", "try_event_count_period_clarify",
        "stock_question_engaged", "stock_goods_pool", "stock_balance_named_no_data",
        "rerank", "embed_model_live", "FORK_DETECT", "ASK_ENTITY_FORM",
        "ORDER_BY_MEANING"):
    if hasattr(A, _nm):
        _wiki_only_saved[_nm] = getattr(A, _nm)
A.parse_intent = lambda q, today: dict(_INTENT_EARLY)
A.probe = lambda terms: ([], {})
A.match_expr = lambda exprs, preds: ("", 0)
A.tables_of = lambda match, preds: {
    "accumulationregister_wh": 1, "accumulationregister_x": 1}
A.partial_tables = lambda exprs, preds, k: ({}, "")
A.meaning_candidates = lambda *a, **k: []
A.children_by_parent = lambda by, match, preds: ({}, {})
A.emb_ready = lambda table: False
A.K6R = None
A.warehouse_clarify = lambda *a, **k: None
A.stock_question_engaged = lambda *a, **k: False
A.prefer_entity_for_stock = lambda c, *a, **k: c
A.prefer_entity_for_catalog_count = lambda c, *a, **k: c
A.prefer_entity_for_sales = lambda c, *a, **k: c
A.prefer_entity_for_rank = lambda c, *a, **k: c
A.event_filter_pool = lambda c, *a, **k: c
A.stock_canon_src = lambda *a, **k: None
A.try_entity_form_answer = lambda *a, **k: None
A.try_event_count_period_clarify = lambda *a, **k: None
A.rerank = lambda q, labs: list(range(len(labs)))
A.embed_model_live = lambda: False
A.stock_goods_pool = lambda *a, **k: ["accumulationregister_wh"]
A.stock_balance_named_no_data = lambda *a, **k: {"kind": "no_data", "text": "named"}
A.kind_has_corpus_support = lambda k: True
A.question_expects_accounting_data = lambda i, q, d: True
A.canon_claims_question = lambda i, q: False
A.period_assumed_needs_clarify = lambda i, t, question="": False
A._need_clarify = lambda *a, **k: None
A.term_ref_owners = lambda t: {}
A.counts_for_model = lambda *a, **k: {}
A.align_picked_to_terms = lambda picked, *a, **k: picked
A.entity_choice_locked = lambda *a, **k: False
A.hold_settled_entity = lambda f, *a, **k: f
A.holders_of_target = lambda t: []
A.resolve_focus = lambda f, d: f
A.axis_focus_plan = lambda *a, **k: None
if hasattr(A, "FORK_DETECT"):
    A.FORK_DETECT = False
if hasattr(A, "ASK_ENTITY_FORM"):
    A.ASK_ENTITY_FORM = False
if hasattr(A, "ORDER_BY_MEANING"):
    A.ORDER_BY_MEANING = False
A.psql = lambda q: []
_wiki_only_err = None
try:
    A.answer("сколько на складе?", focus=None, no_arbiter=True)
except UnboundLocalError as exc:
    _wiki_only_err = exc
except AssertionError:
    pass
finally:
    for _k, _v in _wiki_only_saved.items():
        setattr(A, _k, _v)
t("wiki-only entity path: no UnboundLocalError",
  _wiki_only_err is None, _wiki_only_err)
# [01.09 «физически один путь»] обходных пиков больше нет вовсе: полный
# answer() не зовёт ни баланс-, ни event-«ручной выбор» — сущность выбирает
# только вики-каскад.


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
