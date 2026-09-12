#!/usr/bin/env python3
"""Негатив: мерного люка A/B/C нет (решение владельца 12.09, PLAN §7 п.8).

S1: pick_measure/unresolved_quantity снесены с veto-зоной; меню мер —
через measure_choice / _settle_measure на одном пути.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASK = ROOT / "ask"

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


z20 = (ASK / "z20_ask_main_http.py").read_text(encoding="utf-8")

t("0 measure_hatch в z20", "measure_hatch" not in z20)
t("0 measure_hatch_B/C в z20",
  "measure_hatch_B" not in z20 and "measure_hatch_C" not in z20)
t("0 _fork_headline_measure в z20", "_fork_headline_measure" not in z20)
t("0 _fork_sum_headline_pool в z20", "_fork_sum_headline_pool" not in z20)
t("0 FORK_OTHER_READING в z20", "FORK_OTHER_READING" not in z20)
t("0 _entity_locked в z20", "_entity_locked" not in z20)

t("measure_captions жив в z20", "measure_captions(" in z20)
t("readings_menu / settle живы",
  "readings_menu" in z20 and "_settle_measure" in z20)

sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

t("S1: _fork_headline_measure снесён",
  not hasattr(A, "_fork_headline_measure"))
t("S1 slit: _fork_sum_headline_pool жив (sales)",
  callable(getattr(A, "_fork_sum_headline_pool", None)))
t("S1: pool *Документа+Всего",
  A._fork_sum_headline_pool(["СуммаДокумента", "Количество", "Всего"])
  == ["СуммаДокумента", "Всего"])

t("S1: unresolved_quantity снесён", not hasattr(A, "unresolved_quantity"))
t("S1: pick_measure снесён", not hasattr(A, "pick_measure"))
t("measure_choice жив", callable(A.measure_choice))

got, alts, how = A.measure_choice(
    ["Всего", "Количество"], "всего", alias_by={})
t("measure_choice: точное имя",
  got == "Всего" and how in ("exact", "single", "substring", "alias", "base"),
  (got, how, alts))

_hits = []
for m in re.finditer(r"\bsales_money_measure\s*\(", z20):
    ls = z20.rfind("\n", 0, m.start()) + 1
    line = z20[ls:z20.find("\n", m.start())]
    if "sales_money_measure" in line.split("#", 1)[0]:
        _hits.append(line.strip())
t("0 call-site sales_money_measure в z20", not _hits, _hits[:2])

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
