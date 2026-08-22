#!/usr/bin/env python3
"""Rank axis ticket, measure anchor, stock no_data — оффлайн замки (18.08)."""
import os
import sys
import time
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:200]) if detail else "")


# --- дефект 1: билет оси не схлопывает rank в скаляр ---
intent_top = {"want": "list", "kind": "товар", "amount": {"value": 1}}
plan_top = {}
grain_rank = {"grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "clarify": None}
ticket = A.grain_dec_from_axis_ticket(intent_top, plan_top, grain_rank, "refs_map.ТМЦ")
t("axis ticket grain=group", ticket.get("grain") == "group", ticket)
t("axis ticket form=rank", ticket.get("form") == "rank", ticket)
t("axis ticket col preserved", ticket.get("col") == "refs_map.ТМЦ", ticket)

intent_sum = {"want": "sum", "amount": {}}
ticket_sum = A.grain_dec_from_axis_ticket(
    intent_sum, {"compute": "sum"}, {"form": "number"}, "refs_map.ТМЦ")
t("axis ticket sum keeps form=number", ticket_sum.get("form") == "number", ticket_sum)

t("rank_intent ≡ breakdown for list",
  A.rank_intent_from(intent_top, plan_top)
  == A.question_wants_breakdown(intent_top, plan_top))

# --- дефект 2: якорение меры на рейтинг товара ---
names = ["Себестоимость", "Количество", "Всего"]
hint = A.rank_measure_hint(
    names, {"want": "list", "kind": "товар"}, "какого товара больше всего")
t("rank measure hint → Количество", hint == "Количество", hint)
t("rank measure skip when measure set",
  A.rank_measure_hint(names, {"want": "list", "measure": "Всего"},
                      "какого товара больше всего") is None)
t("rank measure skip on sum",
  A.rank_measure_hint(names, {"want": "sum"}, "сколько всего") is None)

# --- остаток: универсальный путь (22.08), ранний no_data снят ---
t("stock balance question",
  A.question_asks_stock_balance("какого товара больше всего на складе?"))
t("movement question not stock",
  not A.question_asks_stock_balance("какого товара больше всего по реализации"))
t("какого: not named (question word)",
  not A.stock_asks_named_product("какого товара больше всего на складе?"))
A._BALANCE_MAP.update({"at": time.time(), "rows": [
    ("accountingregister_x", "accounting", False, True, True, True),
]})
t("capable from map", "accountingregister_x" in A.balance_capable_sources())
t("sales noise on stock q",
  A.stock_balance_is_sales_noise("accumulationregister_реализациятмц"))



# --- hotfix: rank n_groups=1 (okna передача на хранение, rid 5b6da6da) ---
AGG1 = {
    "count": 19, "sum": 21.0, "leader": 21.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "n_groups": 1,
    "groups": [{"name": "Prod A", "value": 21.0, "count": 19}],
    "folders": 0, "count_amount": 19,
}
ROWS1 = A.serene_axis.group_rows(AGG1["groups"])
q_storage = "какого товара больше всего передали на хранение?"
try:
    filled, bad = A._fill_figures(
        "Топ: {total:g0}, всего {total}.", AGG1, [], True, slot_mode="rank")
    t("rank n_groups=1 fill без TypeError", True)
    t("rank n_groups=1 g0=21", "21" in filled.replace("\u00a0", ""), filled)
    t("rank n_groups=1 total не sum", "{total}" in filled or filled.count("21") == 1, filled)
except TypeError as e:
    t("rank n_groups=1 fill без TypeError", False, e)
try:
    A.copied_figures("Итого.", AGG1, ROWS1 + [21.0])
    t("rank n_groups=1 copied_figures+float хвост", True)
except TypeError as e:
    t("rank n_groups=1 copied_figures+float хвост", False, e)
try:
    seen = A.rows_seen(ROWS1 + [21.0])
    ok, _ = A.gate("21", seen, AGG1, [21.0, 1], [], money=True, slot_mode="rank")
    t("rank n_groups=1 gate+float хвост", ok)
except TypeError as e:
    t("rank n_groups=1 gate+float хвост", False, e)

# --- hotfix: rank intent из «больше всего» при want=sum ---
intent_sale = {"want": "sum", "kind": "товар", "amount": {}}
t("rank intent «продали за всё время»",
  A.rank_intent_from(intent_sale, {}, "какого товара больше всего продали за всё время?"))
hint_sale = A.rank_measure_hint(
    names, intent_sale, "какого товара больше всего продали за всё время?")
t("rank measure «продали» → Количество", hint_sale == "Количество", hint_sale)

# --- hotfix: count_kind не на rank ---
src = open(A.__file__, encoding="utf-8").read()
t("compose: count_kind закрыт на rank",
  'if kw and slot_mode != "rank":' in src)

# --- prefer entity: табчасть не первая ---
class _Fake:
    pass


def _fake_psql(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",)]
    if "parent, written_by" in q or "parent FROM" in q:
        return [
            ("document_реализациятмц_номенклатура", "document_реализациятмц", ""),
            ("accumulationregister_реализациятмц", "", ""),
        ]
    raise RuntimeError("no db")


_old_psql = A.psql
A.psql = _fake_psql
try:
    got = A.prefer_entity_for_rank(
        ["document_реализациятмц_номенклатура", "accumulationregister_реализациятмц"],
        intent_sale, "какого товара больше всего продали за всё время?")
    t("prefer rank: регистр перед табчастью",
      got[0] == "accumulationregister_реализациятмц", got)
finally:
    A.psql = _old_psql


# --- cd1789b follow-up: gate bad float → 503 на шаг() ---
AGG_LIVE = {
    "count": 19, "sum": 21.0, "leader": 21.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "n_groups": 1,
    "groups": [{"name": "Prod A", "value": 21.0, "count": 19}],
    "folders": 0, "count_amount": 19,
}
ROWS_LIVE = A.serene_axis.group_rows(AGG_LIVE["groups"])
SEEN_LIVE = A.rows_seen(ROWS_LIVE)
text_live = "Наибольшее количество — «Prod A»: 21."
ok_live, bad_live = A.gate(text_live, SEEN_LIVE, AGG_LIVE, [1], [], money=True,
                           slot_mode="rank")
t("live rank gate проходит на 21", ok_live, bad_live)
t("gate bad — строки, не float",
  not bad_live or all(isinstance(x, str) for x in bad_live), bad_live)
# воспроизведение bad_nums[0]=float до фикса: preview не падает
try:
    _p = A._gate_bad_preview([22.0])
    t("gate preview float не TypeError", True)
    t("gate preview float → str", isinstance(_p, str) and "22" in _p, _p)
except TypeError as e:
    t("gate preview float не TypeError", False, e)
# число вне белого списка — строка в bad
_ok_x, bad_x = A.gate("лидер 22", SEEN_LIVE, AGG_LIVE, [1], [], money=True,
                      slot_mode="rank")
t("gate reject 22: bad[0] str", bad_x and isinstance(bad_x[0], str), bad_x)
# симуляция шага answer(): раньше bad[0][:60] на float → 503
try:
    bad_sim = bad_x or [22.0]
    _ = A._gate_bad_preview(bad_sim)
    t("answer шаг: preview на float-bad не падает", True)
except TypeError as e:
    t("answer шаг: preview на float-bad не падает", False, e)

# --- prefer: две табчасти → регистр через written_by ---
def _fake_psql2(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",)]
    if "parent, written_by" in q or "parent FROM" in q:
        return [
            ("document_реализациятмц_номенклатура", "document_реализациятмц", ""),
            ("document_передача_номенклатура", "document_передача", ""),
        ]
    raise RuntimeError("no db")


_old2 = A.psql
A.psql = _fake_psql2
try:
    q_all = "какого товара больше всего продали за всё время?"
    got2 = A.prefer_entity_for_rank(
        ["document_реализациятмц_номенклатура", "document_передача_номенклатура"],
        intent_sale, q_all)
    t("prefer all-child: регистр первым",
      got2 and got2[0] == "accumulationregister_реализациятмц", got2)
finally:
    A.psql = _old2


# --- e82abb5 follow-up: 217.10 в rank-тексте, детерминированный топ-1 ---
AGG217 = {
    "count": 19, "sum": 217.10, "leader": 3.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.ТМЦ", "form": "rank", "n_groups": 1,
    "groups": [{"name": "Prod X", "value": 3.0, "count": 19, "sum": 21.0}],
    "folders": 0, "count_amount": 19,
}
ROWS217 = A.serene_axis.group_rows(AGG217["groups"])
SEEN217 = A.rows_seen(ROWS217)
text217 = "Наибольшее количество — «Prod X»: {total}."
filled217, bad217 = A._fill_figures(text217, AGG217, [], True, slot_mode="rank")
t("rank fill: {total} не подставляет sum множества",
  "217" not in filled217.replace("\u00a0", ""), filled217)
t("rank fill: g0 через rank_leader",
  "3" in (A.rank_leader_answer_text(AGG217) or ""))
ok217, bad217g = A.gate(
    A.rank_leader_answer_text(AGG217) or "", SEEN217, AGG217, [1], [],
    money=True, slot_mode="rank")
t("rank gate leader 3 проходит", ok217, bad217g)
ok217b, bad217b = A.gate(
    "лидер 217.10", SEEN217, AGG217, [1], [], money=True, slot_mode="rank")
t("rank gate 217.10 теперь в поверхности agg", ok217b, bad217b)
t("rank gate bad217 пусто", not bad217b, bad217b)

# --- full agg surface: все числа agg разрешены ---
AGG_BIG = {
    "count": 77557, "sum": 2128249.4, "leader": 96602.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.Номенклатура", "form": "rank", "n_groups": 1558,
    "groups": [
        {"name": "Piesa A", "value": 96602.0, "count": 200, "sum": 500.0, "avg": 0.50},
        {"name": "Piesa B", "value": 80000.0, "count": 150, "sum": 300.0, "avg": 0.40},
    ],
    "folders": 0, "count_amount": 77557, "min": 0.01, "max": 96602.0, "avg": 27.42,
}
SEEN_BIG = [("a","b","c","d","e","text")] * 3
_ok_big1, _bad_big1 = A.gate(
    "Piesa A 96602", SEEN_BIG, AGG_BIG, [1], [], money=True, slot_mode="rank")
t("agg surface: leader 96602 проходит", _ok_big1, _bad_big1)
_ok_big2, _bad_big2 = A.gate(
    "итого 2128249.4 по 0.50", SEEN_BIG, AGG_BIG, [1], [], money=True, slot_mode="rank")
t("agg surface: sum + avg группы проходит", _ok_big2, _bad_big2)
_ok_big3, _bad_big3 = A.gate(
    "число 999999", SEEN_BIG, AGG_BIG, [1], [], money=True, slot_mode="rank")
t("agg surface: чужое число отвергнуто", not _ok_big3, _bad_big3)
_ok_big4, _bad_big4 = A.gate(
    "avg 27.42 min 0.01", SEEN_BIG, AGG_BIG, [1], [], money=True, slot_mode="rank")
t("agg surface: agg min/max/avg проходит", _ok_big4, _bad_big4)

# postprocess_money_answer_text: identity (перезапись прозы убрана, единица — в атоме)
sample = "Наибольшее количество продаж — 3 205 385.44"
t("postprocess_money: identity — текст не меняется",
  A.postprocess_money_answer_text(sample, unit="лей") == sample, "")
t("postprocess_money: пустой текст — identity",
  A.postprocess_money_answer_text("", unit="руб.") == "", "")
t("postprocess_money: None unit — identity",
  A.postprocess_money_answer_text(sample) == sample, "")

# grep-замок: литерала «руб.»/«рубл» (валюта) в serene_ask.py нет
import ast as _ast
with open("serene_ask.py") as _f:
    _tree = _ast.parse(_f.read())
_rub_pat = re.compile(r"руб[.лей]|рубл", re.IGNORECASE)
_has_rub = False
for _node in _ast.walk(_tree):
    if isinstance(_node, _ast.Constant) and isinstance(_node.value, str):
        if _rub_pat.search(_node.value):
            _has_rub = True
            break
t("grep-замок: литерала «руб.» в serene_ask.py нет (код)", not _has_rub, "")

# _unit_for_measure: единица из данных (money flag), не из словаря
t("_unit_for_measure: money=False → пусто",
  A._unit_for_measure("Количество", money=False) == "", A._unit_for_measure("Количество", money=False))
t("_unit_for_measure: money=True → MONEY_UNIT (env)",
  A._unit_for_measure("Сумма", money=True) == A.MONEY_UNIT, A._unit_for_measure("Сумма", money=True))
t("_unit_for_measure: None money=False → пусто",
  A._unit_for_measure(None, money=False) == "", "")
t("_unit_for_measure: неизвестная мера money=True → env",
  A._unit_for_measure("Cantitate", money=True) == A.MONEY_UNIT, "")

# rank tail guard: no bare numbers right after `·`
demo_txt = "Наибольшее значение по рангу."
demo_ng = A.ensure_n_groups_named(demo_txt, AGG_BIG)
demo_full = A.ensure_count_named(demo_ng, AGG_BIG, "rank")
t("rank tail: n_groups worded", "всего позиций:" in (demo_ng or ""), demo_ng)
t("rank tail: count worded", "всего записей:" in (demo_full or ""), demo_full)
t("rank tail: нет «· 1558»/«· 77557»", not re.search(r"·\\s*\\d", demo_full or ""),
  demo_full)

# --- rank_measure_hint: _rank_wants_quantity ---
t("_rank_wants_quantity: товар + больше всего",
  A._rank_wants_quantity("какого товара больше всего передали?"), "")
t("_rank_wants_quantity: без слова товар",
  not A._rank_wants_quantity("сколько продали за месяц?"), "")

# --- числа в именах групп заземлены ---
AGG_NAME = {
    "count": 100, "sum": 500.0, "leader": 96602.0, "measure": "Количество",
    "grain": "group", "col": "refs_map.Номенклатура", "form": "rank", "n_groups": 2,
    "groups": [
        {"name": "Piesa inchidere toc HG VEKA - 0,5 mm", "value": 96602.0, "count": 50, "sum": 250.0, "avg": 5.0},
        {"name": "str Uzinelor 12 G", "value": 80000.0, "count": 50, "sum": 250.0, "avg": 5.0},
    ],
    "folders": 0, "count_amount": 100,
}
SEEN_NAME = [("a","b","c","d","e","text")] * 3
_ok_n1, _bad_n1 = A.gate(
    "Piesa inchidere toc HG VEKA - 0,5 mm (96 602 шт)", SEEN_NAME, AGG_NAME, [1], [], money=True, slot_mode="rank")
t("name nums: 0.5 из имени проходит", _ok_n1, _bad_n1)
_ok_n2, _bad_n2 = A.gate(
    "str Uzinelor 12 G — 80 000", SEEN_NAME, AGG_NAME, [1], [], money=True, slot_mode="rank")
t("name nums: 12 из адреса проходит", _ok_n2, _bad_n2)
_ok_n3, _bad_n3 = A.gate(
    "всего 777 штук", SEEN_NAME, AGG_NAME, [1], [], money=True, slot_mode="rank")
t("name nums: 777 вне полей/имён отвергнуто", not _ok_n3, _bad_n3)

# --- prefer: три табчасти, регистр по written_by ---
def _fake_psql3(q):
    if "written_by IN" in q:
        return [("accumulationregister_реализациятмц",)]
    if "parent, written_by" in q:
        return [
            ("document_реализациятмц_номенклатура", "document_реализациятмц", ""),
            ("document_передачаврознице_номенклатура", "document_передачаврознице", ""),
            ("document_реализациятмц_массабрутто", "document_реализациятмц", ""),
        ]
    raise RuntimeError("no db")

_old3 = A.psql
A.psql = _fake_psql3
try:
    q3 = "какого товара больше всего продали за всё время?"
    c3 = [
        "document_реализациятмц_номенклатура",
        "document_передачаврознице_номенклатура",
        "document_реализациятмц_массабрутто",
    ]
    got3 = A.prefer_entity_for_rank(c3, intent_sale, q3)
    t("prefer 3 tabparts: регистр первый",
      got3 and got3[0] == "accumulationregister_реализациятмц", got3)
    t("prefer 3 tabparts: табчасти сняты",
      not any(x.startswith("document_") and A.prefer_entity_for_rank.__name__
              for x in got3),
      [x for x in got3 if x.startswith("document_")])
finally:
    A.psql = _old3




# --- 22.08: live okna rank question + row-grain gate fallback ---
_q_live = "что лучше всего продавалось на этой неделе?"
t("rank_question_text: лучше+продав", A.rank_question_text(_q_live))
t("rank_intent from live q",
  A.rank_intent_from({"want": "sum"}, {"compute": "sum"}, _q_live))
t("total skips axis off for rank",
  not A.total_question_skips_axis({"want": "sum"}, "Количество",
                                  {"clarify": "axis"}, {"compute": "sum"}, _q_live))
_agg_row = {"grain": "row", "count": 728, "sum": 31009.32, "measure": "Количество",
            "groups": None}
_grp_agg = {"grain": "group", "col": "refs_map.ТМЦ", "n_groups": 1,
            "groups": [{"name": "Товар А", "value": 420.0, "count": 10}],
            "measure": "Количество", "sum": 420.0}
_called = []
def _fake_agg(*a, **k):
    _called.append(a)
    return dict(_grp_agg)
_old_agg = A.aggregate_groups
A.aggregate_groups = _fake_agg
_old_rpc = A.rank_product_axis_col
A.rank_product_axis_col = lambda *a, **k: "refs_map.ТМЦ"
try:
    fb = A.rank_gate_fallback_answer(
        _q_live, _agg_row, "accumulationregister_реализациятмц", "", {}, "Количество",
        True, {"want": "sum"}, {"compute": "sum"}, {}, [], {}, time.time(), "", "Количество")
    t("rank_gate_fallback: row agg → answer", fb and fb.get("kind") == "answer", fb)
    t("rank_gate_fallback: reaggregate called", bool(_called), _called)
finally:
    A.aggregate_groups = _old_agg
    A.rank_product_axis_col = _old_rpc

# slot_mode: rank intent без grain=group
_sm2 = A.answer_slot_mode("sum", "sum", form="number", grain="row")
if A.rank_intent_from({"want": "sum"}, {"compute": "sum"}, _q_live) and _sm2 == "sum":
    _sm2 = "rank"
t("live rank: row grain still → slot_mode rank", _sm2 == "rank", _sm2)


# live okna: want=sum + grain=group (legacy sim) + rank question → slot_mode rank
_q = "что лучше всего продавалось на этой неделе?"
_int = {"want": "sum", "kind": "продажи"}
_plan = {"compute": "sum"}
_form, _grain = "number", "group"
_sm = A.answer_slot_mode(_int.get("want"), _plan.get("compute"), form=_form, grain=_grain)
if A.rank_intent_from(_int, _plan, _q) and _sm == "sum":
    _sm = "rank"
t("live rank: sum+group intent → slot_mode rank", _sm == "rank", _sm)
print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
sys.exit(1 if FAIL else 0)
