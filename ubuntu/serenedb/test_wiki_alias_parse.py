#!/usr/bin/env python3
"""Оффлайн-проба разбора словаря величин: БЕЗ базы, БЕЗ сети, БЕЗ модели.

Имена выдуманы: проба не знает ни одной настоящей базы. Держит два инварианта,
без которых словарь величин врёт с первого такта:

  * имя поля, которого не было во входе, в таблицу не попадает;
  * пустой алиас — не ответ (это попытка, её пишет осечка пачки, а не разбор).
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

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
