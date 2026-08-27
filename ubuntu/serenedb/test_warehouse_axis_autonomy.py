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

# ── запрет привязки к конфигурации ──────────────────────────────────────────
t("нет литерала МестоХранения",
  "МестоХранения" not in src and "местохранения" not in src.lower())
t("нет маски catalog_%мест%хран%",
  not re.search(r"мест[%_].*хран|хран[%_].*мест", src, re.I)
  and "мест%%хран" not in src
  and "мест%хран" not in src)
t("нет attrs Description как запасного пути",
  "Description" not in src)

# ── штатный путь проекта ────────────────────────────────────────────────────
t("каталог через entity_form_catalogs_for_kind",
  "entity_form_catalogs_for_kind" in src)
t("ось через search_refcols / target_src",
  "search_refcols" in src and "target_src" in src)
t("значения через map_extract_value(refs_map, …)",
  "map_extract_value" in src and "refs_map" in src)
t("запасной search_refmap по owner",
  "search_refmap" in src and "owner" in src)

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
try:
    got = A.warehouse_axis_values(limit=20)
    t("мок: два имени с оси refs_map",
      got == ["Alpha WH", "Beta WH"], got)
    t("мок: SQL не содержит МестоХранения",
      all("МестоХранения" not in c for c in calls),
      [c[:80] for c in calls[:3]])
finally:
    A.psql = _real


print()
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
