#!/usr/bin/env python3
"""Compare-продажи: diff двух окон (SCORER #6/#7, фаза A).

Класс: «эта/этот vs прошлая/прошлый» — cur = WTD/MTD (по today),
prior = ПОЛНЫЙ предыдущий календарный период (неделя пн–вс / месяц целиком),
не обрезок по дню today. Иначе mid-week / mid-month diff ≠ gold.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


def _ef(on):
    old = A.ASK_ENTITY_FORM
    A.ASK_ENTITY_FORM = bool(on)
    return old


def _ef_restore(old):
    A.ASK_ENTITY_FORM = old


TODAY = "2026-08-23"
intent_week = {
    "period": {"from": "2026-08-17", "to": "2026-08-23"},
    "want": "sum",
}
t("#6 sales_compare_intent",
  A.sales_compare_intent(intent_week, "эта неделя лучше прошлой или хуже?"))
p1, p2, fid = A.sales_compare_windows(intent_week, TODAY,
                                      "эта неделя лучше прошлой или хуже?")
t("#6 windows: wtd form", fid == "wtd")
t("#6 cur week Mon→today",
  p1.get("from") == "2026-08-17" and p1.get("to") == TODAY)
t("#6 prior full prev week",
  p2.get("from") == "2026-08-10" and p2.get("to") == "2026-08-16", p2)

intent_month = {
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "want": "sum",
}
t("#7 sales_compare_intent",
  A.sales_compare_intent(intent_month,
                         "в этом месяце продали больше, чем в прошлом?"))
m1, m2, mfid = A.sales_compare_windows(intent_month, TODAY,
                                       "в этом месяце продали больше, чем в прошлом?")
t("#7 windows: mtd form", mfid == "mtd")
t("#7 cur MTD", m1.get("from") == "2026-08-01" and m1.get("to") == TODAY)
# prior = полный прошлый месяц, не Jul 1..today.day (K5b / класс compare)
t("#7 prior full prev month",
  m2.get("from") == "2026-07-01" and m2.get("to") == "2026-07-31", m2)

GOLD6 = 817289.51
GOLD7 = 579169.67

def _mock_agg(src, match, preds, measure=None):
    fr = next((p.split("'")[1] for p in (preds or []) if "doc_date >=" in p), "")
    if fr == "2026-08-17":
        return {"count": 100, "sum": 1000000.0, "src": src, "measure": measure}
    if fr == "2026-08-10":
        return {"count": 80, "sum": 1000000.0 - GOLD6, "src": src, "measure": measure}
    if fr == "2026-08-01":
        return {"count": 200, "sum": 3346620.65, "src": src, "measure": measure}
    if fr == "2026-07-01":
        return {"count": 180, "sum": 3346620.65 - GOLD7, "src": src, "measure": measure}
    return {"count": 0, "sum": 0.0, "src": src, "measure": measure}

real_agg = A.aggregate
A.aggregate = _mock_agg
agg6 = A.aggregate_compare_sales("reg", "", p1, p2, "Всего")
t("#6 diff эталон", agg6 and abs(float(agg6["sum"]) - GOLD6) < 0.02,
  agg6.get("sum") if agg6 else None)
agg7 = A.aggregate_compare_sales("reg", "", m1, m2, "Всего")
t("#7 diff эталон", agg7 and abs(float(agg7["sum"]) - GOLD7) < 0.02,
  agg7.get("sum") if agg7 else None)
t("compare agg form", agg7 and agg7.get("form") == "compare")
A.aggregate = real_agg

# ── класс: mid-week / mid-month — prior полный, не day-aligned ───────────────
# [замер 26.08] «эта неделя лучше прошлой» mid-week: fr=пн этой → prior обрезался
# до пн–ср прошлой → digits ≠ gold (gold = WTD − полная прошлая неделя).
MID = "2026-08-26"  # среда
_q_w = "эта неделя лучше прошлой или хуже?"
_q_m = "в этом месяце продали больше, чем в прошлом?"
_sv = _ef(True)
try:
    intent_cur_wtd = {
        "period": {"from": "2026-08-24", "to": MID},
        "want": "list", "kind": "продажи",
    }
    cw1, cw2, cwf = A.sales_compare_windows(intent_cur_wtd, MID, _q_w)
    t("mid-week: form wtd", cwf == "wtd", cwf)
    t("mid-week: cur WTD Mon→today",
      cw1.get("from") == "2026-08-24" and cw1.get("to") == MID, cw1)
    t("mid-week: prior FULL prev week (не пн–ср)",
      cw2.get("from") == "2026-08-17" and cw2.get("to") == "2026-08-23", cw2)

    intent_prev_week = {
        "period": {"from": "2026-08-17", "to": "2026-08-23"},
        "want": "list", "kind": "продажи",
    }
    pw1, pw2, pwf = A.sales_compare_windows(intent_prev_week, MID, _q_w)
    t("mid-week: prev_week remap → та же пара окон",
      (pw1, pw2, pwf) == (cw1, cw2, cwf), (pw1, pw2, pwf))

    intent_cur_mtd = {
        "period": {"from": "2026-08-01", "to": MID},
        "want": "list", "kind": "продажи",
    }
    cm1, cm2, cmf = A.sales_compare_windows(intent_cur_mtd, MID, _q_m)
    t("mid-month: form mtd", cmf == "mtd", cmf)
    t("mid-month: cur MTD",
      cm1.get("from") == "2026-08-01" and cm1.get("to") == MID, cm1)
    t("mid-month: prior FULL prev month (не Jul 1..26)",
      cm2.get("from") == "2026-07-01" and cm2.get("to") == "2026-07-31", cm2)

    # Атом compare: exact_value = diff, figures несут sum=diff (форма наружу).
    _diff = -792128.74
    _cagg = {
        "count": 10, "sum": _diff, "form": "compare", "grain": "row",
        "compare_base": 470821.66, "compare_other": 1262950.40, "period2": True,
    }
    _atom = A.atom_from_agg(
        _cagg, operation="compare", measure_id="Всего",
        measure_label="Реализация ТМЦ", money=True,
        period=cw1, form="compare")
    t("atom compare: exact=diff",
      _atom and abs(float(_atom.get("exact_value")) - _diff) < 0.02,
      (_atom or {}).get("exact_value"))
    _figs = A._fork_figures_of(_atom)
    t("atom compare: figures.sum=diff",
      _figs.get("sum") is not None
      and abs(float(_figs["sum"]) - _diff) < 0.02, _figs)
    _pair = A.render_atom_pair(_atom) or ""
    t("atom compare: pair несёт diff, не · rank",
      "792" in _pair.replace(" ", "").replace("\xa0", "")
      and "rank" not in _pair.lower(), _pair)
finally:
    _ef_restore(_sv)


# ── K2 P1–P5 offline locks (27.08) ───────────────────────────────────────────
TODAY_K2 = "2026-08-27"
_q_f3 = "в этом месяце продали больше, чем в прошлом?"
_intent_f3 = {
    "period": {"from": "2026-08-01", "to": "2026-08-27"},
    "want": "sum", "kind": "продажи",
}
# P2 entry cases
t("P2: сравни продажи июля и августа",
  A.sales_compare_intent(
      {"want": "sum", "kind": "продажи",
       "period": {"from": "2026-07-01", "to": "2026-08-31"}},
      "сравни продажи июля и августа"))
t("P2: против",
  A.sales_compare_intent(
      {"want": "sum", "kind": "продажи"},
      "продажи за август против июля"))
t("P2: насколько больше",
  A.sales_compare_intent(
      {"want": "sum", "kind": "продажи",
       "period": {"from": "2026-08-01", "to": "2026-08-27"}},
      "насколько продажи этого месяца больше прошлого"))
t("P2: год назад marker",
  A._yoy_compare_marker("а год назад?"))
t("P2: year-ago with prior period -> intent",
  A.sales_compare_intent(
      {"want": "sum", "period": {"from": "2026-08-01", "to": "2026-08-27"}},
      "а год назад?"))

# P4: two months -> two full calendar windows
sp = A.sales_compare_split_month_pair(
    "продажи за август против июля", TODAY_K2)
t("P4: split returns pair", sp is not None and len(sp) == 2, sp)
if sp:
    t("P4: first = full August",
      sp[0].get("from") == "2026-08-01" and sp[0].get("to") == "2026-08-31", sp[0])
    t("P4: second = full July",
      sp[1].get("from") == "2026-07-01" and sp[1].get("to") == "2026-07-31", sp[1])
w1, w2, wf = A.sales_compare_windows(
    {"want": "sum", "period": {"from": "2026-07-01", "to": "2026-08-31"}},
    TODAY_K2, "сравни продажи августа с июлем")
t("P4: windows from compare_windows",
  w1.get("from") == "2026-08-01" and w2.get("from") == "2026-07-01", (w1, w2, wf))

# P3: yoy shift
yp1, yp2, yf = A.sales_compare_windows(
    {"period": {"from": "2026-08-01", "to": "2026-08-27"}, "want": "sum"},
    TODAY_K2, "а год назад?")
t("P3: form yoy", yf == "yoy", yf)
t("P3: prior = cur - 1 year",
  yp2.get("from") == "2025-08-01" and yp2.get("to") == "2025-08-27", yp2)

# P1+P5: atom compare form, text has diff + pair, not rank
GOLD_F3 = 1049991.33
_cagg_f3 = {
    "count": 10, "sum": GOLD_F3, "form": "compare", "grain": "row",
    "compare_base": 3817442.31, "compare_other": 2767450.98, "period2": True,
}
_p1_f3 = {"from": "2026-08-01", "to": "2026-08-27"}
_p2_f3 = {"from": "2026-07-01", "to": "2026-07-31"}
_atom_f3 = A.atom_from_agg(
    _cagg_f3, operation="compare", measure_id="Всего",
    measure_label="Всего", money=True,
    period=_p1_f3, period2=_p2_f3, form="compare", compare_form="mtd")
t("P1: form=compare", _atom_f3 and _atom_f3.get("form") == "compare",
  (_atom_f3 or {}).get("form"))
t("P1: exact=diff",
  _atom_f3 and abs(float(_atom_f3.get("exact_value")) - GOLD_F3) < 0.02,
  (_atom_f3 or {}).get("exact_value"))
_figs_f3 = A._fork_figures_of(_atom_f3)
t("P1: figures carry compare_base/other/diff",
  abs(float(_figs_f3.get("diff", 0)) - GOLD_F3) < 0.02
  and _figs_f3.get("compare_base") is not None
  and _figs_f3.get("compare_other") is not None, _figs_f3)
_pair_f3 = A.render_atom_pair(_atom_f3) or ""
t("P1: text has diff, no form=rank",
  "1049991.33" in _pair_f3.replace("\xa0", "").replace(" ", "")
  or "1\u00a0499\u00a0991.33" in _pair_f3
  or "1049991" in _pair_f3.replace("\xa0", "").replace(" ", ""),
  _pair_f3)
t("P1: no rank in pair", "rank" not in _pair_f3.lower(), _pair_f3)
t("P5: pair windows in text",
  "против" in _pair_f3
  and "2026-08-01" in _pair_f3
  and "2026-07-01" in _pair_f3, _pair_f3)
t("P5: mtd incomplete note",
  "неполный" in _pair_f3 and "полный" in _pair_f3, _pair_f3)

# P1 lock: _cmp_form_locked independent of ASK_ENTITY_FORM (simulate flag off)
_sv2 = _ef(False)
try:
    # Intent + windows for F3 still compare
    t("P1: intent with flag off",
      A.sales_compare_intent(_intent_f3, _q_f3))
    m1, m2, mf = A.sales_compare_windows(_intent_f3, TODAY_K2, _q_f3)
    t("P1: windows mtd with flag off", mf == "mtd", mf)
finally:
    _ef_restore(_sv2)


# ── K2 live-fail locks (Q1/Q3/Q6 windows + rank)
_sv3 = _ef(False)
try:
    _i_prev = {"want": "sum", "kind": "продажи",
               "period": {"from": "2026-07-01", "to": "2026-07-31"}}
    t("Q1: intent сравни с прошлым месяцем",
      A.sales_compare_intent(_i_prev, "сравни продажи с прошлым месяцем"))
    _w1, _w2, _wf = A.sales_compare_windows(
        _i_prev, TODAY_K2, "сравни продажи с прошлым месяцем")
    t("Q1: windows mtd vs full July",
      _wf == "mtd" and _w1.get("from") == "2026-08-01"
      and _w2.get("from") == "2026-07-01", (_w1, _w2, _wf))
    t("Q3: intent на сколько больше чем в июле",
      A.sales_compare_intent(_i_prev, "на сколько больше, чем в июле"))
    _w1b, _w2b, _wfb = A.sales_compare_windows(
        _i_prev, TODAY_K2, "на сколько больше, чем в июле")
    t("Q3: windows mtd vs July",
      _wfb == "mtd" and _w2b.get("from") == "2026-07-01", (_w1b, _w2b, _wfb))
    _i_w = {"want": "sum", "kind": "продажи",
            "period": {"from": "2026-08-24", "to": "2026-08-27"}}
    t("Q6: intent лучше прошлой (over rank)",
      A.sales_compare_intent(_i_w, "эта неделя лучше прошлой или хуже?"))
    _w1c, _w2c, _wfc = A.sales_compare_windows(
        _i_w, TODAY_K2, "эта неделя лучше прошлой или хуже?")
    t("Q6: windows wtd",
      _wfc == "wtd" and _w1c.get("from") == "2026-08-24", (_w1c, _w2c, _wfc))
finally:
    _ef_restore(_sv3)


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
