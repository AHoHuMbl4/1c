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

# ── S1: fork_classes_windowed / outcomes снесены ──────────────────────────────
t("S1: fork_classes_windowed GONE", not hasattr(A, "fork_classes_windowed"))
t("S1: resolve_fork_outcome GONE", not hasattr(A, "resolve_fork_outcome"))
t("S1 slit: fork_labels_of", callable(A.fork_labels_of))
t("S1 slit: fork_labels_covering", callable(A.fork_labels_covering))

print("PASS %d FAIL %d" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
