#!/usr/bin/env python3
"""Оффлайн-пробы чистых функций детектора развилки (shadow, включён по умолчанию).

Детектор (`PLAN_ANSWER_CONTRACT` §3) считает полный круг одним SQL и сводит ячейки в
классы эквивалентности типизированным атомом. Здесь проверяется та часть, которая не
требует базы: сведение в классы (`fork_classes`) и выбор относящихся величин
(`_fork_relevant`, тем же `measure_choice`, что выбор величины ответа).

Запуск:  python3 ubuntu/serenedb/test_fork_detector.py
Без базы, сети и вызовов модели.
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


def row(n, folders=0, **sums):
    return {"count": n, "folders": folders, "sums": sums}


_MW = "сумма"
_REL_SUM = lambda names: {s: list(names) for s in names}


# ── fork_classes: классы по AnswerAtom без src ────────────────────────────────
t("одинаковый атом у двух src — один класс (A, согласие)",
  len(A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)},
                     _MW, want="sum",
                     rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})) == 1)
t("разные суммы — два класса (развилка видна кодом)",
  len(A.fork_classes({"a": row(19, Сумма=100.0), "b": row(19, Сумма=200.0)},
                     _MW, want="sum",
                     rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})) == 2)
t("разный счёт — два класса (count)",
  len(A.fork_classes({"a": row(19), "b": row(20)}, want="count")) == 2)
t("папки — дискриминатор для count: 19 записей ≠ 19 групп",
  len(A.fork_classes({"a": row(19, 0), "b": row(19, 5)}, want="count")) == 2)
t("копейка в сумме — округление round 2, один класс",
  len(A.fork_classes({"a": row(1, Сумма=100.001), "b": row(1, Сумма=100.004)},
                     _MW, want="sum",
                     rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})) == 1)
t("копейка расхождения — разные классы, допуска нет",
  len(A.fork_classes({"a": row(1, Сумма=100.0), "b": row(1, Сумма=100.01)},
                     _MW, want="sum",
                     rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})) == 2)
t("величины с разными именами не схлопываются: разные атомы",
  len(A.fork_classes({"a": row(1, Сумма=5.0), "b": row(1, Стоимость=5.0)},
                     _MW, want="sum",
                     rel_by_src={"a": ["Сумма"], "b": ["Стоимость"]})) == 2)
t("src в атом не входит: три src с одним атомом — один класс из трёх",
  len(A.fork_classes({"a": row(7), "b": row(7), "c": row(7)}, want="count")) == 1
  and sorted(next(iter(A.fork_classes(
      {"a": row(7), "b": row(7), "c": row(7)}, want="count").values()))) == ["a", "b", "c"])
t("пустой круг — классов нет", A.fork_classes({}) == {})

# ── Живой okna 19.08: writer_pair document_реализациятмц + register, same Всего ─
# SQL: обе ветки 49155.96 за день; count/folders разли — не разный ответ (§3).
DOC = "document_реализациятмц"
REG = "accumulationregister_реализациятмц"
LIVE_SUM = 49155.96
rows_live = {DOC: row(824, folders=2, Всего=LIVE_SUM),
             REG: row(156, folders=0, Всего=LIVE_SUM)}
rel_live = {DOC: ["Всего"], REG: ["Всего"]}
cls_live = A.fork_classes(rows_live, "", want="sum", rel_by_src=rel_live)
t("live okna: doc+reg same Всего, diff count → 1 class", len(cls_live) == 1)
fp_live = next(iter(cls_live))
t("live okna: fp поля = op/status/value/measure_id",
  fp_live[:3] == ("sum", A.PROOF_COMPUTED, round(LIVE_SUM, 2))
  and fp_live[3] == "Всего")
out_live, pay_live = A.resolve_fork_outcome(
    cls_live, rows_live, measure_ctx="", want="sum", rel_by_src=rel_live)
t("live okna: resolve_fork_outcome → A", out_live == "A" and len(pay_live.get("srcs") or []) == 2)

# Замок prod-пути: measure пуст, want=sum — rel не [], атом computed, не NA при SQL-сумме
_mbs_live = {DOC: ["Всего", "СуммаНДС", "СуммаОплатыКарточкой"],
             REG: ["Всего", "Сумма", "Количество"]}
_rel_prod = {c: A._fork_relevant("", _mbs_live.get(c) or [], {}, want="sum") for c in rows_live}
t("prod: want=sum без measure → rel содержит Всего",
  _rel_prod[DOC] == ["Всего"] and _rel_prod[REG] == ["Всего"])
atom_prod = A._fork_atom_of(rows_live[DOC], [DOC], "", want="sum",
                            rel_measures=_rel_prod[DOC])
t("prod: sum посчитана + rel Всего → computed, не NA",
  atom_prod.get("proof_status") == A.PROOF_COMPUTED
  and atom_prod.get("exact_value") == LIVE_SUM
  and atom_prod.get("measure_id") == "Всего")
cls_prod = A.fork_classes(rows_live, "", want="sum", rel_by_src=_rel_prod)
out_prod, pay_prod = A.resolve_fork_outcome(
    cls_prod, rows_live, measure_ctx="", want="sum", rel_by_src=_rel_prod)
t("prod: writer_pair classes=1 → outcome A, не empty",
  out_prod == "A" and pay_prod.get("reason") is None)
t("regression: rel=[] при want=sum и Всего в row — NA (контроль связки)",
  A._fork_atom_of(rows_live[DOC], [DOC], "", want="sum", rel_measures=[]).get("proof_status")
  == A.PROOF_NA)
cls_na = A.fork_classes(rows_live, "", want="sum", rel_by_src={DOC: [], REG: []})
out_na, pay_na = A.resolve_fork_outcome(
    cls_na, rows_live, "", want="sum", rel_by_src={DOC: [], REG: []})
t("offline: no_applicable_cells → outcome_reason + na_classes",
  out_na == "empty" and pay_na.get("reason") == "no_applicable_cells"
  and pay_na.get("na_classes") == 1)

# Живой путь 21.08: intent.величина="продали" (глагол), не "" — af935cc не ловил
_rel_verb = {c: A._fork_relevant("продали", _mbs_live.get(c) or [], {}, want="sum")
             for c in rows_live}
t("prod: word=продали want=sum → rel Всего (не [])",
  _rel_verb[DOC] == ["Всего"] and _rel_verb[REG] == ["Всего"])
atom_verb = A._fork_atom_of(rows_live[DOC], [DOC, REG], "продали", want="sum",
                            rel_measures=_rel_verb[DOC])
t("prod: продали + Всего в row → COMPUTED 49155.96, не NA",
  atom_verb.get("proof_status") == A.PROOF_COMPUTED
  and atom_verb.get("exact_value") == LIVE_SUM
  and atom_verb.get("measure_id") == "Всего")
cls_verb = A.fork_classes(rows_live, "продали", want="sum", rel_by_src=_rel_verb)
out_verb, pay_verb = A.resolve_fork_outcome(
    cls_verb, rows_live, measure_ctx="продали", want="sum", rel_by_src=_rel_verb)
t("prod: продали writer_pair → outcome A",
  out_verb == "A" and len(pay_verb.get("srcs") or []) == 2)
t("NA: себестоимость названа, у источника нет → rel=[]",
  A._fork_relevant("себестоимость", _mbs_live[DOC], {}, want="sum") == [])
atom_sebes = A._fork_atom_of(rows_live[DOC], [DOC], "себестоимость", want="sum",
                             rel_measures=[])
t("NA: себестоимость + rel=[] → PROOF_NA",
  atom_sebes.get("proof_status") == A.PROOF_NA)

# разный смысл (склад) — классы не схлопываются
t("разный sum — два класса (контроль §11)",
  len(A.fork_classes(
      {"inv": row(10, Количество=100.0), "xfer": row(10, Количество=50.0)},
      "количество", want="sum",
      rel_by_src={"inv": ["Количество"], "xfer": ["Количество"]})) == 2)

# ── _fork_relevant ────────────────────────────────────────────────────────────
t("точное совпадение слова — одна величина",
  A._fork_relevant("сумма", ["Сумма", "СуммаНДС"], {}) == ["Сумма"])
t("слова нет — величин в атоме нет (не sum)",
  A._fork_relevant("", ["Сумма"], {}) == [])
t("want=sum без слова — headline Всего в rel",
  A._fork_relevant("", ["Сумма", "Всего"], {}, want="sum") == ["Всего"])
t("want=sum без слова — fallback на все имена, если нет headline",
  A._fork_relevant("", ["Сумма"], {}, want="sum") == ["Сумма"])
t("want=sum + продали → headline Всего",
  A._fork_relevant("продали", ["Сумма", "Всего", "Количество"], {}, want="sum")
  == ["Всего"])
t("want=sum + себестоимость без поля → [] (NA)",
  A._fork_relevant("себестоимость", ["Сумма", "Всего"], {}, want="sum") == [])
t("величин нет — атом по счёту",
  A._fork_relevant("сумма", [], {}) == [])
t("несколько подходящих — все в атом (как measure_alts)",
  sorted(A._fork_relevant("цена", ["ЦенаЗакупки", "ЦенаПродажи"], {}))
  == ["ЦенаЗакупки", "ЦенаПродажи"])

# ── _fork_headline_measure ────────────────────────────────────────────────────
_zakup_doc = {
    "СуммаДокумента": 73181157.68,
    "СуммаВзаиморасчетов": 71045277.59,
    "СуммаВзаиморасчетовПоЗаказу": 0.0,
    "СуммаВзаиморасчетовПоТаре": 11964.0,
}
t("headline: document_* + «сумма» → СуммаДокумента, не Взаиморасчетов",
  A._fork_headline_measure("document_приобретениетоваровуслуг", _zakup_doc, "сумма")
  == "СуммаДокумента")
t("_fork_atom_of: exact_value = СуммаДокумента",
  A._fork_atom_of(row(249, **_zakup_doc),
                  ["document_приобретениетоваровуслуг"], "сумма")["exact_value"]
  == 73181157.68)
t("headline: document_* без *Документа → Всего",
  A._fork_headline_measure("document_отгрузка",
      {"Всего": 79435925.51, "СуммаНДС": 1.0, "СуммаОплатыКарточкой": 2.0},
      "сумма") == "Всего")
t("headline: Всего раньше единственного substring СуммаБезНДС",
  A._fork_headline_measure(
      "document_выручкаотреализациитмцфизлицо_номенклатура",
      {"Всего": 1572493.22, "СуммаБезНДС": 1310413.93}, "сумма") == "Всего")
t("headline: одна величина — она",
  A._fork_headline_measure("accumulationregister_закупки", {"Сумма": 1137949.71}, "сумма")
  == "Сумма")

_reg_sums = {"Сумма": 0.0, "Всего": 79925955.81}
_live = A._fork_answering_sums(_reg_sums, ["Сумма", "Всего"])
t("answering_sums: мёртвая Сумма выбывает, Всего остаётся",
  _live == {"Всего": 79925955.81})
t("headline регистра по живым: Всего, не Сумма=0",
  A._fork_headline_measure("accumulationregister_реализациятмц", _live, "сумма")
  == "Всего")
t("answering_sums: живая мера вне rel не входит",
  A._fork_answering_sums({"Сумма": 0.0, "Количество": 5.0}, ["Сумма"]) == {})
t("headline: «количество» не берёт Всего",
  A._fork_headline_measure(
      "accumulationregister_реализациятмц",
      {"Всего": 79925955.81, "Количество": 100.0}, "количество")
  == "Количество")
t("headline регистра: Всего раньше точной живой Сумма (sum-слово)",
  A._fork_headline_measure(
      "accumulationregister_реализациятмц",
      {"Сумма": 1.0, "Всего": 79925955.81}, "сумма") == "Всего")

# п.13: src пула без живой ячейки — явная причина, не молчание
t("excluded: pool src без row → no_live_cells",
  A._fork_pool_excluded(["a", "b", "c"], {"a": row(1), "b": row(2)})
  == [{"src": "c", "reason": "no_live_cells"}])
t("excluded: все живые → []",
  A._fork_pool_excluded(["a", "b"], {"a": row(1), "b": row(2)}) == [])

# clarify: ось из классов fork (Э3 measure)
_ord_ax = [
    {"srcs": ["a"], "atom": A.build_answer_atom(
        operation="sum", exact_value=100.0, measure_id="Сумма",
        proof_status=A.PROOF_COMPUTED),
     "row": row(10, Сумма=100.0)},
    {"srcs": ["a"], "atom": A.build_answer_atom(
        operation="count", exact_value=10, proof_status=A.PROOF_COMPUTED),
     "row": row(10, Сумма=100.0)},
]
t("fork detector: sum|count classes → measure axis",
  A._fork_clarify_axis_kind(_ord_ax, "Сколько мы закупили товаров?") == "measure")

# ── complement / отрицание (K6, C4) ───────────────────────────────────────────
_q_pos = "сколько позиций продавалось в этом месяце"
_q_neg = "сколько позиций совсем не продаётся в этом месяце"
_int_pos = {"want": "count", "action_class": "event", "kind": "positions",
            "period": {"from": "2026-08-01", "to": "2026-08-28"}}
_int_neg = dict(_int_pos)
t("complement: negation detected structurally",
  A.intent_fact_complement(_int_neg, _q_neg) is True)
t("complement: positive event not complement",
  A.intent_fact_complement(_int_pos, _q_pos) is False)
# [замер 29.08, живой okna] «сколько позиций совсем не продаётся» разбирается
# как object (предмет), а не event: object-класс не должен снимать отрицание,
# иначе позитивное чтение молча подменяет вопрос (43 · Контрагенты).
_int_neg_obj = dict(_int_neg, action_class="object")
t("complement: object-class with negation still complement",
  A.intent_fact_complement(_int_neg_obj, _q_neg) is True)

_row_dist_wrong = {"count": 43, "folders": 0, "sums": {},
                   "distinct_axis": "Counterparty",
                   "distinct_axis_label": "Counterparties"}
_rows_neg = {
    "accumulationregister_sales": _row_dist_wrong,
    "catalog_product": {"count": 2000, "folders": 0, "sums": {}},
}
_rel_neg = {"accumulationregister_sales": [], "catalog_product": []}
_enr_neg = A._fork_enrich_event_rows(
    _int_neg, "", ["doc_date >= '2026-08-01'"], _rows_neg, _rel_neg, question=_q_neg)
t("complement enrich: no distinct_axis on movement",
  "distinct_axis" not in (_enr_neg.get("accumulationregister_sales") or {}))
t("complement enrich: movement suppressed",
  (_enr_neg.get("accumulationregister_sales") or {}).get(
      "_complement_positive_suppressed") is True)

_old_flag = A.ASK_ENTITY_FORM
_old_efc = A.entity_form_compute
_old_efs = A.entity_form_structs
_old_appl = A.entity_form_applicable
_old_exp = A.entity_form_expand_pool
A.ASK_ENTITY_FORM = True
A.entity_form_expand_pool = lambda p, intent=None: list(p or [])
A.entity_form_applicable = lambda intent, pool: True
A.entity_form_structs = lambda intent, pool, today=None: [(
    "complement", {
        "catalog_src": "catalog_product",
        "sales_src": "accumulationregister_sales",
        "axis": "Product",
        "period": _int_neg["period"],
    })]
A.entity_form_compute = lambda form, meta, match="": A.entity_form_atom_complement(
    catalog_src=meta["catalog_src"], sales_src=meta["sales_src"],
    axis=meta["axis"], catalog_n=2000, distinct_n=109, period=meta.get("period"))
try:
    _enr_comp = A._fork_enrich_event_rows(
        _int_neg, "", ["doc_date >= '2026-08-01'"], _rows_neg, _rel_neg,
        question=_q_neg)
    t("complement enrich: catalog row form=complement",
      (_enr_comp.get("catalog_product") or {}).get("form") == "complement"
      and (_enr_comp.get("catalog_product") or {}).get("count") == 1891.0)
    _cls_comp = A.fork_classes(_enr_comp, "", want="count", rel_by_src=_rel_neg)
    _out_comp, _pay_comp = A.resolve_fork_outcome(
        _cls_comp, _enr_comp, want="count", rel_by_src=_rel_neg,
        intent=_int_neg, question=_q_neg)
    t("complement resolve: unique/A not misread B",
      _out_comp in ("unique", "A")
      and ((_pay_comp.get("class") or {}).get("atom") or {}).get("form")
          == "complement")
finally:
    A.ASK_ENTITY_FORM = _old_flag
    A.entity_form_compute = _old_efc
    A.entity_form_structs = _old_efs
    A.entity_form_applicable = _old_appl
    A.entity_form_expand_pool = _old_exp

_cls_mis = A.fork_classes(
    {"accumulationregister_x": _row_dist_wrong}, want="count",
    rel_by_src={"accumulationregister_x": []})
_out_mis, _pay_mis = A.resolve_fork_outcome(
    _cls_mis, {"accumulationregister_x": _row_dist_wrong},
    want="count", rel_by_src={"accumulationregister_x": []},
    intent=_int_neg, question=_q_neg)
t("complement guard: distinct-only → C not unique",
  _out_mis == "C" and _pay_mis.get("reason") == "complement_unresolved")

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    sys.exit(1)
print("все", PASS, "проверок зелёные")
