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

# --- K9-ф4: distinct на event-пути ---
_old_lac = A.live_axis_col_for_count
A.live_axis_col_for_count = lambda intent, src, axes=None: "Контрагент"
try:
    t("count_defer_fork_outcomes event+axis",
      A.count_defer_fork_outcomes(
          {"want": "count", "action_class": "event", "kind": "клиенты",
           "action_axis": "клиенты"},
          "accumulationregister_x", []))
    t("count_defer_fork_outcomes sum -> False",
      not A.count_defer_fork_outcomes(
          {"want": "sum", "action_class": "event", "kind": "торги"},
          "accumulationregister_x", []))
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

_old_kah3 = A.kind_axis_hits
_old_ada3 = A.aggregate_distinct_axis
_old_ro3 = A.refcols_of
A.kind_axis_hits = lambda axes, word: ["Контрагент"] if word else []
A.refcols_of = lambda src: [{"col": "Контрагент", "target_src": "catalog_контрагенты"}]
A.aggregate_distinct_axis = lambda src, match, preds, col: {
    "count": 141, "sum": None, "src": src, "form": "distinct_axis",
    "axis": col, "grain": "axis"}
try:
    _agg = A.aggregate_distinct_axis(
        "accumulationregister_реализациятмц", "", ["doc_date >= '2026-08-01'"],
        "Контрагент")
    t("distinct agg has axis field", _agg.get("axis") == "Контрагент"
      and _agg.get("form") == "distinct_axis")
    _dd = {}
    t("fork_defer_distinct sets diag",
      A._fork_defer_distinct(
          {"want": "count", "action_class": "event", "kind": "клиенты",
           "action_axis": "клиенты"},
          "accumulationregister_реализациятмц", _dd)
      and _dd.get("fork_outcome_deferred_distinct"))
finally:
    A.kind_axis_hits = _old_kah3
    A.aggregate_distinct_axis = _old_ada3
    A.refcols_of = _old_ro3

print("---")
print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    sys.exit(1)
