#!/usr/bin/env python3
"""Негатив: мерного люка A/B/C нет (решение владельца 12.09, PLAN §7 п.8).

При entity-locked и >1 мере с разными totals — kind=clarify меню мер,
не figures с вторыми числами и не measure_hatch.
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

# ── диск: люк-маркеры сняты ──────────────────────────────────────────────────
t("0 measure_hatch в z20", "measure_hatch" not in z20)
t("0 measure_hatch_B/C в z20",
  "measure_hatch_B" not in z20 and "measure_hatch_C" not in z20)
t("0 _fork_headline_measure в z20", "_fork_headline_measure" not in z20)
t("0 _fork_sum_headline_pool в z20", "_fork_sum_headline_pool" not in z20)
t("0 FORK_OTHER_READING в z20", "FORK_OTHER_READING" not in z20)
t("0 _entity_locked в z20", "_entity_locked" not in z20)

# ── меню мер живёт ───────────────────────────────────────────────────────────
t("measure_alts → kind=clarify",
  'diag["measure_ambiguous"]' in z20
  and '"kind": "clarify"' in z20
  and "measure_captions(" in z20)

# ── runtime: equal totals / one name / >1 alts ───────────────────────────────
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

t("headline helper в z09 жив (fork)",
  A._fork_headline_measure(
      "accumulationregister_x",
      {"Всего": 100.0, "Количество": 5.0, "СуммаНДС": 10.0},
      "", want="sum") == "Всего")

m, alts = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 100.0, "Количество": 5.0},
    entity_locked=True)
t("locked + >1 → alts-меню (не winner)",
  m is None and set(alts) == {"Всего", "Количество"}, (m, alts))

m2, a2 = A.unresolved_quantity(
    None, [], "sum", "sum",
    ["Всего", "Количество"], {"Всего": 10.0, "Количество": 10.0},
    entity_locked=True)
t("locked + равные totals → тоже alts (меню форсирует z20)",
  m2 is None and set(a2) == {"Всего", "Количество"}, (m2, a2))

# равные totals в z20 → обычный ответ (не люк): контракт measure_ambiguous
t("равные totals — не ambiguous",
  A.measure_ambiguous(
      ["Всего", "Количество"], {"Всего": 10.0, "Количество": 10.0}) is False)
t("разные totals — ambiguous",
  A.measure_ambiguous(
      ["Всего", "Количество"], {"Всего": 100.0, "Количество": 5.0}) is True)

# негатив P1 (не люк): measure_in_kin / code_ambiguous
t("measure_in_kin_blocked при wiki_verify",
  "measure_in_kin_blocked" in z20
  and 'diag.get("wiki_verify") == src' in z20)
t("code_ambiguous не растит picked при wiki_hybrid_pick",
  'if not diag.get("wiki_hybrid_pick"):' in z20
  and 'diag["code_ambiguous"] = extra' in z20
  and z20.find('diag["code_ambiguous"] = extra')
     < z20.find('if not diag.get("wiki_hybrid_pick"):'))

# нет call-site sales_money_measure
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
