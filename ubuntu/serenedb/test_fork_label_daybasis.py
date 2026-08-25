#!/usr/bin/env python3
"""Оффлайн-замок §7bis day-basis: очередь подписей и исходы B/C.

Замки:
  · класс day-basis попадает в search_fork_class (src_set=id веток);
  · подписей нет → исход C, ветки не названы;
  · подписи в search_fork_label → исход B, лидер + подписанный люк;
  · в новом коде нет литералов подписей (корни рабоч/календарн/будн).

Запуск: python3 ubuntu/serenedb/test_fork_label_daybasis.py
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


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


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


# ── (а) очередь разметки ─────────────────────────────────────────────────────
queue = []
_real_psql = A.psql


def _mock_psql(sql):
    if "INSERT INTO search_fork_class" in sql:
        queue.append(sql)
    return []


A.psql = _mock_psql
saved = with_flag(True)
p_cal = {"from": "2026-08-01", "to": "2026-08-15", "origin": "explicit",
         "interpretation_id": "explicit", "day_basis": "calendar_days"}
p_work = dict(p_cal, day_basis="working_days")
wfp_c = A.window_fp_of(p_cal, "explicit")
wfp_w = A.window_fp_of(p_work, "explicit")
rows_diff = {
    ("reg_x", wfp_c): row(10, Сумма=100.0),
    ("reg_x", wfp_w): row(8, Сумма=80.0),
}
pby = {("reg_x", wfp_c): p_cal, ("reg_x", wfp_w): p_work}
cls_diff = A.fork_classes_windowed(
    rows_diff, pby, "summa", want="sum", rel_by_src={"reg_x": ["Сумма"]})
expected_fk = A.fork_key_of(
    ["reg_x"], "summa", window_fp=A._window_fp_base(p_cal, "explicit"))
A._fork_log(cls_diff, "summa")
A.psql = _real_psql
restore_flag(saved)

t("очередь: INSERT search_fork_class был", len(queue) >= 1, len(queue))
branch_ins = [q for q in queue if "calendar_days" in q and "working_days" in q]
t("очередь: src_set calendar_days+working_days", len(branch_ins) == 1, queue)
t("очередь: fork_key с базовым окном",
  branch_ins and expected_fk in branch_ins[0], expected_fk)
t("очередь: без дубля src таблицы",
  not any("reg_x" in q and "calendar_days" not in q for q in queue), queue)

# ── (б)(в) исходы C и B ──────────────────────────────────────────────────────
saved = with_flag(True)
cls_diff = A.fork_classes_windowed(
    rows_diff, pby, "summa", want="sum", rel_by_src={"reg_x": ["Сумма"]})
rows_flat = {"reg_x": row(10, Сумма=100.0)}

_real_labs = A.fork_labels_of
_real_cov = A.fork_labels_covering
_fk = expected_fk


def _labs_from_db(fk, srcs):
    if fk != _fk:
        return {}
    out = {}
    for s in srcs or []:
        if s == "calendar_days":
            out[s] = "lbl-cal-window"
        elif s == "working_days":
            out[s] = "lbl-work-window"
    return out


def _cov_from_db(srcs):
    m = _labs_from_db(_fk, srcs)
    return m, _fk if m else None


# (б) без подписей → C
A.fork_labels_of = lambda fk, srcs: {}
A.fork_labels_covering = lambda srcs: ({}, None)
out_c, pay_c = A.resolve_fork_outcome(
    cls_diff, rows_flat, measure_ctx="summa", want="sum",
    rel_by_src={"reg_x": ["Сумма"]})
t("без подписей → C", out_c == "C" and pay_c.get("reason") == "unsigned_class", out_c)
cres = A.fork_outcome_c(
    "q", pay_c, cls_diff, rows_flat, {}, picked_src="reg_x")
t("C: options пуст", cres and cres.get("options") == [], (cres or {}).get("options"))
t("C: FORK_OTHER_READING в тексте",
  cres and A.FORK_OTHER_READING in (cres.get("text") or ""), (cres or {}).get("text"))

# (в) с подписями → B
A.fork_labels_of = _labs_from_db
A.fork_labels_covering = _cov_from_db
out_b, pay_b = A.resolve_fork_outcome(
    cls_diff, rows_flat, measure_ctx="summa", want="sum",
    rel_by_src={"reg_x": ["Сумма"]})
t("с подписями → B", out_b == "B", out_b)
bres = A.fork_outcome_b("q", pay_b, {}, picked_src="reg_x")
t("B: лидер calendar + lbl-cal-window",
  bres and bres.get("atoms")
  and bres["atoms"][0].get("measure_label") == "lbl-cal-window",
  (bres or {}).get("atoms"))
t("B: люк working_days + lbl-work-window",
  bres and len(bres.get("options") or []) == 1
  and bres["options"][0].get("day_basis") == "working_days"
  and bres["options"][0].get("label") == "lbl-work-window",
  (bres or {}).get("options"))

A.fork_labels_of = _real_labs
A.fork_labels_covering = _real_cov
restore_flag(saved)

# ── (г) нет литералов подписей в новом коде ──────────────────────────────────
TRIG = re.compile(r"рабоч|будн|календарн", re.I)
NEW_FUNCS = [
    A._window_fp_base, A._fork_key_for_period, A._fork_day_basis_groups,
    A._fork_log_day_basis,
]
src_blob = "\n".join(inspect.getsource(f) for f in NEW_FUNCS)
t("grep: нет корней подписей в новых хелперах", not TRIG.search(src_blob))
# wiki_alias day-basis блок — только английские scope в SQL CASE
wa = open(os.path.join(os.path.dirname(__file__), "wiki_alias.sh"),
          encoding="utf-8").read()
start = wa.find("# ── §7 / §7bis: подписи веток развилок")
end = wa.find("# ── Ф6.3: Solr-словарь", start)
wa_block = wa[start:end] if start >= 0 and end > start else ""
t("wiki_alias day-basis блок найден", start >= 0)
t("wiki_alias: нет корней подписей в day-basis блоке",
  wa_block and not TRIG.search(wa_block), wa_block[:80])

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
