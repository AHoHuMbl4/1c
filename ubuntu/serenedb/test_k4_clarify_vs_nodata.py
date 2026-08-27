#!/usr/bin/env python3
"""K4-2 / K5: уточнение вместо честного no_data (Э3 okna №6,14,17,18).

Оффлайн. Источник: docs/K4_CLARIFY_VS_NODATA.md §5.
Запуск: python3 ubuntu/serenedb/test_k4_clarify_vs_nodata.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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


# ── Место A: unmatched terms → сигнал отказа ─────────────────────────────────
# matched_group_count / ветка answer проверяются через контракт хелпера:
# при n_groups>0 и matched < n — это дыра (раньше только matched==0).
t("A: matched_group_count пустых kinds = 0",
  A.matched_group_count({}) == 0)
t("A: одна группа matched (ключ-int из probe)",
  A.matched_group_count({0: "literal"}) == 1)

# ── Страж B: src_supports_question ───────────────────────────────────────────
t("B1: terms непустые → support",
  A.src_supports_question(
      "document_x", {"terms": [["ПАНГЕЯ"]]}, {}, by={}))
t("B2: пустые terms + period-fill + чужой src → нет support",
  not A.src_supports_question(
      "informationregister_курсывалют",
      {"terms": [], "kind": ""},
      {"by_period_fill": True},
      by={"informationregister_курсывалют": 10},
      question="Кто сейчас президент России?"))
t("B3: пустые terms + by_meaning hit → support",
  A.src_supports_question(
      "document_реализация",
      {"terms": [], "kind": "продажи"},
      {"by_meaning": ["document_реализация"]},
      by={},
      question="сколько продали?"))
t("B4: sales_canon_locked → support",
  A.src_supports_question(
      "accumulationregister_x",
      {"terms": []},
      {"sales_canon_locked": "accumulationregister_x"},
      by={}))
t("B5: src в буквальном by без fill → support",
  A.src_supports_question(
      "document_заказы",
      {"terms": []},
      {},
      by={"document_заказы": 3},
      question="заказы"))
t("B6: by_vector без meaning → нет support",
  not A.src_supports_question(
      "informationregister_курсывалют",
      {"terms": []},
      {"by_vector": True},
      by={"informationregister_курсывалют": 1},
      question="Кто сейчас президент России?"))

# Контроль: честная неоднозначность меры на поддержанном src — не режется стражем
t("B-ctrl: support на живом by → clarify мер допустим",
  A.src_supports_question(
      "document_реализациятмц",
      {"terms": [], "want": "sum", "kind": "продажи"},
      {},
      by={"document_реализациятмц": 6},
      question="Сколько мы закупили товаров?"))

# measure_class_alts: money|qty вместо полного nums
_ma = A.measure_class_alts(
    ["Всего", "Количество", "СуммаНДС"],
    {"Всего": "итого,деньги", "Количество": "кол-во,штуки"})
t("class: money|qty → 2 alts",
  _ma[0] is None and len(_ma[1]) == 2
  and "Всего" in _ma[1] and "Количество" in _ma[1], _ma)
t("class: только money → пусто",
  A.measure_class_alts(["Всего", "СуммаНДС"],
                       {"Всего": "деньги"})[1] == [])

print("----")
print("%d ok, %d FAIL" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
