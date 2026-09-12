#!/usr/bin/env python3
"""S3: entity_form-терминалы снесены; catalogs / compare / axis helpers живы.

Запуск: python3 ubuntu/serenedb/test_entity_form.py
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
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


DEL = (
    "register_count_src", "entity_form_count_target_is_movement",
    "entity_form_expand_pool", "event_kind_catalog_expand_pool",
    "entity_form_rolling_year", "entity_form_gate_open",
    "entity_form_applicable", "entity_form_collapse_guard",
    "entity_form_pre_entity_ok", "entity_form_atom_distinct",
    "entity_form_atom_complement", "entity_form_axis_on_sales",
    "entity_form_structs", "entity_form_pick", "entity_form_compute",
    "try_entity_form_answer", "try_event_count_period_clarify",
    "event_duel_applies",
)
for name in DEL:
    t("S3 GONE: " + name, not hasattr(A, name))

t("ASK_ENTITY_FORM exists", hasattr(A, "ASK_ENTITY_FORM"))
t("entity_form_catalogs_for_kind жив",
  callable(getattr(A, "entity_form_catalogs_for_kind", None)))
t("live_axis_col_for_count жив",
  callable(getattr(A, "live_axis_col_for_count", None)))
t("_pick_kind_axis_col жив",
  callable(getattr(A, "_pick_kind_axis_col", None)))
t("aggregate_compare_sales жив",
  callable(getattr(A, "aggregate_compare_sales", None)))

# compare atom пара
cmp_atom = A.build_answer_atom(
    operation="compare", exact_value=-792128.74, measure_id="measure_x",
    measure_label="measure_x", form="compare", proof_status=A.PROOF_COMPUTED)
pair = A.render_atom_pair(cmp_atom)
t("compare pair собрана", bool(pair) and "792" in pair.replace(" ", ""), pair)
t("compare pair без · rank",
  pair and "· rank" not in pair and "rank" not in pair.lower())

# нет banned литералов в живых compare/catalogs хелперах
_src = (ROOT / "ask" / "z05_entity_form.py").read_text(encoding="utf-8")
tree = ast.parse(_src)
banned = ("не продаётся", "реально", "книгапродаж")
found_banned = []
for node in tree.body:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        continue
    if node.name not in (
            "entity_form_catalogs_for_kind", "aggregate_compare_sales",
            "live_axis_col_for_count", "_pick_kind_axis_col",
            "_kind_axis_col_candidates", "live_axis_col_candidates"):
        continue
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            low = n.value.lower()
            for b in banned:
                if b in low:
                    found_banned.append((node.name, n.value[:60]))
t("нет banned литералов в live entity_form helpers",
  not found_banned, found_banned)

# catalogs callable smoke
_old = A.psql
A.psql = lambda q: []
try:
    cats = A.entity_form_catalogs_for_kind("номенклатура")
    t("catalogs_for_kind возвращает list|None",
      cats is None or isinstance(cats, list), cats)
finally:
    A.psql = _old

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
sys.exit(1 if FAIL else 0)
