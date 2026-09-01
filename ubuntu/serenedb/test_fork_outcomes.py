#!/usr/bin/env python3
"""Исходы A/B/C на классах детектора (план §2, шаг 4).

Замки:
  · A только при полном совпадении атома и нескольких src;
  · B только при всех ветках с подписями и всех ячейках посчитанных;
  · C иначе (непосчитанное / неподписанное);
  · непосчитанная ячейка → не A/B;
  · детерминизм порядка пар на снимке;
  · перестановка пар невозможна (только fill/render по индексу);
  · ASK_FORK_OUTCOMES=0 — эвакуация (флаг читается).

Запуск: python3 ubuntu/serenedb/test_fork_outcomes.py
Без базы, сети и модели (подписи — подменой fork_labels_of).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402

PASS, FAIL = 0, []


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


def fc_sum(rows):
    rel = {s: list((rows[s].get("sums") or {}).keys()) for s in rows}
    return A.fork_classes(rows, "сумма", want="sum", rel_by_src=rel)



# ── resolve_fork_outcome ──────────────────────────────────────────────────────
cls1 = fc_sum({"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)})
rows1 = {"a": row(19, Сумма=100.0), "b": row(19, Сумма=100.0)}
out, pay = A.resolve_fork_outcome(cls1, rows1, measure_ctx="сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("A: один класс, два src", out == "A" and len(pay["srcs"]) == 2)

cls_u = fc_sum({"a": row(19, Сумма=100.0)})
out, pay = A.resolve_fork_outcome(cls_u, {"a": row(19, Сумма=100.0)}, "сумма", want="sum", rel_by_src={"a": ["Сумма"]})
t("unique: один класс, один src", out == "unique")

cls2 = fc_sum({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}


def _labs(fk, srcs):
    return {}


A.fork_labels_of = _labs
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("C: несколько классов без подписей", out == "C" and pay["reason"] == "unsigned_class")


def _labs_ok(fk, srcs):
    return {"a": "Отгрузки", "b": "Оплаты"}


A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("B: несколько классов с подписями",
  out == "B" and len(pay["classes"]) == 2
  and all(c.get("label") for c in pay["classes"]))

# непосчитанная ячейка
unc = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}
cls_u2 = fc_sum(unc)
# подменим атом на uncounted через прямую сборку payload
ordered = A.ordered_fork_classes(cls_u2, unc)
ordered[0]["atom"] = A.build_answer_atom(
    operation="sum", exact_value=None, proof_status=A.PROOF_UNCOUNTED)
# resolve смотрит proof через ordered_fork_classes заново — подменим rows на битый
# через scan_error / прямой путь: atom с None exact
# Проще: пустой sums и count None — но fork_scan так не отдаёт.
# Проверяем правило: uncounted в resolve через atom status.
# Соберём вручную: если atom exact None → C.


def resolve_with_uncounted():
    classes = fc_sum({"a": row(1, Сумма=1.0), "b": row(2, Сумма=2.0)})
    rows = {"a": row(1, Сумма=1.0), "b": row(2, Сумма=2.0)}
    real_of = A.ordered_fork_classes

    def boom(classes, rows, measure_word="", want=None, rel_by_src=None):
        items = real_of(classes, rows, measure_word, want=want)
        items[0]["atom"]["proof_status"] = A.PROOF_UNCOUNTED
        items[0]["atom"]["exact_value"] = None
        return items

    A.ordered_fork_classes = boom
    try:
        return A.resolve_fork_outcome(classes, rows, "сумма")
    finally:
        A.ordered_fork_classes = real_of


out, pay = resolve_with_uncounted()
t("C: непосчитанная ячейка — не A/B", out == "C" and pay["reason"] == "uncounted_cell")

out, pay = A.resolve_fork_outcome({}, {}, "сумма")
t("empty: нет живых ячеек", out == "empty")

out, pay = A.resolve_fork_outcome(None, None, scan_error=RuntimeError("x"))
t("unavailable: ошибка скана", out == "unavailable")

# ── детерминизм порядка ───────────────────────────────────────────────────────
A.fork_labels_of = _labs_ok
o1 = A.ordered_fork_classes(cls2, rows2)
o2 = A.ordered_fork_classes(cls2, rows2)
t("детерминизм ordered_fork_classes",
  [c["srcs"] for c in o1] == [c["srcs"] for c in o2]
  and [c["fingerprint"] for c in o1] == [c["fingerprint"] for c in o2])

# перестановка: B строит пары только через render; порядок = ordered
A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
bres = A.fork_outcome_b("сколько?", pay, {}, picked_src="a")
t("B: text = одна пара лидера (picked=a)",
  bres and bres["kind"] == "figures"
  and len(bres["atoms"]) == 2
  and len(bres["options"]) == 1
  and "Отгрузки" in bres["text"] and "100" in bres["text"]
  and "Оплаты" not in bres["text"] and "200" not in bres["text"])
# порядок текста = порядок atoms = ordered; смешать нельзя API
swapped = "Оплаты: 100"
# exact values: a has 100, b has 200; labels from _labs_ok by src
# after ordered sort by fingerprint — whichever first
t("B: source_fixed/memory_eligible false",
  bres.get("source_fixed") is False and bres.get("memory_eligible") is False)
t("B: options только не-лидерские классы",
  len(bres["options"]) == 1
  and bres["options"][0].get("label") == "Оплаты"
  and all(o.get("src") and o.get("label") for o in bres["options"]))

# §2 B / аудит §6: обе пары в основном тексте (не меню clarify); память только по нажатию
t("B §2: kind=figures, не clarify-меню",
  bres.get("kind") == "figures"
  and "100" in (bres.get("text") or "")
  and "200" not in (bres.get("text") or "")
  and "\n" not in (bres.get("text") or ""))
t("B §2: люк options = N-1, memory_eligible=false (только нажатие)",
  len(bres.get("options") or []) == 1
  and bres.get("memory_eligible") is False
  and bres.get("source_fixed") is False)

# ── лидер люка (контракт 23.08) ───────────────────────────────────────────────
split = A.fork_leader_class("a", pay.get("classes") or [])
t("fork_leader_class: picked в классе a",
  split and split[0].get("label") == "Отгрузки" and len(split[1]) == 1)
t("B: atoms[0] = лидер", bres["atoms"][0].get("measure_label") == "Отгрузки")
t("fork_leader_class: чужой src → None", A.fork_leader_class("z", pay.get("classes") or []) is None)

# ── A: без метки источника ────────────────────────────────────────────────────
out, pay = A.resolve_fork_outcome(cls1, rows1, "сумма")
ares = A.fork_outcome_a("сколько?", pay["class"], {})
t("A: kind=answer, sources пуст, source_fixed=false",
  ares["kind"] == "answer"
  and ares["sources"] == []
  and ares.get("source_fixed") is False
  and ares.get("memory_eligible") is False)
t("A: в тексте нет имён src",
  "document_" not in (ares.get("text") or "")
  and "accumulation" not in (ares.get("text") or ""))

# ── флаг эвакуации ────────────────────────────────────────────────────────────
t("FORK_OUTCOMES умолчание True", A.FORK_OUTCOMES is True)

# ── класс из многих src — одна пара в B-логике (один класс не B) ──────────────
many = {"s%02d" % i: row(5, Сумма=50.0) for i in range(5)}
cls_m = A.fork_classes(many)
out, pay = A.resolve_fork_outcome(cls_m, many, "сумма")
t("много src с одним атомом → A (одна пара), не по источникам",
  out == "A" and len(pay["srcs"]) == 5)



# ── NA: sum-вопрос, нет релевантных величин — не блокирует B ───────────────
na_rows = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0), "c": row(5)}
na_cls = A.fork_classes(na_rows)
A.fork_labels_of = _labs_ok
out, pay = A.resolve_fork_outcome(
    na_cls, na_rows, "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"], "c": []})
t("NA класс не блокирует B",
  out == "B" and len(pay.get("classes") or []) == 2
  and pay.get("na_classes") == 1)
atom_na = A._fork_atom_of(row(5), ["c"], "сумма", want="sum", rel_measures=[])
t("want=sum без rel_measures → NA",
  atom_na.get("proof_status") == A.PROOF_NA)

# лексическая Сумма тождественно 0, живая мера вне rel — NA, не «0», не блокирует B
A.fork_labels_of = _labs_ok
dead0 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0),
         "c": row(50, Сумма=0.0, Количество=5.0)}
out, pay = A.resolve_fork_outcome(
    A.fork_classes(dead0), dead0, "сумма", want="sum",
    rel_by_src={"a": ["Сумма"], "b": ["Сумма"], "c": ["Сумма"]})
t("мёртвая Сумма регистра → NA, B из живых",
  out == "B" and len(pay.get("classes") or []) == 2
  and pay.get("na_classes") == 1)
atom_dead = A._fork_atom_of(row(50, Сумма=0.0, Количество=5.0), ["c"], "сумма",
                           want="sum", rel_measures=["Сумма"])
t("want=sum + тождественный 0 в rel → NA, не computed 0",
  atom_dead.get("proof_status") == A.PROOF_NA
  and atom_dead.get("exact_value") is None)

# ── covering: подписи по src, не только по sha1(ctx) ───────────────────────────
real_cov = A.fork_labels_covering
A.fork_labels_covering = lambda srcs: (
    {"a": "Отгрузки", "b": "Оплаты"}, "fk_cover")
A.fork_labels_of = lambda fk, srcs: {}  # точный ключ пуст
cls2 = fc_sum({"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)})
rows2 = {"a": row(10, Сумма=100.0), "b": row(10, Сумма=200.0)}
out, pay = A.resolve_fork_outcome(cls2, rows2, "сумма", want="sum", rel_by_src={"a": ["Сумма"], "b": ["Сумма"]})
t("B через covering, когда точный fork_key пуст",
  out == "B" and pay.get("fork_key") == "fk_cover")
A.fork_labels_covering = real_cov

# ── want=sum: не count при пустых sums ────────────────────────────────────────
atom_sum = A._fork_atom_of(row(100), ["x"], "сумма", want="sum")
t("want=sum без величин → uncounted, не count",
  atom_sum.get("operation") == "sum"
  and atom_sum.get("exact_value") is None
  and atom_sum.get("proof_status") == A.PROOF_UNCOUNTED)
atom_cnt = A._fork_atom_of(row(100, Сумма=50.0), ["x"], "сумма", want="count")
t("want=count → count, не sum",
  atom_cnt.get("operation") == "count" and atom_cnt.get("exact_value") == 100)

# ── широкий класс: десятки src, одна пара на класс атома ─────────────────────
many_same = {"s%02d" % i: row(5, Сумма=50.0) for i in range(30)}
cls_wide = A.fork_classes(many_same)
t("30 src, один атом → 1 класс",
  len(cls_wide) == 1 and len(next(iter(cls_wide.values()))) == 30)

two_atoms = dict(many_same)
two_atoms["t00"] = row(5, Сумма=99.0)
cls2w = A.fork_classes(two_atoms)
A.fork_labels_of = lambda fk, srcs: {}
A.fork_labels_covering = lambda srcs: (
    {sorted(srcs)[0]: "Класс A", list(cls2w.values())[1][0]: "Класс B"}
    if len(srcs) == 1 else ({}, None))
real_cov = A.fork_labels_covering
def _cov(srcs):
    m = {}
    for ss in cls2w.values():
        rep = sorted(ss)[0]
        if rep in srcs:
            m[rep] = "Класс-%s" % rep
    return m, "fk"
A.fork_labels_covering = _cov
A.fork_labels_of = lambda fk, srcs: {s: "L-%s" % s for s in srcs}
out, pay = A.resolve_fork_outcome(cls2w, two_atoms, "сумма", want="sum")
t("2 класса атомов из 31 src → B с 2 парами, не 31",
  out == "B" and len(pay.get("classes") or []) == 2)
A.fork_labels_covering = real_cov


# ── clarify: человеческая подпись оси (Э3 №7/№10) ─────────────────────────────
_ord_measure = [
    {"srcs": ["doc_a"], "atom": A.build_answer_atom(
        operation="sum", exact_value=100.0, measure_id="Сумма",
        proof_status=A.PROOF_COMPUTED),
     "row": row(10, Сумма=100.0)},
    {"srcs": ["doc_a"], "atom": A.build_answer_atom(
        operation="count", exact_value=10, proof_status=A.PROOF_COMPUTED),
     "row": row(10, Сумма=100.0)},
]
t("clarify axis: sum|count → measure",
  A._fork_clarify_axis_kind(_ord_measure, "Сколько мы закупили товаров?") == "measure")
_mopts = A._fork_clarify_opts(_ord_measure, {}, {}, {}, "", [], {},
                              "measure", "Сколько мы закупили товаров?")
t("clarify measure: 2 варианта по классам", len(_mopts) == 2)
t("clarify measure: needle сумм",
  any("сумм" in (o.get("label") or "").lower() for o in _mopts))
t("clarify measure: needle колич",
  any("колич" in (o.get("label") or "").lower() for o in _mopts))

_ord_place = [
    {"srcs": ["reg_a"], "atom": A.build_answer_atom(
        operation="count", exact_value=5, proof_status=A.PROOF_COMPUTED),
     "row": row(5)},
    {"srcs": ["reg_b"], "atom": A.build_answer_atom(
        operation="count", exact_value=3, proof_status=A.PROOF_COMPUTED),
     "row": row(3)},
]
_stock_intent = {"want": "count", "kind": "номенклатура", "action_class": "object",
                 "action_axis": "склад"}
_old_cats_fork = A.entity_form_catalogs_for_kind
A.entity_form_catalogs_for_kind = lambda w, **kw: (
    ["catalog_склады"] if str(w or "").lower().startswith("склад")
    else ["catalog_номенклатура"])
t("clarify axis: stock question → place",
  A._fork_clarify_axis_kind(_ord_place, "Сколько товара на складе?",
                            intent=_stock_intent) == "place")
A.entity_form_catalogs_for_kind = _old_cats_fork
_old_wh = A.warehouse_axis_values
A.warehouse_axis_values = lambda limit=20: ["Склад A", "Склад B"]
_popts_wh = A._fork_clarify_opts(_ord_place,
                                 {"reg_a": "Товар X", "reg_b": "Товар Y"},
                                 {}, {}, "", [], {}, "place",
                                 "Сколько товара на складе?")
t("clarify place: options = warehouse values",
  len(_popts_wh) == 2
  and {o["label"] for o in _popts_wh} == {"Склад A", "Склад B"})
t("clarify place: not nomenclature in options",
  not any("Товар" in (o.get("label") or "") for o in _popts_wh))
A.warehouse_axis_values = lambda limit=20: ["Only"]
t("clarify place: single warehouse → empty options",
  A._fork_clarify_opts(_ord_place, {}, {}, {}, "", [], {},
                       "place", "q") == [])
A.warehouse_axis_values = _old_wh
_item_place = {"srcs": ["reg_a"], "atom": A.build_answer_atom(
    operation="count", exact_value=5, proof_status=A.PROOF_COMPUTED),
    "row": {"count": 5, "distinct_axis_label": "Филиалы"}}
t("place label from distinct_axis_label",
  A._fork_human_place_label("q", class_item=_item_place) == "Филиалы")
t("place label fallback neutral ru",
  A._fork_human_place_label("сколько?", class_item={"row": {}, "atom": {}})
  == "место хранения")
A.warehouse_axis_values = lambda limit=20: []
t("clarify place: empty warehouse list → no options",
  A._fork_clarify_opts(_ord_place, {}, {}, {}, "", [], {},
                       "place", "q") == [])
A.warehouse_axis_values = _old_wh

# ── complement guard (K6/C4) ──────────────────────────────────────────────────
_row_dist = {"count": 43, "folders": 0, "sums": {},
             "distinct_axis": "AxisX", "distinct_axis_label": "Wrong axis"}
_int_neg = {"want": "count", "action_class": "event", "kind": "items",
            "period": {"from": "2026-08-01", "to": "2026-08-28"}}
_q_neg = "how many items were not sold this month"
_cls_dist = A.fork_classes(
    {"reg_a": _row_dist}, want="count", rel_by_src={"reg_a": []})
out_c_comp, pay_c_comp = A.resolve_fork_outcome(
    _cls_dist, {"reg_a": _row_dist}, want="count", rel_by_src={"reg_a": []},
    intent=_int_neg, question=_q_neg)
t("complement guard blocks positive distinct",
  out_c_comp == "C" and pay_c_comp.get("reason") == "complement_unresolved")

# [замер 29.08, живой okna] event_code_lock + writer_pair, complement-формы NA,
# отрицание в вопросе — без intent/question в resolve_fork_outcome ушло в B/figures.
_q_live = "сколько позиций совсем не продаётся в этом месяце?"
_int_live = {"want": "count", "action_class": "event", "kind": "позиции",
             "period": {"from": "2026-08-01", "to": "2026-08-29"}}
_row_reg = {"count": 43, "folders": 0, "sums": {},
            "distinct_axis": "AxisX", "distinct_axis_label": "Axis label"}
_row_doc = {"count": 49, "folders": 0, "sums": {},
            "distinct_axis": "AxisX", "distinct_axis_label": "Axis label"}
_rows_live = {"accumulationregister_x": _row_reg, "document_y": _row_doc}
_rel_live = {"accumulationregister_x": [], "document_y": []}
_cls_live = A.fork_classes(_rows_live, want="count", rel_by_src=_rel_live)
_old_fl = A.fork_labels_of
A.fork_labels_of = lambda fk, srcs, *a, **k: {s: "Period label" for s in srcs}
out_live, pay_live = A.resolve_fork_outcome(
    _cls_live, _rows_live, want="count", rel_by_src=_rel_live,
    intent=_int_live, question=_q_live)
t("live diag: negation+event lock path → C not B",
  out_live == "C" and pay_live.get("reason") == "complement_unresolved")
out_live_na, _ = A.resolve_fork_outcome(
    _cls_live, _rows_live, want="count", rel_by_src=_rel_live)
t("live diag: without intent/question guard absent → B",
  out_live_na == "B")
A.fork_labels_of = _old_fl

_atom_comp = A._fork_atom_of(
    {"count": 1891, "folders": 0, "sums": {}, "form": "complement",
     "complement_axis_label": "Items"},
    ["catalog_a"], want="count")
t("complement atom form preserved",
  _atom_comp.get("form") == "complement"
  and _atom_comp.get("exact_value") == 1891)

# ── K2: partial B при недосчитанной day-basis ветке (карта оси пуста) ───────
_real_map_ready = A.calendar_axis_map_ready
A.calendar_axis_map_ready = lambda: False
_p_cal = {"from": "2026-08-01", "to": "2026-08-15",
          "interpretation_id": "explicit", "day_basis": "calendar_days"}
_p_work = dict(_p_cal, day_basis="working_days")
_item_cal = {
    "srcs": ["reg_x"],
    "atom": A.build_answer_atom(
        operation="sum", exact_value=100.0, measure_id="Сумма",
        proof_status=A.PROOF_COMPUTED, period=_p_cal),
    "period": _p_cal,
    "row": row(10, Сумма=100.0),
    "fingerprint": ("cal",),
}
_item_work = {
    "srcs": ["reg_x"],
    "atom": A.build_answer_atom(
        operation="sum", exact_value=None, measure_id="Сумма",
        proof_status=A.PROOF_UNCOUNTED, period=_p_work),
    "period": _p_work,
    "row": row(0),
    "fingerprint": ("work",),
}
_real_of = A.ordered_fork_classes


def _ord_partial(_c, _r, measure_word="", want=None, rel_by_src=None):
    return [_item_cal, _item_work]


A.ordered_fork_classes = _ord_partial
A.fork_labels_of = lambda fk, srcs: (
    {"calendar_days": "lbl-cal", "working_days": "lbl-work"}
    if "calendar_days" in (srcs or []) or "working_days" in (srcs or []) else {})
A.fork_labels_covering = lambda srcs: (
    ({"calendar_days": "lbl-cal", "working_days": "lbl-work"}, "fk-db")
    if set(srcs or []) & {"calendar_days", "working_days"} else ({}, None))
out_pb, pay_pb = A.resolve_fork_outcome(
    {"x": {"reg_x"}}, {"reg_x": row(10, Сумма=100.0)},
    measure_ctx="summa", want="sum", rel_by_src={"reg_x": ["Сумма"]},
    today="2026-08-29")
t("partial B: axis missing → B not C",
  out_pb == "B" and pay_pb.get("partial_axis"))
bres_pb = A.fork_outcome_b("q", pay_pb, {}, picked_src="reg_x", today="2026-08-29")
t("partial B: leader number in text",
  bres_pb and bres_pb.get("kind") == "figures"
  and "100" in (bres_pb.get("text") or ""))
t("partial B: люк working label",
  bres_pb and any(
      (o.get("label") or "") == "lbl-work"
      for o in (bres_pb.get("options") or [])))
A.ordered_fork_classes = _real_of
A.calendar_axis_map_ready = _real_map_ready

# clarify day-basis: подписи из §7 в options
_ord_db = [_item_cal, {
    "srcs": ["reg_x"],
    "atom": A.build_answer_atom(
        operation="sum", exact_value=80.0, measure_id="Сумма",
        proof_status=A.PROOF_COMPUTED, period=_p_work),
    "period": _p_work,
    "row": row(8, Сумма=80.0),
}]
_copts = A._fork_clarify_opts(
    _ord_db, {}, {}, {}, "", [], {}, "period", "Сколько отгрузили с 1 по 15",
    measure_ctx="summa")
t("clarify day-basis: 2 options", len(_copts) == 2)
t("clarify day-basis: needle lbl-work",
  any("lbl-work" in (o.get("label") or "") for o in _copts))

# 🔴 [замер 01.09 okna] uncounted_cell: числа нет — меню из непосчитанного
# не показываем (п. 21: отвечать нечем → честный отказ, а не переспрос).
# Живой случай: «остатки по каждому складу отдельно» без регистров остатков.
_c_res = A.fork_outcome_c(
    "остатки по каждому складу отдельно",
    {"reason": "uncounted_cell", "uncounted": [{"srcs": ["reg_a", "reg_b"]}]},
    {}, {}, {}, picked_src=None, today="2026-09-01")
t("uncounted_cell → no_data (не меню)",
  _c_res and _c_res.get("kind") == "no_data"
  and not (_c_res.get("options") or []))
t("uncounted_cell: диагноз несёт причину",
  (_c_res.get("diag") or {}).get("fork_c_reason") == "uncounted_cell")

print()
if FAIL:
    print("ПРОВАЛЕНО:", len(FAIL), "из", PASS + len(FAIL), FAIL)
    sys.exit(1)
print("все", PASS, "проверок зелёные")
