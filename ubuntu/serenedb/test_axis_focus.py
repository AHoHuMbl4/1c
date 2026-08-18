#!/usr/bin/env python3
"""Focus = ось target_src, не источник. Оффлайн, без базы и сети.

Свидетель okna 2a960e42: focus=номенклатура + мера → справочник no_data, хотя
отгрузки живые. Проба подставляет выдуманные имена — не знает ни одной базы.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402
import serene_axis as X  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


CAT = "catalog_номенклатурапробная"
HOLD = "document_отгрузкапробная_номенклатура"
HOLD2 = "document_закупкапробная_номенклатура"
COL = "Номенклатура"
HDR = "document_отгрузкапробная"
NOT_AXIS = "document_отгрузкапробная_номенклатура"
DOC_SALE = "document_реализацияпробная"
PKO = "document_пкопробный"
COL_BASE = "ДокументОснование"

_HOLDERS = {
    CAT: [(HOLD, COL)],
    "catalog_двеосипробные": [(HOLD, COL), (HOLD2, COL)],
    DOC_SALE: [(PKO, COL_BASE)],
}
_NUMS = {
    CAT: ["Код"],
    HOLD: ["Сумма", "Количество"],
    HOLD2: ["Сумма", "Количество"],
    DOC_SALE: ["Всего", "Сумма"],
    PKO: ["СуммаДокумента"],
}
_LIVE = {HOLD: 542, HOLD2: 120, CAT: 2381, DOC_SALE: 331, PKO: 4}
_PARENT = {HOLD: HDR, HOLD2: "document_закупкапробная", CAT: "",
           DOC_SALE: "", PKO: ""}
_SQL = []


def _in_list(sql, name):
    return ("'%s'" % name) in sql or name in sql


def _fake(sql, *a, **kw):
    s = " ".join(sql.split())
    _SQL.append(s)
    if "FROM search_refcols" in s and "target_src" in s:
        m = re.search(r"target_src = '([^']*)'", s)
        tgt = m.group(1) if m else ""
        return [[src, col] for src, col in _HOLDERS.get(tgt, [])]
    if "unnest(map_keys(nums))" in s:
        out = []
        for src, keys in _NUMS.items():
            if _in_list(s, src):
                out.extend([[src, k] for k in keys])
        return out
    if "count(*) AS n" in s:
        out = []
        for src, n in _LIVE.items():
            if "src_table = '%s'" % src in s:
                out.append([src, n])
        return out
    if "SELECT src_table, parent FROM" in s:
        out = []
        for src, par in _PARENT.items():
            if _in_list(s, src):
                out.append([src, par])
        return out
    if "SELECT parent FROM" in s:
        m = re.search(r"src_table = '([^']*)'", s)
        src = m.group(1) if m else ""
        return [[_PARENT.get(src, "")]]
    return []


A.psql = _fake


def _plan(focus, want, measure="", amount=None, match="doc @@ x"):
    _SQL.clear()
    intent = {"want": want, "measure": "", "amount": amount or {}}
    diag = {}
    return A.axis_focus_plan(focus, intent, measure, match, ["doc_date >= '2026-08-07'"],
                             {}, diag), diag


plan, diag = _plan(CAT, "sum", "сумма")
t("focus=номенклатура + сумма → держатель, не catalog",
  plan and plan[0] == "holder" and plan[1] == HOLD and plan[2] == COL, plan)
t("diag: ось, не catalog как src счёта",
  (diag.get("focus_was_axis") or {}).get("стало") == HOLD
  and (diag.get("focus_was_axis") or {}).get("было") == CAT, diag.get("focus_was_axis"))

dec = X.decide_grain([{"col": COL, "target_src": CAT}], [COL], {}, "sum", True)
t("после держателя grain=group, не row",
  dec["grain"] == "group" and dec["col"] == COL, dec)

plan, _ = _plan(CAT, "list", "Количество")
t("focus=номенклатура + количество → держатель",
  plan and plan[0] == "holder" and plan[1] == HOLD, plan)

plan, _ = _plan(CAT, "list", "топ-5", {"value": 5})
t("чип топ-5 (слово не поле каталога) → держатель",
  plan and plan[0] == "holder" and plan[1] == HOLD, plan)

plan, diag = _plan(CAT, "count")
t("счёт позиций без величины движений → каталог",
  plan is None and diag.get("focus_axis_keep") == "catalog_self", (plan, diag))
t("счёт позиций не зовёт живой счёт держателей",
  not any("count(*) AS n" in q for q in _SQL),
  [q[:80] for q in _SQL if "count" in q.lower()])

plan, _ = _plan(NOT_AXIS, "sum", "сумма")
t("focus табличной части (не target_src) → прежний путь", plan is None, plan)

_SQL.clear()
plan, _ = _plan("catalog_двеосипробные", "sum", "сумма")
t("два держателя → clarify, не no_data",
  plan and plan[0] == "clarify" and set(plan[1]) == {HOLD, HOLD2}, plan)

# Контроль зерна без оси не сломать
dec = X.decide_grain([{"col": COL, "target_src": CAT}], [], {}, "sum", True)
t("sum без kind (контроль без оси) → row", dec["grain"] == "row", dec)

# live_src_counts: pred_by снимает match у ребёнка
_SQL.clear()
A.live_src_counts([HOLD, CAT], "doc @@ ts_phrase('номенклатура')",
                  ["doc_date >= 'x'"], pred_by={HOLD: "split_part(row_key,'|',1) IN (1)"},
                  require_nums=True)
parts = re.split(r"\sUNION ALL\s", _SQL[0]) if _SQL else []
hold_part = next((p for p in parts if "src_table = '%s'" % HOLD in p), "")
cat_part = next((p for p in parts if "src_table = '%s'" % CAT in p), "")
t("pred_by: у держателя match не в WHERE, источник CORPUS",
  hold_part and "ts_phrase" not in hold_part and "search_corpus" in hold_part,
  hold_part[:240])
t("без pred_by match остаётся, источник INDEX",
  cat_part and "ts_phrase" in cat_part and "search_idx" in cat_part, cat_part[:240])
t("require_nums в живом счёте", any("map_keys(nums)" in q for q in _SQL),
  (_SQL[0] if _SQL else "")[:200])

# Повтор ТЧ при нуле с match: первый UNION с match, второй без
_LIVE_ZERO = dict(_LIVE)
_LIVE[HOLD] = 0


def _fake_zero(sql, *a, **kw):
    s = " ".join(sql.split())
    _SQL.append(s)
    if "FROM search_refcols" in s and "target_src" in s:
        return [[HOLD, COL]]
    if "unnest(map_keys(nums))" in s:
        return [[HOLD, "Сумма"], [HOLD, "Количество"]]
    if "count(*) AS n" in s:
        if "doc @@" in s:
            return [[HOLD, 0]]
        return [[HOLD, 542]]
    if "SELECT src_table, parent FROM" in s:
        return [[HOLD, HDR]]
    return []


A.psql = _fake_zero
_SQL.clear()
plan, diag = _plan(CAT, "sum", "сумма", match="doc @@ ts_phrase('номенклатура')")
t("ТЧ ноль при match → повтор без match → держатель",
  plan and plan[0] == "holder" and plan[1] == HOLD, (plan, [q[:100] for q in _SQL]))
t("повтор живого счёта без лексики номенклатуры",
  any("count(*)" in q and "ts_phrase" not in q for q in _SQL),
  [q[:120] for q in _SQL if "count" in q])

_LIVE.clear()
_LIVE.update(_LIVE_ZERO)
A.psql = _fake

# Класс F: снятый документ реализации не пересаживается на ПКО
plan, diag = _plan(DOC_SALE, "sum", "сумма")
t("без билета документ+сумма → держатель ПКО (прежний путь оси)",
  plan and plan[0] == "holder" and plan[1] == PKO, plan)
diag_s = {}
plan_s = A.axis_focus_plan(
    DOC_SALE, {"want": "sum", "measure": "", "amount": {}}, "сумма",
    "doc @@ x", ["doc_date >= '2026-08-07'"], {}, diag_s,
    trusted=None, resolved={"src": DOC_SALE})
t("settled документ + ДокументОснование → keep, не ПКО",
  plan_s is None and diag_s.get("focus_axis_keep") == "entity_settled",
  (plan_s, diag_s))
plan_c, diag_c = _plan(CAT, "sum", "сумма")
t("каталог без билета по-прежнему держатель",
  plan_c and plan_c[0] == "holder" and plan_c[1] == HOLD, plan_c)

print("\nИТОГ: ok %d, FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("ПРОВАЛЕНО: %s" % "; ".join(FAIL))
    raise SystemExit(1)
