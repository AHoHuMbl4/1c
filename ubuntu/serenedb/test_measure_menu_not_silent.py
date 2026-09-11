#!/usr/bin/env python3
"""В3: при >1 мере ответ без measure_choice/clarify невозможен (статический разбор).

Замок формулы №15 ступень 4 / PLAN §7-3/4: проверка: путь totals_of→compose при >1 мере отсутствует;
measure_alts-путь ведёт в clarify; pick_measure/unresolved не выбирают winner.
"""
from __future__ import annotations

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

# (1) measure_alts clarify-return жив
t("measure_alts → kind=clarify return есть",
  'diag["measure_ambiguous"] = measure_alts' in z20
  and '"kind": "clarify"' in z20
  and "measure_captions(measure_alts" in z20)

# (2) totals_of всем именам при >1 блокируется
t("totals_of>1 blocked (measure_totals_of_blocked)",
  "measure_totals_of_blocked" in z20)
t("нет голого totals_of(..., measures_of(src)) → compose",
  not re.search(
      r'totals\s*=\s*\[\].*else totals_of\(src,\s*match,\s*preds,\s*measures_of\(src\)\)',
      z20)
  and "Величина не названа — считаем итоги по всем" not in z20)

# (3) pick_measure: rerank → ask при >1
t("pick_measure: >1 → how=ask",
  "return (None, fits, 'ask')" in z16
  or 'return (None, fits, "ask")' in z16)
t("pick_measure: нет return (top, [], 'rerank')",
  "return (top, [], 'rerank')" not in z16
  and 'return (top, [], "rerank")' not in z16)

# (4) unresolved_quantity: нет names[0] при >1
t("unresolved_quantity: нет return names[0] после len>1",
  "return names[0], []" not in z16.split("def unresolved_quantity")[1].split("def ")[0]
  or z16.count("return None, names") >= 1)
uq = z16.split("def unresolved_quantity")[1].split("\ndef ")[0]
t("unresolved: при >1 → None, names",
  "return None, names" in uq
  and uq.strip().endswith("return None, names")
  or ("# В3" in uq and "return None, names" in uq))

# (5) rank_axis_resolve: ≥2 → None, picked (меню)
t("rank_axis_resolve: ≥2 → None, picked",
  "return None, picked" in z10)
t("rank_axis_resolve: нет return picked[0], picked[1:]",
  "return picked[0], picked[1:]" not in z10)

# (6) load helpers: unresolved + pick на живом модуле
sys.path.insert(0, str(ROOT))
import os
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")
import serene_ask as A  # noqa: E402

m, alts = A.unresolved_quantity(None, [], "sum", "sum",
                                ["Всего", "Количество"], {"Всего": 1, "Количество": 1})
t("runtime unresolved >1 равные итоги → меню",
  m is None and set(alts) == {"Всего", "Количество"}, (m, alts))

m1, a1 = A.unresolved_quantity(None, [], "sum", "sum", ["Всего"], {"Всего": 10})
t("runtime unresolved 1 имя → брать",
  m1 == "Всего" and not a1, (m1, a1))

print("PASS", PASS, "FAIL", len(FAIL))
if FAIL:
    print("failed:", "; ".join(FAIL))
    sys.exit(1)
sys.exit(0)
