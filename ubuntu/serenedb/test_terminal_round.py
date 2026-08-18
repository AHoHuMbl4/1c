#!/usr/bin/env python3
"""Терминальный второй круг: снятые уровни не теряются, ось только для разреза."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, ("| " + str(detail)[:160]) if detail else "")


A.reset_decisions_for_tests()
Q = "сколько продали вчера всего?"
USER = "web:test"

intent_sum = {"want": "sum", "amount": {}}
intent_top = {"want": "list", "amount": {"value": 5}}
grain_axis = {"clarify": "axis", "grain": "row", "form": "number"}

t("«всего» + sum → skip axis",
  A.total_question_skips_axis(intent_sum, "Всего", grain_axis,
                              {"compute": "sum"}, Q))
t("top-5 → axis не skip",
  not A.total_question_skips_axis(intent_top, None, grain_axis,
                                  {}, "топ-5 товаров по продажам"))
t("want=list → breakdown", A.question_wants_breakdown(intent_top))
t("sum без amount → не breakdown",
  not A.question_wants_breakdown(intent_sum, {"compute": "sum"}))

A.reset_decisions_for_tests()
ent_opts = [
    {"src": "document_a", "label": "Док A", "found": 10},
    {"src": "register_b", "label": "Рег B", "found": 5},
]
sealed_e = A.seal_clarify({"kind": "clarify", "text": "?", "options": ent_opts}, Q,
                          user=USER)
id_e = sealed_e["options"][0]["decision_id"]
ticket_e, err = A.consume_decision(id_e, Q, user=USER)
A.accumulate_resolution(Q, USER, ticket_e)
resolved = A.peek_resolved(Q, USER)
t("entity → src в resolved", resolved.get("src") == "document_a")

meas_opts = [
    {"src": "register_b", "measure": "Всего", "label": "сумма", "distinct_by": ""},
    {"src": "register_b", "measure": "Количество", "label": "кол-во", "distinct_by": ""},
]
sealed_m = A.seal_clarify({"kind": "clarify", "text": "?", "options": meas_opts}, Q,
                          user=USER)
id_m = sealed_m["options"][0]["decision_id"]
ticket_m, err = A.consume_decision(id_m, Q, user=USER)
A.accumulate_resolution(Q, USER, ticket_m)
resolved2 = A.peek_resolved(Q, USER)
t("entity+measure: src сохранён", resolved2.get("src") == "register_b")
t("entity+measure: measure сохранена", resolved2.get("measure") == "Всего")
t("measure_already_proven после цепочки", A.measure_already_proven(None, resolved2))

axis_opts = [
    {"src": "register_b", "label": "Контрагенты", "distinct_by": "Контрагент"},
    {"src": "register_b", "label": "Договоры", "distinct_by": "Договор"},
]
sealed_a = A.seal_clarify({"kind": "clarify", "text": "?", "options": axis_opts}, Q,
                          user=USER)
id_a = sealed_a["options"][0]["decision_id"]
ticket_a, err = A.consume_decision(id_a, Q, user=USER)
A.accumulate_resolution(Q, USER, ticket_a)
resolved3 = A.peek_resolved(Q, USER)
t("после axis measure не потеряна",
  resolved3.get("measure") == "Всего" and resolved3.get("axis") == "Контрагент")
t("choice_levels: entity+measure+axis",
  A.choice_levels_proven(None, resolved3) == {"entity", "measure", "axis"})

A.reset_decisions_for_tests()
calls = []

def _core_stub(question, focus=None, measure_pick=None, context="", prior=None,
               trusted=None, resolved=None):
    calls.append({"focus": focus, "measure_pick": measure_pick,
                  "resolved": dict(resolved or {}), "trusted": trusted})
    if not (resolved or {}).get("measure"):
        return {"kind": "clarify", "text": "мера?", "options": meas_opts,
                "sources": [], "partial": None}
    return {"kind": "answer", "text": "766510.44", "sources": ["x"],
            "partial": None, "diag": {}}

old_core = A._answer_checked_core
A._answer_checked_core = _core_stub
try:
    out1 = A.answer_checked(Q, decision_id=id_e, user=USER)
    t("шаг1 entity → clarify measure", out1.get("kind") == "clarify")
    sealed_m2 = A.seal_clarify(out1, Q, user=USER)
    id_m2 = sealed_m2["options"][0]["decision_id"]
    out2 = A.answer_checked(Q, decision_id=id_m2, user=USER)
    t("шаг2 measure → answer", out2.get("kind") == "answer" and len(calls) == 2)
    c2 = calls[1]
    t("шаг2: measure из resolved/билета",
      c2["measure_pick"] == "Всего" or c2["resolved"].get("measure") == "Всего")
finally:
    A._answer_checked_core = old_core

# Класс F, rid 83ca8b22 / 13:23: третий hop не меняет снятую сущность.
REG = "accumulationregister_реализациятмц"
PKO = "document_приходныйкассовыйордер"
FIZ = "document_выручкаотреализациитмцфизлицо_номенклатура"
DOC = "document_реализациятмц"
FOUND = {REG: 331, PKO: 4, FIZ: 0, DOC: 10}

t("(а) entity+measure + focus=ПКО → регистр",
  A.hold_settled_entity(PKO, None, {"src": REG, "measure": "Всего"},
                        found_by=FOUND) == REG)
t("(а) entity+measure + focus=физлицо → регистр",
  A.hold_settled_entity(FIZ, None, {"src": REG, "measure": "Всего"},
                        found_by=FOUND) == REG)
t("(б) документ + держатель ПКО → документ",
  A.hold_settled_entity(PKO, None, {"src": DOC},
                        found_by=FOUND, holder_srcs=[PKO]) == DOC)
t("(в) регистр 331 + физлицо 0 → регистр",
  A.hold_settled_entity(FIZ, None, {"src": REG}, found_by=FOUND) == REG)
t("без settled focus не трогаем",
  A.hold_settled_entity(DOC, None, {}, found_by=FOUND) == DOC)
t("entity_choice_locked по resolved.src",
  A.entity_choice_locked(None, {"src": REG}))
t("нулевой кандидат режется, если кто-то жив",
  A.keep_empty_period_opts([REG, FIZ], FOUND, ["doc_date >= 'x'"]) == [REG])

A.reset_decisions_for_tests()
ent_opts_f = [
    {"src": REG, "label": "Реализация ТМЦ (регистр)", "found": 331},
    {"src": DOC, "label": "Реализация ТМЦ (документ)", "found": 10},
]
sealed_ef = A.seal_clarify({"kind": "clarify", "text": "?", "options": ent_opts_f},
                           Q, user=USER)
id_ef = sealed_ef["options"][0]["decision_id"]
ticket_ef, _err = A.consume_decision(id_ef, Q, user=USER)
A.accumulate_resolution(Q, USER, ticket_ef)
meas_opts_f = [
    {"src": REG, "measure": "Всего", "label": "итого", "distinct_by": ""},
    {"src": REG, "measure": "Количество", "label": "кол-во", "distinct_by": ""},
]
sealed_mf = A.seal_clarify({"kind": "clarify", "text": "?", "options": meas_opts_f},
                           Q, user=USER)
id_mf = sealed_mf["options"][0]["decision_id"]
ticket_mf, _err = A.consume_decision(id_mf, Q, user=USER)
A.accumulate_resolution(Q, USER, ticket_mf)

calls_f = []


def _core_f(question, focus=None, measure_pick=None, context="", prior=None,
            trusted=None, resolved=None):
    calls_f.append(focus)
    if focus in (PKO, FIZ, DOC) and (resolved or {}).get("src") == REG:
        return {"kind": "clarify", "text": "касса?", "options": [
            {"src": PKO, "label": "ПКО", "found": 4}], "sources": [], "partial": None}
    return {"kind": "answer", "text": "766578.68", "sources": ["x"],
            "partial": None, "diag": {}}


old_core2 = A._answer_checked_core
A._answer_checked_core = _core_f
try:
    out_hop = A.answer_checked(Q, focus=PKO, user=USER)
    t("шаг3 rid-рисунок: hop ПКО после entity+measure → answer",
      out_hop.get("kind") == "answer" and len(calls_f) == 1, out_hop.get("kind"))
    t("шаг3: в core ушёл регистр, не ПКО", calls_f[0] == REG, calls_f)
    out_fiz = A.answer_checked(Q, focus=FIZ, user=USER)
    t("шаг3 rid-рисунок: hop физлицо 0 → answer",
      out_fiz.get("kind") == "answer", out_fiz.get("kind"))
    t("шаг3: физлицо не прошёл в core", calls_f[-1] == REG, calls_f)
finally:
    A._answer_checked_core = old_core2

print()
if FAIL:
    print("ИТОГ: FAIL — %d из %d: %s" % (len(FAIL), len(FAIL) + PASS, "; ".join(FAIL)))
    sys.exit(1)
print("ИТОГ: ok — все %d проверок прошли" % PASS)
