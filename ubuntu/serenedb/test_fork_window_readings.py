#!/usr/bin/env python3
"""Окна W в детекторе развилок (фаза A, план §3).

Замки:
  · period_readings: MTD + full_month при today=2026-08-23;
  · period_readings: 1 reading при today=2026-08-31 (границы совпали);
  · прошлый месяц (assumed+from/to): одно окно, без drop_assumed;
  · этот месяц: MTD+full_month; без периода: none+drop_assumed;
  · вчера / день на 1-е: одно explicit, без лишних классов;
  · понедельник assumed 17–23 при today=24.08 → wtd+full_week + люк 17–23;
  · понедельник assumed скользящее 18–24 → wtd+full_week + люк 18–24, лидер wtd;
  · пятница 17–23 при today=21.08: wtd+full_week без сдвига;
  · _fork_atom_equiv_fp: разные period → разные классы; одинаковые → один;
  · render_window_label: без кириллических литералов-маркеров;
  · без относительного периода — одно reading (§10.14).

Запуск: python3 ubuntu/serenedb/test_fork_window_readings.py
"""
import os
import re
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


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


def _ids(readings):
    return {x["interpretation_id"] for x in readings}


intent_month = {
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r23 = A.period_readings(intent_month, today="2026-08-23")
t("period_readings 2026-08-23: 2 reading",
  len(r23) == 2 and _ids(r23) == {"mtd", "full_month"})
r31 = A.period_readings(intent_month, today="2026-08-31")
t("period_readings 2026-08-31: 1 reading (границы совпали)",
  len(r31) == 1 and r31[0]["interpretation_id"] == "full_month")

intent_dec = {"period": {"from": "2025-12-01", "to": "2025-12-31"}}
r_dec = A.period_readings(intent_dec, today="2026-08-23")
t("явный декабрь: одно explicit reading",
  len(r_dec) == 1 and r_dec[0]["interpretation_id"] == "explicit")

intent_no_rel = {"period": {"from": "2025-12-01", "to": "2025-12-31"}}
t("§10.14: фиксированный период → 1 reading",
  len(A.period_readings(intent_no_rel, today="2026-08-23")) == 1)

# ── drop_assumed: только без from/to (§3) ─────────────────────────────────────
intent_last_month = {
    "period": {"from": "2026-07-01", "to": "2026-07-31"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_last = A.period_readings(intent_last_month, today="2026-08-23")
t("прошлый месяц: 1 окно без drop_assumed",
  len(r_last) == 1 and _ids(r_last) == {"explicit"},
  _ids(r_last))
t("этот месяц: MTD+full_month (два)",
  len(r23) == 2 and _ids(r23) == {"mtd", "full_month"})

intent_no_period = {
    "period": {},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_none = A.period_readings(intent_no_period, today="2026-08-23")
t("без периода: none + drop_assumed",
  len(r_none) == 2 and _ids(r_none) == {"none", "drop_assumed"},
  _ids(r_none))

# один класс за июль (живая diag: 2 767 450,98) → unique/A, не C с all-time
p_july = {"from": "2026-07-01", "to": "2026-07-31", "origin": "assumed",
          "interpretation_id": "explicit"}
wfp_july = A.window_fp_of(p_july, "assumed")
rows_july = {("x", wfp_july): row(10, Сумма=2767450.98)}
pby_july = {("x", wfp_july): p_july}
cls_july = A.fork_classes_windowed(
    rows_july, pby_july, "сумма", want="sum", rel_by_src={"x": ["Сумма"]})
july_sums = [k[2] for k in cls_july]
t("прошлый месяц: 1 класс (июль), не drop all-time",
  len(cls_july) == 1 and july_sums == [2767450.98], july_sums)
out_july, _pay = A.resolve_fork_outcome(
    cls_july, {"x": row(10, Сумма=2767450.98)},
    measure_ctx="сумма", want="sum", rel_by_src={"x": ["Сумма"]})
t("прошлый месяц: исход unique/A (один класс)",
  out_july in ("unique", "A"), out_july)

# ── явные даты: без лишних классов ───────────────────────────────────────────
intent_yesterday = {
    "period": {"from": "2026-08-22", "to": "2026-08-22"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_yday = A.period_readings(intent_yesterday, today="2026-08-23")
t("вчера: 1 explicit без drop_assumed",
  len(r_yday) == 1 and _ids(r_yday) == {"explicit"}, _ids(r_yday))

intent_yday_1st = {
    "period": {"from": "2026-08-01", "to": "2026-08-01"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_y1 = A.period_readings(intent_yday_1st, today="2026-08-02")
t("вчера на 1-е: 1 explicit, не MTD+full_month",
  len(r_y1) == 1 and _ids(r_y1) == {"explicit"}, _ids(r_y1))

intent_last_week = {
    "period": {"from": "2026-08-10", "to": "2026-08-16"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_lw = A.period_readings(intent_last_week, today="2026-08-23")
t("прошлая неделя: 1 explicit без drop_assumed",
  len(r_lw) == 1 and _ids(r_lw) == {"explicit"}, _ids(r_lw))

intent_this_week = {
    "period": {"from": "2026-08-17", "to": "2026-08-23"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_tw = A.period_readings(intent_this_week, today="2026-08-20")
t("эта неделя mid: WTD+full_week",
  len(r_tw) == 2 and _ids(r_tw) == {"wtd", "full_week"}, _ids(r_tw))

r_mon = A.period_readings(intent_this_week, today="2026-08-24")
t("понедельник assumed 17–23 → wtd+full_week+люк",
  len(r_mon) == 3 and _ids(r_mon) == {"wtd", "full_week", "explicit"}, _ids(r_mon))
_wtd_m = next(x for x in r_mon if x["interpretation_id"] == "wtd")
_full_m = next(x for x in r_mon if x["interpretation_id"] == "full_week")
_hatch_m = next(x for x in r_mon if x["interpretation_id"] == "explicit")
t("понедельник wtd = 24.08",
  _wtd_m["period"].get("from") == "2026-08-24"
  and _wtd_m["period"].get("to") == "2026-08-24",
  _wtd_m["period"])
t("понедельник full_week = 24–30.08",
  _full_m["period"].get("from") == "2026-08-24"
  and _full_m["period"].get("to") == "2026-08-30",
  _full_m["period"])
t("понедельник люк = 17–23",
  _hatch_m["period"].get("from") == "2026-08-17"
  and _hatch_m["period"].get("to") == "2026-08-23",
  _hatch_m["period"])
t("понедельник origin=assumed",
  _wtd_m.get("origin") == "assumed" and _full_m.get("origin") == "assumed"
  and _hatch_m.get("origin") == "assumed")
t("понедельник лидер = wtd",
  (A.prefer_window_leader(r_mon) or {}).get("interpretation_id") == "wtd")

intent_slide = {
    "period": {"from": "2026-08-18", "to": "2026-08-24"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
r_slide = A.period_readings(intent_slide, today="2026-08-24")
t("пн скользящее 18–24 → wtd+full_week+люк",
  len(r_slide) == 3 and _ids(r_slide) == {"wtd", "full_week", "explicit"},
  _ids(r_slide))
_wtd_s = next(x for x in r_slide if x["interpretation_id"] == "wtd")
_full_s = next(x for x in r_slide if x["interpretation_id"] == "full_week")
_hatch_s = next(x for x in r_slide if x["interpretation_id"] == "explicit")
t("скользящее wtd = 24.08..24.08",
  _wtd_s["period"].get("from") == "2026-08-24"
  and _wtd_s["period"].get("to") == "2026-08-24",
  _wtd_s["period"])
t("скользящее full_week = 24–30.08",
  _full_s["period"].get("from") == "2026-08-24"
  and _full_s["period"].get("to") == "2026-08-30",
  _full_s["period"])
t("скользящее люк = 18–24",
  _hatch_s["period"].get("from") == "2026-08-18"
  and _hatch_s["period"].get("to") == "2026-08-24",
  _hatch_s["period"])
t("скользящее лидер = календарное wtd",
  (A.prefer_window_leader(r_slide) or {}).get("interpretation_id") == "wtd"
  and (A.prefer_window_leader(r_slide) or {}).get("period", {}).get("from")
  == "2026-08-24")

r_fri = A.period_readings(intent_this_week, today="2026-08-21")
t("пятница окно 17–23: WTD+full_week",
  len(r_fri) == 2 and _ids(r_fri) == {"wtd", "full_week"}, _ids(r_fri))
_wtd_f = next(x for x in r_fri if x["interpretation_id"] == "wtd")
_full_f = next(x for x in r_fri if x["interpretation_id"] == "full_week")
t("пятница wtd = 17–21.08",
  _wtd_f["period"].get("from") == "2026-08-17"
  and _wtd_f["period"].get("to") == "2026-08-21",
  _wtd_f["period"])
t("пятница full_week = 17–23.08",
  _full_f["period"].get("from") == "2026-08-17"
  and _full_f["period"].get("to") == "2026-08-23",
  _full_f["period"])

intent_mon_explicit = {"period": {"from": "2026-08-17", "to": "2026-08-23"}}
r_mon_ex = A.period_readings(intent_mon_explicit, today="2026-08-24")
t("понедельник явные 17–23: explicit, не сдвиг на текущую",
  len(r_mon_ex) == 1 and _ids(r_mon_ex) == {"explicit"}, _ids(r_mon_ex))

p_mtd = {"from": "2026-08-01", "to": "2026-08-23", "origin": "assumed",
         "interpretation_id": "mtd"}
p_full = {"from": "2026-08-01", "to": "2026-08-31", "origin": "assumed",
          "interpretation_id": "full_month"}
a1 = A._fork_atom_of(row(10, Сумма=100.0), ["x"], "сумма", want="sum",
                     rel_measures=["Сумма"], period=p_mtd)
a2 = A._fork_atom_of(row(10, Сумма=200.0), ["x"], "сумма", want="sum",
                     rel_measures=["Сумма"], period=p_full)
fp1, fp2 = A._fork_atom_equiv_fp(a1), A._fork_atom_equiv_fp(a2)
t("разные period → разные fp", fp1 != fp2)
a1b = A._fork_atom_of(row(10, Сумма=100.0), ["x"], "сумма", want="sum",
                      rel_measures=["Сумма"], period=p_mtd)
t("одинаковые period → один fp",
  A._fork_atom_equiv_fp(a1) == A._fork_atom_equiv_fp(a1b))

rows_w = {
    ("x", A.window_fp_of(p_mtd, "assumed")): row(10, Сумма=100.0),
    ("x", A.window_fp_of(p_full, "assumed")): row(10, Сумма=200.0),
}
pby = {
    ("x", A.window_fp_of(p_mtd, "assumed")): p_mtd,
    ("x", A.window_fp_of(p_full, "assumed")): p_full,
}
cls_w = A.fork_classes_windowed(rows_w, pby, "сумма", want="sum",
                                rel_by_src={"x": ["Сумма"]})
t("fork_classes_windowed: 2 класса при 2 окнах", len(cls_w) == 2)

lab = A.render_window_label(p_mtd, origin="assumed", today="2026-08-23")
t("render_window_label: даты DD.MM.YYYY",
  lab and "01.08.2026" in lab and "23.08.2026" in lab)
t("render_window_label: без кириллицы",
  lab and not re.search(r"[А-Яа-яЁё]", lab))
t("render_window_label: mtd id", lab and "mtd" in lab)

real_scan = A.fork_scan

def _mock_scan(match, preds, rel):
    return {"reg": row(5, Сумма=1.0)}

A.fork_scan = _mock_scan
readings = A.period_readings(intent_month, today="2026-08-23")
cells, merged, _pby = A.fork_scan_readings("", readings, {"reg": ["Сумма"]})
A.fork_scan = real_scan
statuses = {c["status"] for c in cells}
t("multi-scan: есть computed", "computed" in statuses)
t("multi-scan: 2 окна × 1 src", len(merged) == 2)

# ── фаза B: лидер MTD в intent + fork_leader по оси W ─────────────────────────
intent_b = {
    "period": {"from": "2026-08-01", "to": "2026-08-31"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
rb = A.apply_period_leader(intent_b, today="2026-08-23")
t("фаза B: apply_period_leader → 2 readings", len(rb) == 2)
t("фаза B: intent.period = MTD",
  intent_b.get("period", {}).get("to") == "2026-08-23"
  and intent_b.get("period", {}).get("interpretation_id") == "mtd")
t("фаза B: prefer_window_leader = mtd",
  (A.prefer_window_leader(rb) or {}).get("interpretation_id") == "mtd")

p_mtd_b = {"from": "2026-08-01", "to": "2026-08-23", "origin": "assumed",
           "interpretation_id": "mtd"}
p_full_b = {"from": "2026-08-01", "to": "2026-08-31", "origin": "assumed",
            "interpretation_id": "full_month"}
cls_w_lead = [
    {"srcs": ["reg"], "period": p_full_b,
     "atom": {"period": p_full_b, "exact_value": 200.0}},
    {"srcs": ["reg"], "period": p_mtd_b,
     "atom": {"period": p_mtd_b, "exact_value": 100.0}},
]
split_w = A.fork_leader_class("reg", cls_w_lead)
t("фаза B: fork_leader W → mtd",
  split_w and A._class_window_form(split_w[0]) == "mtd" and len(split_w[1]) == 1)


print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
