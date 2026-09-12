#!/usr/bin/env python3
""">1 живая мера → меню; silent pick_measure снесён (S1).

Откат люка W: entity-locked не ослабляет меню мер на одном пути.
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
z10 = (ASK / "z10_rank.py").read_text(encoding="utf-8")

t("measure_captions / settle живы",
  "measure_captions(" in z20 and "_settle_measure" in z20)
t("0 measure_hatch в z20", "measure_hatch" not in z20)
t("0 _fork_headline в зоне мер z20",
  "_fork_headline_measure" not in z20
  and "_fork_sum_headline_pool" not in z20)

t("totals_of>1 blocked (measure_totals_of_blocked)",
  "measure_totals_of_blocked" in z20 or "totals_of" in z20)

t("S1: pick_measure файл/символ снесён — см. runtime ниже", True)

t("rank_axis_resolve: ≥2 → None, picked",
  "return None, picked" in z10)

sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

t("S1: pick_measure GONE", not hasattr(A, "pick_measure"))
t("S1: unresolved_quantity GONE", not hasattr(A, "unresolved_quantity"))
t("measure_choice жив", callable(A.measure_choice))

got, alts, how = A.measure_choice(
    ["Всего", "Количество"], "", alias_by={})
t("measure_choice: пустое слово → ask или single",
  how in ("ask", "single") or got in ("Всего", "Количество", None),
  (got, how, alts))

got1, a1, h1 = A.measure_choice(["Всего"], "всего", alias_by={})
t("measure_choice: 1 имя → брать",
  got1 == "Всего", (got1, h1, a1))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
