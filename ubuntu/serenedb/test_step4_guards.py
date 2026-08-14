#!/usr/bin/env python3
"""Оффлайн-прогон ЗАЩИТ ШАГА 4: БЕЗ базы, БЕЗ сети, БЕЗ вызовов модели.

Защиты шага 4 — это три правила, которые решают, уходит ответ человеку или вместо него
уходит вопрос. Каждое из них уже однажды отвергло ВЕРНЫЙ ответ, а по п. 21 такой случай
считается дефектом самой проверки. Отсюда этот прибор: проба каждого правила, которая стоит
ноль и повторяется дословно:

  · `figures_numbers` / `same_number` — совпадение прочтений доказывается ЧИСЛАМИ, в том
    числе теми, что кандидат завернул в уточнение о своей величине;
  · `alias_supported` — форма правила «подтверждает ли словарь синонимов выбор сущности»;
  · `answers_diverge` — зеркальное правило, расхождение (проверяется здесь же, чтобы
    правки одного не расходились с другим);
  · `answers_src_conflict` — A3: совпавший отпечаток при разных src не согласие.

Живые числа этим прибором не заменяются: сколько ответов вернулось на приёмочном наборе —
меряет `work/acceptance/step4_bench.py` на боевой базе.

Запуск:  python3 ubuntu/serenedb/test_step4_guards.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

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


# ── Числа кандидата: ответом стали или нет ──────────────────────────────────────────
t("итог ответа берётся как число",
  A.figures_numbers({"figures": {"sum": 100.0, "count": 3}}) == [100.0])
t("итога нет — берётся число записей",
  A.figures_numbers({"figures": {"count": 164}}) == [164])
t("ни того, ни другого — чисел нет",
  A.figures_numbers({"figures": {}}) == [])
t("кандидата нет вовсе — чисел нет",
  A.figures_numbers(None) == [])
t("уточнение о величине несёт итоги всех подходящих величин",
  sorted(A.figures_numbers({"kind": "clarify",
                            "diag": {"measure_totals": {"Сумма": 10.0,
                                                        "СуммаНДС": 2.0}}})) == [2.0, 10.0])
t("встречный вопрос несёт своё посчитанное число",
  A.figures_numbers({"kind": "clarify", "figures": {"sum": 71045277.59}}) == [71045277.59])
t("уточнение о величине И встречный вопрос — числа складываются, не теряются",
  sorted(A.figures_numbers({"kind": "clarify", "figures": {"sum": 5.0},
                            "diag": {"measure_totals": {"А": 7.0}}})) == [5.0, 7.0])

# ── Совпадение доказывается равенством, а не молчанием ──────────────────────────────
t("равное число среди чисел соперника — совпадение доказано",
  A.same_number(2456400.0, [1.0, 2456400.0]) is True)
t("равных чисел нет — доказательства нет",
  A.same_number(2456400.0, [1.0, 2.0]) is False)
t("у соперника нет ни одного числа — доказательства нет",
  A.same_number(100.0, []) is False)
t("у нас нет числа — доказательства нет",
  A.same_number(None, [100.0]) is False)
t("целое и дробное одного значения — это одно число",
  A.same_number(164, [164.0]) is True)
t("строка вместо числа не роняет правило",
  A.same_number(100.0, ["сто", None]) is False)
t("сравнимая строка сравнивается как число",
  A.same_number(100.0, ["100"]) is True)
t("допуска нет: копейка расхождения — не совпадение",
  A.same_number(100.0, [100.01]) is False)

# ── Форма правила «подтверждает ли словарь синонимов выбор» ─────────────────────────
t("знания о сущности нет — проверять нечем, выбор проходит",
  A.alias_supported(0, 0, "catalog_a", "catalog_b", veto=True) is True)
t("жёсткая форма: лидер той же семьи — подтверждено",
  A.alias_supported(5, 0, "catalog_a", "catalog_a", veto=True) is True)
t("жёсткая форма: лидер чужой — не подтверждено даже при своём совпадении",
  A.alias_supported(5, 3, "catalog_a", "catalog_b", veto=True) is False)
t("жёсткая форма без лидера (словарь молчит) — решает своё совпадение",
  A.alias_supported(5, 3, "catalog_a", "", veto=True) is True)
t("жёсткая форма без лидера и без своего совпадения — не подтверждено",
  A.alias_supported(5, 0, "catalog_a", "", veto=True) is False)
t("мягкая форма: довольно своего совпадения",
  A.alias_supported(5, 1, "catalog_a", "catalog_b", veto=False) is True)
t("мягкая форма: своего совпадения нет — не подтверждено",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=False) is False)
t("семья, а не сущность: табличная часть подтверждается своей шапкой",
  A.alias_supported(5, 0, "document_x", "document_x", veto=True) is True)

# Форма «лидер обязан стоять ВЫШЕ выбора в общем порядке кандидатов». Места считаются по
# семьям и берутся из того же порядка, которым шаг 3 отдаёт кандидатов модели.
A.VETO_NEEDS_RANK = True
t("лидера словаря нет в круге кандидатов — словарь один против всех, выбор проходит",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=2, rank_leader=-1) is True)
t("лидер стоит НИЖЕ выбора — вето не срабатывает",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=1, rank_leader=7) is True)
t("лидер стоит ВЫШЕ выбора — вето срабатывает",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=7, rank_leader=1) is False)
t("выбора нет в круге кандидатов — сравнивать нечем, решает семья лидера",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=-1, rank_leader=1) is False)
t("лидер той же семьи подтверждает и при худшем месте",
  A.alias_supported(5, 0, "catalog_a", "catalog_a", veto=True,
                    rank_cand=7, rank_leader=1) is True)
A.VETO_NEEDS_RANK = False
t("форма выключена — места не смотрятся, решает лидер",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=1, rank_leader=7) is False)

# Вторая попытка подтверждения (п. 21): голова общего порядка кандидатов — независимое от
# словаря подтверждение. Это НЕ послабление: не голова — правило работает как прежде.
A.VETO_HEAD_WINS = True
t("выбор возглавляет общий порядок и спора не было — подтверждение есть",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=0, rank_leader=3, undisputed=True) is True)
t("🔴 спор был — вторая попытка не даётся, даже если выбор голова порядка",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=0, rank_leader=3, undisputed=False) is False)
t("выбор не голова — вторая попытка не помогает, решает лидер словаря",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=1, rank_leader=3, undisputed=True) is False)
t("выбора нет в круге кандидатов — второй попытке не на что опереться",
  A.alias_supported(5, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=-1, rank_leader=3, undisputed=True) is False)
t("знания о сущности нет — вторая попытка не нужна, выбор и так проходит",
  A.alias_supported(0, 0, "catalog_a", "catalog_b", veto=True,
                    rank_cand=5, rank_leader=0, undisputed=False) is True)
A.VETO_HEAD_WINS = os.environ.get("ASK_VETO_HEAD_WINS", "0") == "1"
A.VETO_NEEDS_RANK = os.environ.get("ASK_VETO_NEEDS_RANK", "1") == "1"

# ── Зеркальное правило: расхождение ─────────────────────────────────────────────────
t("одинаковые числа — расхождения нет",
  A.answers_diverge([{"sum": 5.0}, {"sum": 5.0}]) is False)
t("разные числа — расхождение",
  A.answers_diverge([{"sum": 5.0}, {"sum": 6.0}]) is True)
t("итог против числа записей — расхождение",
  A.answers_diverge([{"sum": 5.0}, {"count": 5}]) is True)
t("сравнивать нечем — расхождение (доказательства совпадения нет)",
  A.answers_diverge([{"sum": 5.0}, {}]) is True)
t("один кандидат — сравнивать не с чем, расхождения нет",
  A.answers_diverge([{"sum": 5.0}]) is False)
t("величина выбрана, один счёт, разные суммы — расхождение",
  A.answers_diverge([
      A.compose_slot_values({"count": 19, "sum": 112325.97}, measure="Всего"),
      A.compose_slot_values({"count": 19, "sum": 28356.37}, measure="Всего")]) is True)
t("без величины деньги в отпечаток не входят: 19=19 не расхождение",
  A.answers_diverge([
      A.compose_slot_values({"count": 19, "sum": 112325.97}, measure=None),
      A.compose_slot_values({"count": 19, "sum": 28356.37}, measure=None)]) is False)
t("счёт совпал, среднее в плейсхолдерах разошлось — расхождение",
  A.answers_diverge([{"count": 19, "avg": 100.0}, {"count": 19, "avg": 200.0}]) is True)
t("счёт совпал, число папок разошлось — расхождение",
  A.answers_diverge([
      A.compose_slot_values({"count": 19}, folders=2, money=False),
      A.compose_slot_values({"count": 19}, folders=5, money=False)]) is True)
t("arbiter_figures не поднимает diag.totals",
  A.arbiter_figures({"figures": {"count": 19},
                     "diag": {"totals": {"Всего": [28356.37, 1, 1]}}})
  == {"count": 19})

# ── A3: совпавший отпечаток при разных src — не согласие ────────────────────────────
# Чистая функция на {src, kind, figures}. Не разбор исходника answer().
# Отпечаток — answers_diverge / слоты compose, не голое count.
_doc19 = A.compose_slot_values({"count": 19, "sum": 112325.97}, measure=None)
_book19 = A.compose_slot_values({"count": 19, "sum": 28356.37}, measure=None)
t("A3: 19=19 разные src оба answer — не согласие",
  A.answers_src_conflict([
      {"src": "document_sale", "kind": "answer", "figures": _doc19},
      {"src": "register_book", "kind": "answer", "figures": _book19}]) is True)
t("A3: один src — согласие",
  A.answers_src_conflict([
      {"src": "document_sale", "kind": "answer", "figures": _doc19},
      {"src": "document_sale", "kind": "answer", "figures": _book19}]) is False)
t("A3: три src, отпечаток совпал — не пара, не согласие",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": {"count": 155}},
      {"src": "b", "kind": "answer", "figures": {"count": 155}},
      {"src": "c", "kind": "answer", "figures": {"count": 155}}]) is True)
t("A3: цена 155=155 разные src — не согласие",
  A.answers_src_conflict([
      {"src": "catalog_partners", "kind": "answer", "figures": {"count": 155}},
      {"src": "catalog_contractors", "kind": "answer", "figures": {"count": 155}}]) is True)
t("A3: отпечатки разошлись — не эта ветка (это answers_diverge)",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": {"count": 19, "avg": 100.0}},
      {"src": "b", "kind": "answer", "figures": {"count": 19, "avg": 200.0}}]) is False)
t("A3: отпечаток через arbiter_figures, покрытие не разводит",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": A.arbiter_figures(
          {"figures": {"count": 19, "in_1c": 1, "_totals": {"x": 1}}})},
      {"src": "b", "kind": "answer", "figures": A.arbiter_figures(
          {"figures": {"count": 19, "in_1c": 99, "_totals": {"x": 2}}})}]) is True)
t("A3: kind не answer — не эта ветка",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": {"count": 19}},
      {"src": "b", "kind": "clarify", "figures": {"count": 19}}]) is False)
t("A3: один кандидат — согласие не из чего снимать",
  A.answers_src_conflict([
      {"src": "a", "kind": "answer", "figures": {"count": 19}}]) is False)
# answers_diverge на том же 19=19 без величины — по-прежнему ложь (функция не тронута).
t("A3 не меняет answers_diverge: 19=19 без величины — не расхождение",
  A.answers_diverge([_doc19, _book19]) is False)

# ── A2: свести поле только когда вопрос про итог/max/min/avg ────────────────────────
t("want=count + compute=sum + поле — денег нет (живой «сколько … всего»)",
  A.answer_money("count", "sum", "Всего") is False)
t("want=sum + поле — деньги есть (A1 цел)",
  A.answer_money("sum", None, "Всего") is True)
t("want=count + compute=count + поле — денег нет",
  A.answer_money("count", "count", "Всего") is False)

# JSON человеку vs diag: два места, не вызов /ask и не копия моста.
import inspect as _ins
_ans = _ins.getsource(A.answer)
_after = _ans.split("money = answer_money", 1)[1]
_m = "Всего"
t("смесь: JSON пустой при живом поле (закон OR)",
  A.answer_money("count", "sum", _m) is False and bool(_m))
t("гигиена: say_measure от money, counting_rows снят",
  "say_measure = measure if money else None" in _after
  and "counting_rows" not in _after)
t("JSON kind=answer: measure = say_measure, не сырое поле",
  '"measure": say_measure' in _after
  and '"completeness": cov, "measure": measure' not in _after)
t("diag.measure — сырое поле, не say_measure",
  'diag["measure"] = measure' in _ans
  and 'diag["measure"] = say_measure' not in _ans)
t("want=sum: JSON имя останется (A1 на сумме)",
  A.answer_money("sum", "sum", _m) is True)
t("agg.measure не гасится",
  '"measure": measure' in _ins.getsource(A.aggregate))
t("options[].measure не гасится",
  '"measure": m' in _ans)

t("count+поле: отпечаток без суммы, 19=19 не расхождение",
  A.answers_diverge([
      A.compose_slot_values({"count": 19, "sum": 112325.97}, measure="Всего",
                            money=False),
      A.compose_slot_values({"count": 19, "sum": 28356.37}, measure="Всего",
                            money=False)]) is False)
t("want=sum: 112k vs 28k в плейсхолдерах — расхождение",
  A.answers_diverge([
      A.compose_slot_values({"count": 19, "sum": 112325.97}, measure="Всего",
                            money=True),
      A.compose_slot_values({"count": 19, "sum": 28356.37}, measure="Всего",
                            money=True)]) is True)
t("want=count, величина пуста — поле не сводим",
  A.unresolved_quantity(None, [], "count", None, ["Всего", "НДС"],
                        {"Всего": 112325.97, "НДС": 18721}) == (None, []))
t("want=list, величина пуста — поле не сводим",
  A.unresolved_quantity(None, [], "list", None, ["Всего", "НДС"]) == (None, []))
t("compute=max, два поля с разными итогами — уточнение полей",
  A.unresolved_quantity(None, [], "count", "max", ["Всего", "НДС"],
                        {"Всего": 100.0, "НДС": 20.0}) == (None, ["Всего", "НДС"]))
t("want=sum, одно поле — берём его",
  A.unresolved_quantity(None, [], "sum", None, ["Всего"]) == ("Всего", []))
t("want=sum, итоги совпали — берём первое, вопрос был бы шумом",
  A.unresolved_quantity(None, [], "sum", None, ["Всего", "Копия"],
                        {"Всего": 100.0, "Копия": 100.0}) == ("Всего", []))
t("want=sum, итоги разные — уточнение тем же перечнем",
  A.unresolved_quantity(None, [], "sum", None, ["Всего", "НДС"],
                        {"Всего": 112325.97, "НДС": 18721}) == (None, ["Всего", "НДС"]))

# ── Одиночка круга: документ в уточнении полей, книга ответила ──────────────────────
_book = {"diag": {"focus": "register_book"},
         "figures": {"count": 19, "sum": 28356.37}}
_mute_doc = {"document_sale": {"diag": {
    "measure_ambiguous": ["Всего", "НДС"],
    "measure_totals": {"Всего": 112325.97, "НДС": 18721.29}}}}
t("книга ответила, документ в уточнении с другими итогами — держим круг",
  A.mute_measure_blocks("register_book", _mute_doc, [_book]) == "document_sale")
t("итоги совпали — вопрос был бы шумом, одиночку отпускаем",
  A.mute_measure_blocks("register_book",
                        {"document_sale": {"diag": {
                            "measure_ambiguous": ["Всего", "Копия"],
                            "measure_totals": {"Всего": 28356.37,
                                               "Копия": 28356.37}}}},
                        [_book]) is None)
t("выбор модели = одиночка: single_is_rival молчит, mute всё равно держит",
  A.single_is_rival("register_book", "register_book") is False
  and A.mute_measure_blocks("register_book", _mute_doc, [_book]) == "document_sale")

# ── Отсев по знанию «на что НЕ отвечает» (`not_for_excludes`) ───────────────────────
# Форма: весь род вопроса накрыт ОДНОЙ записью без указателя на соседнюю сущность.
# Записи даны в виде (основы левой части, есть_указатель), как их собирает `answer`.
t("весь род накрыт записью без указателя — кандидат отсекается",
  A.not_for_excludes({"продаж"}, [({"оптов", "продаж"}, False)]) is True)
t("та же запись с указателем на соседа — НЕ отсекает",
  A.not_for_excludes({"продаж"}, [({"оптов", "продаж"}, True)]) is False)
t("род многословный — случайное слово записи отсев не даёт",
  A.not_for_excludes({"документ", "реализац", "товар", "услуг"},
                     [({"закупк", "услуг", "проч", "актив"}, False)]) is False)
t("род шире записи — подмножества нет, отсев молчит",
  A.not_for_excludes({"позиц", "номенклатур"},
                     [({"остатк", "движен", "номенклатур"}, False)]) is False)
t("рода нет (разбор молчит) — отсекать нечем",
  A.not_for_excludes(set(), [({"продаж"}, False)]) is False)
t("записей о сущности нет — поведение прежнее",
  A.not_for_excludes({"продаж"}, []) is False)
t("достаточно одной записи без указателя среди прочих с указателем",
  A.not_for_excludes({"продаж"}, [({"план", "продаж"}, True),
                                  ({"оптов", "продаж"}, False)]) is True)
t("пустые записи отсева не дают",
  A.not_for_excludes({"продаж"}, [(set(), False)]) is False)

# ── Соперник по связи «кто пишет» без ответа в круге (`pair_unanswered`) ────────────
t("соперник дал ответ — сравнение было, правило молчит",
  A.pair_unanswered("document_a", {"document_a", "register_b"}) is False)
t("соперник в уточнении (mute) — ответа нет, правило говорит",
  A.pair_unanswered("document_a", {"register_b"}) is True)
t("соперник упал исключением — ни в ответах, ни в mute, правило говорит",
  A.pair_unanswered("document_a", set()) is True)
t("соперника нет вовсе (связь не нашлась) — правило молчит",
  A.pair_unanswered("", {"register_b"}) is False)

# ── Одиночный ответ круга — от соперника, а не от выбора (`single_is_rival`) ────────
t("одиночка — соперник, выбор молчит: отдавать его число — скрытый выбор наугад",
  A.single_is_rival("document_a", "register_b") is True)
t("одиночка — сам выбор модели: ответ законен, дальше проверяет вето",
  A.single_is_rival("document_a", "document_a") is False)
t("выбора не было (пустой picked) — сравнивать не с чем",
  A.single_is_rival("", "register_b") is False)
t("одиночки нет (пустой sole) — правило молчит",
  A.single_is_rival("document_a", "") is False)

# ── Лидер словаря — из неотсеянных (`veto_top_without`) ──────────────────────────────
t("отсеянный лидер пропускается — лидером становится следующий пригодный",
  A.veto_top_without([("a", 9.0), ("b", 8.0)], {"a"}) == [("b", 8.0)])
t("отсеяных нет в вершине — порядок не меняется",
  A.veto_top_without([("a", 9.0), ("b", 8.0)], {"z"}) == [("a", 9.0), ("b", 8.0)])
t("отсеяны все — словарь молчит (пустая вершина)",
  A.veto_top_without([("a", 9.0)], {"a"}) == [])
t("отсев пуст — вершина как была",
  A.veto_top_without([("a", 9.0)], set()) == [("a", 9.0)])

# ── Пустое после фильтра периода ≠ «данных нет» ────────────────────────────────
t("выведенный период + пустые rows — снять догадку, не no_data",
  A.empty_after_period_action({"period": {"from": "2026-05-14"},
                               "parse": {"assumed": ["period.from"]}}) == "drop_assumed")
t("названный период + пустые rows — пустой период, не существование",
  A.empty_after_period_action({"period": {"from": "2026-05-14", "to": "2026-08-14"},
                               "parse": {"assumed": []}}) == "empty_period")
t("периода нет + пустые rows — no_data как прежде",
  A.empty_after_period_action({"period": {}, "parse": {"assumed": []}}) == "no_data")
t("выведенный период уже снят — повторно не снимаем",
  A.empty_after_period_action({"period": {},
                               "parse": {"assumed": ["period.from"]}}) == "no_data")
t("mk_opts: живой счёт 0 не попадает в варианты",
  A.mk_opts(["a", "b"], {"a": "A", "b": "B"}, live={"a": 0, "b": 5})
  == [{"src": "b", "label": "B", "hint": "", "distinct_by": "", "found": 5}])
t("mk_opts: все живые счета 0 — пустой перечень, не выбор из нулей",
  A.mk_opts(["a", "b"], {"a": "A", "b": "B"}, live={"a": 0, "b": 0}) == [])
t("mk_opts без live — found из лексики, как прежде",
  A.mk_opts(["a"], {"a": "A"}, by={"a": 12})[0]["found"] == 12)

print("\n%d прошло, %d упало" % (PASS, len(FAIL)))
for n in FAIL:
    print("  ✗", n)
sys.exit(1 if FAIL else 0)
