#!/usr/bin/env python3
"""Замок: петля меню осей (билет axis + skip после decide_grain).

Корень 1: axis-опции без found → seal → consume → accumulate → resolved.axis.
Корень 2: count / sum+proven measure → _settle_axis без меню; rank → меню есть.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

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
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


def _reset():
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
        A._RESOLVED_CHOICES.clear()


# ── Корень 1: полный путь клика оси ──────────────────────────────────────────
_reset()
Q = "сколько продали на этой неделе"
USER = "web:axis-loop-lock"
axis_opts = [
    {"src": "register_demo", "label": "По контрагенту", "distinct_by": "Контрагент"},
    {"src": "register_demo", "label": "По договору", "distinct_by": "Договор"},
]
t("вход: axis opts без found",
  all("found" not in o for o in axis_opts)
  and A.ambiguity_of_options(axis_opts) == "axis")

resp = A.clarify_opts_response(Q, axis_opts, {}, None, 0.0, reason="уточните ось")
t("clarify_opts_response жив", resp is not None and resp.get("kind") == "clarify")
clean = (resp or {}).get("options") or []
t("после clarify_opts: found не синтезирован",
  all("found" not in o for o in clean),
  detail=repr(clean[:1]))
t("ambiguity после clarify_opts = axis",
  A.ambiguity_of_options(clean) == "axis")

sealed = A.seal_clarify(resp, Q, user=USER)
opt0 = (sealed.get("options") or [None])[0] or {}
tid = opt0.get("decision_id")
t("seal выдал decision_id", bool(tid))

ticket, err = A.consume_decision(tid, Q, user=USER)
t("consume ok", err is None and ticket is not None, detail=err)
t("ticket.ambiguity == axis", (ticket or {}).get("ambiguity") == "axis",
  detail=repr((ticket or {}).get("ambiguity")))
t("ticket.axis == Контрагент", (ticket or {}).get("axis") == "Контрагент",
  detail=repr((ticket or {}).get("axis")))

A.accumulate_resolution(Q, USER, ticket)
resolved = A.peek_resolved(Q, USER)
t("resolved.axis накоплен", resolved.get("axis") == "Контрагент",
  detail=repr(resolved))

# контрольный контраст: синтетический found ломал бы ambiguity
broken = [dict(o, found=0) for o in axis_opts]
t("контраст: found=0 → ambiguity entity",
  A.ambiguity_of_options(broken) == "entity")

# ── Корень 2: порядок skip в _settle_axis ────────────────────────────────────
_reset()

class _FakeAxis:
    @staticmethod
    def decide_grain(axes, kh, th, compute, is_child, rank_intent=False):
        return {"grain": "group", "col": None, "form": "number",
                "named_gis": [], "clarify": "axis"}


fake_axes = [
    {"col": "Контрагент", "target_src": "catalog_x"},
    {"col": "Договор", "target_src": "catalog_y"},
    {"col": "Склад", "target_src": "catalog_z"},
]

diag = {}
with mock.patch.object(A, "serene_axis", _FakeAxis), \
     mock.patch.object(A, "refcols_of", return_value=list(fake_axes)), \
     mock.patch.object(A, "kind_axis_hits", return_value=[]), \
     mock.patch.object(A, "term_axis_hits", return_value={}), \
     mock.patch.object(A, "src_is_child", return_value=False), \
     mock.patch.object(A, "rank_axis_resolve", return_value=(None, None)):
    # count без меры → skip, меню нет
    g1, ax1, alts1 = A._settle_axis(
        "register_demo", {"want": "count"}, {}, Q, None, {}, diag, None)
    t("count: axis_clarify_skipped",
      diag.get("axis_clarify_skipped") == "count_without_measure",
      detail=repr(diag))
    t("count: clarify погашен", g1.get("clarify") in (None, ""))
    t("count: меню оси пусто", not alts1)

    # sum + proven measure → total skip
    diag2 = {}
    resolved_m = {"src": "register_demo", "measure": "Сумма"}
    g2, ax2, alts2 = A._settle_axis(
        "register_demo", {"want": "sum"}, {"compute": "sum"},
        "сколько продали всего", None, resolved_m, diag2, "Сумма")
    t("sum+proven: axis_clarify_skipped total",
      diag2.get("axis_clarify_skipped") == "total_without_breakdown",
      detail=repr(diag2))
    t("sum+proven: меню оси пусто", not alts2)

    # rank / breakdown → меню остаётся (skip не глотает)
    diag3 = {}
    intent_rank = {"want": "list", "amount": {"value": 3}}
    g3, ax3, alts3 = A._settle_axis(
        "register_demo", intent_rank, {}, "топ-3 по складам",
        None, {}, diag3, None)
    t("rank: skip не сработал", "axis_clarify_skipped" not in diag3,
      detail=repr(diag3))
    t("rank: меню оси есть", len(alts3) > 1, detail=repr(alts3))

    # после клика оси → axis_from_choice, без второго меню
    diag4 = {}
    g4, ax4, alts4 = A._settle_axis(
        "register_demo", {"want": "sum"}, {"compute": "sum"}, Q,
        None, {"axis": "Контрагент", "measure": "Сумма"}, diag4, "Сумма")
    t("после клика: axis_from_choice",
      diag4.get("axis_from_choice") == "Контрагент", detail=repr(diag4))
    t("после клика: без меню", not alts4)

# ── Корень 2b: kind_hits>1 / count+rank до skip ─────────────────────────────
_reset()
kh_sklad = ["Склад", "СкладОтправитель"]
diag5 = {}
with mock.patch.object(A, "serene_axis", _FakeAxis), \
     mock.patch.object(A, "refcols_of", return_value=list(fake_axes) + [
         {"col": "СкладОтправитель", "target_src": "catalog_w"}]), \
     mock.patch.object(A, "kind_axis_hits", return_value=list(kh_sklad)), \
     mock.patch.object(A, "term_axis_hits", return_value={}), \
     mock.patch.object(A, "src_is_child", return_value=False), \
     mock.patch.object(A, "rank_axis_resolve", return_value=(None, None)):
    # (а) sum + action_axis + kind_hits>1 → меню = kind_hits, total-skip не глотает
    g5, ax5, alts5 = A._settle_axis(
        "register_demo",
        {"want": "sum", "action_axis": "склад"},
        {"compute": "sum"},
        "сколько продали по складам",
        None, {}, diag5, "Сумма")
    t("sum+kh>1: skip не сработал",
      "axis_clarify_skipped" not in diag5, detail=repr(diag5))
    t("sum+kh>1: alts == kind_hits",
      alts5 == kh_sklad, detail=repr(alts5))

# (б) want=count + ранговая фраза, без kind_hits>1 → count-skip не глотает
diag6 = {}
with mock.patch.object(A, "serene_axis", _FakeAxis), \
     mock.patch.object(A, "refcols_of", return_value=list(fake_axes)), \
     mock.patch.object(A, "kind_axis_hits", return_value=[]), \
     mock.patch.object(A, "term_axis_hits", return_value={}), \
     mock.patch.object(A, "src_is_child", return_value=False), \
     mock.patch.object(A, "rank_axis_resolve", return_value=(None, None)):
    g6, ax6, alts6 = A._settle_axis(
        "register_demo",
        {"want": "count"},
        {},
        "топ-3 по складам",
        None, {}, diag6, None)
    t("count+rank: skip не сработал",
      "axis_clarify_skipped" not in diag6, detail=repr(diag6))
    t("count+rank: меню оси есть",
      len(alts6) > 1, detail=repr(alts6))


print()
print("PASS %d  FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
