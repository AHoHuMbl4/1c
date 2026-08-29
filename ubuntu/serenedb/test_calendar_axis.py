#!/usr/bin/env python3
"""Оффлайн-замок §7bis шаг 2: ось calendar_days vs working_days в serene_ask.

Замки (work/calendar-axis-design.md §5.1):
  · ASK_CALENDAR_AXIS умолч. 0
  · флаг off → calendar_axis_readings пуст / expand no-op
  · флаг on + пустая карта → ось не открыта
  · флаг on + meta → ровно 2 day-basis reading при окне
  · числа равны → resolve_fork_outcome ∈ {A, unique}
  · числа разные + подписи → B, лидер calendar_days
  · числа разные без подписей → C, options пуст
  · ticket working → лидер working_days
  · ticket_variant только при trusted click
  · нет триггер-литералов в calendar-хелперах

Запуск: python3 ubuntu/serenedb/test_calendar_axis.py
Без LLM/сети (мок psql / фикстуры search_meta).
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
os.environ.pop("ASK_CALENDAR_AXIS", None)

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


def with_flag(on):
    saved = os.environ.get("ASK_CALENDAR_AXIS")
    if on:
        os.environ["ASK_CALENDAR_AXIS"] = "1"
    else:
        os.environ.pop("ASK_CALENDAR_AXIS", None)
    A.ASK_CALENDAR_AXIS = os.environ.get("ASK_CALENDAR_AXIS", "0") == "1"
    return saved


def restore_flag(saved):
    if saved is None:
        os.environ.pop("ASK_CALENDAR_AXIS", None)
    else:
        os.environ["ASK_CALENDAR_AXIS"] = saved
    A.ASK_CALENDAR_AXIS = os.environ.get("ASK_CALENDAR_AXIS", "0") == "1"


def clear_cal_cache():
    A._CALENDAR_REGS.update({"at": 0.0, "set": None})
    A._CALENDAR_WORK_KEYS.update({"at": 0.0, "set": None})
    A._CALENDAR_MAP.update({"at": 0.0, "rows": None})


def mock_meta(regs="informationregister_cal", keys="wk1,wk2",
              rows=None):
    """Подмена чтения search_meta / search_calendar_map."""
    if rows is None:
        rows = [("informationregister_cal", "Дата", "День_Key", "Часы")]
    clear_cal_cache()
    A.calendar_registers = lambda: frozenset(
        x.strip() for x in str(regs).split(",") if x.strip()) if regs else frozenset()
    A.calendar_working_day_keys = lambda: frozenset(
        x.strip() for x in str(keys).split(",") if x.strip()) if keys else frozenset()
    A.calendar_map_rows = lambda: list(rows or [])


def restore_meta(real):
    (A.calendar_registers, A.calendar_working_day_keys,
     A.calendar_map_rows) = real
    clear_cal_cache()


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


_real_meta = (A.calendar_registers, A.calendar_working_day_keys, A.calendar_map_rows)

# ── умолчание флага ──────────────────────────────────────────────────────────
t("ASK_CALENDAR_AXIS default off", A.ASK_CALENDAR_AXIS is False)

# ── флаг off → no-op ─────────────────────────────────────────────────────────
saved = with_flag(False)
mock_meta()
base = A._window_reading(
    {"from": "2026-08-01", "to": "2026-08-15"}, "explicit", "explicit")
t("off: calendar_axis_readings пуст", A.calendar_axis_readings(base) == [])
readings = [base]
t("off: expand no-op",
  A.expand_readings_calendar_axis(readings) is not None
  and len(A.expand_readings_calendar_axis(readings)) == 1
  and A.expand_readings_calendar_axis(readings)[0].get("day_basis") in (None, ""))
# window_fp без day_basis = прежний формат
t("off: window_fp без day_basis",
  A.window_fp_of({"from": "2026-08-01", "to": "2026-08-15"}, "explicit")
  == "2026-08-01|2026-08-15|explicit")
restore_flag(saved)
restore_meta(_real_meta)

# ── on + пустая карта → ось не открыта ───────────────────────────────────────
saved = with_flag(True)
mock_meta(regs="", keys="", rows=[])
t("on+empty: axis closed", A.calendar_axis_open() is False)
t("on+empty: readings пуст", A.calendar_axis_readings(base) == [])
mock_meta(regs="informationregister_cal", keys="", rows=[
    ("informationregister_cal", "Дата", "День_Key", "Часы")])
t("on+no keys: axis closed", A.calendar_axis_open() is False)
mock_meta(regs="informationregister_cal", keys="wk1", rows=[])
t("on+no map: axis closed", A.calendar_axis_open() is False)
restore_flag(saved)
restore_meta(_real_meta)

# ── on + meta → ровно 2 reading ──────────────────────────────────────────────
saved = with_flag(True)
mock_meta()
cals = A.calendar_axis_readings(base)
t("on+meta: ровно 2 reading", len(cals) == 2, len(cals))
bases = {r.get("day_basis") for r in cals}
t("on+meta: calendar_days + working_days",
  bases == {"calendar_days", "working_days"}, bases)
t("on+meta: разные window_fp",
  cals[0]["window_fp"] != cals[1]["window_fp"])
t("on+meta: лидер порядка calendar_days",
  cals[0].get("day_basis") == "calendar_days")
expanded = A.expand_readings_calendar_axis([base])
t("on+meta: expand → 2", len(expanded) == 2)
# без окна — не раскрываем
none_rd = A._window_reading({}, "none", "none")
t("on+meta: без from/to → 0", A.calendar_axis_readings(none_rd) == [])
restore_flag(saved)
restore_meta(_real_meta)

# ── равные числа → A/unique ──────────────────────────────────────────────────
saved = with_flag(True)
mock_meta()
p_cal = {"from": "2026-08-01", "to": "2026-08-15", "origin": "explicit",
         "interpretation_id": "explicit", "day_basis": "calendar_days"}
p_work = dict(p_cal, day_basis="working_days")
wfp_c = A.window_fp_of(p_cal, "explicit")
wfp_w = A.window_fp_of(p_work, "explicit")
t("fp: calendar ≠ working", wfp_c != wfp_w)

rows_eq = {
    ("x", wfp_c): row(10, Сумма=100.0),
    ("x", wfp_w): row(10, Сумма=100.0),
}
pby_eq = {("x", wfp_c): p_cal, ("x", wfp_w): p_work}
cls_eq = A.fork_classes_windowed(
    rows_eq, pby_eq, "сумма", want="sum", rel_by_src={"x": ["Сумма"]})
t("равные числа: 1 класс", len(cls_eq) == 1, len(cls_eq))
out_eq, _ = A.resolve_fork_outcome(
    cls_eq, {"x": row(10, Сумма=100.0)}, measure_ctx="сумма",
    want="sum", rel_by_src={"x": ["Сумма"]})
t("равные числа → A/unique", out_eq in ("A", "unique"), out_eq)

# ── разные + подписи → B, лидер calendar ─────────────────────────────────────
rows_diff = {
    ("x", wfp_c): row(10, Сумма=100.0),
    ("x", wfp_w): row(8, Сумма=80.0),
}
pby_diff = {("x", wfp_c): p_cal, ("x", wfp_w): p_work}
cls_diff = A.fork_classes_windowed(
    rows_diff, pby_diff, "сумма", want="sum", rel_by_src={"x": ["Сумма"]})
t("разные числа: 2 класса", len(cls_diff) == 2, len(cls_diff))


def _labs_day(fk, srcs):
    out = {}
    for s in srcs or []:
        if s == "calendar_days":
            out[s] = "by-calendar"
        elif s == "working_days":
            out[s] = "by-working"
    return out


_real_labs = A.fork_labels_of
A.fork_labels_of = _labs_day
# covering fallback
_real_cov = A.fork_labels_covering


def _cov_day(srcs):
    m = _labs_day("", srcs)
    return m, "fk-day" if m else None


A.fork_labels_covering = _cov_day
out_b, pay_b = A.resolve_fork_outcome(
    cls_diff, {"x": row(10, Сумма=100.0)}, measure_ctx="сумма",
    want="sum", rel_by_src={"x": ["Сумма"]})
t("разные+подписи → B", out_b == "B", out_b)
bres = A.fork_outcome_b("q", pay_b, {}, picked_src="x")
t("B: лидер calendar (default)",
  bres and bres.get("atoms")
  and (bres["atoms"][0].get("measure_label") == "by-calendar"
       or A._class_day_basis(
           {"period": (bres["atoms"][0].get("period") or {}),
            "atom": bres["atoms"][0]}) in ("", "calendar_days")),
  (bres or {}).get("atoms", [{}])[0] if bres else None)
# строже: fork_leader_class
split = A.fork_leader_class("x", pay_b.get("classes") or [])
t("B: fork_leader day_basis=calendar_days",
  split and A._class_day_basis(split[0]) == "calendar_days",
  A._class_day_basis(split[0]) if split else None)
t("B: atoms[0] label by-calendar",
  bres and bres["atoms"][0].get("measure_label") == "by-calendar",
  (bres["atoms"][0] if bres else None))
t("B: options люк working",
  bres and len(bres.get("options") or []) == 1
  and bres["options"][0].get("day_basis") == "working_days",
  (bres or {}).get("options"))

# ── разные без подписей → C ──────────────────────────────────────────────────
A.fork_labels_of = lambda fk, srcs: {}
A.fork_labels_covering = lambda srcs: ({}, None)
out_c, pay_c = A.resolve_fork_outcome(
    cls_diff, {"x": row(10, Сумма=100.0)}, measure_ctx="сумма",
    want="sum", rel_by_src={"x": ["Сумма"]})
t("разные без подписей → C", out_c == "C" and pay_c.get("reason") == "unsigned_class",
  out_c)
cres = A.fork_outcome_c(
    "q", pay_c, cls_diff, {"x": row(10, Сумма=100.0)}, {},
    picked_src="x")
t("C: options пуст", cres and cres.get("options") == [],
  (cres or {}).get("options"))
t("C: FORK_OTHER_READING в тексте",
  cres and A.FORK_OTHER_READING in (cres.get("text") or ""),
  (cres or {}).get("text"))

# ── ticket working → лидер working ───────────────────────────────────────────
A.fork_labels_of = _labs_day
A.fork_labels_covering = _cov_day
out_b2, pay_b2 = A.resolve_fork_outcome(
    cls_diff, {"x": row(10, Сумма=100.0)}, measure_ctx="сумма",
    want="sum", rel_by_src={"x": ["Сумма"]})
split_w = A.fork_leader_class(
    "x", pay_b2.get("classes") or [], day_basis_prefer="working_days")
t("ticket working → лидер working_days",
  split_w and A._class_day_basis(split_w[0]) == "working_days",
  A._class_day_basis(split_w[0]) if split_w else None)
pref = A.calendar_day_basis_prefer(
    intent={}, trusted={"day_basis": "working_days"})
t("calendar_day_basis_prefer from ticket", pref == "working_days")
ord_w = A.calendar_axis_readings(base, prefer="working_days")
t("readings order: working first when prefer",
  ord_w and ord_w[0].get("day_basis") == "working_days")

# ── ticket_variant только при нажатии ────────────────────────────────────────
t("ticket_variant без trusted → None",
  A._journal_ticket_variant({"kind": "figures", "diag": {}}, trusted=None) is None)
t("ticket_variant с trusted → label",
  A._journal_ticket_variant(
      {"kind": "figures"}, trusted={"label": "by-working"}) == "by-working")

A.fork_labels_of = _real_labs
A.fork_labels_covering = _real_cov
restore_flag(saved)
restore_meta(_real_meta)

# ── K2: ось выключена (пустая карта) — рабочие/праздники → no_data ───────────
_real_phrases = A.calendar_day_basis_phrases


def _phrases_work_hol():
    return {
        "working_days": ["рабочие дни этой недели", "будни"],
        "holiday": ["праздники", "в праздники"],
    }


A.calendar_day_basis_phrases = _phrases_work_hol
mock_meta(regs="", keys="", rows=[])
t("map_ready: пустая карта", A.calendar_axis_map_ready() is False)
blk_w = A.calendar_axis_unavailable_block(
    "Сколько продаж за рабочие дни этой недели?", intent={}, trusted=None)
t("рабочие дни: no_data без карты",
  blk_w and blk_w.get("kind") == "no_data"
  and (blk_w.get("diag") or {}).get("reason") == "calendar_axis_unavailable",
  blk_w)
blk_h = A.calendar_axis_unavailable_block("Продажи в праздники")
t("праздники: no_data без карты",
  blk_h and blk_h.get("kind") == "no_data", blk_h)
t("календарная неделя: block None",
  A.calendar_axis_unavailable_block("Продажи за календарную неделю") is None)
mock_meta()
saved_on = with_flag(True)
t("рабочие дни: карта есть → не block",
  A.calendar_axis_unavailable_block(
      "Сколько продаж за рабочие дни этой недели?") is None)
restore_flag(saved_on)
A.calendar_day_basis_phrases = _real_phrases
restore_meta(_real_meta)

TRIG = re.compile(r"рабоч|будн|праздн|календарн", re.I)
funcs = [
    A.calendar_axis_readings, A.calendar_axis_open, A.expand_readings_calendar_axis,
    A.calendar_day_basis_prefer, A.prefer_day_basis_leader, A._working_day_doc_preds,
    A._day_basis_reading, A.calendar_registers, A.calendar_working_day_keys,
    A.calendar_map_rows, A._class_day_basis,
    A.calendar_axis_map_ready, A.calendar_day_basis_phrases,
    A.day_basis_from_question, A.calendar_day_basis_needed,
    A.calendar_axis_unavailable_block,
]
bad = []
for fn in funcs:
    try:
        src = inspect.getsource(fn)
    except OSError:
        continue
    if TRIG.search(src):
        bad.append(fn.__name__)
t("нет триггер-литералов в calendar-хелперах", not bad, bad)

# machine ids ascii only in helpers
t("machine ids calendar_days/working_days",
  A._DAY_BASIS_CALENDAR == "calendar_days"
  and A._DAY_BASIS_WORKING == "working_days")

# working preds строит один SQL с query_table (не цикл по дням)
saved = with_flag(True)
mock_meta()
preds = A._working_day_doc_preds(p_work)
t("working preds: один предикат", len(preds) == 1, preds)
t("working preds: query_table + IN",
  preds and "query_table" in preds[0] and " IN (" in preds[0],
  preds[0][:120] if preds else "")
t("calendar_days preds: пусто",
  A._working_day_doc_preds(p_cal) == [])
restore_flag(saved)
restore_meta(_real_meta)

try:
    _ans_src = inspect.getsource(A.answer)
except OSError:
    _ans_src = ""
t("z20: calendar block wired in answer",
  "calendar_axis_unavailable_block(" in _ans_src
  and "return _cal_blk" in _ans_src)

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
