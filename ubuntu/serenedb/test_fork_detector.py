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

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL))
    sys.exit(1)
print("все", PASS, "проверок зелёные")
