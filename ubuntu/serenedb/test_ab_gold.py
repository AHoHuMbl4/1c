#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Замки золотого набора okna: разбор строк, клик по развилке, проверки классов.

Ни базы, ни сервиса тут нет: проверяется только разбор набора и правила годности.
Отбор сущностей и величин генератором проверяется на живой базе прогоном
`work/acceptance/okna-gold-build.sh` — здесь ловится порча правил.

Запуск: python3 ubuntu/serenedb/test_ab_gold.py
"""
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append("%s%s" % (name, (" — " + detail) if detail else ""))


GOLD_SAMPLE = """# заголовок
# класс 1
Сколько всего по «Реализация ТМЦ» за вчера?\tSELECT 1\tCLS=1 итог периода PICK=src:accumulationregister_р|measure:Всего
# класс 8
Какие сейчас остатки?\tMODE=kind\tCLS=8 остатки: no_data
# класс 6
Сколько было «Реализация ТМЦ» за 2026-07?\tMODE=fork\tCLS=6 вилка
# класс 7
Какой итог по величине «Сумма»?\tMODE=pivot\tCLS=7 пустышка PICK=src:accumulationregister_р
"""


def load(gold_text):
    path = os.path.join(tempfile.mkdtemp(), "gold.tsv")
    open(path, "w", encoding="utf-8").write(gold_text)
    os.environ["AB_CONTOUR"] = "okna"
    os.environ["AB_GOLD_FILE"] = path
    spec = importlib.util.spec_from_file_location(
        "ab_scorer_under_test", os.path.join(HERE, "ab_scorer.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = load(GOLD_SAMPLE)
G = M.GOLD

# --- разбор строк набора
t("строк набора 4", len(G) == 4, str(len(G)))
t("режимы разобраны", [r["mode"] for r in G] == ["sql", "kind", "fork", "pivot"],
  str([r["mode"] for r in G]))
t("класс разобран", G[0]["cls"] == "1 итог периода", G[0]["cls"])
t("клики разобраны", G[0]["picks"] == ["src:accumulationregister_р", "measure:Всего"],
  str(G[0]["picks"]))
t("у kind кликов нет", G[1]["picks"] == [], str(G[1]["picks"]))
t("комментарии пропущены", all(not r["q"].startswith("#") for r in G))

# --- клик по развилке: билет берётся по тому, что база знает о себе сама
FORK = {"kind": "clarify", "text": "1. … 2. …", "options": [
    {"src": "accumulationregister_реализациятмц", "label": "Движения реализации",
     "distinct_by": "", "decision_id": "T1"},
    {"src": "document_реализациятмц", "label": "Реализация ТМЦ с оплатой",
     "distinct_by": "", "decision_id": "T2"}]}
did, pick, rest = M.pick_option(FORK, ["src:accumulationregister_реализациятмц",
                                       "measure:Всего"])
t("клик по сущности", did == "T1", str(did))
t("остаток кликов", rest == ["measure:Всего"], str(rest))
t("клик по чужой сущности не проходит", M.pick_option(FORK, ["src:catalog_нет"])[0] is None)

MEASURES = {"kind": "clarify", "options": [
    {"src": "x", "label": "Сумма Без НДС", "distinct_by": "", "decision_id": "M1"},
    {"src": "x", "label": "Всего", "distinct_by": "", "decision_id": "M2"}]}
t("подпись величины = имя поля с пробелами",
  M.pick_option(MEASURES, ["measure:СуммаБезНДС"])[0] == "M1")
t("величина по точному имени", M.pick_option(MEASURES, ["measure:Всего"])[0] == "M2")

AXES = {"kind": "clarify", "options": [
    {"src": "x", "label": "Номенклатура", "distinct_by": "ТМЦ", "decision_id": "A1"},
    {"src": "x", "label": "Контрагенты", "distinct_by": "Контрагент", "decision_id": "A2"}]}
t("клик по оси", M.pick_option(AXES, ["axis:Контрагент"])[0] == "A2")

t("вариант без билета не кликается",
  M.pick_option({"kind": "clarify", "options": [{"src": "s", "label": "л"}]},
                ["src:s"])[0] is None)
t("развилка видна", M.clickable(FORK) and not M.clickable({"kind": "answer", "options": []}))

# --- класс 6: вилка спрошена, подписи человеческие
ok, why = M.fork_row_ok(FORK)
t("вилка годна", ok, why)
t("ответ вместо вилки — брак", not M.fork_row_ok({"kind": "answer", "text": "5"})[0])
t("одна ветка — брак", not M.fork_row_ok(
    {"kind": "clarify", "options": [{"label": "одна"}]})[0])
t("внутреннее имя в подписи — брак", not M.fork_row_ok(
    {"kind": "clarify", "text": "", "options": [{"label": "accumulationregister_x"},
                                                {"label": "Человеческая"}]})[0])
t("пустая подпись — брак", not M.fork_row_ok(
    {"kind": "clarify", "text": "", "options": [{"label": ""}, {"label": "Человеческая"}]})[0])

# --- класс 7: пустышку не выдают за «0»
t("«0» как ответ — брак", not M.pivot_row_ok(
    {"kind": "answer", "text": "Итог: 0", "atom": {"exact_value": 0}})[0])
t("ноль в claims — брак", not M.pivot_row_ok(
    {"kind": "answer", "text": "итог посчитан", "diag": {"claims": {"sum": 0}}})[0])
t("отказ при данных — брак", not M.pivot_row_ok({"kind": "no_data", "text": "нет данных"})[0])
t("пивот на живую величину годен", M.pivot_row_ok(
    {"kind": "figures", "text": "Всего: 80 300 612,08",
     "atoms": [{"exact_value": 80300612.08}]})[0])
t("перечень величин годен", M.pivot_row_ok(
    {"kind": "clarify", "text": "какую величину считать",
     "options": [{"label": "Всего"}, {"label": "Себестоимость"}]})[0])

# --- класс 8: no_data без чисел итогов
t("no_data годен", M.check_row({"mode": "kind", "want": None},
                               {"kind": "no_data", "text": "Данных об остатках нет"})[0])
t("no_data с итогом — брак", M.check_row(
    {"mode": "kind", "want": None},
    {"kind": "no_data", "text": "Данных нет, но всего 80 300 612,08"})[0] is False)
t("число вместо no_data — брак", M.check_row(
    {"mode": "kind", "want": None}, {"kind": "answer", "text": "1 234"})[0] is False)

# --- числовые классы: сверка по цифрам, разрядка не мешает
t("число с разрядкой сходится",
  M.check_row({"mode": "sql", "want": "2767450.98"},
              {"text": "итог 2 767 450,98 леев"})[0])
t("число из claims сходится",
  M.check_row({"mode": "sql", "want": "349"},
              {"text": "нет числа", "diag": {"claims": {"count": 349}}})[0])
t("чужое число — брак",
  M.check_row({"mode": "sql", "want": "349"}, {"text": "8 008"})[0] is False)

print("ok %d, брак %d" % (PASS, len(FAIL)))
for f in FAIL:
    print("  ✗ %s" % f)
sys.exit(1 if FAIL else 0)
