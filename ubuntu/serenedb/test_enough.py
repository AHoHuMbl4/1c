#!/usr/bin/env python3
"""Оффлайн-прогон шага «достаточен ли вопрос»: БЕЗ базы, БЕЗ сети, БЕЗ вызовов модели.

Зачем отдельный прибор. Живая приёмка стоит денег и даёт разброс ±1-3 ответа из десяти,
поэтому правкой она ничего не доказывает поодиночке (`HOW_NOT_TO §1.34`). Здесь
проверяется то, что проверяется бесплатно и воспроизводимо: разбор описания вопроса по
типам, оба вердикта и — главное — СВЯЗКА с сервисом ответов, где живут две ошибки, которых
чистая функция не видит: шаг, сработавший на подчинённом вызове круга арбитра, и шаг,
переспросивший человека о том, что он только что выбрал сам.

Модель, база и гейт подменяются заготовками, поэтому прогон детерминирован.

Запуск:  python3 ubuntu/serenedb/test_enough.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A       # noqa: E402
import serene_enough as E    # noqa: E402

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


def intent(**kw):
    """Разбор шага 1 в том виде, в каком его отдаёт `parse_intent`."""
    d = {"terms": [], "kind": "", "measure": "", "want": "list",
         "period": {"from": None, "to": None},
         "amount": {"op": None, "value": None, "value2": None},
         "about": "data", "parse": {"lost": [], "assumed": [], "unstable": []}}
    d.update(kw)
    return d


# ═════════════════════════ описание вопроса: разбор по типам ═════════════════════════
t("описание разбирается из чистого JSON",
  E.parse_facts('{"one_of_many": "товар", "period_named": false, '
                '"measure_named": true}')["one_of_many"] == "товар")
t("описание разбирается из болтливого ответа со скобками в рассуждении",
  E.parse_facts('Sure! {здесь} мысль. {"one_of_many": "товар", "period_named": false}'
                )["one_of_many"] == "товар")
t("описание в заборе ```json разбирается",
  E.parse_facts('```json\n{"one_of_many": null, "period_named": true}\n```'
                )["one_of_many"] is None)
t("ответа-объекта нет — None, а не пустое описание",
  E.parse_facts("не смог") is None)
t("пустая строка — None",
  E.parse_facts("") is None and E.parse_facts(None) is None)
t("`one_of_many` списком не роняет разбор и читается как «нет»",
  E.parse_facts('{"one_of_many": ["товар"]}')["one_of_many"] is None)
t("`one_of_many` числом читается как «нет»",
  E.parse_facts('{"one_of_many": 5}')["one_of_many"] is None)
t("строка «null» отличается от существительного",
  E.parse_facts('{"one_of_many": "  "}')["one_of_many"] is None)
t("пересказ вопроса вместо существительного отбрасывается по длине",
  E.parse_facts('{"one_of_many": "%s"}' % ("товар " * 20))["one_of_many"] is None)
t("`period_named` строкой «true» читается как истина",
  E.parse_facts('{"period_named": "true"}')["period_named"] is True)
t("`period_named` строкой «no» читается как ложь",
  E.parse_facts('{"period_named": "no"}')["period_named"] is False)
t("`period_named` мусором читается как «сведений нет»",
  E.parse_facts('{"period_named": "может быть"}')["period_named"] is None)
t("не-объект описанием не становится",
  E.normalize_facts(["товар"]) is None and E.normalize_facts("товар") is None)

# ═════════════════════════ где вообще спрашивать модель ═════════════════════════
t("описание запрашивается: просят итог, значений в вопросе нет",
  E.facts_wanted(intent(want="sum", kind="продажи")))
t("значение в вопросе названо — описание не запрашивается",
  not E.facts_wanted(intent(want="sum", kind="продажи", terms=[["Альтаир"]])))
t("счёт записей — описание не запрашивается",
  not E.facts_wanted(intent(want="count", kind="контрагенты")))
t("перечень — описание не запрашивается",
  not E.facts_wanted(intent(want="list", kind="партнёры")))
t("вопрос о самих данных — описание не запрашивается",
  not E.facts_wanted(intent(want="sum", about="coverage")))
t("мусор вместо разбора описания не требует",
  not E.facts_wanted(None) and not E.facts_wanted([]))

# ═════════════════════════ назван ли период В ВОПРОСЕ ═════════════════════════
t("период задан датами — назван",
  E.period_given(intent(period={"from": "2017-12-01", "to": "2017-12-31"})))
t("задана только нижняя граница — назван",
  E.period_given(intent(period={"from": "2017-12-01", "to": None})))
t("периода нет — не назван",
  not E.period_given(intent()))
t("период ВЫВЕДЕН системой (`assumed`) — за названный не считается",
  not E.period_given(intent(period={"from": "2025-08-05", "to": None},
                            parse={"assumed": ["period.from"]})))
t("period_assumed: выведенный период опознан",
  E.period_assumed(intent(period={"from": "2025-08-05", "to": None},
                          parse={"assumed": ["period.from"]})))
t("period_assumed: названный период — не догадка",
  not E.period_assumed(intent(period={"from": "2017-12-01", "to": "2017-12-31"})))
t("period_assumed: периода нет",
  not E.period_assumed(intent()))

# ═════════════════════════ дешёвая половина: до поиска ═════════════════════════
t("итог просят, но не названо ни рода записей, ни значений — спросить",
  E.verdict_before(intent(want="sum"))[0])
t("в уточнении два слота: предмет и период",
  [s["kind"] for s in E.verdict_before(intent(want="sum"))[1]] == ["subject", "period"])
t("период в вопросе есть — слот периода не добавляется",
  [s["kind"] for s in E.verdict_before(
      intent(want="sum", period={"from": "2017-01-01", "to": None}))[1]] == ["subject"])
t("род записей назван — дешёвая половина молчит",
  not E.verdict_before(intent(want="sum", kind="продажи"))[0])
t("значение названо — дешёвая половина молчит",
  not E.verdict_before(intent(want="sum", terms=[["Альтаир"]]))[0])
t("числа не просят вовсе — дешёвая половина молчит",
  not E.verdict_before(intent(want="list"))[0])
t("названа величина без `want=sum` — вырожденный случай тоже ловится",
  E.verdict_before(intent(want="list", measure="штук"))[0])
t("вопрос о полноте данных мимо шага",
  not E.verdict_before(intent(want="sum", about="coverage"))[0])
t("мусор вместо разбора уточнением не становится",
  not E.verdict_before(None)[0] and not E.verdict_before("")[0])

# ═════════════════════════ решающая половина: после счёта ═════════════════════════
FACT_ONE = {"one_of_many": "товар", "period_named": False, "measure_named": True}
FACT_NONE = {"one_of_many": None, "period_named": False, "measure_named": True}

t("вопрос указал один неназванный предмет, итог из 990 записей — спросить",
  E.verdict_after(intent(want="sum"), FACT_ONE, 990, True)[0])
t("в уточнении названо слово ИЗ ВОПРОСА, а не наше",
  "товар" in E.slots_text(E.verdict_after(intent(want="sum"), FACT_ONE, 990, True)[1])[0])
t("предмета в вопросе нет («сколько у нас контрагентов») — отвечаем",
  not E.verdict_after(intent(want="sum"), FACT_NONE, 155, False)[0])
t("итог сложен из ОДНОЙ записи — выбор предмета его не меняет, отвечаем",
  not E.verdict_after(intent(want="sum"), FACT_ONE, 1, True)[0])
t("записей ноль — отвечаем (спрашивать не о чем)",
  not E.verdict_after(intent(want="sum"), FACT_ONE, 0, True)[0])
t("число записей не разобрать — шаг молчит, а не гадает",
  not E.verdict_after(intent(want="sum"), FACT_ONE, None, True)[0])
t("дат у источника нет — про период не спрашиваем",
  [s["kind"] for s in E.verdict_after(intent(want="sum"), FACT_ONE, 990, False)[1]]
  == ["subject"])
t("даты есть и период не назван — спрашиваем и про него",
  [s["kind"] for s in E.verdict_after(intent(want="sum"), FACT_ONE, 990, True)[1]]
  == ["subject", "period"])
t("период назван в вопросе — про него не спрашиваем",
  [s["kind"] for s in E.verdict_after(
      intent(want="sum", period={"from": "2017-12-01", "to": "2017-12-31"}),
      FACT_ONE, 990, True)[1]] == ["subject"])
t("период назван по описанию модели — про него не спрашиваем",
  [s["kind"] for s in E.verdict_after(
      intent(want="sum"), dict(FACT_ONE, period_named=True), 990, True)[1]] == ["subject"])
t("описания нет вовсе — шаг молчит",
  not E.verdict_after(intent(want="sum"), None, 990, True)[0])
t("причина вердикта называет число, на котором он стоит",
  "990" in E.verdict_after(intent(want="sum"), FACT_ONE, 990, True)[2])

# ═════════════════════════ перечень слотов для модели ═════════════════════════
t("слот предмета со словом вопроса",
  E.slots_text([{"kind": "subject", "word": "товар"}]) == ["which particular «товар» is meant"])
t("слот предмета без слова — общий вопрос о роде записей",
  "records" in E.slots_text([{"kind": "subject", "word": ""}])[0])
t("слот периода",
  E.slots_text([{"kind": "period"}]) == ["what time period is meant"])
t("мусор в слотах пропускается",
  E.slots_text([None, "x", {"kind": "?"}]) == [])

# ═════════════════════════ текст уточнения: модель + гейт ═════════════════════════
def say(model_answer, gate_ok=True, diag=None):
    return E.need_say("Сколько штук товара мы продали?",
                      [{"kind": "subject", "word": "товар"}, {"kind": "period"}],
                      lambda *a, **k: model_answer,
                      lambda *a, **k: (gate_ok, [] if gate_ok else [42.0]),
                      diag)


t("формулировка модели проходит гейт и уходит человеку",
  say("Какой товар и за какой период вас интересует?")
  == "Какой товар и за какой период вас интересует?")
t("формулировка с числом вне данных гейтом отвергается — шаг молчит",
  say("Уточните: 42 товара?", gate_ok=False) == "")
_d = {}
say("Уточните: 42 товара?", gate_ok=False, diag=_d)
t("отказ гейта виден в следе ответа", "need_gate_rejected" in _d)
t("модель промолчала — шаг молчит, ответ остаётся прежним", say("") == "")
t("модель упала — шаг молчит",
  E.need_say("q", [{"kind": "period"}],
             lambda *a, **k: (_ for _ in ()).throw(RuntimeError("сеть")),
             lambda *a, **k: (True, [])) == "")
t("пересказ собственного задания шага гейт отвергает как утечку",
  not A._gate_need("Итак: - Ask in the SAME language the question was asked in.")[0])
t("обычное уточнение без чисел гейт пропускает",
  A._gate_need("Какой товар и за какой период вас интересует?")[0])
t("слотов нет — модель не зовётся вовсе",
  E.need_say("q", [], lambda *a, **k: "вызова тут не ожидается",
             lambda *a, **k: (True, [])) == "")

# ═════════════════════════ связка с сервисом ответов ═════════════════════════
# Подменяем всё, что ходит наружу. `answer` считает свои вызовы: так видно, экономит ли
# дешёвая половина прогон и не зовётся ли шаг на подчинённых вызовах круга арбитра.
CALLS = {"answer": 0, "facts": 0}
ANSWER_OUT = {"kind": "answer", "text": "26 239,5 штук", "sources": ["Товары"],
              "diag": {"focus": "document_реализациятоваровуслуг_товары",
                       "счёт": {"строк": 990, "со_значением": 990}}}


def fake_answer(question, focus=None, measure_pick=None, context=""):
    CALLS["answer"] += 1
    return dict(ANSWER_OUT)


def fake_facts(question, today):
    CALLS["facts"] += 1
    return dict(FACT_ONE)


A.answer = fake_answer
A.question_facts = fake_facts
A.entity_has_dates = lambda src: True
A.ds_chat = lambda *a, **k: "Какой товар и за какой период вас интересует?"
A.gate_out = lambda *a, **k: (True, [])
A.parse_intent = lambda q, today: intent(want="sum", kind="продажи", measure="штук")

CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("вопрос с неназванным предметом становится уточнением", out["kind"] == "clarify")
t("уточнение несёт след «чего не хватает»",
  out["diag"]["not_enough"]["чего_нет"] == ["subject", "period"])
t("уточнение сформулировано на языке вопроса моделью",
  out["text"] == "Какой товар и за какой период вас интересует?")
t("уточнение без вариантов выбора — спрашиваем про вопрос, а не про источники",
  out["options"] == [])

CALLS.update(answer=0, facts=0)
A.parse_intent = lambda q, today: intent(want="sum", kind="контрагенты")
A.question_facts = lambda q, today: dict(FACT_NONE)
out = A.answer_checked("Сколько у нас контрагентов?")
t("полный вопрос отвечается, а не переспрашивается", out["kind"] == "answer")

A.question_facts = fake_facts
A.parse_intent = lambda q, today: intent(want="sum", kind="продажи")
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?", focus="Реализация Товаров Услуг")
t("человек уже выбрал источник — шаг молчит целиком", out["kind"] == "answer")
t("при выборе человека модель об описании не спрашивается", CALLS["facts"] == 0)

CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук?", measure_pick="Количество")
t("человек уже выбрал величину — шаг молчит", out["kind"] == "answer")

A.parse_intent = lambda q, today: intent(want="sum")
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук?")
t("дешёвая половина спрашивает ДО поиска", out["kind"] == "clarify")
t("дешёвая половина экономит весь прогон: поиск не запускался",
  CALLS["answer"] == 0 and CALLS["facts"] == 0)

A.parse_intent = lambda q, today: intent(want="sum", kind="продажи")
A.answer = lambda *a, **k: {"kind": "no_data", "text": "", "diag": {}}
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("отказ не переделывается в уточнение", out["kind"] == "no_data")
t("на отказе описание вопроса не запрашивается", CALLS["facts"] == 0)

A.answer = lambda *a, **k: {"kind": "clarify", "text": "какой источник?", "diag": {}}
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("уточнение шага 4 остаётся своим, шаг его не подменяет",
  out["text"] == "какой источник?" and CALLS["facts"] == 0)

A.answer = fake_answer
A.question_facts = lambda q, today: None
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("описание не разобралось — ответ уходит как есть", out["kind"] == "answer")

A.question_facts = fake_facts
A.ds_chat = lambda *a, **k: ""
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("уточнение не сформулировалось — ответ уходит как есть, а не пропадает",
  out["kind"] == "answer" and out["text"] == "26 239,5 штук")

A.ds_chat = lambda *a, **k: "Какой товар?"
A.answer = lambda *a, **k: dict(ANSWER_OUT, diag={"focus": "x",
                                                  "счёт": {"строк": 1, "со_значением": 1}})
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("итог из одной записи — отвечаем, вопрос был бы шумом", out["kind"] == "answer")

A.answer = lambda *a, **k: dict(ANSWER_OUT, diag={"focus": "x", "rows": 990})
CALLS.update(answer=0, facts=0)
out = A.answer_checked("Сколько штук товара мы продали?")
t("следа «счёт» нет — число записей берётся из `rows`", out["kind"] == "clarify")

A.answer = fake_answer
A.ENOUGH_ON = False
try:
    A.ENOUGH_ON = False
    CALLS.update(answer=0, facts=0)
    out = A.answer_checked("Сколько штук товара мы продали?")
    t("выключатель `ASK_ENOUGH=0` гасит шаг целиком",
      out["kind"] == "answer" and CALLS["facts"] == 0)
finally:
    A.ENOUGH_ON = True

_saved = A.serene_enough
A.serene_enough = None
try:
    out = A.answer_checked("Сколько штук товара мы продали?")
    t("файла шага нет (старая раскладка) — сервис отвечает, а не падает",
      out["kind"] == "answer")
finally:
    A.serene_enough = _saved

print("\n%d проверок пройдено" % PASS)
if FAIL:
    print("ПРОВАЛЕНО %d: %s" % (len(FAIL), "; ".join(FAIL)))
    raise SystemExit(1)
