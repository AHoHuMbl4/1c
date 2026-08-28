#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""K9: action_class/action_axis в разборе и COUNT(DISTINCT ось) без базы.

Запуск: python3 ubuntu/serenedb/test_action_class.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402
import entity_rank_v2 as K6  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


def parse_one(reply, **kw):
    calls, queue = [], [reply]

    def fake(messages, **_):
        calls.append(messages)
        return queue[0]

    real = (A.ds_chat, A.INTENT_SAMPLES, A.INTENT_MEMO, A.INTENT_LEAD)
    A.ds_chat, A.INTENT_SAMPLES = fake, 1
    A.INTENT_MEMO, A.INTENT_LEAD = 0, 2
    try:
        return A._normalize_intent(
            __import__("json").loads(reply),
            kw.get("question", "вопрос"),
        )
    finally:
        A.ds_chat, A.INTENT_SAMPLES, A.INTENT_MEMO, A.INTENT_LEAD = real


# --- разбор: схема event/object/none ---
t("action_class event",
  parse_one('{"kind":"клиенты","want":"count","action_class":"event",'
            '"action_axis":"клиенты","terms":[]}')["action_class"] == "event")
t("action_class object",
  parse_one('{"kind":"клиенты","want":"count","action_class":"object",'
            '"terms":[]}')["action_class"] == "object")
t("action_class missing → none",
  parse_one('{"kind":"клиенты","want":"count","terms":[]}')["action_class"] == "none")
t("action_class garbage → none",
  parse_one('{"kind":"x","want":"count","action_class":"verb","terms":[]}'
            )["action_class"] == "none")
t("action_axis string",
  parse_one('{"kind":"клиенты","want":"count","action_class":"event",'
            '"action_axis":"покупатели","terms":[]}')["action_axis"] == "покупатели")
t("action_axis missing → empty",
  parse_one('{"kind":"клиенты","want":"count","terms":[]}')["action_axis"] == "")

# --- entity_rank_v2: event tier ---
_feat_mov = {"prefix": "accumulationregister", "cls": "business",
             "axis_fit": 2, "holds_kind_axis": True, "n_dated": 10}
_feat_cat = {"prefix": "catalog", "cls": "business", "is_kind_catalog": True,
             "n_cards": 100, "axis_fit": 0}
_k_mov = K6.rank_key_v2(
    "accumulationregister_x", _feat_mov,
    {"want": "count", "action_class": "event"}, "distinct", 5)
_k_cat = K6.rank_key_v2(
    "catalog_y", _feat_cat,
    {"want": "count", "action_class": "event"}, "distinct", 0)
t("event: movement before catalog", _k_mov < _k_cat, (_k_mov, _k_cat))

t("infer_rank_form event+count → distinct",
  K6.infer_rank_form({"want": "count", "action_class": "event"}, "") == "distinct")

t("dual_atom clarify on none",
  K6._dual_atom_clarify({"action_class": "none"}) is True)
t("dual_atom no clarify on event",
  K6._dual_atom_clarify({"action_class": "event"}) is False)

# --- COUNT(DISTINCT): структура без psql ---
_old_kah = A.kind_axis_hits
_old_ra = A.refcols_of
_old_ada = A.aggregate_distinct_axis
A.kind_axis_hits = lambda axes, word: ["Контрагент"] if word else []
A.refcols_of = lambda src: [{"col": "Контрагент", "target_src": "catalog_x"}]
A.aggregate_distinct_axis = lambda src, match, preds, col: {
    "count": 141, "sum": None, "src": src, "form": "distinct_axis",
    "axis": col, "grain": "axis"}
try:
    col = A.live_axis_col_for_count(
        {"want": "count", "action_class": "event", "kind": "клиенты",
         "action_axis": "клиенты"},
        "accumulationregister_реализациятмц")
    t("live_axis_col event movement", col == "Контрагент", col)
    t("live_axis_col object → None",
      A.live_axis_col_for_count(
          {"want": "count", "action_class": "object", "kind": "клиенты"},
          "catalog_контрагенты") is None)
    t("live_axis_col catalog src → None",
      A.live_axis_col_for_count(
          {"want": "count", "action_class": "event", "kind": "клиенты"},
          "catalog_контрагенты") is None)
finally:
    A.kind_axis_hits = _old_kah
    A.refcols_of = _old_ra
    A.aggregate_distinct_axis = _old_ada

# --- K9-ф2: count+ось → defer clarify мер ---
_old_kah2 = A.kind_axis_hits
A.kind_axis_hits = lambda axes, word: (
    ["Контрагент"] if word and axes else [])
try:
    t("count_defer_measure_clarify event+axis",
      A.count_defer_measure_clarify(
          {"want": "count", "action_class": "event", "kind": "клиенты",
           "action_axis": "клиенты"},
          "accumulationregister_x",
          [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]))
    t("count_defer no axis → False",
      not A.count_defer_measure_clarify(
          {"want": "count", "action_class": "event", "kind": "клиенты"},
          "accumulationregister_x", []))
    t("count_defer sum want → False",
      not A.count_defer_measure_clarify(
          {"want": "sum", "action_class": "event", "kind": "клиенты"},
          "accumulationregister_x",
          [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]))
finally:
    A.kind_axis_hits = _old_kah2

# --- K9-ф3: event code pick (офлайн, без psql) ---
_old_k6r = A.K6R
_feats_f3 = {
    "accumulationregister_sales": {
        "prefix": "accumulationregister", "holds_kind_axis": True,
        "n_with_nums": 10, "axis_fit": 2, "has_qty_measure": 1,
        "has_money_measure": 1, "n_ref_axes": 4},
    "accumulationregister_книгапокупок": {
        "prefix": "accumulationregister", "holds_kind_axis": True,
        "n_with_nums": 10, "axis_fit": 2, "has_qty_measure": 0,
        "has_money_measure": 1, "n_ref_axes": 1},
}
class _K6Stub:
    @staticmethod
    def event_rank_pick(cands, feats, intent, question=""):
        return _old_k6r.event_rank_pick(cands, feats, intent, question)
    @staticmethod
    def event_movement_pool(cands, feats, intent):
        return _old_k6r.event_movement_pool(cands, feats, intent)
A.K6R = _K6Stub
_old_pe = A.pick_entity
A.pick_entity = lambda *a, **k: (_ for _ in ()).throw(AssertionError("model called"))
try:
    _intent = {"want": "count", "action_class": "event", "kind": "клиенты",
               "action_axis": "клиенты"}
    _diag = {"answer_fit_v2_full": _feats_f3}
    _out = A.try_event_code_entity_pick(
        "сколько покупают", _intent,
        ["accumulationregister_книгапокупок", "accumulationregister_sales"],
        _diag, {}, 0.0, {}, "", [], {})
    t("event_code_pick: leader without model",
      _out and _out.get("picked") == ["accumulationregister_sales"])
    t("event_code_pick: diag lock",
      _diag.get("event_code_lock") == "accumulationregister_sales")
finally:
    A.pick_entity = _old_pe
    A.K6R = _old_k6r

# --- K9-ф4/ф5: event distinct + fork A/B/C ---
_old_lac = A.live_axis_col_for_count
A.live_axis_col_for_count = lambda intent, src, axes=None: "Контрагент"
try:
    t("event_duel_applies two axis movements",
      A.event_duel_applies(
          {"want": "count", "action_class": "event", "kind": "клиенты",
           "action_axis": "клиенты"},
          ["accumulationregister_a", "accumulationregister_b"]))
    t("event_duel_applies sum -> False",
      not A.event_duel_applies(
          {"want": "sum", "action_class": "event"},
          ["accumulationregister_a", "accumulationregister_b"]))
finally:
    A.live_axis_col_for_count = _old_lac

class _K6Stub2:
    @staticmethod
    def event_movement_pool(cands, feats, intent):
        return []
    @staticmethod
    def event_rank_pick(cands, feats, intent, question=""):
        return None, []
    @staticmethod
    def event_movement_any(cands):
        return K6.event_movement_any(cands)
A.K6R = _K6Stub2
try:
    _out2 = A.try_event_code_entity_pick(
        "сколько наторговали", {"want": "sum", "action_class": "event"},
        ["accumulationregister_sales"], {"answer_fit_v2_full": {}}, {}, 0.0,
        {}, "", [], {})
    t("event_code_pick: empty pool + movement -> None", _out2 is None)
finally:
    A.K6R = _old_k6r

# fork A/B/C на distinct-атомах (офлайн)
_intent_ev = {"want": "count", "action_class": "event", "kind": "клиенты",
              "action_axis": "клиенты"}

def _row_dist(n):
    return {"count": n, "folders": 0, "sums": {},
            "distinct_axis": "Контрагент", "distinct_axis_label": "Контрагенты"}

def _fc_dist(rows):
    rel = {s: [] for s in rows}
    return A.fork_classes(rows, "", want="count", rel_by_src=rel)

_rows_eq = {"src_a": _row_dist(141), "src_b": _row_dist(141)}
_cls_eq = _fc_dist(_rows_eq)
out_a, pay_a = A.resolve_fork_outcome(_cls_eq, _rows_eq, want="count")
_ares = A.fork_outcome_a("q", pay_a["class"], {})
t("event duel equal -> A", out_a == "A" and _ares.get("kind") == "answer"
  and not (_ares.get("options") or []))

_rows_diff = {"src_a": _row_dist(141), "src_b": _row_dist(76)}
_cls_diff = _fc_dist(_rows_diff)
_old_fl = A.fork_labels_of
A.fork_labels_of = lambda fk, srcs: {s: "Движение %s" % s for s in srcs}
out_b, pay_b = A.resolve_fork_outcome(_cls_diff, _rows_diff, want="count")
_bres = A.fork_outcome_b("q", pay_b, {}, picked_src="src_a")
t("event duel diff+labels -> B", out_b == "B" and _bres and _bres.get("options")
  and len(_bres.get("options") or []) >= 1)
A.fork_labels_of = lambda fk, srcs: {}
out_c, pay_c = A.resolve_fork_outcome(_cls_diff, _rows_diff, want="count")
_cres = A.fork_outcome_c("q", pay_c, _cls_diff, _rows_diff, {}, picked_src="src_a")
t("event duel diff no labels -> C",
  out_c == "C" and pay_c.get("reason") == "unsigned_class"
  and A.FORK_OTHER_READING in (_cres.get("text") or ""))
A.fork_labels_of = _old_fl

_atom_a = A._fork_atom_of(_row_dist(141), ["src_a"], want="count")
t("distinct render carries axis",
  "Контрагенты" in (A.render_atom_pair(_atom_a) or "")
  and "141" in (A.render_atom_pair(_atom_a) or ""))

_old_kah3 = A.kind_axis_hits
_old_ada3 = A.aggregate_distinct_axis
_old_ro3 = A.refcols_of
_old_tl = A._table_label
A.kind_axis_hits = lambda axes, word: ["Контрагент"] if word else []
A.refcols_of = lambda src: [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
A._table_label = lambda src: "Контрагенты"
A.aggregate_distinct_axis = lambda src, match, preds, col: {
    "count": 141, "sum": None, "src": src, "form": "distinct_axis",
    "axis": col, "grain": "axis"}
try:
    _agg = A.aggregate_distinct_axis(
        "accumulationregister_реализациятмц", "", ["doc_date >= '2026-08-01'"],
        "Контрагент")
    t("distinct agg has axis field", _agg.get("axis") == "Контрагент"
      and _agg.get("form") == "distinct_axis")
    _rows = {"accumulationregister_x": {"count": 99, "folders": 0, "sums": {}}}
    _enr = A._event_distinct_fork_rows(
        _intent_ev, "", [], _rows, {"accumulationregister_x": []})
    t("event distinct fork rows",
      _enr["accumulationregister_x"].get("distinct_axis") == "Контрагент"
      and _enr["accumulationregister_x"].get("count") == 141)
finally:
    A.kind_axis_hits = _old_kah3
    A.aggregate_distinct_axis = _old_ada3
    A.refcols_of = _old_ro3
    A._table_label = _old_tl


# --- K9-ф6: kind→catalog axis (две ref-оси) ---
_axes_dual = [
    {"col": "Договор", "target_src": "catalog_договоры"},
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
]
_intent_k = {"want": "count", "action_class": "event", "kind": "клиенты",
             "action_axis": "клиенты",
             "period": {"from": "2026-08-01", "to": "2026-08-28"}}
_old_efc = A.entity_form_catalogs_for_kind
_old_kar = A.kind_axis_rerank
A.entity_form_catalogs_for_kind = lambda kind, allow_meaning=True: (
    ["catalog_контрагенты"] if kind == "клиенты" else [])
A.kind_axis_rerank = lambda axes, word: [a["col"] for a in axes if a.get("col")]
try:
    col_dual = A.live_axis_col_for_count(
        _intent_k, "accumulationregister_реализациятмц", _axes_dual)
    t("kind duel axis picks counterparty col",
      col_dual == "Контрагент", col_dual)
    t("kind duel skips contract col",
      col_dual != "Договор", col_dual)
finally:
    A.entity_form_catalogs_for_kind = _old_efc
    A.kind_axis_rerank = _old_kar

# --- K9-ф6: mtd-distinct render ---
_agg_mtd = {"count": 76, "sum": None, "src": "accumulationregister_x",
            "form": "distinct_axis", "axis": "Контрагент", "grain": "axis"}
_axes_mtd = [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
_old_tl6 = A._table_label
A._table_label = lambda src: "Контрагенты" if "контрагент" in src else src
try:
    _atom_mtd = A.atom_from_agg(
        _agg_mtd, operation="count", grain="axis", form="distinct_axis",
        axis=A._passport_axis_label("Контрагент", _axes_mtd))
    _pair_mtd = A.render_atom_pair(_atom_mtd) or ""
    t("mtd distinct pair carries axis label",
      "76" in _pair_mtd and "Контрагенты" in _pair_mtd, _pair_mtd)
finally:
    A._table_label = _old_tl6



# --- K9-ф7: event+count без периода → clarify; явный период → нет ---
_intent_ev_nop = {"want": "count", "action_class": "event", "kind": "клиенты",
                  "action_axis": "клиенты", "period": {}}
_intent_ev_mtd = {"want": "count", "action_class": "event", "kind": "клиенты",
                  "action_axis": "клиенты",
                  "period": {"from": "2026-08-01", "to": "2026-08-28",
                             "interpretation_id": "mtd"}}
t("event_count_period_unspecified: пустой period",
  A.event_count_period_unspecified(_intent_ev_nop, {}))
t("event_count_period_unspecified: mtd задан",
  not A.event_count_period_unspecified(_intent_ev_mtd, {}))
t("event_count_period_unspecified: drop_assumed",
  A.event_count_period_unspecified(_intent_ev_mtd,
                                 {"period_assumed_dropped": True}))

_old_lac7 = A.live_axis_col_for_count
A.live_axis_col_for_count = lambda intent, src, axes=None: "Контрагент"
try:
    t("event_count_period_clarify_applies: event+axis+нет period",
      A.event_count_period_clarify_applies(
          _intent_ev_nop, {}, src="accumulationregister_x", axes=[]))
    t("event_count_period_clarify_applies: mtd → False",
      not A.event_count_period_clarify_applies(
          _intent_ev_mtd, {}, src="accumulationregister_x", axes=[]))
    _opts = A.event_count_period_option_readings(today="2026-08-28")
    t("period options: >=4 readings",
      len(_opts) >= 4 and any(r.get("interpretation_id") == "rolling_12m"
                              for r in _opts))
    _ids = {r.get("interpretation_id") for r in _opts}
    t("period options: month/quarter/year/none",
      {"full_month", "full_quarter", "rolling_12m", "none"} <= _ids)
    _cl = A.event_count_period_clarify(
        "сколько покупают", _intent_ev_nop, {}, None, 0.0, today="2026-08-28")
    t("period clarify: kind+options",
      _cl and _cl.get("kind") == "clarify"
      and len(_cl.get("options") or []) >= 4
      and all(isinstance(o.get("period"), dict) for o in _cl["options"]))
finally:
    A.live_axis_col_for_count = _old_lac7

# mtd entity_form axis label (ф7)
_old_efc = A.entity_form_compute
_old_ro = A.refcols_of
_old_tl = A._table_label
_old_ada = A.aggregate_distinct_axis
A.refcols_of = lambda src: [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
A._table_label = lambda src: "Контрагенты"
A.aggregate_distinct_axis = lambda src, match, preds, col: {
    "count": 76, "form": "distinct_axis", "axis": col}
try:
    _atom_ef = A.entity_form_compute(
        "distinct_axis",
        {"sales_src": "accumulationregister_x", "axis": "Контрагент",
         "period": {"from": "2026-08-01", "to": "2026-08-28"}},
        match="")
    _pair_ef = A.render_atom_pair(_atom_ef) or ""
    t("entity_form mtd distinct axis label",
      "76" in _pair_ef and "Контрагенты" in _pair_ef, _pair_ef)
finally:
    A.entity_form_compute = _old_efc
    A.refcols_of = _old_ro
    A._table_label = _old_tl
    A.aggregate_distinct_axis = _old_ada

# --- K9-ф8: явный период event+count → нет assumed-clarify; terminal mtd label ---
_intent_ev_year = {"want": "count", "action_class": "event", "kind": "клиенты",
                   "action_axis": "клиенты",
                   "period": {"from": "2025-08-28", "to": "2026-08-28",
                              "interpretation_id": "rolling_12m"},
                   "parse": {"assumed": ["period.from", "period.to"]}}
_intent_sum_year = {"want": "sum", "kind": "продажи",
                    "period": {"from": "2025-08-28", "to": "2026-08-28"},
                    "parse": {"assumed": ["period.from", "period.to"]}}
t("event_count_has_explicit_period: rolling year в разборе",
  A.event_count_has_explicit_period(_intent_ev_year, {}))
t("period_assumed_needs_clarify: event+year → False",
  not A.period_assumed_needs_clarify(_intent_ev_year, today="2026-08-28"))
t("period_assumed_needs_clarify: sum+year assumed → True",
  A.period_assumed_needs_clarify(_intent_sum_year, today="2026-08-28"))

_old_ada8 = A.aggregate_distinct_axis
_old_lac8 = A.live_axis_col_for_count
_old_pal8 = A._passport_axis_label
_old_ro8 = A.refcols_of
A.live_axis_col_for_count = lambda intent, src, axes=None: "Контрагент"
A.refcols_of = lambda src: [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
A._passport_axis_label = lambda col, axes: "Контрагенты"
A.aggregate_distinct_axis = lambda src, match, preds, col: {
    "count": 76, "form": "distinct_axis", "axis": col, "grain": "axis"}
try:
    _intent_mtd_ev = {"want": "count", "action_class": "event", "kind": "клиенты",
                      "action_axis": "клиенты",
                      "period": {"from": "2026-08-01", "to": "2026-08-28",
                                 "interpretation_id": "mtd"}}
    _agg_row = {"count": 76, "sum": None, "src": "accumulationregister_x",
                "grain": "row"}
    _diag8 = {}
    _dac8 = A.live_axis_col_for_count(_intent_mtd_ev, "accumulationregister_x", [])
    if _dac8:
        _diag8["count_distinct_axis"] = _dac8
    _agg8 = _agg_row
    if _dac8 and (_agg8 or {}).get("form") != "distinct_axis":
        _dagg8 = A.aggregate_distinct_axis("x", "", [], _dac8)
        if _dagg8:
            _agg8 = _dagg8
    _ax_col8 = (_agg8 or {}).get("axis") or _diag8.get("count_distinct_axis")
    _ax_lab8 = A._passport_axis_label(_ax_col8, []) or (_ax_col8 or "")
    _atom8 = A.build_answer_atom(
        operation="count", exact_value=_agg8.get("count"), measure_id=None,
        measure_label=None, axis=_ax_lab8 or None, form="distinct_axis",
        proof_status=A.PROOF_COMPUTED, grain="axis")
    _pair8 = A.render_atom_pair(_atom8) or ""
    t("event mtd distinct terminal pair",
      "76" in _pair8 and "Контрагенты" in _pair8 and "assumed" not in _pair8,
      _pair8)
finally:
    A.aggregate_distinct_axis = _old_ada8
    A.live_axis_col_for_count = _old_lac8
    A._passport_axis_label = _old_pal8
    A.refcols_of = _old_ro8

# --- K9-ф9: kind-каталог → осевое движение в пул ---
_pool_lex = ["document_возвраттмцотпокупателя", "accumulationregister_кассовыеордера"]
_intent_buy_mtd = {"want": "count", "action_class": "event", "kind": "покупатели",
                   "action_axis": "покупатели",
                   "period": {"from": "2026-08-01", "to": "2026-08-28"}}
_intent_nokind = {"want": "count", "action_class": "event", "kind": "",
                  "period": {"from": "2026-08-01", "to": "2026-08-28"}}
_old_efc9 = A.entity_form_catalogs_for_kind
_old_hot9 = A.holders_of_target
A.entity_form_catalogs_for_kind = lambda kind, allow_meaning=True: (
    ["catalog_контрагенты"] if kind == "покупатели" else [])
A.holders_of_target = lambda target: (
    [{"src": "accumulationregister_реализациятмц", "col": "Контрагент"}]
    if target == "catalog_контрагенты" else [])
try:
    _exp9 = A.event_kind_catalog_expand_pool(_pool_lex, _intent_buy_mtd)
    t("kind pool expand: adds sales register without lexical hit",
      "accumulationregister_реализациятмц" in _exp9
      and "catalog_контрагенты" in _exp9, _exp9)
    _exp9b = A.event_kind_catalog_expand_pool(_pool_lex, _intent_nokind)
    t("kind pool expand: no kind -> pool unchanged",
      _exp9b == _pool_lex, _exp9b)
    _exp9c = A.event_kind_catalog_expand_pool(
        _pool_lex,
        {"want": "count", "action_class": "object", "kind": "покупатели"})
    t("kind pool expand: object -> pool unchanged",
      _exp9c == _pool_lex, _exp9c)
finally:
    A.entity_form_catalogs_for_kind = _old_efc9
    A.holders_of_target = _old_hot9

_old_efc9b = A.entity_form_catalogs_for_kind
A.entity_form_catalogs_for_kind = lambda kind, allow_meaning=True: []
try:
    _exp9d = A.event_kind_catalog_expand_pool(_pool_lex, _intent_buy_mtd)
    t("kind pool expand: no catalog link -> pool unchanged",
      _exp9d == _pool_lex, _exp9d)
finally:
    A.entity_form_catalogs_for_kind = _old_efc9b

# distinct-ответ: подпись оси на mtd-пути (контроль ф9)
_axes9 = [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
_old_tl9 = A._table_label
A._table_label = lambda src: "Контрагенты" if "контрагент" in src else src
try:
    _atom9 = A.atom_from_agg(
        {"count": 43, "form": "distinct_axis", "axis": "Контрагент", "grain": "axis"},
        operation="count", grain="axis", form="distinct_axis",
        axis=A._passport_axis_label("Контрагент", _axes9))
    _pair9 = A.render_atom_pair(_atom9) or ""
    t("distinct mtd pair axis label (43 buyers)",
      "43" in _pair9 and "Контрагенты" in _pair9 and "assumed" not in _pair9,
      _pair9)
finally:
    A._table_label = _old_tl9

print("---")
print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
