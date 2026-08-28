#!/usr/bin/env python3
"""Rank-путь: ось из данных, GROUP BY, имя лидера, compare≠rank (24.08).

Замки:
  · sales_compare не крадёт «лучше всего» (живой дефект okna 24.08);
  · compare «неделя лучше прошлой» остаётся compare;
  · rank_axis_resolve: pick/rerank по вопросу → ось; две правдоподобные → лидер+люк;
  · предмет продажи (ТМЦ+Договоры) → лидер ТМЦ + люк Договоры;
  · клиент → ось Контрагент;
  · нет оси → (None, pool), не «тихо row»;
  · rank_leader_answer_text / atom несут имя из groups;
  · rank_deterministic_answer: row agg → reaggregate + имя в text;
  · decide_grain: rank + 1 col → group; rank + много без hits → clarify.

Запуск: python3 ubuntu/serenedb/test_rank_leader_path.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("ASK_TOKEN", "test")
os.environ.setdefault("EMBED_BASE_URL", "-")
os.environ.setdefault("EMBED_MODEL", "-")

import serene_ask as A  # noqa: E402
import serene_axis as AX  # noqa: E402

PASS, FAIL = 0, []


def t(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print("ok  -", name)
    else:
        FAIL.append(name)
        print("FAIL-", name, detail)


# ── compare vs rank (корневая причина 24.08) ─────────────────────────────────
q_rank = "что лучше всего продавалось на этой неделе?"
intent_sale = {"want": "sum", "kind": "продажи",
               "period": {"from": "2026-08-24", "to": "2026-08-24"}}
t("rank intent на «лучше всего»",
  A.rank_intent_from(intent_sale, {"compute": "sum"}, q_rank))
t("sales_compare НЕ на «лучше всего»",
  not A.sales_compare_intent(intent_sale, q_rank))
p1, p2, _f = A.sales_compare_windows(intent_sale, "2026-08-24", q_rank)
t("окна WTD всё ещё считаются (инфра)",
  p1.get("from") == "2026-08-24" and bool(p2.get("from")))

q_cmp = "эта неделя лучше прошлой или хуже?"
t("compare на «неделя лучше прошлой»",
  A.sales_compare_intent({"want": "sum", "kind": "продажи"}, q_cmp))
t("rank НЕ на чистый compare периодов",
  not A.rank_intent_from({"want": "sum"}, {}, q_cmp))

q_client = "какой клиент больше всех купил в этом месяце?"
t("rank на «больше всех» клиент",
  A.rank_intent_from({"want": "list", "kind": "клиент"}, {}, q_client))
t("sales_compare НЕ на клиента",
  not A.sales_compare_intent({"want": "list", "kind": "клиент"}, q_client))


# ── rank_axis_resolve: классификация по перечню осей (не словари имён) ───────
_axes = [
    {"col": "ВидДеятельности", "target_src": "catalog_видыдеятельности"},
    {"col": "Договор", "target_src": "catalog_договоры"},
    {"col": "Контрагент", "target_src": "catalog_контрагенты"},
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
]
_axes_sale = [
    {"col": "ТМЦ", "target_src": "catalog_номенклатура"},
    {"col": "Договор", "target_src": "catalog_договоры"},
]


def _fake_axis_pick(question, kind, axes):
    """Мок классификатора: ответ модели по именам осей (как live pick)."""
    q = " ".join(str(question or "").lower().split())
    cols = [a.get("col") for a in (axes or []) if a.get("col")]
    if "клиент" in q or "контрагент" in q:
        return [c for c in cols if c == "Контрагент"]
    if any(w in q for w in ("продав", "продаж", "продал", "sold", "sales")):
        out = []
        if "ТМЦ" in cols:
            out.append("ТМЦ")
        if "Договор" in cols:
            out.append("Договор")
        if "НоменклатурнаяГруппа" in cols:
            out.append("НоменклатурнаяГруппа")
        return out
    return []


_old_pick = A.rank_axis_pick
_old_kh = A.kind_axis_hits
_old_rr = A.kind_axis_rerank
_old_rar = A.rank_axes_rerank
A.rank_axis_pick = _fake_axis_pick
A.kind_axis_hits = lambda axes, kind_text: []
A.kind_axis_rerank = lambda axes, kind: []
A.rank_axes_rerank = lambda query, axes: []
try:
    col, alts = A.rank_axis_resolve(
        "accumulationregister_реализациятмц", _axes,
        {"kind": "клиент"}, q_client)
    t("resolve клиент → Контрагент", col == "Контрагент" and not alts, (col, alts))

    col_sale, alts_sale = A.rank_axis_resolve(
        "accumulationregister_реализациятмц", _axes_sale,
        {"kind": "продажи"}, q_rank)
    t("предмет продажи: лидер ТМЦ + люк Договоры",
      col_sale == "ТМЦ" and alts_sale == ["Договор"], (col_sale, alts_sale))

    col2, alts2 = A.rank_axis_resolve(
        "accumulationregister_реализациятмц", _axes,
        {"kind": "продажи"}, q_rank)
    t("resolve продажи → ТМЦ лидер (Договор в люке)",
      col2 == "ТМЦ" and "Договор" in (alts2 or []), (col2, alts2))

    _axes2 = _axes + [{"col": "НоменклатурнаяГруппа",
                       "target_src": "catalog_номенклатурныегруппы"}]
    col3, alts3 = A.rank_axis_resolve(
        "accumulationregister_реализациятмц", _axes2,
        {"kind": "продажи"}, q_rank)
    t("две+ оси pick → лидер + люк",
      col3 == "ТМЦ" and "НоменклатурнаяГруппа" in (alts3 or []),
      (col3, alts3))

    # Без сигнала pick/hits/rerank — честный None + pool (не silent first).
    A.rank_axis_pick = lambda *a, **k: []
    col4, alts4 = A.rank_axis_resolve(
        "src", [{"col": "Склад", "target_src": "catalog_склады"},
                {"col": "Организация", "target_src": "catalog_организации"}],
        {"kind": ""}, "кто лидер?")
    t("нет сигнала → None + pool (честный исход)",
      col4 is None and len(alts4) == 2, (col4, alts4))

    # Симметрия: вопрос о клиенте при полном наборе осей.
    A.rank_axis_pick = _fake_axis_pick
    col5, alts5 = A.rank_axis_resolve(
        "accumulationregister_реализациятмц", _axes,
        {"kind": "продажи"}, q_client)
    t("вопрос о клиенте → ось Контрагент",
      col5 == "Контрагент" and not alts5, (col5, alts5))
finally:
    A.rank_axis_pick = _old_pick
    A.kind_axis_hits = _old_kh
    A.kind_axis_rerank = _old_rr
    A.rank_axes_rerank = _old_rar


# ── SQL-контракт aggregate_groups (структура) ────────────────────────────────
src_ag = A.ask_source()
t("aggregate_groups: GROUP BY в SQL",
  "GROUP BY g" in src_ag and "ORDER BY" in src_ag and "LIMIT %(k)d" in src_ag)
t("aggregate_groups: refs_map ось",
  "map_extract_value(refs_map" in src_ag)


# ── имя в тексте / атоме ─────────────────────────────────────────────────────
AGG = {
    "count": 3, "sum": 4.0, "leader": 2.0, "measure": "Количество",
    "grain": "group", "col": "ТМЦ", "form": "rank", "n_groups": 3,
    "groups": [
        {"name": "Item-A", "value": 2.0, "count": 1},
        {"name": "Other", "value": 1.0, "count": 1},
    ],
    "folders": 0, "count_amount": 3,
}
txt = A.rank_leader_answer_text(AGG, "Количество", unit="")
t("leader text содержит имя",
  txt and "Item-A" in txt and "2" in txt.replace("\u00a0", ""),
  txt)
atom = A.rank_leader_atom(AGG, "Количество", money=False, src="accumulationregister_x")
t("leader atom: measure_label=имя группы",
  atom and atom.get("measure_label", "").startswith("Item-A"), atom)
t("leader atom: exact_value=2",
  atom and float(atom.get("exact_value")) == 2.0, atom)
t("render_atom_pair несёт имя",
  "Item-A" in (A.render_atom_pair(atom) or ""), A.render_atom_pair(atom))


# ── deterministic: row → reaggregate ─────────────────────────────────────────
_called = []


def _fake_agg(src, match, preds, measure, col, k, compute=None, members=None):
    _called.append(col)
    return dict(AGG, col=col)


_old_agg = A.aggregate_groups
_old_pick2 = A.rank_axis_pick
A.aggregate_groups = _fake_agg
A.rank_axis_pick = _fake_axis_pick
try:
    fb = A.rank_deterministic_answer(
        q_rank, {"grain": "row", "sum": 100.0, "count": 5, "measure": "Количество"},
        "accumulationregister_реализациятмц", "", {}, "Количество", False,
        intent_sale, {"compute": "sum"}, {}, _axes, {}, time.time(), "",
        "Количество")
    t("deterministic: kind=answer", fb and fb.get("kind") == "answer", fb)
    t("deterministic: имя в text",
      fb and "Item-A" in (fb.get("text") or ""), fb and fb.get("text"))
    t("deterministic: SQL-ось вызвана", "ТМЦ" in _called, _called)
    t("deterministic: atom с именем",
      fb and fb.get("atom") and "Item-A" in str(fb["atom"].get("measure_label")),
      fb.get("atom") if fb else None)
    t("deterministic: люк Договоры в options",
      fb and any(o.get("distinct_by") == "Договор" for o in (fb.get("options") or [])),
      fb.get("options") if fb else None)
finally:
    A.aggregate_groups = _old_agg
    A.rank_axis_pick = _old_pick2


# ── decide_grain ─────────────────────────────────────────────────────────────
_gd1 = AX.decide_grain(
    [{"col": "ТМЦ"}], [], {}, "sum", False, rank_intent=True)
t("decide_grain: 1 col + rank → group",
  _gd1.get("grain") == "group" and _gd1.get("col") == "ТМЦ" and not _gd1.get("clarify"),
  _gd1)
_gd2 = AX.decide_grain(
    [{"col": "A"}, {"col": "B"}], [], {}, "sum", False, rank_intent=True)
t("decide_grain: много cols без hits → clarify (не silent row)",
  _gd2.get("clarify") == "axis", _gd2)


# ── K6b: исход B не подменяет rank-лидера суммой периода ─────────────────────
t("fork_classes_window_only: одни src",
  A.fork_classes_window_only([{"srcs": ["a"]}, {"srcs": ["a"]}]))
t("fork_classes_window_only: разные src",
  not A.fork_classes_window_only([{"srcs": ["a"]}, {"srcs": ["b"]}]))
t("rank_defer_fork_outcome_b на «больше всех» + окна",
  A.rank_defer_fork_outcome_b(
      {"want": "list", "kind": "клиент"}, {}, q_client,
      [{"srcs": ["accumulationregister_x"]}, {"srcs": ["accumulationregister_x"]}]))
t("rank_defer_fork_outcome_b false на sum без rank",
  not A.rank_defer_fork_outcome_b(
      {"want": "sum"}, {}, "сколько продали?",
      [{"srcs": ["a"]}, {"srcs": ["a"]}]))


print("\n%d ok, %d fail" % (PASS, len(FAIL)))
if FAIL:
    print("failed:", ", ".join(FAIL))
    sys.exit(1)
sys.exit(0)
