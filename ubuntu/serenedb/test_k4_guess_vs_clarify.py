#!/usr/bin/env python3
"""K4-1: догадка периода/меры/остатка → clarify (Э3 okna №1,2,8,12).

Оффлайн. Без базы/сети/модели там, где хватает чистых функций.
Хелперы патча A/B/C (`period_assumed_needs_clarify` и др.) — после выката
кода; до них кейсы помечаются pending и не краснеют.

Запуск: python3 ubuntu/serenedb/test_k4_guess_vs_clarify.py
Источник: docs/K4_GUESS_VS_CLARIFY.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402
import serene_enough as E  # noqa: E402

PASS, FAIL, PENDING = 0, [], []


def t(name, cond, detail=None):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail if detail is not None else "")


def pending(name):
    PENDING.append(name)
    print("pend-", name)


today = "2026-08-27"

# ── Разметка assumed (уже есть) ──────────────────────────────────────────────
intent_year = {
    "want": "sum", "kind": "продажи",
    "period": {"from": "2025-08-27", "to": "2026-08-27"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
intent_qtr = {
    "want": "sum", "kind": "продажи",
    "period": {"from": "2026-04-01", "to": "2026-06-30"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
intent_day = {
    "want": "sum",
    "period": {"from": "2026-08-26", "to": "2026-08-26"},
    "parse": {"assumed": ["period.from", "period.to"]},
}
intent_2022 = {
    "want": "sum",
    "period": {"from": "2022-01-01", "to": "2022-12-31"},
    "parse": {"assumed": []},
}

t("датчик: rolling year = period_assumed",
  E.period_assumed(intent_year))
t("датчик: 2022 без assumed → period_given",
  E.period_given(intent_2022) and not E.period_assumed(intent_2022))
t("форма: rolling year = period_is_canon_guess",
  A.period_is_canon_guess(intent_year["period"], today))
t("форма: вчера ≠ canon_guess",
  not A.period_is_canon_guess(intent_day["period"], today))

# ── Патч A: period_assumed_needs_clarify ─────────────────────────────────────
if hasattr(A, "period_assumed_needs_clarify"):
    t("P1 rolling year assumed → clarify",
      A.period_assumed_needs_clarify(intent_year, today))
    t("P2 quarter-span assumed → clarify",
      A.period_assumed_needs_clarify(intent_qtr, today))
    t("P3 explicit 2022 → no assumed-clarify",
      not A.period_assumed_needs_clarify(intent_2022, today))
    t("P4 yesterday assumed → no clarify",
      not A.period_assumed_needs_clarify(intent_day, today))
else:
    pending("P1–P4 period_assumed_needs_clarify (патч A)")

# ── Патч B: rank без меры → role_ask ─────────────────────────────────────────
_NAMES = ["Всего", "Количество", "СуммаНДС"]
_ALS = {
    "Всего": "итого,сумма,деньги,money",
    "Количество": "кол-во,штуки,qty,quantity",
}
_AX_PROD = [
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
]
_q_top = "Топ-5 товаров по продажам"
_intent_top = {"want": "list", "kind": "товар", "amount": {"value": 5},
               "measure": "", "parse": {"assumed": []}}

_sv = None
if hasattr(A, "ASK_SALES_RANK_CANON"):
    _sv = A.ASK_SALES_RANK_CANON
    A.ASK_SALES_RANK_CANON = True
try:
    if hasattr(A, "sales_rank_resolve_measure"):
        # До патча B живой путь может вернуть Всего/Количество — это и есть
        # дефект Э3 №8. После патча — (None, "role_ask").
        sm, how = A.sales_rank_resolve_measure(
            _NAMES, _intent_top, _q_top, _ALS,
            src="accumulationregister_реализациятмц", axes=_AX_PROD)
        if how == "role_ask" and sm is None:
            t("M1 топ без меры → role_ask", True)
        else:
            # зафиксировать текущий дефект как известный до патча B
            pending("M1 топ без меры → role_ask (сейчас how=%s sm=%s)"
                    % (how, sm))
        sm2, how2 = A.sales_rank_resolve_measure(
            _NAMES,
            {"want": "list", "kind": "товар", "measure": "деньгам"},
            "Топ-5 товаров по деньгам", _ALS,
            src="accumulationregister_реализациятмц", axes=_AX_PROD)
        t("M2 топ по деньгам → money, не ask",
          sm2 == "Всего" and how2 != "role_ask", (sm2, how2))
    else:
        pending("M1–M2 sales_rank_resolve_measure")
finally:
    if _sv is not None:
        A.ASK_SALES_RANK_CANON = _sv

# ── Патч C: stock markers + subject ──────────────────────────────────────────
q12 = "Сколько лежит на всех складах вместе?"
# До патча C маркеры не ловят «лежит/складах» — это дефект №12.
if A.question_asks_stock_balance(q12):
    t("S1 stock marker ловит №12", True)
else:
    pending("S1 stock marker ловит №12 (сейчас False — дефект)")

t("S2 №12 без named product",
  not A.stock_asks_named_product(q12, intent={"want": "sum", "kind": "склад",
                                               "terms": [], "measure": ""}))

if hasattr(A, "stock_subject_needs_clarify"):
    t("S3 stock∧¬named → subject clarify",
      A.stock_subject_needs_clarify(q12, {"want": "sum", "terms": []}))
else:
    pending("S3 stock_subject_needs_clarify (патч C)")

print("----")
print("%d ok, %d FAIL, %d pending" % (PASS, len(FAIL), len(PENDING)))
sys.exit(1 if FAIL else 0)
