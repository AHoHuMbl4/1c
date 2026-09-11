#!/usr/bin/env python3
"""Волна W: мерное clarify при зафиксированной сущности отсутствует (A/B/C).

Замок Z2/PLAN §6W: entity-locked → число+люк, не kind=clarify мер;
без фиксации сущности меню мер остаётся; pick_measure не silent-rerank.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"

PASS, FAIL = 0, []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


z20 = (ASK / "z20_ask_main_http.py").read_text(encoding="utf-8")
z16 = (ASK / "z16_veto_pick_entity.py").read_text(encoding="utf-8")
z10 = (ASK / "z10_rank.py").read_text(encoding="utf-8")

# (1) entity-locked hatch: A/B/C маркеры на диске
t("measure_hatch A маркер", 'diag["measure_hatch"] = "A"' in z20)
t("measure_hatch B маркер", 'diag["measure_hatch"] = "B"' in z20)
t("measure_hatch C маркер", 'diag["measure_hatch"] = "C"' in z20)
t("FORK_OTHER_READING в мерном C", "FORK_OTHER_READING" in z20)
t("entity_locked гейт перед hatch", "_entity_locked" in z20
  and "wiki_hybrid_pick" in z20)

# (2) мерное clarify только без фиксации (else-ветка)
# при locked нет return kind=clarify в hatch-блоке — есть measure_hatch
t("hatch B → kind=figures",
  '"kind": "figures"' in z20 and "measure_hatch_B" in z20)
t("без locked — clarify мер жив",
  'diag["measure_ambiguous"] = measure_alts' in z20
  and '"kind": "clarify"' in z20)

# (3) pick_measure: rerank → ask при >1 (не silent)
t("pick_measure: >1 → how=ask",
  "return (None, fits, 'ask')" in z16
  or 'return (None, fits, "ask")' in z16)
t("pick_measure: нет return (top, [], 'rerank')",
  "return (top, [], 'rerank')" not in z16
  and 'return (top, [], "rerank")' not in z16)

# (4) unresolved: entity_locked параметр; без lock → меню
uq = z16.split("def unresolved_quantity")[1].split("\ndef ")[0]
t("unresolved: entity_locked параметр", "entity_locked" in uq)
t("unresolved: без lock → None, names", "return None, names" in uq)

# (5) rank_axis_resolve: ≥2 → None, picked (меню)
t("rank_axis_resolve: ≥2 → None, picked",
  "return None, picked" in z10)

# (6) runtime
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

# без lock: >1 → alts (меню)
m, alts = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 1, "Количество": 2},
    entity_locked=False)
t("runtime unresolved без lock → меню",
  m is None and set(alts) == {"Всего", "Количество"}, (m, alts))

# locked + равные → A (одно число)
m_a, a_a = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 10, "Количество": 10},
    entity_locked=True)
t("runtime unresolved locked равные → A",
  m_a == "Всего" and not a_a, (m_a, a_a))

# locked + разные → alts для z20 hatch (не silent winner)
m_b, a_b = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 100, "Количество": 5},
    entity_locked=True)
t("runtime unresolved locked разные → hatch-alts",
  m_b is None and set(a_b) == {"Всего", "Количество"}, (m_b, a_b))

m1, a1 = A.unresolved_quantity(None, [], "sum", "sum", ["Всего"], {"Всего": 10})
t("runtime unresolved 1 имя → брать",
  m1 == "Всего" and not a1, (m1, a1))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
