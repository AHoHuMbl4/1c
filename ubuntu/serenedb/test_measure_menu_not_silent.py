#!/usr/bin/env python3
""">1 живая мера → clarify-меню и при зафиксированной сущности.

Откат люка W (PLAN §7 п.8): entity-locked не ослабляет меню мер;
pick_measure/unresolved не выбирают silent winner при >1.
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


z20 = (ASK / "z20_ask_main_http_legacy.py").read_text(encoding="utf-8")
z16 = (ASK / "z16_veto_pick_entity.py").read_text(encoding="utf-8")
z10 = (ASK / "z10_rank.py").read_text(encoding="utf-8")

# (1) measure_alts clarify-return жив; люка нет
t("measure_alts → kind=clarify return есть",
  'diag["measure_ambiguous"]' in z20
  and '"kind": "clarify"' in z20
  and "measure_captions(" in z20)
t("0 measure_hatch в z20", "measure_hatch" not in z20)
t("0 _fork_headline в зоне мер z20",
  "_fork_headline_measure" not in z20
  and "_fork_sum_headline_pool" not in z20)

# (2) totals_of всем именам при >1 блокируется
t("totals_of>1 blocked (measure_totals_of_blocked)",
  "measure_totals_of_blocked" in z20)
t("нет голого totals_of(..., measures_of(src)) → compose",
  not re.search(
      r'totals\s*=\s*\[\].*else totals_of\(src,\s*match,\s*preds,\s*measures_of\(src\)\)',
      z20)
  and "Величина не названа — считаем итоги по всем" not in z20)

# (3) pick_measure: rerank → ask при >1 (не silent)
t("pick_measure: >1 → how=ask",
  "return (None, fits, 'ask')" in z16
  or 'return (None, fits, "ask")' in z16)
t("pick_measure: нет return (top, [], 'rerank')",
  "return (top, [], 'rerank')" not in z16
  and 'return (top, [], "rerank")' not in z16)

# (4) unresolved: >1 → None, names (entity_locked не ослабляет)
uq = z16.split("def unresolved_quantity")[1].split("\ndef ")[0]
t("unresolved: при >1 → None, names",
  "return None, names" in uq)
t("unresolved: нет entity_locked-ветки ослабления",
  "if entity_locked:" not in uq)

# (5) rank_axis_resolve: ≥2 → None, picked (меню)
t("rank_axis_resolve: ≥2 → None, picked",
  "return None, picked" in z10)

# (6) runtime
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

m, alts = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 1, "Количество": 2},
    entity_locked=False)
t("runtime unresolved без lock → меню",
  m is None and set(alts) == {"Всего", "Количество"}, (m, alts))

m_a, a_a = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 10, "Количество": 10},
    entity_locked=True)
t("runtime unresolved locked равные → меню (не silent A)",
  m_a is None and set(a_a) == {"Всего", "Количество"}, (m_a, a_a))

m_b, a_b = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 100, "Количество": 5},
    entity_locked=True)
t("runtime unresolved locked разные → меню",
  m_b is None and set(a_b) == {"Всего", "Количество"}, (m_b, a_b))

m1, a1 = A.unresolved_quantity(None, [], "sum", "sum", ["Всего"], {"Всего": 10})
t("runtime unresolved 1 имя → брать",
  m1 == "Всего" and not a1, (m1, a1))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
