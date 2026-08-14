#!/usr/bin/env python3
"""Оффлайн-прогон ШАГА 6 «формулировка»: БЕЗ базы, БЕЗ сети, БЕЗ вызовов модели.

Парный `test_gate.py`. Тот проверяет шаг 7 (гейт исходящего) — сорок с лишним случаев;
у шага 6 (`compose`, `_split_answer`, `_fill_figures`, `_ask_back`) не было ни одного.
А это шаг, на котором решается, дойдёт ли посчитанное базой число до человека и в каком
виде: подстановка чисел кодом, разбор обёртки модели, оговорки о неполноте и об
отброшенном, вторая попытка. Правки здесь доказывались только приёмкой через модель —
платно и с разбросом ±1-3 ошибки на десять вопросов, то есть не доказывались вовсе.

Изъяны, которые проба ловит (мерило дня — число ошибок, цель ноль):
  • неверное или несуществующее число в тексте;
  • ПОСЧИТАННОЕ число не дошло до человека (тихо пропало, заменилось пустотой);
  • служебное — обёртка модели, незаполненное место `{total}`, кусок нашей инструкции —
    видно клиенту;
  • молчаливая потеря: показано подмножество, а сказано как про всё (п. 13).

Запуск:  python3 ubuntu/serenedb/test_compose.py

Импорт `serene_ask` к базе не ходит: на уровне модуля только чтение окружения.
`compose` единственная зовёт модель — здесь она подменяется и проверяется ТЕЛО запроса,
то есть ровно то, что модель видит.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402

PASS = 0
FAIL = []


def t(name, cond):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name)


NBSP = " "

# Счёт по всему множеству в том виде, в каком его отдаёт `aggregate`.
AGG = {"count": 249, "count_amount": 249, "sum": 73181157.68, "min": 152800.0,
       "max": 1629700.0, "avg": 293900.23, "date_min": "2019-01-09",
       "date_max": "2019-11-18", "src": "entity_x",
       "measure": "ВеличинаА", "folders": 0}
# Итоги по каждой величине с именами из базы — их модель адресует как {total:ИМЯ}.
TOTALS = [("ВеличинаА", 73181157.68, 1629700.0, 152800.0),
          ("ВеличинаБ", 73181157.68, 1629700.0, 152800.0),
          ("Штуки", 92683.0, 1200.0, 1.0)]


def row(amount="", when="", doc=""):
    return ["", "", amount, when, "", doc]


# ------------------------------------------------- разбор обёртки модели (_split_answer)
t("чистый JSON: текст достаётся, служебное не уходит",
  A._split_answer('{"text": "Итого на {total} руб.", "ask": null, "claims": {}}')[0]
  == "Итого на {total} руб.")
t("JSON в пояснении и в ограде — текст всё равно достаётся",
  A._split_answer('Вот ответ:\n```json\n{"text": "Найдено {count} документов", '
                  '"ask": null, "claims": {}}\n```')[0] == "Найдено {count} документов")
t("простая проза без обёртки отдаётся как есть",
  A._split_answer("Таких данных нет.")[0] == "Таких данных нет.")
# [замер 27.07] сюда уходило `{"text":":"В предоставленных данных нет информации…`
t("поломанная обёртка: наружу идёт текст, а не сырая строка со скобками",
  "{" not in A._split_answer('{"text":":"В предоставленных данных нет информации')[0])
t("обёртка без поля text не даёт выдумать ответ",
  A._split_answer('{"answer": "Итого на 5000"}')[0] == "")
# Модель упёрлась в max_tokens — ответ оборван на полуслове, обёртка не закрыта.
t("оборванный ответ модели не отдаёт клиенту служебную строку",
  "{" not in A._split_answer('{"text": "Итого на {total} руб., крупнейшая пост')[0])

# ------------------------------------------------- уточняющий вопрос (_ask_back)
t("уточнение достаётся из обёртки",
  A._ask_back('{"text": "…", "ask": "Вас интересуют закупки или продажи?", "claims": {}}')
  == "Вас интересуют закупки или продажи?")
t("уточнения нет — пусто, а не мусор",
  A._ask_back('{"text": "…", "ask": null, "claims": {}}') == "")

# ------------------------------------------------- подстановка чисел (_fill_figures)
# 🔴 Числа ставит КОД. Модель их физически не пишет, поэтому неверное число невозможно,
# а не «отлавливается».
txt, bad = A._fill_figures("Итого на {total} руб. по {count} документам.",
                           AGG, TOTALS)
t("итог подставлен кодом и разряды разделены НЕРАЗРЫВНЫМ пробелом",
  "73" + NBSP + "181" + NBSP + "157.68" in txt and not bad)
t("счёт записей подставлен",
  "249" in txt)
txt2, bad2 = A._fill_figures("Всего {total:Штуки} штук.", AGG, TOTALS)
t("величина по имени: {total:ИМЯ} берётся из итогов по именам",
  "92" + NBSP + "683" in txt2 and not bad2)
t("имя, которого нет, — отказ формулировки, а не тихая пустота",
  A._fill_figures("Итого {total:Выдуманная}.", AGG, TOTALS)[1])
t("в отказе названы ДОСТУПНЫЕ имена — второй попытке есть чем заменить",
  "есть:" in " ".join(A._fill_figures("Итого {itogo}.", AGG, TOTALS)[1]))
# Роль — наше служебное слово, оно всегда латиницей. Место, названное словом вопроса,
# подставить нечем, и ловит его не подстановка, а проверка готового текста.
t("место, названное по-русски, ловится проверкой формулировки",
  A.formulation_flaws(*A._fill_figures("Итого {Итого}.", AGG, TOTALS)))
# [замер 28.07] «Общая сумма поступлений — 0 руб.» при настоящих 2 088 800.
t("величина не выбрана — безымянное место НЕ заполняется нулём",
  A._fill_figures("Сумма {total}.", dict(AGG, sum=0.0), TOTALS, has_measure=False)[1])
t("но счёт записей без выбранной величины подставляется",
  "249" in A._fill_figures("Записей {count}.", AGG, TOTALS, has_measure=False)[0])
t("отрицательное число не теряет знак и группируется",
  A._fill_figures("{total}", dict(AGG, sum=-1234567.0), TOTALS)[0]
  == "-1" + NBSP + "234" + NBSP + "567")
t("границы периода подставляются датами",
  A._fill_figures("с {date_min} по {date_max}", AGG, TOTALS)[0]
  == "с 2019-01-09 по 2019-11-18")

# 🔴 Место, которое НЕ РАСПОЗНАНО, обязано быть отказом формулировки. Иначе оно уходит
# человеку буквально: «Итого на {Total} руб.» — ни числа, ни ошибки.
t("место в другом регистре не уезжает клиенту буквально",
  "{" not in A._fill_figures("Итого на {Total} руб.", AGG, TOTALS)[0]
  or A._fill_figures("Итого на {Total} руб.", AGG, TOTALS)[1])
t("место с пробелами внутри не уезжает клиенту буквально",
  "{" not in A._fill_figures("Итого на { total } руб.", AGG, TOTALS)[0]
  or A._fill_figures("Итого на { total } руб.", AGG, TOTALS)[1])
t("имя величины в другом регистре не роняет верный ответ",
  not A._fill_figures("Итого {total:штуки}.", AGG, TOTALS)[1])
# У сущности может не быть ни одной даты: `aggregate` отдаёт пустую строку, а не None.
t("пустая дата — отказ, а не дыра в тексте («данные за  ..»)",
  A._fill_figures("Данные за {date_min}.", dict(AGG, date_min="", date_max=""),
                  TOTALS)[1])

# ------------------------------------------- посчитанное число, набранное моделью
# 🔴 [замер 04.08, step6_live.py] на восьми вопросах модель семь раз оставила место и
# один раз набрала 249 сама. Промт это запрещает словами — значит не запрещает.
HROWS = [row("152800.00", "2019-01-09", "Документ 0001 от 09.01.2019, Сторона А"),
         row("1629700.00", "2019-11-18", "Документ 0002 от 18.11.2019, Сторона Б")]
t("итог, набранный цифрами вместо места, — находка",
  A.copied_figures("Итого на 73 181 157.68 руб.", AGG, HROWS))
t("счёт записей, набранный цифрами вместо места, — находка",
  A.copied_figures("Всего 249 документов.", AGG, HROWS))
t("в находке названо место, которым это заменить",
  "{total}" in " ".join(A.copied_figures("Итого 73 181 157.68", AGG, HROWS)))
t("место под подстановку находкой НЕ является",
  not A.copied_figures("Итого на {total} руб. по {count} документам.", AGG, HROWS))
# Промт прямо разрешает копировать значения ИЗ СТРОКИ — и max по построению равен
# значению какой-то строки. Считать цитату рукописью значит объявить дефектом верное.
t("значение, взятое из показанной строки, — цитата, а не рукопись",
  not A.copied_figures("Самая крупная — 1 629 700 у Сторона Б.", AGG, HROWS))
t("номер документа и дата из строки — цитата",
  not A.copied_figures("Документ 0002 от 18.11.2019.", AGG, HROWS))
t("выдуманное число этой проверкой не ловится — это работа гейта",
  not A.copied_figures("Итого на 925 000 руб.", AGG, HROWS))
t("без посчитанного нечего и искать",
  not A.copied_figures("Всего 249 документов.", None, HROWS))

# ------------------------------------------------- что видит модель (compose)
SENT = {}


def _fake_chat(messages, temperature=0, max_tokens=900):
    SENT["sys"] = messages[0]["content"]
    SENT["body"] = messages[1]["content"]
    return '{"text": "ок", "ask": null, "claims": {}}'


A.ds_chat = _fake_chat
ROWS = [row("152800.00", "2019-01-09", "Документ 0001 от 09.01.2019"),
        row("1629700.00", "2019-11-18", "Документ 0002 от 18.11.2019")]

A.compose("на какую сумму учтено", ROWS, AGG, totals=TOTALS)
t("модель видит вопрос",
  "на какую сумму учтено" in SENT["body"])
# 🔴 ГЛАВНОЕ СВОЙСТВО ШАГА 6: списать посчитанное число неоткуда. Пока значения были в
# задании, модель их иногда списывала — [замер 04.08] 1 раз из 8, а на повторе 0 из 8, то
# есть неустойчиво; проверкой это не чинится (роль числа в прозе кодом не определяется),
# поэтому убран источник. Проверяется на ВСЕХ посчитанных значениях сразу, а не на одном.
# `min`/`max` в перечень не входят намеренно: они РАВНЫ значению какой-то строки, а
# строки модель видит и должна видеть — иначе не из чего цитировать. Проверяется то, что
# списать действительно неоткуда: итог, среднее, счёт и итоги по именам величин.
_VALUES = ["73181157.68", "73 181 157.68", "293900.23", "92683", "249"]
t("🔴 ни одного посчитанного ЗНАЧЕНИЯ в задании модели нет",
  not [v for v in _VALUES if v in SENT["body"]])
t("вместо значений модель видит МЕСТА под них",
  "{total}" in SENT["body"] and "{count}" in SENT["body"] and "{max}" in SENT["body"])
t("модель видит имя величины, по которой считали",
  "ВеличинаА" in SENT["body"])
t("итоги по именам величин адресуются по имени, тоже без значений",
  "{total:Штуки}" in SENT["body"])
t("внутреннее имя таблицы модели не показывается",
  "entity_x" not in SENT["body"])
# Значения СТРОК остаются: цитата из записи — не арифметика, а выписка, и она нужна.
t("значения строк модели по-прежнему видны — из них берутся цитаты",
  "amount=152800" in SENT["body"] and "2019-01-09" in SENT["body"])
# 🔴 Размер ВЫБОРКИ выдавался за размер множества: строки обрезаны по TOPK, а в задании
# стояло «ROWS FOUND (40)». [замер 04.08] ответ «есть только три документа приобретения»
# при 249 записях — ровно эта подмена (п. 13).
t("число показанных строк за число записей не выдаётся",
  "ROWS FOUND" not in SENT["body"] and "the number of records is {count}" in SENT["body"])
A.compose("покажи строки", ROWS, None)
t("счёта нет вовсе — остаётся прежний вид, без выдумки",
  "ROWS FOUND (2)" in SENT["body"])

# 🔴 Среднее и сумма посчитаны по строкам, У КОТОРЫХ ЭТА ВЕЛИЧИНА ЕСТЬ. Их бывает
# меньше, чем записей: `aggregate` считает `count_amount` отдельно ровно поэтому
# («иначе среднее по 31 строке уходит как среднее по 1344»). Если модели этого не
# сказать, ответ «средний чек 293 900 по 1344 документам» неверен, а гейт его пропустит:
# оба числа посчитаны базой.
A.compose("средний чек", ROWS, dict(AGG, count=1344, count_amount=31), totals=TOTALS)
t("модель знает, ПО СКОЛЬКИМ записям посчитаны сумма и среднее",
  "{count_amount}" in SENT["body"] and "31" not in SENT["body"])
A.compose("средний чек", ROWS, dict(AGG, count=249, count_amount=249), totals=TOTALS)
t("числа сошлись — лишней строки на каждый вопрос не появляется",
  "count_amount" not in SENT["body"])


# count_kind из kind_word(src) — не «документы» для регистра
A.compose("сколько записей", ROWS, {"count": 19, "count_amount": 0, "sum": 0, "min": 0,
                                  "max": 0, "avg": 0, "date_min": "", "date_max": "",
                                  "folders": 0}, src="accumulationregister_продажи")
t("count_kind: место kind_word в задании модели (не «documents»)",
  "{count_kind}" in SENT["body"])
t("count_kind: подстановка kind_word",
  A._fill_figures("Найдено {count} {count_kind}.", {"count": 19}, [], extra={"count_kind": "регистр накопления"})[0]
  == "Найдено 19 регистр накопления.")

A.compose("сколько всего", ROWS, {"count": 249, "count_amount": 0, "sum": 0, "min": 0,
                                  "max": 0, "avg": 0, "date_min": "", "date_max": "",
                                  "folders": 0})
t("денежной колонки нет — модель видит только место под счёт записей",
  "{count}" in SENT["body"] and "{total}" not in SENT["body"])

# A2: want=count|list, величина не выбрана — денежных мест нет, даже если итоги
# по полям посчитаны (они ушли бы в {total:ИМЯ} и детектор их не видел).
A.compose("сколько продаж было всего позавчера", ROWS,
          dict(AGG, count=19, sum=28356.37), totals=TOTALS, money=False)
t("A2 count без величины: нет {total}/{max}/{avg} и нет {total:ИМЯ}",
  "{count}" in SENT["body"]
  and "{total" not in SENT["body"]
  and "{max}" not in SENT["body"]
  and "{avg}" not in SENT["body"])
t("A2 count: отпечатки 19=19 при 112k vs 28k — не расхождение",
  not A.answers_diverge([
      A.compose_slot_values(dict(AGG, count=19, sum=112325.97), measure=None),
      A.compose_slot_values(dict(AGG, count=19, sum=28356.37), measure=None)]))
txt_nomoney, bad_nomoney = A._fill_figures(
    "19 продаж на {total:Штуки}.", dict(AGG, count=19, sum=28356.37), [],
    has_measure=False)
t("A2 count: без totals_shown число поля в текст не встаёт",
  "28356" not in txt_nomoney and "92" not in txt_nomoney and bad_nomoney)
A.compose("покажи продажи", ROWS, AGG, totals=TOTALS, money=False)
t("A2 list без величины: {total:ИМЯ} модели не показывается",
  "{total" not in SENT["body"] and "{count}" in SENT["body"])
t("A1 деньги в compose: величина выбрана — 112k vs 28k это расхождение",
  A.answers_diverge([
      A.compose_slot_values(dict(AGG, count=19, sum=112325.97), measure="Всего"),
      A.compose_slot_values(dict(AGG, count=19, sum=28356.37), measure="Всего")]))

# Живой разбор «сколько … всего»: want=count, compute=sum, поле уже есть.
_agg_cnt = dict(AGG, count=19, sum=28356.37, measure="Всего")
A.compose("сколько продаж было всего позавчера", ROWS, _agg_cnt,
          totals=TOTALS, money=False)
t("count+поле: нет {total} и нет amount= в задании",
  "{total" not in SENT["body"] and "amount=" not in SENT["body"]
  and "{count}" in SENT["body"])
A.compose("сумма продаж", ROWS, _agg_cnt, totals=TOTALS, money=True)
t("want=sum: {total} на месте, A1 не сломан",
  "{total}" in SENT["body"] and "amount=" in SENT["body"])
A.compose("сколько продаж было всего позавчера", ROWS, _agg_cnt,
          totals=TOTALS, money=False,
          corrections=["нераспознанное место: {total} (есть: нет)"])
t("retry с тем же money=False: денежных мест в COMPUTED нет",
  "-> {total}" not in SENT["body"] and "amount=" not in SENT["body"]
  and "{count}" in SENT["body"])
txt_fill, bad_fill = A._fill_figures(
    "Итого {total}.", dict(AGG, sum=28356.37), TOTALS, has_measure=False)
t("заливка при money=False: безымянный {total} не заполняется при живом sum",
  "28356" not in txt_fill and bad_fill)
import inspect as _ins
_ans = _ins.getsource(A.answer)
_after = _ans.split("money = answer_money", 1)[1]
t("retry: fill и gate второй попытки на money, не на bool(measure)",
  "bool(measure)" not in _after
  and "_fill_figures(text2, agg, totals_shown, money" in _after
  and "money=money" in _after)

A.compose("сколько складов", ROWS, dict(AGG, folders=25), totals=TOTALS, folders=25)
t("отброшенные группы названы местом, а не числом (п. 13: сказать о потере — обязательно)",
  "{folders}" in SENT["body"] and " 25 " not in SENT["body"])
t("место под отброшенное заполняется из посчитанного",
  A._fill_figures("Исключено {folders} групп.", dict(AGG, folders=25), TOTALS)[0]
  == "Исключено 25 групп.")

COV = {"in_1c": 1000, "in_search": 896, "missing": 104, "reason": "нет прав"}
A.compose("сколько продали", ROWS, AGG, totals=TOTALS, coverage=COV)
t("неполнота уходит модели МЕСТАМИ и с причиной, но без самих чисел",
  "{missing}" in SENT["body"] and "нет прав" in SENT["body"]
  and "104" not in SENT["body"] and "1000" not in SENT["body"])
t("числа неполноты подставляются кодом наравне с итогами",
  A._fill_figures("Не дошло {missing} из {in_1c} строк.", AGG, TOTALS, True,
                  {"in_1c": 1000, "in_search": 896, "missing": 104})[0]
  == "Не дошло 104 из 1" + NBSP + "000 строк.")
t("без переписи место неполноты остаётся отказом, а не нулём",
  A._fill_figures("Не дошло {missing} строк.", AGG, TOTALS, True, None)[1])

A.compose("на какую сумму", ROWS, AGG, totals=TOTALS,
          corrections=["число 925000 не найдено в данных", 5000.0])
t("вторая попытка: причины отказа склеиваются, число среди них не роняет сервис",
  "925000" in SENT["body"] and "5000" in SENT["body"])

# Строка корпуса режется по бюджету — человек не должен получить обрезок как целое.
LONG = row("100.00", "2019-01-09", "Контрагент " + "Ы" * 5000)
A.compose("кто это", [LONG] * 25, AGG, totals=TOTALS)
t("обрезанная по бюджету строка помечена как обрезанная",
  "…" in SENT["body"])

# ------------------------------------------------- формулировка как целое
t("пустая формулировка не может уйти человеку",
  A.formulation_flaws("", []))
t("формулировка с незаполненным местом не может уйти человеку",
  A.formulation_flaws("Итого на {Итого} руб.", []))
t("нормальная формулировка проходит",
  not A.formulation_flaws("Итого на 73 181 157.68 руб. по 249 документам.", []))
t("нераспознанное место из подстановки — та же причина отказа",
  A.formulation_flaws("Итого.", ["{total:Выдуманная}"]))
# Данные 1С содержат GUID в фигурных скобках — это цитата из строки, а не наше место.
t("GUID в фигурных скобках не считается незаполненным местом",
  not A.formulation_flaws("Ссылка {a1b2c3d4-0000-1111-2222-333344445555}", []))


# ------------------------------------------------- слот периода из prior
chip = {"want": "count", "measure": "", "kind": "продажи", "terms": ["книга"],
        "amount": {"op": "gt", "value": 1}, "about": "data",
        "period": {}, "parse": {"assumed": []}}
prior_sum = {"want": "sum", "measure": "Сумма", "kind": "продажи",
             "terms": ["продано"], "amount": {}, "about": "data",
             "period": {"from": "2026-08-12", "to": "2026-08-12"},
             "parse": {"assumed": ["period.from", "period.to"]}}
t("prior: пустой слот берёт период, want остаётся с chip",
  A.apply_prior_period(chip, prior_sum) is True
  and chip["period"] == {"from": "2026-08-12", "to": "2026-08-12"}
  and chip["want"] == "count"
  and chip["measure"] == ""
  and chip["kind"] == "продажи"
  and chip["terms"] == ["книга"]
  and chip["amount"] == {"op": "gt", "value": 1})

assumed_year = {"want": "count", "measure": "", "kind": "", "terms": [],
                "amount": {}, "about": "data",
                "period": {"from": "2025-08-14", "to": "2026-08-14"},
                "parse": {"assumed": ["period.from", "period.to"]}}
t("prior: год-от-сегодня (assumed) заменяется периодом prior",
  A.apply_prior_period(assumed_year, prior_sum) is True
  and assumed_year["period"]["from"] == "2026-08-12"
  and assumed_year["want"] == "count")

named = {"want": "count", "measure": "", "kind": "", "terms": [],
         "amount": {}, "about": "data",
         "period": {"from": "2026-08-12", "to": "2026-08-12"},
         "parse": {"assumed": []}}
t("prior: период chip не затирается, want prior не протекает",
  A.apply_prior_period(named, prior_sum) is False
  and named["period"] == {"from": "2026-08-12", "to": "2026-08-12"}
  and named["want"] == "count")

empty_prior = {"want": "sum", "period": {}, "parse": {"assumed": []}}
chip2 = {"want": "count", "period": {}, "parse": {"assumed": []}}
t("prior: пустой prior ничего не копирует",
  A.apply_prior_period(chip2, empty_prior) is False and chip2["want"] == "count")

_GAGG = dict(AGG, grain="group", col="Номенклатура", n_groups=80, max=36651.0,
             sum=46204.58,
             groups=[{"name": "Balama Rollenband", "value": 46204.58, "count": 4}])
import serene_axis as _AX
_GROWS = _AX.group_rows(_GAGG["groups"])
A.compose("какой товар больше продали", _GROWS, _GAGG, totals=TOTALS, money=True)
t("group: модели группы, не largest single",
  "GROUPS" in SENT["body"] and "{max}" not in SENT["body"]
  and "largest single" not in SENT["body"])
t("group: сырой 36651 в задании как amount строки не стоит",
  "36651" not in SENT["body"] and "amount=36651" not in SENT["body"])
t("group: имя группы модели видно, итог группы — местом {total}",
  "Balama Rollenband" in SENT["body" ] and "{total}" in SENT["body"])
txt_g, bad_g = A._fill_figures("Лидер {total}, не {max}.", _GAGG, [], True)
t("group: {max} = лидер группы, не 36651 строки",
  not bad_g and "46204" in txt_g.replace(" ", "").replace("\xa0", "")
  and "{max}" not in txt_g and "36651" not in txt_g)
txt_gn, bad_gn = A._fill_figures("Итог {total:Balama}.", _GAGG, [], True)
t("group: {total:фрагмент имени} — итог группы",
  not bad_gn and "46204" in txt_gn.replace(" ", "").replace("\xa0", ""))
txt_ng = A.ensure_n_groups_named("Лидер 46 204.58", _GAGG)
t("group: n_groups > K дописывается числом",
  "80" in txt_ng.replace(" ", "").replace("\xa0", "")
  and A.asked_figure_missing(txt_ng, _GAGG, "list", True) is None)
slots_g = A.compose_slot_values(_GAGG, measure="Сумма", money=True)
t("group: слоты без max/min строки",
  "max" not in slots_g and "min" not in slots_g and slots_g.get("sum") == 46204.58)

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
