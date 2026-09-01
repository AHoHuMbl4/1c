#!/usr/bin/env python3
"""B9: маршрутизация /ask okna — оффлайн-замки routing-правок (18.08).

Запуск: python3 ubuntu/serenedb/test_b9_routing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


# ── axis clarify → row count (B8-02) ─────────────────────────────────────────
t("count без measure пропускает axis clarify",
  A.count_question_skips_axis({"want": "count"}, None,
                              {"clarify": "axis"}) is True)
t("sum с axis clarify не пропускается",
  A.count_question_skips_axis({"want": "sum"}, "сумма",
                              {"clarify": "axis"}) is False)
t("count с amount не пропускается",
  A.count_question_skips_axis({"want": "count", "amount": {"value": 5}},
                              None, {"clarify": "axis"}) is False)

# ── outcome B без pair_budget (B8-01/04) ─────────────────────────────────────
many = [{"atom": {"operation": "sum", "exact_value": i, "proof_status": A.PROOF_COMPUTED},
         "label": "L%d" % i, "srcs": ["s%d" % i], "row": {"count": 1}}
        for i in range(20)]
pay = {"classes": many, "fork_key": "fk"}
bres = A.fork_outcome_b("сколько?", pay, {}, picked_src="s5")
t("B: лидер в text, 19 в люке, atoms=20",
  bres and len(bres.get("atoms") or []) == 20
  and len(bres.get("options") or []) == 19
  and "L5" in (bres.get("text") or "")
  and (bres.get("partial") or {}).get("fork_limitation") is None)
t("B: pairs_hidden null",
  (bres.get("figures") or {}).get("pairs_hidden") is None)

# ── literal resolver fallback (B8-03) ──────────────────────────────────────────
real_r = A._resolver_psql
A._resolver_psql = lambda sql: [["Г. КАЗАНЬ"]] if "resolver_index" in sql else []
try:
    t("_resolve_values_literal: Казань → Г. КАЗАНЬ",
      A._resolve_values_literal("Казани") == ["Г. КАЗАНЬ"])
finally:
    A._resolver_psql = real_r

real_rv = A.resolve_values
real_psql_saved = A.psql
A.resolve_values = lambda term: []
A._resolver_psql = lambda sql: [["Г. КАЗАНЬ"]] if "resolver_index" in sql else []
A.psql = lambda sql: []  # буквальный поиск пуст — только literal fallback
try:
    out, diag = A.probe([["Казань"]])
    t("probe: literal fallback находит resolved",
      diag.get(0) == "resolved" and "ts_phrase" in (out[0] if out else ""))
finally:
    A.resolve_values = real_rv
    A._resolver_psql = real_r
    A.psql = real_psql_saved


# ── literal: не матчить «оказания» на «казан» ───────────────────────────────
A._resolver_psql = lambda sql: [["Доходы от оказания услуг"], ["Г. КАЗАНЬ"]] if "resolver_index" in sql else []
try:
    t("literal: «оказания» отфильтровано",
      "Г. КАЗАНЬ" in A._resolve_values_literal("Казани")
      and not any("оказан" in v.lower() for v in A._resolve_values_literal("Казани")))
finally:
    A._resolver_psql = real_r

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
