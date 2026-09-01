#!/usr/bin/env python3
"""K7: ось склада без имени реквизита и без маски таблицы.

Оффлайн. Источник: docs/K7_WAREHOUSE_AXIS.md.
Запуск: python3 ubuntu/serenedb/test_warehouse_axis_autonomy.py
"""
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

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


src = inspect.getsource(A.warehouse_axis_values)
src_axis = inspect.getsource(A.axis_catalog_values)
src_combined = src + src_axis

# ── запрет привязки к конфигурации ──────────────────────────────────────────
t("нет литерала МестоХранения",
  "МестоХранения" not in src_combined and "местохранения" not in src_combined.lower())
t("нет маски catalog_%мест%хран%",
  not re.search(r"мест[%_].*хран|хран[%_].*мест", src_combined, re.I)
  and "мест%%хран" not in src_combined
  and "мест%хран" not in src_combined)
t("нет attrs Description как запасного пути",
  "Description" not in src_combined)

# ── штатный путь проекта ────────────────────────────────────────────────────
t("каталог через entity_form_catalogs_for_kind",
  "entity_form_catalogs_for_kind" in src_combined)
t("ось через search_refcols / target_src",
  "search_refcols" in src_combined and "target_src" in src_combined)
t("значения через map_extract_value(refs_map, …)",
  "map_extract_value" in src_combined and "refs_map" in src_combined)
t("запасной search_refmap по owner",
  "search_refmap" in src_combined and "owner" in src_combined)

# ── [замер 01.09 okna] ось места не резолвится по примерам вопросов ─────────
# best_used_for карточек держит ПРИМЕРЫ вопросов («сколько сотрудников»):
# любое вопросительное слово ложно резолвилось осью и включало stock_override
# поверх верифицированного вики лидера («сколько организаций» → импорттмц).
_here = os.path.dirname(os.path.abspath(__file__))
_z12 = open(os.path.join(_here, "ask", "z12_stock_balance.py"), encoding="utf-8").read()
_z05 = open(os.path.join(_here, "ask", "z05_entity_form.py"), encoding="utf-8").read()
t("ось места: резолв без best_used_for (include_examples=False)",
  re.search(r"def _catalogs_for_axis_word[\s\S]{0,900}include_examples=False",
            _z12) is not None)
t("kind-резолв прежний: include_examples=True в entity_form_catalogs_for_kind",
  "include_examples=True" in _z05 and "best_used_for" in _z05)

# ── поведение clarify (мок, без БД) ──────────────────────────────────────────
wh = ["Vitrina / 1", "Bubuieci / 2", "Depozit / 3"]
ask = A.warehouse_clarify("Сколько осталось на складе?", {}, {}, 0.0,
                          warehouses=wh)
t("clarify: 3 склада → kind=clarify",
  ask and ask.get("kind") == "clarify" and len(ask.get("options") or []) == 3)
t("clarify: 1 склад → None",
  A.warehouse_clarify("q", {}, {}, 0.0, warehouses=["only"]) is None)

# ── оффлайн warehouse_axis_values: пустой psql → [] ─────────────────────────
_real = A.psql
A.psql = lambda q: (_ for _ in ()).throw(RuntimeError("offline"))
try:
    t("offline entity_form → []",
      A.warehouse_axis_values() == [])
finally:
    A.psql = _real

# мок: catalogs + best col + values (только psql, как live)
calls = []


def _mock_psql(q):
    calls.append(q)
    ql = q.lower()
    if "search_tables" in ql and "search_entity_alias" in ql:
        return [("catalog_wh_demo",)]
    if "map_extract_value" in ql and "best" in ql:
        return [("Alpha WH",), ("Beta WH",)]
    if "search_refmap" in ql:
        return [("Gamma WH",)]
    return []


A.psql = _mock_psql
_old_cats_wh = A.entity_form_catalogs_for_kind
A.entity_form_catalogs_for_kind = lambda w, **kw: ["catalog_wh_demo"]
try:
    got = A.warehouse_axis_values(
        limit=20, intent={"kind": "номенклатура", "action_axis": "склад"},
        question="на складе")
    t("мок: два имени с оси refs_map",
      got == ["Alpha WH", "Beta WH"], got)
    t("мок: SQL не содержит МестоХранения",
      all("МестоХранения" not in c for c in calls),
      [c[:80] for c in calls[:3]])
finally:
    A.psql = _real
    A.entity_form_catalogs_for_kind = _old_cats_wh


print()
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
