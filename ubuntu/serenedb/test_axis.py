#!/usr/bin/env python3
"""Ось группы: зерно row|parent|group, сравнение ≠ AND. Без базы и сети."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_axis as X  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


AX_NOM = [{"col": "Номенклатура", "target_src": "catalog_номенклатура"}]
AX_TWO = AX_NOM + [{"col": "Склад", "target_src": "catalog_склады"}]

# Две terms-группы на одной оси → compare, не AND
col, gis = X.groups_on_same_axis({0: ["Номенклатура"], 1: ["Номенклатура"]})
t("две группы на одной оси — колонка оси", col == "Номенклатура" and gis == [0, 1])
owners = {0: ["catalog_номенклатура"], 1: ["catalog_номенклатура"]}
merged, sets = X.merge_compare_term_groups(
    [["Piesa HG VEKA"], ["Stift"]], owners)
t("сравнение схлопывает AND в одну группу",
  len(merged) == 1 and len(merged[0]) == 2 and sets == [[0, 1]])
dec = X.decide_grain(AX_NOM, [], {0: ["Номенклатура"], 1: ["Номенклатура"]},
                     "max", True)
t("две terms-группы на оси → grain=group form=compare",
  dec["grain"] == "group" and dec["form"] == "compare" and dec["clarify"] is None)

# Разные оси → не compare (AND измерений остаётся вызывающему)
dec = X.decide_grain(AX_TWO, [], {0: ["Номенклатура"], 1: ["Склад"]}, "sum", True)
t("группы на разных осях — не сравнение", dec["form"] != "compare")

# kind → target_src → group
dec = X.decide_grain(AX_TWO, ["Номенклатура"], {}, "max", True)
t("kind попал в одну ось → grain=group rank",
  dec["grain"] == "group" and dec["form"] == "rank" and dec["col"] == "Номенклатура")

# focus обнуляет compute; want=list держит kind (реранкер снаружи)
dec = X.decide_grain(AX_TWO, ["Номенклатура"], {}, None, True)
t("kind без compute (focus) → group rank",
  dec["grain"] == "group" and dec["form"] == "rank" and dec["col"] == "Номенклатура")

# Нет оси + max + не child → row, не рейтинг по сырым строкам
dec = X.decide_grain([], [], {}, "max", False)
t("нет оси и не child + max → grain=row",
  dec["grain"] == "row" and dec["form"] == "number" and dec["clarify"] is None)

# Шапка + max → row (parent-вперёд: самая крупная продажа — документ)
dec = X.decide_grain(AX_NOM, [], {}, "max", False)
t("шапка + max → row, не group", dec["grain"] == "row")

# Child + 1 ось + max → rank
dec = X.decide_grain(AX_NOM, [], {}, "max", True)
t("child + одна ось + max → rank",
  dec["grain"] == "group" and dec["form"] == "rank")

# Child + 2 оси + max + kind не снял → уточнить ось
dec = X.decide_grain(AX_TWO, [], {}, "max", True)
t("child + две оси + max без kind → clarify axis",
  dec["clarify"] == "axis" and dec["grain"] == "row")

# Несколько kind-осей → clarify
dec = X.decide_grain(AX_TWO, ["Номенклатура", "Склад"], {}, "max", True)
t("kind попал в две оси → clarify", dec["clarify"] == "axis")

# Контроль want=sum без kind → row
dec = X.decide_grain(AX_TWO, [], {}, "sum", True)
t("sum без kind и без двух имён → row", dec["grain"] == "row")

# Focus назвал ось: kind_hits = col оси, даже при want=sum — group, не row
dec = X.decide_grain(AX_NOM, ["Номенклатура"], {}, "sum", True)
t("ось из kind + sum → group (focus был осью)",
  dec["grain"] == "group" and dec["col"] == "Номенклатура" and dec["form"] == "rank")

# amount без порога / list при нескольких осях без kind — не рейтинг сырых строк
dec = X.decide_grain(AX_TWO, [], {}, None, True, rank_intent=True)
t("rank_intent + две оси без kind → clarify, не row-рейтинг",
  dec["clarify"] == "axis" and dec["grain"] == "row")

t("K: amount без op = 5",
  X.rank_k({"op": None, "value": 5}, "max", 0, 25) == 5)
t("K: amount с op не есть K",
  X.rank_k({"op": ">", "value": 5}, "max", 0, 25) == 1)
t("K: max без имён → 1", X.rank_k({}, "max", 0, 25) == 1)
t("K: два члена → ровно 2", X.rank_k({}, "max", 2, 25) == 2)
t("K: amount 100 сверх cap → cap при max даёт 1 (имена 0)",
  X.rank_k({"value": 100}, "max", 0, 25) == 1)
t("K: amount 5 при rank без max",
  X.rank_k({"value": 5}, "sum", 0, 25) == 5)

# Focus = target_src оси, не источник
t("count без величины движений → каталог",
  X.catalog_self_question("count", False, False, True))
t("list без величины движений → каталог",
  X.catalog_self_question("list", False, False, True))
t("sum — не счёт позиций каталога",
  not X.catalog_self_question("sum", True, False, True))
t("мера каталога есть, у держателей пусто → каталог",
  X.catalog_self_question("sum", True, True, False))
t("мера на держателях живая → не каталог",
  not X.catalog_self_question("sum", True, False, True))

t("want=sum → величина движений",
  X.asks_movement_magnitude("sum"))
t("слово меры на держателе → величина движений",
  X.asks_movement_magnitude("list", "сумма", {}, True, False))
t("топ-N amount без op → величина движений",
  X.asks_movement_magnitude("list", "", {"value": 5}, False, False))
t("чип «топ-5»: слово не поле каталога → движения",
  X.asks_movement_magnitude("list", "топ-5", {}, False, False))
t("count без слова меры → не движения",
  not X.asks_movement_magnitude("count", "", {}, False, False))
t("порог amount с op — не рейтинг",
  not X.asks_movement_magnitude("list", "", {"op": ">", "value": 5}, False, False))

t("не ось → keep",
  X.decide_axis_focus(False, False, ["document_x"]) == ("keep", None))
t("вопрос про каталог → keep",
  X.decide_axis_focus(True, True, ["document_x"]) == ("keep", None))
t("один держатель → holder",
  X.decide_axis_focus(True, False, ["document_строки"]) == ("holder", "document_строки"))
t("два держателя → clarify, не no_data",
  X.decide_axis_focus(True, False, ["document_a", "document_b"])
  == ("clarify", ["document_a", "document_b"]))
t("держателей нет → keep (честный путь каталога)",
  X.decide_axis_focus(True, False, []) == ("keep", None))

print("\nИТОГ: ok %d, FAIL %d" % (PASS, len(FAIL)))
if FAIL:
    print("ПРОВАЛЕНО: %s" % "; ".join(FAIL))
    raise SystemExit(1)
