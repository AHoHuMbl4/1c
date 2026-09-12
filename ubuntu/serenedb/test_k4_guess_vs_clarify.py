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

# ── Патч A: assumed-period clarify ДО вики снесён (негатив) ──────────────────
# До wiki_primary_entity_cascade — ни одного period-clarify; хелпер может жить
# как библиотека, но для sales/assumed-года не форсирует pre-wiki clarify.
_Z20_NEW = os.path.join(os.path.dirname(__file__), "ask", "z20_ask_main_http.py")
_z20_new = open(_Z20_NEW, encoding="utf-8").read() if os.path.isfile(_Z20_NEW) else ""
_wiki_pos = _z20_new.find("wiki_primary_entity_cascade")
_pre_wiki = _z20_new[:_wiki_pos] if _wiki_pos >= 0 else _z20_new
t("P0: до wiki_primary в новом z20 нет period_assumed_needs_clarify",
  "period_assumed_needs_clarify" not in _pre_wiki
  and "wiki_primary_entity_cascade" in _z20_new)
if hasattr(A, "period_assumed_needs_clarify"):
    t("P1 rolling year assumed → НЕ clarify до вики (снесён)",
      not A.period_assumed_needs_clarify(intent_year, today))
    t("P2 quarter-span assumed → НЕ clarify до вики (снесён)",
      not A.period_assumed_needs_clarify(intent_qtr, today))
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

# В3: sales_rank_resolve_measure / money-канон снесены — авто-мера запрещена.
t("sales_rank_resolve_measure GONE (В3)",
  not hasattr(A, "sales_rank_resolve_measure"))
# measure_class_alts при money+qty → меню (не silent money)
if hasattr(A, "measure_class_alts"):
    _mc, _ma = A.measure_class_alts(_NAMES, _ALS)
    t("M1 топ без меры → class alts меню (2)",
      _mc is None and len(_ma) == 2, (_mc, _ma))
    t("M2 class alts = money|qty представители",
      set(_ma) == {"Всего", "Количество"}, _ma)
else:
    pending("M1–M2 measure_class_alts")
# pick_measure / unresolved: >1 → ask, не winner
_old_mof = getattr(A, "measures_of", None)
_old_als = getattr(A, "measure_aliases_of", None)
A.measures_of = lambda src: list(_NAMES)
A.measure_aliases_of = lambda src: dict(_ALS)
try:
    got, alts, how = A.pick_measure("src_x", _q_top, "")
    t("M3 pick_measure без слова → не silent winner при >1",
      (got is None and len(alts or []) > 1) or how in ("none", "ask"),
      (got, alts, how))
    um, ua = A.unresolved_quantity(None, [], "sum", "sum", _NAMES,
                                   {"Всего": 10, "Количество": 3, "СуммаНДС": 1})
    t("M4 unresolved >1 → меню (не names[0])",
      um is None and len(ua) > 1, (um, ua))
finally:
    if _old_mof is not None:
        A.measures_of = _old_mof
    if _old_als is not None:
        A.measure_aliases_of = _old_als

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

# Склад-clarify ДО вики снесён: subject не спрашивается pre-wiki
t("P0b: до wiki_primary в новом z20 нет warehouse/stock_subject clarify",
  "warehouse_clarify(" not in _pre_wiki
  and "stock_subject_needs_clarify(" not in _pre_wiki)
if hasattr(A, "stock_subject_needs_clarify"):
    t("S3 stock∧¬named → НЕ subject clarify до вики (снесён)",
      not A.stock_subject_needs_clarify(q12, {"want": "sum", "terms": []}))
else:
    pending("S3 stock_subject_needs_clarify (патч C)")

print("----")
print("%d ok, %d FAIL, %d pending" % (PASS, len(FAIL), len(PENDING)))
sys.exit(1 if FAIL else 0)
