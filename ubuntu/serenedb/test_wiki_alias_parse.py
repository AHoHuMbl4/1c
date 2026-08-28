#!/usr/bin/env python3
"""Оффлайн-проба разбора словаря: БЕЗ базы, БЕЗ сети, БЕЗ модели.

Имена выдуманы: проба не знает ни одной настоящей базы. Держит инварианты,
без которых словарь врёт с первого такта:

  * имя поля, которого не было во входе, в таблицу величин не попадает;
  * пустой алиас — не ответ (это попытка, её пишет осечка пачки, а не разбор);
  * обиходные слова из ответа модели доходят до aliases сущности;
  * имена величин и их алиасы из ответа в aliases сущности не пишутся.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wiki_alias_parse as P  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


PAY = [{"entity": "document_отгрузкапробная", "title": "Отгрузка Пробная",
        "quantities": "ИтогПробный, СуммаКартойПробная, Курс"}]

TEXT = """
{"items":[{
  "entity":"document_отгрузкапробная",
  "aliases":["отгрузка пробная","продажа"],
  "quantities":[
    {"name":"ИтогПробный","aliases":["оборот","сумма продаж","итог"]},
    {"name":"суммакартойпробная","aliases":["оплата картой","карта"]},
    {"name":"ВыдуманноеПоле","aliases":["секретный итог"]},
    {"name":"Курс","aliases":[]}
  ],
  "bestUsedFor":["сколько отгрузили"],
  "notEnoughFor":["книга продаж"]
}]}
"""

ents, meas = P.parse_items(TEXT, PAY)
by = {(r["src_table"], r["measure"]): r["aliases"] for r in meas}

t("сущность разобрана", len(ents) == 1 and ents[0]["src_table"] == "document_отгрузкапробная")
t("каноническое имя величины сохранено дословно",
  by.get(("document_отгрузкапробная", "ИтогПробный")) == "оборот, сумма продаж, итог")
t("имя в другом регистре сводится к канону из входа, а не пишется как выдумала модель",
  by.get(("document_отгрузкапробная", "СуммаКартойПробная")) == "оплата картой, карта"
  and "суммакартойпробная" not in {r["measure"] for r in meas})
t("🔴 выдуманное имя величины отброшено",
  not any(r["measure"] == "ВыдуманноеПоле" for r in meas), meas)
t("пустой алиас — не ответ, в таблицу не идёт (Курс без слов)",
  "Курс" not in {r["measure"] for r in meas}, meas)
t("во входе три поля, в словарь попали только два описанных",
  len(meas) == 2, meas)

ents2, meas2 = P.parse_items("not json at all", PAY)
t("неразбираемый ответ — пустые списки, а не исключение",
  ents2 == [] and meas2 == [])

t("канон: точное имя из списка",
  P.canon_measure("ИтогПробный", ["ИтогПробный", "Курс"]) == "ИтогПробный")
t("канон: выдумка — None",
  P.canon_measure("Секрет", ["ИтогПробный"]) is None)

# ── обиходные слова сущности vs мусор величин (дефект словаря 25.08) ──────────
# Паттерн живого срыва: модель клала title + склонения + имена реквизитов в
# aliases, а обиход («покупатель») либо не просила, либо теряла. Здесь — выдуманная
# сущность; слова не из боевой базы.
PAY_H = [{"entity": "catalog_партнёрыпробные", "title": "Партнёры Пробные",
          "quantities": "ДниОтсрочкиПробные, ЛимитКредитаПробный"}]

TEXT_H = """
{"items":[{
  "entity":"catalog_партнёрыпробные",
  "aliases":["Партнёры Пробные","партнёр пробный","покупатель","клиент пробный",
             "ДниОтсрочкиПробные","дни отсрочки пробные","лимит кредита"],
  "quantities":[
    {"name":"ДниОтсрочкиПробные","aliases":["дни отсрочки пробные","отсрочка"]},
    {"name":"ЛимитКредитаПробный","aliases":["лимит кредита","кредитный лимит"]}
  ],
  "bestUsedFor":["кто покупает"],
  "notEnoughFor":["другой каталог"]
}]}
"""

ents_h, meas_h = P.parse_items(TEXT_H, PAY_H)
alias_csv = (ents_h[0]["aliases"] if ents_h else "") or ""
alias_set = {a.strip().casefold() for a in alias_csv.split(",") if a.strip()}

t("обиходное слово из ответа доходит до aliases сущности",
  "покупатель" in alias_set and "клиент пробный" in alias_set, alias_csv)
t("title сущности в aliases сохраняется",
  "партнёры пробные" in alias_set, alias_csv)
t("🔴 имя величины из входа не пишется в aliases сущности",
  "дниотсрочкипробные" not in alias_set, alias_csv)
t("🔴 алиас величины из ответа не пишется в aliases сущности",
  "дни отсрочки пробные" not in alias_set
  and "лимит кредита" not in alias_set
  and "кредитный лимит" not in alias_set, alias_csv)
t("величины при этом получили свои обиходные слова",
  len(meas_h) == 2
  and any("отсрочка" in (r["aliases"] or "") for r in meas_h)
  and any("кредитный лимит" in (r["aliases"] or "") for r in meas_h), meas_h)

got = P.filter_entity_aliases(
    ["Title", "human word", "FieldName", "field nickname"],
    quantity_names=["FieldName"],
    quantity_aliases=["field nickname"])
t("filter_entity_aliases: обиход остаётся, мусор величин уходит",
  got == ["Title", "human word"], got)
t("filter_entity_aliases: пустой ответ — пустой список",
  P.filter_entity_aliases([], quantity_names=["X"]) == [])
t("filter_entity_aliases: дубликаты схлопываются без учёта регистра",
  P.filter_entity_aliases(["Alpha", "alpha", "Beta"]) == ["Alpha", "Beta"])

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)

# ── обрезанный ответ (лимит токенов вызова; живой случай окна 28.08) ────────
TEXT_TRUNC = """{
  "items": [
    {"entity":"catalog_пробный","aliases":["Пробный","проба"],
     "quantities":[],"bestUsedFor":["t"],"notEnoughFor":["n"]},
    {"entity":"catalog_второй","aliases":["Второй","вт","обре
"""
ents_t, _ = P.parse_items(TEXT_TRUNC, {"items": []})
t("🔴 обрезанный JSON: целые элементы спасаются, а не теряются пачкой",
  len(ents_t) == 1 and ents_t[0]["src_table"] == "catalog_пробный", ents_t)
t("salvage: пустой/без items — пусто, не исключение",
  P._salvage_items("{}") == [] and P._salvage_items("xx") == [])
