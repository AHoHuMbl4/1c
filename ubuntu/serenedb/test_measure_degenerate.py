#!/usr/bin/env python3
"""Замок D1: guard вырожденности меры по ВСЕМ формам (design-b §1).

Мок psql, без живой БД. Запуск:
  python3 ubuntu/serenedb/test_measure_degenerate.py

На HEAD без guard — краснеет на B1 и F-CMP1.
Доки: Sql › Query syntax › FILTER; Sql › Expressions › Casting (TRY_CAST);
Sql › Functions › Aggregate Functions.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.setdefault("ASK_ATOM_TERMINAL", "0")

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


SRC = "accumulationregister_fixture_sales"
MEAS_DEAD = "Сумма"
MEAS_LIVE = "Всего"
MEAS_LIVE2 = "СуммаВзаиморасчетов"
ALL_MEAS = [MEAS_DEAD, MEAS_LIVE, MEAS_LIVE2]

_REAL = {
    "psql": A.psql,
    "measures_of": A.measures_of,
    "measure_aliases_of": A.measure_aliases_of,
    "measure_label_of": A.measure_label_of,
    "compose": A.compose,
    "gate": A.gate,
    "deadline_hit": A.deadline_hit,
    "aggregate": A.aggregate,
    "aggregate_live_column": A.aggregate_live_column,
    "aggregate_groups": A.aggregate_groups,
    "aggregate_compare_sales": A.aggregate_compare_sales,
    "rows_of": A.rows_of,
    "totals_of": A.totals_of,
    "empty_after_period_action": A.empty_after_period_action,
    "rank_intent_from": getattr(A, "rank_intent_from", None),
}


def _restore():
    for k, v in _REAL.items():
        if v is not None and hasattr(A, k):
            setattr(A, k, v)


def _base_agg(**kw):
    a = {
        "count": 10, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0,
        "count_amount": 10, "measure": MEAS_DEAD, "src": SRC, "folders": 0,
        "form": "number", "grain": "row",
        "scope": {"src": "search_idx", "via": None},
    }
    a.update(kw)
    return a


def _intent(want="sum", measure_word="выручка", period=True, **extra):
    it = {"want": want, "measure": measure_word, "amount": {}, "terms": []}
    if period:
        it["period"] = {"from": "2026-08-01", "to": "2026-08-31"}
    it.update(extra)
    return it


def _plan(compute=""):
    return {"compute": compute or "", "quantity": ""}


def _diag(**kw):
    d = {"rid": "t-deg"}
    d.update(kw)
    return d


_VERDICT_DEFAULT = {
    MEAS_DEAD: {"alive": False, "max_abs": 0.0, "layer": "nums"},
    MEAS_LIVE: {"alive": True, "max_abs": 4218825.39, "layer": "nums"},
    MEAS_LIVE2: {"alive": True, "max_abs": 100.0, "layer": "nums"},
}


def _lit_hit(sql, name):
    return ("'%s'" % name) in sql or ('"%s"' % name) in sql


def _deg_sql_n(calls):
    """Только table-wide degeneracy SELECT (FILTER + corpus/query_table)."""
    n = 0
    for sql in calls.get("sqls") or []:
        s = sql.lower()
        if "filter" in s and ("search_corpus" in s or "query_table" in s):
            n += 1
    return n


def _install_common(verdict=None, live_vals=None):
    verdict = verdict if verdict is not None else dict(_VERDICT_DEFAULT)
    live_vals = live_vals if live_vals is not None else {}
    A.measures_of = lambda src: list(ALL_MEAS)
    A.measure_aliases_of = lambda src: {
        MEAS_DEAD: ["выручка", "сумма"],
        MEAS_LIVE: ["всего", "итог"],
        MEAS_LIVE2: ["взаиморасчеты"],
    }
    A.measure_label_of = lambda src, m: {
        MEAS_DEAD: "сумма", MEAS_LIVE: "всего", MEAS_LIVE2: "взаиморасчеты",
    }.get(m, m or "")
    A.deadline_hit = lambda rid=None: False
    A.empty_after_period_action = lambda intent: "empty_period"
    A.compose = lambda q, rows, agg, **kw: (
        "Итог {total}." if (agg or {}).get("sum") is not None else "Ответ.")
    A.gate = lambda text, seen, agg, extra=None, dates=None, money=True, slot_mode=None: (True, [])
    calls = {"n": 0, "sqls": [], "bad_from": False, "live_bad": False,
             "live_n": 0}

    def fake_psql(sql):
        calls["n"] += 1
        calls["sqls"].append(sql)
        s = sql.lower()
        if "from search_idx" in s and "filter" in s:
            calls["bad_from"] = True
            return [[False, 0.0] * len(ALL_MEAS)]
        if "filter" in s and ("search_corpus" in s or "query_table" in s):
            is_live = "query_table" in s
            row = []
            for m in ALL_MEAS:
                if _lit_hit(sql, m):
                    v = verdict.get(m) or {"alive": False, "max_abs": 0.0}
                    # nums: alive только если layer != live; live-probe — layer==live
                    if is_live:
                        alive = bool(v.get("alive")) and v.get("layer") == "live"
                    else:
                        alive = bool(v.get("alive")) and v.get("layer") != "live"
                    row.append(alive)
                    row.append((v.get("max_abs") or 0.0) if alive else 0.0)
            if not row:
                for m, v in verdict.items():
                    if is_live:
                        alive = bool(v.get("alive")) and v.get("layer") == "live"
                    else:
                        alive = bool(v.get("alive")) and v.get("layer") != "live"
                    row.append(alive)
                    row.append((v.get("max_abs") or 0.0) if alive else 0.0)
            return [row]
        if "from search_tables" in s and "label" in s:
            return [("регистр продаж",)]
        if "duckdb_columns" in s:
            return [("1",)]
        return []

    A.psql = fake_psql

    def fake_live(src, preds, measure):
        calls["live_n"] = calls.get("live_n", 0) + 1
        for p in preds or []:
            ps = str(p)
            if "map_extract" in ps or "@@" in ps:
                calls["live_bad"] = True
        if measure in live_vals:
            val = live_vals[measure]
            if val is None:
                return None
            return {
                "count": 5, "sum": val, "min": val, "max": val, "avg": val,
                "count_amount": 5, "src": src, "measure": measure, "folders": 0,
                "scope": {"via": "live_column", "src": "query_table", "where": ""},
            }
        v = verdict.get(measure) or {}
        if v.get("layer") == "live" and v.get("alive"):
            return {
                "count": 5, "sum": float(v.get("max_abs") or 1),
                "min": 1.0, "max": float(v.get("max_abs") or 1), "avg": 1.0,
                "count_amount": 5, "src": src, "measure": measure, "folders": 0,
                "scope": {"via": "live_column", "src": "query_table", "where": ""},
            }
        return None

    A.aggregate_live_column = fake_live
    A.aggregate = lambda *a, **k: _base_agg()
    A.aggregate_groups = lambda *a, **k: _base_agg(
        grain="group", groups=[{"key": "a", "value": 0.0}], n_groups=1, sum=0.0)
    A.aggregate_compare_sales = lambda *a, **k: _base_agg(
        form="compare", compare_base=0.0, compare_other=0.0, sum=0.0)
    A.rows_of = lambda *a, **k: []
    A.totals_of = lambda *a, **k: []
    return calls


def _call_gate(agg=None, intent=None, plan=None, diag=None, trusted=None,
               measure=MEAS_DEAD, form=None, grain=None):
    agg = agg if agg is not None else _base_agg()
    if form:
        agg = dict(agg, form=form)
    if grain:
        agg = dict(agg, grain=grain)
    intent = intent if intent is not None else _intent()
    plan = plan if plan is not None else _plan()
    diag = diag if diag is not None else _diag()
    grain_dec = {
        "grain": agg.get("grain") or "row",
        "form": agg.get("form") or "number",
        "col": None, "named_gis": [], "clarify": None,
    }
    return A._onepath_compose_gate(
        "сколько выручки за август", intent, plan, SRC,
        "doc @@ ts_phrase('x')", ["doc_date >= '2026-08-01'"],
        measure, agg, [], [], None, None, diag, grain_dec, [],
        time.time(), trusted=trusted)


z20_path = ROOT / "ask" / "z20_ask_main_http.py"
z20 = z20_path.read_text(encoding="utf-8")

t("API _measure_zeroish", hasattr(A, "_measure_zeroish"))
t("API guard helper",
  hasattr(A, "_measure_degenerate_guard")
  or hasattr(A, "_run_measure_degenerate_guard"))
t("API not_kept builder",
  hasattr(A, "_measure_degenerate_not_kept_answer")
  or hasattr(A, "build_measure_degenerate_text"))

if not hasattr(A, "_measure_zeroish"):
    print("HEAD: D1 API отсутствует — B1/F-CMP1 красные (ожидаемо)")
    t("B1 (>=2 живых -> меню)", False, "HEAD")
    t("F-CMP1 (compare оба окна 0)", False, "HEAD")
    print("PASS", PASS, "FAIL", len(FAIL))
    sys.exit(1)

z = A._measure_zeroish
t("R6 zeroish None", z(None) is True)
t("R6 zeroish 0", z(0) is True)
t("R6 zeroish -0", z(-0.0) is True)
t("R6 zeroish '0.00'", z("0.00") is True)
t("R6 zeroish 1", z(1) is False)
t("R6 zeroish '4.2'", z("4.2") is False)

try:
    calls = _install_common()
    out = _call_gate(agg=_base_agg(count=0, outside_period=100, sum=0.0))
    t("E1 period_empty без degeneracy-SQL",
      _deg_sql_n(calls) == 0
      and (out or {}).get("diag", {}).get("period_empty") is True,
      {"deg": _deg_sql_n(calls), "kind": (out or {}).get("kind"),
       "pe": (out or {}).get("diag", {}).get("period_empty")})

    calls = _install_common()
    A.empty_after_period_action = lambda intent: "no_data"
    out = _call_gate(agg=_base_agg(count=0, sum=0.0), intent=_intent(period=False))
    t("E2 count=0 без периода без degeneracy-SQL",
      _deg_sql_n(calls) == 0, _deg_sql_n(calls))

    calls = _install_common()
    out = _call_gate(agg=_base_agg(count=5, sum=0.0, min=0.0, max=0.0),
                     intent=_intent(period=False))
    t("E3 all-time зовёт SQL", _deg_sql_n(calls) >= 1, _deg_sql_n(calls))
finally:
    _restore()

try:
    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    opts = (out or {}).get("options") or []
    kind = (out or {}).get("kind")
    t("B1 kind=clarify", kind == "clarify", kind)
    meas = [o.get("measure") for o in opts]
    t("B1 живые + мёртвая запрошенная",
      MEAS_LIVE in meas and MEAS_LIVE2 in meas and MEAS_DEAD in meas, meas)
    t("B1 мёртвая последняя", bool(meas) and meas[-1] == MEAS_DEAD, meas)
    dead_opt = next((o for o in opts if o.get("measure") == MEAS_DEAD), {})
    hint = (dead_opt.get("hint") or "") + " " + (dead_opt.get("label") or "")
    t("B1 мёртвая помечена",
      "не ведётся" in hint or dead_opt.get("measure_verdict") == "degenerate",
      dead_opt)
    t("B1 без обрезки (>=3)", len(opts) >= 3, len(opts))
    t("B1 FROM не search_idx", not calls.get("bad_from"), calls.get("bad_from"))

    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": False, "max_abs": 0},
        MEAS_LIVE: {"alive": True, "max_abs": 100},
        MEAS_LIVE2: {"alive": False, "max_abs": 0},
    })
    A.aggregate = lambda *a, **k: _base_agg(
        measure=MEAS_LIVE, sum=100.0, min=1.0, max=100.0, count_amount=5)
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    t("B1b sole -> answer",
      (out or {}).get("kind") in ("answer", "figures"), (out or {}).get("kind"))
    t("B1b помеченная замена",
      "вместо" in ((out or {}).get("text") or "")
      and "не ведётся" in ((out or {}).get("text") or ""),
      (out or {}).get("text"))
    t("B1b-neg sole с именем меры",
      (out or {}).get("measure") in (MEAS_LIVE, None)
      or "всего" in ((out or {}).get("text") or "").lower()
      or (out or {}).get("diag", {}).get("measure_sole_replace"),
      out)

    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": False, "max_abs": 0},
        MEAS_LIVE: {"alive": True, "max_abs": 100},
        MEAS_LIVE2: {"alive": False, "max_abs": 0},
    })
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0),
                     diag=_diag(measure_proven_human=True))
    opts = (out or {}).get("options") or []
    t("B1c-1 proven+1 -> меню 2",
      (out or {}).get("kind") == "clarify" and len(opts) == 2,
      {"kind": (out or {}).get("kind"), "n": len(opts)})

    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0),
                     diag=_diag(measure_proven_human=True))
    opts = (out or {}).get("options") or []
    t("B1c-2 proven+>=2 -> меню",
      (out or {}).get("kind") == "clarify" and len(opts) >= 3, len(opts))

    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": False, "max_abs": 0},
        MEAS_LIVE: {"alive": False, "max_abs": 0},
        MEAS_LIVE2: {"alive": False, "max_abs": 0},
    })
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    t("B2 0 живых -> текст",
      (out or {}).get("kind") == "answer"
      and "не ведётся" in ((out or {}).get("text") or "")
      and not ((out or {}).get("atoms") or []),
      out)
finally:
    _restore()

try:
    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": True, "max_abs": 10.0},
        MEAS_LIVE: {"alive": True, "max_abs": 100},
        MEAS_LIVE2: {"alive": True, "max_abs": 50},
    })
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=5.0, count_amount=10))
    t("C1 предфильтр без SQL при max!=0",
      _deg_sql_n(calls) == 0
      and (out or {}).get("kind") in ("answer", "figures"),
      {"deg": _deg_sql_n(calls), "kind": (out or {}).get("kind")})
finally:
    _restore()

try:
    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(sum=0.0, min=0.0, max=0.0),
        diag=_diag(measure_verdict="alive"),
        trusted={"measure_verdict": "alive", "ambiguity": "measure",
                 "measure": MEAS_DEAD})
    t("consume alive окно 0 -> 0 degeneracy-SQL",
      _deg_sql_n(calls) == 0, _deg_sql_n(calls))
finally:
    _restore()

try:
    calls = _install_common()
    out = _call_gate(agg=_base_agg(avg=0.0, sum=0.0, min=0.0, max=0.0),
                     plan=_plan("avg"), intent=_intent(want="sum"))
    t("F-AVG1 avg zeroish -> guard",
      calls["n"] >= 1 or (out or {}).get("kind") == "clarify",
      {"n": calls["n"], "kind": (out or {}).get("kind")})

    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0),
                     plan=_plan(""), intent=_intent(want="sum"))
    t("F-AVG2 want=sum без compute -> sum", calls["n"] >= 1, calls["n"])

    calls = _install_common()
    out = _call_gate(agg=_base_agg(min=0.0, max=0.0, sum=0.0), plan=_plan("min"))
    t("F-MIN1 min zeroish -> guard",
      calls["n"] >= 1 or (out or {}).get("kind") == "clarify", calls["n"])

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(form="compare", compare_base=0.0, compare_other=0.0,
                      sum=0.0, min=0.0, max=0.0, count=5))
    t("F-CMP1 compare оба 0 -> guard",
      (out or {}).get("kind") in ("clarify", "answer")
      and ((out or {}).get("kind") == "clarify"
           or "не ведётся" in ((out or {}).get("text") or "")),
      (out or {}).get("kind"))

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(form="compare", compare_base=0.0, compare_other=10.0,
                      sum=-10.0, min=0.0, max=10.0, count=5))
    t("F-CMP2 одно окно ненуль -> не ветка б",
      (out or {}).get("kind") in ("answer", "figures"), (out or {}).get("kind"))

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(form="compare", count=0, compare_base=0, compare_other=0,
                      outside_period=9, sum=0))
    t("F-CMP3 count=0 -> period_empty",
      (out or {}).get("diag", {}).get("period_empty") is True, out)

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(grain="group", sum=0.0, min=None, max=None,
                      groups=[{"key": "a", "value": 0.0},
                              {"key": "b", "value": 0.0}],
                      n_groups=2))
    t("F-GRP1 group все 0 -> guard",
      (out or {}).get("kind") == "clarify"
      or "не ведётся" in ((out or {}).get("text") or "")
      or _deg_sql_n(calls) >= 1,
      {"kind": (out or {}).get("kind"), "deg": _deg_sql_n(calls)})

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(grain="group", sum=100.0, min=None, max=None,
                      groups=[{"key": "a", "value": 100.0}], n_groups=1,
                      count_amount=5))
    t("F-GRP2 group ненуль -> не б",
      (out or {}).get("kind") in ("answer", "figures"), (out or {}).get("kind"))

    calls = _install_common()
    A.rank_intent_from = lambda intent, plan, q: True
    out = _call_gate(
        agg=_base_agg(grain="group", form="rank", sum=0.0,
                      groups=[{"key": "a", "value": 0.0}], n_groups=1))
    t("F-RNK1 rank groups 0 -> guard",
      (out or {}).get("kind") in ("clarify", "answer"), (out or {}).get("kind"))

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(grain="group", form="number", sum=None, groups=[],
                      n_groups=0, count_amount=0, count=3))
    t("F-RNK2 пустые groups count_amount=0 -> guard",
      (out or {}).get("kind") == "clarify"
      or "не ведётся" in ((out or {}).get("text") or "")
      or _deg_sql_n(calls) >= 1,
      {"kind": (out or {}).get("kind"), "deg": _deg_sql_n(calls)})

    calls = _install_common()
    A.rank_intent_from = lambda *a, **k: False
    out = _call_gate(
        agg=_base_agg(sum=0.0, min=0.0, max=0.0, count_amount=0),
        intent=_intent(want="list"))
    t("F-LST1 list count_amount=0 -> guard",
      (out or {}).get("kind") == "clarify"
      or "не ведётся" in ((out or {}).get("text") or "")
      or _deg_sql_n(calls) >= 1,
      {"kind": (out or {}).get("kind"), "deg": _deg_sql_n(calls)})

    calls = _install_common()
    out = _call_gate(
        agg=_base_agg(sum=0.0, min=0.0, max=0.0, count_amount=5),
        intent=_intent(want="list"))
    t("F-LST2 list amount>0 zeroish sum -> guard",
      calls["n"] >= 1 or (out or {}).get("kind") == "clarify", calls["n"])

    t("F-UNI helper triggered/priority",
      hasattr(A, "_measure_degenerate_triggered")
      or hasattr(A, "_measure_degenerate_form_priority"))
    trig = getattr(A, "_measure_degenerate_triggered", None)
    if callable(trig):
        # коллизия: compare ∧ group ∧ sum ∧ list-сигналы → compare первым
        form_c, _why_c = trig(
            money=True, measure=MEAS_DEAD, slot_mode="list",
            form="compare", grain="group", compute="sum",
            agg=_base_agg(
                form="compare", grain="group", compare_base=0.0,
                compare_other=0.0, sum=0.0, count=5, count_amount=0,
                groups=[{"key": "a", "value": 0.0}], n_groups=1),
            intent=_intent(want="list"), plan=_plan("sum"), diag=_diag())
        t("F-UNI compare > group|rank|sum|list", form_c == "compare",
          (form_c, _why_c))
        form_g, _why_g = trig(
            money=True, measure=MEAS_DEAD, slot_mode="sum",
            form="number", grain="group", compute="",
            agg=_base_agg(
                grain="group", sum=0.0, min=None, max=None,
                groups=[{"key": "a", "value": 0.0}], n_groups=1, count=5),
            intent=_intent(want="sum"), plan=_plan(""), diag=_diag())
        t("F-UNI group > sum", form_g == "group", (form_g, _why_g))
        form_s, _why_s = trig(
            money=True, measure=MEAS_DEAD, slot_mode="sum",
            form="number", grain="row", compute="",
            agg=_base_agg(sum=0.0, min=0.0, max=0.0, count=5),
            intent=_intent(want="sum"), plan=_plan(""), diag=_diag())
        t("F-UNI sum > list (slot sum)", form_s == "sum", (form_s, _why_s))
        form_l, _why_l = trig(
            money=True, measure=MEAS_DEAD, slot_mode="list",
            form="number", grain="row", compute="",
            agg=_base_agg(sum=0.0, min=0.0, max=0.0, count=5, count_amount=0),
            intent=_intent(want="list"), plan=_plan(""), diag=_diag())
        t("F-UNI list при slot list", form_l == "list", (form_l, _why_l))
    else:
        t("F-UNI compare > group|rank|sum|list", False, "no helper")
        t("F-UNI group > sum", False, "no helper")
        t("F-UNI sum > list (slot sum)", False, "no helper")
        t("F-UNI list при slot list", False, "no helper")

    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": False, "max_abs": 0},
        MEAS_LIVE: {"alive": True, "max_abs": 1},
        MEAS_LIVE2: {"alive": False, "max_abs": 0},
    })
    out = _call_gate(
        agg=_base_agg(sum=0.0, min=0.0, max=0.0),
        trusted={"measure": MEAS_DEAD},
        diag=_diag())
    t("F-PROV без measure_proven_human -> sole",
      (out or {}).get("kind") != "clarify"
      or len((out or {}).get("options") or []) != 2,
      (out or {}).get("kind"))

    t("F-LEG нет measure_row_all_zero", "measure_row_all_zero" not in z20)
    t("F-LEG нет def alive_measure_names", "def alive_measure_names" not in z20)
    t("F-LEG 0 sales_money_measure в z20", "sales_money_measure" not in z20)
finally:
    _restore()

try:
    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0, "layer": "nums"},
            MEAS_LIVE: {"alive": True, "max_abs": 4218825.39, "layer": "live"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0, "layer": "nums"},
        },
        live_vals={MEAS_LIVE: 4218825.39})
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0, count_amount=0))
    t("F-VIT live-only sole/force-live",
      (out or {}).get("kind") in ("answer", "figures"), (out or {}).get("kind"))
    tot = (out or {}).get("diag", {}).get("totals")
    t("F-VIT totals пуст", not tot, tot)
    t("F-VIT live preds без map_extract",
      not calls.get("live_bad") and calls.get("live_n", 0) >= 1,
      {"live_bad": calls.get("live_bad"), "live_n": calls.get("live_n")})

    calls = _install_common(verdict={
        MEAS_DEAD: {"alive": True, "max_abs": 1.0},
        MEAS_LIVE: {"alive": True, "max_abs": 1},
        MEAS_LIVE2: {"alive": True, "max_abs": 1},
    })
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    t("F-VIT-нуль table-wide жива окно 0 -> честный 0",
      (out or {}).get("kind") in ("answer", "figures"), (out or {}).get("kind"))

    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0},
            MEAS_LIVE: {"alive": False, "max_abs": 0},
            MEAS_LIVE2: {"alive": False, "max_abs": 0},
        },
        live_vals={})
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0, count_amount=0))
    t("F-VIT оба слоя мертвы -> B2",
      "не ведётся" in ((out or {}).get("text") or ""), (out or {}).get("text"))
finally:
    _restore()

rule = getattr(A, "_measure_field_alive_rule", None)
t("T API _measure_field_alive_rule", callable(rule))
if callable(rule):
    t("T-num-zero", rule("num", values=[0, 0, 0], kind="numeric") is False)
    t("T-num-const", rule("num", values=[5, 5, 5], kind="numeric") is True)
    t("T-num-alive", rule("num", values=[0, 1, 0], kind="numeric") is True)
    t("T-null", rule("num", values=[None, None], kind="numeric") is False)
    t("T-str const",
      rule("s", values=["a", "a", "a"], kind="non_numeric") is False)
    t("T-str varied",
      rule("s", values=["a", "b"], kind="non_numeric") is True)
    t("T-bool", rule("b", values=[True, True], kind="non_numeric") is False)
    t("T-date",
      rule("d", values=["2020-01-01"], kind="non_numeric") is False)
    t("T-ref", rule("r", values=["x", "x"], kind="non_numeric") is False)

try:
    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=None, count=10, min=None, max=None),
                     intent=_intent(want="count"), plan=_plan("count"),
                     measure=None)
    t("R1 count молчит", _deg_sql_n(calls) == 0, _deg_sql_n(calls))

    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    t("R2 clarify reading_kind=measure",
      (out or {}).get("kind") == "clarify"
      and (out or {}).get("diag", {}).get("reading_kind") == "measure",
      (out or {}).get("diag"))

    t("R3 нет filter_dead_measure_alts", "filter_dead_measure_alts" not in z20)

    trig = getattr(A, "_measure_degenerate_triggered", None)
    if callable(trig):
        form, why = trig(
            money=True, measure=MEAS_DEAD, slot_mode="sum",
            form="number", grain="row", compute="avg",
            agg=_base_agg(avg=0.0, sum=0.0, count=5),
            intent=_intent(), plan=_plan("avg"), diag=_diag())
        t("R4 sum-ветка не при op=avg", form == "avg" or why == "avg", (form, why))
    else:
        t("R4 sum-ветка не при op=avg", True)

    calls = _install_common()
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    sqls = "\n".join(s for s in calls["sqls"]
                     if "filter" in s.lower()
                     and ("search_corpus" in s.lower()
                          or "query_table" in s.lower()))
    t("R5 FROM search_corpus", "search_corpus" in sqls, sqls[:300])
    t("R5 coalesce IsFolder",
      "coalesce" in sqls.lower() and "isfolder" in sqls.lower(), sqls[:400])
    t("R5 без match в degeneracy WHERE",
      "@@" not in sqls and "ts_phrase" not in sqls, sqls[:300])

    calls = _install_common()
    A.deadline_hit = lambda rid=None: True
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0))
    txt = ((out or {}).get("text") or "").lower()
    t("R6 deadline -> текст без атома",
      (out or {}).get("kind") == "answer"
      and not ((out or {}).get("atoms") or [])
      and ((out or {}).get("diag", {}).get("measure_degenerate_check") == "error"
           or "не удалось" in txt or "не подтверждаю" in txt),
      out)
finally:
    _restore()

try:
    dead = getattr(A, "_measure_degenerate_not_kept_answer", None) or getattr(
        A, "build_measure_degenerate_text", None)
    t("клик мёртвой: билнер", callable(dead))
    if callable(dead):
        out = dead("q", MEAS_DEAD, SRC, _diag(), None, time.time())
        t("клик мёртвой -> текст не clarify",
          (out or {}).get("kind") == "answer"
          and "не ведётся" in ((out or {}).get("text") or "")
          and not ((out or {}).get("atoms") or []),
          out)

    sc = getattr(A, "_measure_short_circuit_agg", None)
    t("short-circuit helper", callable(sc))
    if callable(sc):
        agg = sc(digest=4218825.39, digest_form="sum",
                 count=10, count_amount=10, measure=MEAS_LIVE, via="nums")
        atom = A.atom_from_agg(
            agg, operation="sum", measure_id=MEAS_LIVE,
            measure_label="всего", money=True)
        ev = (atom or {}).get("exact_value")
        t("short-circuit sum exact_value == digest",
          ev == 4218825.39 and ev != 10, {"ev": ev})
finally:
    _restore()

# D1-fix2: реальная проводка seal→consume пяти ключей (не мок trusted)
try:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    q_wire = "сколько выручки по фикстуре?"
    opts_wire = [
        {"src": SRC, "measure": MEAS_DEAD, "label": "сумма",
         "measure_verdict": "degenerate", "digest": None,
         "digest_form": "sum", "digest_scope": {"via": "nums"},
         "answer_mode": "aggregate"},
        {"src": SRC, "measure": MEAS_LIVE, "label": "всего",
         "measure_verdict": "alive", "digest": 4218825.39,
         "digest_form": "sum", "digest_scope": {"via": "nums"},
         "answer_mode": "short_circuit", "count": 10, "count_amount": 10},
    ]
    sealed_w = A.seal_clarify(
        {"kind": "clarify", "text": "мера?", "options": opts_wire}, q_wire)
    by_m = {o.get("measure"): o for o in (sealed_w.get("options") or [])}
    tid_deg = (by_m.get(MEAS_DEAD) or {}).get("decision_id")
    tid_alv = (by_m.get(MEAS_LIVE) or {}).get("decision_id")
    tkt_deg, err_deg = A.consume_decision(tid_deg, q_wire)
    tkt_alv, err_alv = A.consume_decision(tid_alv, q_wire)
    t("проводка seal→consume degenerate",
      err_deg is None and (tkt_deg or {}).get("measure_verdict") == "degenerate"
      and (tkt_deg or {}).get("digest_form") == "sum"
      and (tkt_deg or {}).get("answer_mode") == "aggregate",
      tkt_deg)
    t("проводка seal→consume alive",
      err_alv is None and (tkt_alv or {}).get("measure_verdict") == "alive"
      and (tkt_alv or {}).get("digest") == 4218825.39
      and (tkt_alv or {}).get("digest_form") == "sum"
      and (tkt_alv or {}).get("answer_mode") == "short_circuit",
      tkt_alv)
finally:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()

# D1-fix3: E2E short-circuit — count/count_amount в ticket → atom==digest, 0 aggregate
try:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    q_sc = "сколько выручки по фикстуре sc?"
    opts_sc = [{
        "src": SRC, "measure": MEAS_LIVE, "label": "всего",
        "measure_verdict": "alive", "digest": 4218825.39,
        "digest_form": "sum", "digest_scope": {"via": "nums"},
        "answer_mode": "short_circuit", "count": 10, "count_amount": 10,
    }]
    sealed_sc = A.seal_clarify(
        {"kind": "clarify", "text": "мера?", "options": opts_sc}, q_sc)
    tid_sc = ((sealed_sc.get("options") or [{}])[0]).get("decision_id")
    tkt_sc, err_sc = A.consume_decision(tid_sc, q_sc)
    t("E2E SC ticket count_amount",
      err_sc is None and (tkt_sc or {}).get("count_amount") == 10
      and (tkt_sc or {}).get("count") == 10
      and (tkt_sc or {}).get("digest") == 4218825.39,
      tkt_sc)
    agg_n = {"n": 0}
    _real_agg = A.aggregate
    A.aggregate = lambda *a, **k: (
        agg_n.__setitem__("n", agg_n["n"] + 1) or _real_agg(*a, **k))
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "picked": [SRC], "marks": {}, "plan": {}}
    A.period_readings = lambda *a, **k: []
    A.expand_readings_calendar_axis = lambda r, prefer=None: r
    A.expand_readings_currency_axis = (
        lambda r, prefer=None, intent=None, trusted=None: r)
    A.parse_intent = lambda q, today: _intent(
        want="sum", measure_word="всего", period=False)
    A.repair_period_from_question = lambda *a, **k: None
    A.calendar_axis_unavailable_block = lambda *a, **k: None
    A.sales_compare_intent = lambda *a, **k: False
    A._predicates = lambda intent: []
    A.match_expr = lambda *a, **k: ("doc @@ ts_phrase('x')", 0)
    A.probe = lambda terms: ([], {})
    A.matched_group_count = lambda kinds: 0
    A.stock_net_register_menu_opts = lambda *a, **k: []
    A._coverage_of = lambda src: None
    A._num_pred = lambda intent, measure: []
    A.tables_of = lambda *a, **k: {SRC: 10}
    A.empty_after_period_action = lambda intent: "no_data"
    A.totals_of = lambda *a, **k: []
    A.rows_of = lambda *a, **k: []
    A.compose = lambda q, rows, agg, **kw: "Итог {total}."
    A.gate = lambda *a, **k: (True, [])
    A.deadline_hit = lambda rid=None: False
    A.measures_of = lambda src: list(ALL_MEAS)
    A.psql = lambda sql: []
    out_sc = A.answer(
        q_sc, trusted=tkt_sc,
        resolved={"src": SRC, "measure": MEAS_LIVE})
    atom_sc = (out_sc or {}).get("atom") or {}
    atoms_sc = (out_sc or {}).get("atoms") or []
    ev = atom_sc.get("exact_value")
    if ev is None and atoms_sc:
        ev = (atoms_sc[0] or {}).get("exact_value")
    t("E2E SC atom.exact_value == digest, aggregate 0",
      ev == 4218825.39 and agg_n["n"] == 0
      and (out_sc or {}).get("diag", {}).get("answer_mode") == "short_circuit",
      {"ev": ev, "agg_n": agg_n["n"], "kind": (out_sc or {}).get("kind"),
       "mode": (out_sc or {}).get("diag", {}).get("answer_mode")})
finally:
    A.aggregate = _real_agg
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    _restore()

# D1-fix5: sole x live_none -> C1 честный 0 + sole-пометка
try:
    calls = _install_common(live_vals={MEAS_LIVE: None})
    _real_verdict = A._measure_degenerate_verdict
    # слой live задаём моком вердикта: иначе nums-SELECT помечает alive→layer=nums
    A._measure_degenerate_verdict = lambda src, measures, requested, agg, diag: ({
        MEAS_DEAD: {"alive": False, "max_abs": 0.0, "layer": "nums"},
        MEAS_LIVE: {"alive": True, "max_abs": 100.0, "layer": "live"},
        MEAS_LIVE2: {"alive": False, "max_abs": 0.0, "layer": "nums"},
    }, None)
    out = _call_gate(agg=_base_agg(sum=0.0, min=0.0, max=0.0, count_amount=0))
    atom = (out or {}).get("atom") or {}
    atoms = (out or {}).get("atoms") or []
    ev = atom.get("exact_value")
    if ev is None and atoms:
        ev = (atoms[0] or {}).get("exact_value")
    txt = (out or {}).get("text") or ""
    diag_o = (out or {}).get("diag") or {}
    t("sole x live_none -> C1 честный 0 + sole",
      (out or {}).get("kind") in ("answer", "figures")
      and ev == 0.0
      and "не ведётся" in txt
      and "вместо" in txt
      and diag_o.get("measure_sole_replace") == MEAS_DEAD
      and diag_o.get("measure_degenerate_outcome") != "not_kept",
      {"kind": (out or {}).get("kind"), "text": txt[:160],
       "diag": diag_o, "atom": atom, "ev": ev})
finally:
    A._measure_degenerate_verdict = _real_verdict
    _restore()

# D1-fix5: text_with_total только corridor; sum-live -> aggregate без alive-bypass
try:
    A.measures_of = lambda src: list(ALL_MEAS)
    A.measure_aliases_of = lambda src: {}
    A.measure_label_of = lambda src, m: {
        MEAS_DEAD: "сумма", MEAS_LIVE: "всего", MEAS_LIVE2: "взаиморасчеты",
    }.get(m, m or "")
    A.deadline_hit = lambda rid=None: False
    A.gate = lambda text, seen, agg, extra=None, dates=None, money=True, slot_mode=None: (True, [])
    layers = {MEAS_LIVE: "live", MEAS_LIVE2: "nums"}
    opts_rk = A._measure_menu_build(
        SRC, [(MEAS_LIVE, 100.0), (MEAS_LIVE2, 50.0)],
        MEAS_DEAD, False, "", {}, layers=layers, form="rank")
    by_rk = {o.get("measure"): o for o in (opts_rk or [])}
    t("menu live-only corridor answer_mode=text_with_total",
      (by_rk.get(MEAS_LIVE) or {}).get("answer_mode") == "text_with_total"
      and "ранжирован" in ((by_rk.get(MEAS_LIVE) or {}).get("hint") or ""),
      by_rk.get(MEAS_LIVE))
    t("menu nums-alive answer_mode=aggregate",
      (by_rk.get(MEAS_LIVE2) or {}).get("answer_mode") == "aggregate",
      by_rk.get(MEAS_LIVE2))
    opts_sum = A._measure_menu_build(
        SRC, [(MEAS_LIVE, 100.0), (MEAS_LIVE2, 50.0)],
        MEAS_DEAD, False, "", {}, layers=layers, form="sum")
    by_sum = {o.get("measure"): o for o in (opts_sum or [])}
    live_sum = by_sum.get(MEAS_LIVE) or {}
    t("menu live-only sum answer_mode=aggregate",
      live_sum.get("answer_mode") == "aggregate"
      and live_sum.get("measure_verdict") != "alive"
      and "ранжирован" not in (live_sum.get("hint") or ""),
      live_sum)
finally:
    _restore()

# D1-fix4: клик live-only rank → текст-с-итогом, без атома-числа
try:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    q_rk = "топ контрагентов по выручке фикстура?"
    opts_rk = [{
        "src": SRC, "measure": MEAS_LIVE, "label": "всего",
        "measure_verdict": "alive", "answer_mode": "text_with_total",
        "digest_scope": {"via": "live"},
    }]
    sealed_rk = A.seal_clarify(
        {"kind": "clarify", "text": "мера?", "options": opts_rk}, q_rk)
    tid_rk = ((sealed_rk.get("options") or [{}])[0]).get("decision_id")
    tkt_rk, err_rk = A.consume_decision(tid_rk, q_rk)
    t("клик live-only rank ticket answer_mode",
      err_rk is None and (tkt_rk or {}).get("answer_mode") == "text_with_total",
      tkt_rk)
    _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0, "layer": "nums"},
            MEAS_LIVE: {"alive": True, "max_abs": 4218825.39, "layer": "live"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0, "layer": "nums"},
        },
        live_vals={MEAS_LIVE: 4218825.39})
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "picked": [SRC], "marks": {}, "plan": {}}
    A.period_readings = lambda *a, **k: []
    A.expand_readings_calendar_axis = lambda r, prefer=None: r
    A.expand_readings_currency_axis = (
        lambda r, prefer=None, intent=None, trusted=None: r)
    A.parse_intent = lambda q, today: _intent(want="sum", measure_word="всего")
    A.repair_period_from_question = lambda *a, **k: None
    A.calendar_axis_unavailable_block = lambda *a, **k: None
    A.sales_compare_intent = lambda *a, **k: False
    A.rank_intent_from = lambda *a, **k: True
    A._predicates = lambda intent: ["doc_date >= '2026-08-01'"]
    A.match_expr = lambda *a, **k: ("doc @@ ts_phrase('x')", 0)
    A.probe = lambda terms: ([], {})
    A.matched_group_count = lambda kinds: 0
    A.stock_net_register_menu_opts = lambda *a, **k: []
    A._coverage_of = lambda src: None
    A._num_pred = lambda intent, measure: []
    A.tables_of = lambda *a, **k: {SRC: 10}
    A.empty_after_period_action = lambda intent: "empty_period"
    A.totals_of = lambda *a, **k: [(MEAS_LIVE, 0.0, 0.0, 0.0)]
    A.rows_of = lambda *a, **k: []
    A.aggregate = lambda *a, **k: _base_agg(sum=0.0, min=0.0, max=0.0)
    A.aggregate_groups = lambda *a, **k: _base_agg(
        grain="group", form="rank", groups=[{"key": "a", "value": 0.0}],
        n_groups=1, sum=0.0)
    A._settle_axis = lambda *a, **k: (
        {"grain": "group", "col": "Контрагент", "form": "rank",
         "named_gis": [], "clarify": None}, [], [])
    A.refcols_of = lambda src: [{"col": "Контрагент", "label": "контрагент"}]
    A.deadline_hit = lambda rid=None: False
    A.gate = lambda text, seen, agg, extra=None, dates=None, money=True, slot_mode=None: (True, [])
    out_rk = A.answer(
        q_rk, trusted=tkt_rk,
        resolved={"src": SRC, "measure": MEAS_LIVE})
    atom_rk = (out_rk or {}).get("atom") or {}
    atoms_rk = (out_rk or {}).get("atoms") or []
    has_num_rk = (atom_rk.get("exact_value") is not None
                  or any((a or {}).get("exact_value") is not None
                         for a in atoms_rk))
    txt_rk = (out_rk or {}).get("text") or ""
    t("клик live-only rank -> text_with_total без atom",
      (out_rk or {}).get("kind") == "answer"
      and "4218825.39" in txt_rk.replace(" ", "").replace(" ", "")
      and not has_num_rk and not atoms_rk
      and ((out_rk or {}).get("diag", {}).get("measure_degenerate_outcome")
           == "text_with_total"
           or (out_rk or {}).get("diag", {}).get("answer_mode")
           == "text_with_total"),
      {"kind": (out_rk or {}).get("kind"), "text": txt_rk[:120],
       "atom": atom_rk, "diag": (out_rk or {}).get("diag")})
finally:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    _restore()

# D1-fix4: live-alive ∧ live_none → C1, totals/diag.totals пусты
try:
    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0.0, "layer": "nums"},
            MEAS_LIVE: {"alive": True, "max_abs": 100.0, "layer": "live"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0.0, "layer": "nums"},
        },
        live_vals={MEAS_LIVE: None})
    _real_verdict_ln = A._measure_degenerate_verdict
    A._measure_degenerate_verdict = lambda src, measures, requested, agg, diag: ({
        MEAS_DEAD: {"alive": False, "max_abs": 0.0, "layer": "nums"},
        MEAS_LIVE: {"alive": True, "max_abs": 100.0, "layer": "live"},
        MEAS_LIVE2: {"alive": False, "max_abs": 0.0, "layer": "nums"},
    }, None)
    totals_in = [(MEAS_LIVE, 0.0, 0.0, 0.0)]
    diag_ln = _diag(totals={MEAS_LIVE: [0.0, 0.0, 0.0]})
    grain_dec = {
        "grain": "row", "form": "number",
        "col": None, "named_gis": [], "clarify": None,
    }
    out_ln = A._onepath_compose_gate(
        "сколько выручки за август", _intent(), _plan(), SRC,
        "doc @@ ts_phrase('x')", ["doc_date >= '2026-08-01'"],
        MEAS_LIVE, _base_agg(sum=0.0, min=0.0, max=0.0, measure=MEAS_LIVE),
        [], totals_in, None, None, diag_ln, grain_dec, [],
        time.time(), trusted=None)
    tot_diag = (out_ln or {}).get("diag", {}).get("totals")
    t("live_none→C1 totals пуст",
      (out_ln or {}).get("kind") in ("answer", "figures")
      and not tot_diag
      and calls.get("live_n", 0) >= 1,
      {"kind": (out_ln or {}).get("kind"), "totals": tot_diag,
       "live_n": calls.get("live_n"), "text": (out_ln or {}).get("text")})
finally:
    try:
        A._measure_degenerate_verdict = _real_verdict_ln
    except NameError:
        pass
    _restore()

# D1-fix9: via=live_column + nums-alive → C1 честный 0 (не B2)
try:
    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": True, "max_abs": 100.0, "layer": "nums"},
            MEAS_LIVE: {"alive": False, "max_abs": 0.0, "layer": "nums"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0.0, "layer": "nums"},
        },
        live_vals={})
    # live SELECT первым (via); live мёртв; nums поднимает MEAS_DEAD —
    # F-VIT-нуль: table-wide nums жива ∧ окно 0 → честный 0 (C1), не «не ведётся»
    def fake_psql_via(sql):
        calls["n"] = calls.get("n", 0) + 1
        calls.setdefault("sqls", []).append(sql)
        s = sql.lower()
        if "filter" in s and "query_table" in s:
            return [[False, 0.0, False, 0.0, False, 0.0]]
        if "filter" in s and "search_corpus" in s:
            return [[True, 100.0, False, 0.0, False, 0.0]]
        if "from search_tables" in s and "label" in s:
            return [("регистр продаж",)]
        return []
    A.psql = fake_psql_via
    A.aggregate_live_column = lambda *a, **k: None
    out_via = _call_gate(
        agg=_base_agg(
            sum=0.0, min=0.0, max=0.0, count_amount=0, measure=MEAS_DEAD,
            scope={"src": "query_table", "via": "live_column"}))
    txt_via = (out_via or {}).get("text") or ""
    t("via=live nums-alive → C1 честный 0",
      (out_via or {}).get("kind") in ("answer", "figures")
      and "не ведётся" not in txt_via,
      {"kind": (out_via or {}).get("kind"), "text": txt_via[:120],
       "diag": (out_via or {}).get("diag")})
finally:
    _restore()

# D1-fix8: F-CMP one-sided None → нет ложного exact_value из count
try:
    def _fake_onesided(src, preds, measure):
        blob = " ".join(str(p) for p in (preds or []))
        # period1 (июль) пуст → None; period2 (август) жив sum=10 count=5
        if "2026-07-01" in blob:
            return None
        return {
            "count": 5, "sum": 10.0, "min": 10.0, "max": 10.0, "avg": 10.0,
            "count_amount": 5, "src": src, "measure": measure, "folders": 0,
            "scope": {"via": "live_column", "src": "query_table", "where": ""},
        }
    A.aggregate_live_column = _fake_onesided
    A.deadline_hit = lambda rid=None: False
    intent8 = {
        "period": {"from": "2026-07-01", "to": "2026-07-31"},
        "period2": {"from": "2026-08-01", "to": "2026-08-31"},
    }
    out8, lerr8 = A._force_live_aggregate(
        SRC, [], intent8, MEAS_LIVE, "compare",
        _base_agg(form="compare", sum=None, count=5, compare_base=None,
                  compare_other=None), {})
    ev8 = A._atom_exact_value(out8, "compare", money=True) if out8 else None
    t("F-CMP one-sided None → нет ложного exact_value из count",
      lerr8 is None and out8 is not None
      and float(out8.get("compare_base")) == 0.0
      and float(out8.get("compare_other")) == 10.0
      and float(out8.get("sum")) == -10.0
      and float(ev8) == -10.0
      and float(ev8) != 5.0,
      {"out": out8, "lerr": lerr8, "ev": ev8})
finally:
    _restore()

# D1-fix7: клик live-only corridor ∧ live_none → текст N=0, без «не ведётся»
try:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    q_c7 = "топ контрагентов по выручке фикстура?"
    opts_c7 = [{
        "src": SRC, "measure": MEAS_LIVE, "label": "всего",
        "measure_verdict": "alive", "answer_mode": "text_with_total",
        "digest_scope": {"via": "live"},
    }]
    sealed_c7 = A.seal_clarify(
        {"kind": "clarify", "text": "мера?", "options": opts_c7}, q_c7)
    tid_c7 = ((sealed_c7.get("options") or [{}])[0]).get("decision_id")
    tkt_c7, err_c7 = A.consume_decision(tid_c7, q_c7)
    t("клик live-only corridor ticket answer_mode",
      err_c7 is None and (tkt_c7 or {}).get("answer_mode") == "text_with_total",
      tkt_c7)
    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0, "layer": "nums"},
            MEAS_LIVE: {"alive": True, "max_abs": 100.0, "layer": "live"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0, "layer": "nums"},
        },
        live_vals={MEAS_LIVE: None})
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "picked": [SRC], "marks": {}, "plan": {}}
    A.period_readings = lambda *a, **k: []
    A.expand_readings_calendar_axis = lambda r, prefer=None: r
    A.expand_readings_currency_axis = (
        lambda r, prefer=None, intent=None, trusted=None: r)
    A.parse_intent = lambda q, today: _intent(want="sum", measure_word="всего")
    A.repair_period_from_question = lambda *a, **k: None
    A.calendar_axis_unavailable_block = lambda *a, **k: None
    A.sales_compare_intent = lambda *a, **k: False
    A.rank_intent_from = lambda *a, **k: True
    A._predicates = lambda intent: ["doc_date >= '2026-08-01'"]
    A.match_expr = lambda *a, **k: ("doc @@ ts_phrase('x')", 0)
    A.probe = lambda terms: ([], {})
    A.matched_group_count = lambda kinds: 0
    A.stock_net_register_menu_opts = lambda *a, **k: []
    A._coverage_of = lambda src: None
    A._num_pred = lambda intent, measure: []
    A.tables_of = lambda *a, **k: {SRC: 10}
    A.empty_after_period_action = lambda intent: "empty_period"
    A.totals_of = lambda *a, **k: [(MEAS_LIVE, 0.0, 0.0, 0.0)]
    A.rows_of = lambda *a, **k: []
    A.aggregate = lambda *a, **k: _base_agg(sum=0.0, min=0.0, max=0.0)
    A.aggregate_groups = lambda *a, **k: _base_agg(
        grain="group", form="rank", groups=[{"key": "a", "value": 0.0}],
        n_groups=1, sum=0.0)
    A._settle_axis = lambda *a, **k: (
        {"grain": "group", "col": "Контрагент", "form": "rank",
         "named_gis": [], "clarify": None}, [], [])
    A.refcols_of = lambda src: [{"col": "Контрагент", "label": "контрагент"}]
    A.deadline_hit = lambda rid=None: False
    A.gate = lambda text, seen, agg, extra=None, dates=None, money=True, slot_mode=None: (True, [])
    out_c7 = A.answer(
        q_c7, trusted=tkt_c7,
        resolved={"src": SRC, "measure": MEAS_LIVE})
    txt_c7 = (out_c7 or {}).get("text") or ""
    diag_c7 = (out_c7 or {}).get("diag") or {}
    atom_c7 = (out_c7 or {}).get("atom") or {}
    atoms_c7 = (out_c7 or {}).get("atoms") or []
    has_num_c7 = (atom_c7.get("exact_value") is not None
                  or any((a or {}).get("exact_value") is not None
                         for a in atoms_c7))
    t("клик live-only corridor ∧ live_none → итог=0 без «не ведётся»",
      (out_c7 or {}).get("kind") == "answer"
      and "итог за период = 0" in txt_c7
      and "не ведётся" not in txt_c7
      and not has_num_c7 and not atoms_c7
      and (diag_c7.get("measure_degenerate_outcome") == "text_with_total"
           or diag_c7.get("answer_mode") == "text_with_total"),
      {"kind": (out_c7 or {}).get("kind"), "text": txt_c7[:160],
       "atom": atom_c7, "diag": diag_c7, "live_n": calls.get("live_n")})
finally:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    _restore()

# D1-fix9: клик text_with_total без rank-маркеров → билнер (не atom 0)
try:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    # вопрос клика БЕЗ rank-маркеров; rank_intent_from НЕ мокаем True
    q_nr = "сколько выручки за август фикстура?"
    opts_nr = [{
        "src": SRC, "measure": MEAS_LIVE, "label": "всего",
        "measure_verdict": "alive", "answer_mode": "text_with_total",
        "digest_scope": {"via": "live"},
    }]
    sealed_nr = A.seal_clarify(
        {"kind": "clarify", "text": "мера?", "options": opts_nr}, q_nr)
    tid_nr = ((sealed_nr.get("options") or [{}])[0]).get("decision_id")
    tkt_nr, err_nr = A.consume_decision(tid_nr, q_nr)
    t("клик text_with_total no-rank ticket",
      err_nr is None and (tkt_nr or {}).get("answer_mode") == "text_with_total",
      tkt_nr)
    calls = _install_common(
        verdict={
            MEAS_DEAD: {"alive": False, "max_abs": 0, "layer": "nums"},
            MEAS_LIVE: {"alive": True, "max_abs": 4218825.39, "layer": "live"},
            MEAS_LIVE2: {"alive": False, "max_abs": 0, "layer": "nums"},
        },
        live_vals={MEAS_LIVE: 4218825.39})
    A.wiki_primary_entity_cascade = lambda *a, **k: {
        "picked": [SRC], "marks": {}, "plan": {}}
    A.period_readings = lambda *a, **k: []
    A.expand_readings_calendar_axis = lambda r, prefer=None: r
    A.expand_readings_currency_axis = (
        lambda r, prefer=None, intent=None, trusted=None: r)
    A.parse_intent = lambda q, today: _intent(want="sum", measure_word="всего")
    A.repair_period_from_question = lambda *a, **k: None
    A.calendar_axis_unavailable_block = lambda *a, **k: None
    A.sales_compare_intent = lambda *a, **k: False
    # НЕ мокаем rank_intent_from=True — вопрос без маркеров
    A._predicates = lambda intent: ["doc_date >= '2026-08-01'"]
    A.match_expr = lambda *a, **k: ("doc @@ ts_phrase('x')", 0)
    A.probe = lambda terms: ([], {})
    A.matched_group_count = lambda kinds: 0
    A.stock_net_register_menu_opts = lambda *a, **k: []
    A._coverage_of = lambda src: None
    A._num_pred = lambda intent, measure: []
    A.tables_of = lambda *a, **k: {SRC: 10}
    A.empty_after_period_action = lambda intent: "empty_period"
    A.totals_of = lambda *a, **k: [(MEAS_LIVE, 0.0, 0.0, 0.0)]
    A.rows_of = lambda *a, **k: []
    A.aggregate = lambda *a, **k: _base_agg(sum=0.0, min=0.0, max=0.0)
    A.aggregate_groups = lambda *a, **k: _base_agg(
        grain="row", form="number", sum=0.0)
    A._settle_axis = lambda *a, **k: (
        {"grain": "row", "col": None, "form": "number",
         "named_gis": [], "clarify": None}, [], [])
    A.refcols_of = lambda src: []
    A.deadline_hit = lambda rid=None: False
    A.gate = lambda text, seen, agg, extra=None, dates=None, money=True, slot_mode=None: (True, [])
    out_nr = A.answer(
        q_nr, trusted=tkt_nr,
        resolved={"src": SRC, "measure": MEAS_LIVE})
    atom_nr = (out_nr or {}).get("atom") or {}
    atoms_nr = (out_nr or {}).get("atoms") or []
    has_num_nr = (atom_nr.get("exact_value") is not None
                  or any((a or {}).get("exact_value") is not None
                         for a in atoms_nr))
    txt_nr = (out_nr or {}).get("text") or ""
    t("клик text_with_total без rank → билнер не atom",
      (out_nr or {}).get("kind") == "answer"
      and "4218825.39" in txt_nr.replace(" ", "").replace(" ", "")
      and not has_num_nr and not atoms_nr
      and ((out_nr or {}).get("diag", {}).get("measure_degenerate_outcome")
           == "text_with_total"
           or (out_nr or {}).get("diag", {}).get("answer_mode")
           == "text_with_total"),
      {"kind": (out_nr or {}).get("kind"), "text": txt_nr[:120],
       "atom": atom_nr, "diag": (out_nr or {}).get("diag")})
finally:
    with A._DECISION_LOCK:
        A._DECISIONS.clear()
        A._CLARIFY_BATCHES.clear()
    _restore()

# D1-fix6: corridor sole live-only ∧ live_none → текст N=0, без «не ведётся»
try:
    calls = _install_common(live_vals={MEAS_LIVE: None})
    _real_verdict_c6 = A._measure_degenerate_verdict
    A._measure_degenerate_verdict = lambda src, measures, requested, agg, diag: ({
        MEAS_DEAD: {"alive": False, "max_abs": 0.0, "layer": "nums"},
        MEAS_LIVE: {"alive": True, "max_abs": 100.0, "layer": "live"},
        MEAS_LIVE2: {"alive": False, "max_abs": 0.0, "layer": "nums"},
    }, None)
    A.rank_intent_from = lambda *a, **k: True
    out_c6 = _call_gate(
        agg=_base_agg(
            grain="group", form="rank", sum=0.0, min=0.0, max=0.0,
            groups=[{"key": "a", "value": 0.0}], n_groups=1, count_amount=0),
        measure=MEAS_DEAD)
    txt_c6 = (out_c6 or {}).get("text") or ""
    diag_c6 = (out_c6 or {}).get("diag") or {}
    t("corridor sole live-only ∧ live_none → итог=0 без «не ведётся»",
      (out_c6 or {}).get("kind") == "answer"
      and "итог за период = 0" in txt_c6
      and "не ведётся" not in txt_c6
      and diag_c6.get("measure_degenerate_outcome") == "text_with_total"
      and diag_c6.get("measure_sole_replace") == MEAS_DEAD,
      {"kind": (out_c6 or {}).get("kind"), "text": txt_c6[:160],
       "diag": diag_c6, "live_n": calls.get("live_n")})
finally:
    A._measure_degenerate_verdict = _real_verdict_c6
    _restore()

try:
    A.measures_of = lambda src: list(ALL_MEAS)
    A.measure_aliases_of = lambda src: {}
    diag = {}
    A._settle_measure(
        SRC, _intent(), _plan(), None,
        {"ambiguity": "measure", "measure": MEAS_LIVE}, None, diag)
    t("settle measure_proven_human при choice_levels",
      diag.get("measure_proven_human") is True, diag)
    diag2 = {}
    A._settle_measure(SRC, _intent(), _plan(), MEAS_LIVE, None, None, diag2)
    t("settle без proven на голый measure_pick",
      not diag2.get("measure_proven_human"), diag2)
finally:
    _restore()

print("\nИТОГ:", "ok — %d проверок" % PASS if not FAIL
      else "FAIL — %d из %d: %s" % (
          len(FAIL), PASS + len(FAIL), ", ".join(FAIL[:25])))
sys.exit(1 if FAIL else 0)
